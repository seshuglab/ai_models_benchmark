import itertools
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path


VERSION = "0.9i"
PROGRAM_DIR = Path(
    sys.executable if getattr(sys, "frozen", False) else __file__
).resolve().parent
EXIT_PROMPT = "\nНажми Enter для выхода..."
SHOW_SPINNER = "--no-spinner" not in sys.argv
SPINNER_FRAMES = "|/-\\"
SAVE_AGENT_JSON_LOG = "--opencode-json-log" in sys.argv

PROVIDERS = {
    "ollama": {
        "title": "Ollama",
        "location": "local",
        "location_title": "локально",
        "protocol": "ollama_api",
        "models_url": "http://localhost:11434/api/tags",
        "generate_url": "http://localhost:11434/api/generate",
        "running_command": ["ollama", "ps"],
        "stop_command": ["ollama", "stop"],
        "unavailable": "не обнаружена (нужен запущенный Ollama)",
    },
    "opencode": {
        "title": "OpenCode",
        "location": "cloud",
        "location_title": "облако",
        "protocol": "opencode_cli",
        "executable": "opencode",
        "models_command": ["opencode", "models"],
        "run_command": ["opencode", "run", "--format", "json", "--thinking"],
        "unavailable": "не обнаружен (нужен OpenCode CLI, команда 'opencode')",
    },
    "lmstudio": {
        "title": "LM Studio",
        "location": "local",
        "location_title": "локально",
        "protocol": "lmstudio_api",
        "models_url": "http://localhost:1234/api/v1/models",
        "chat_url": "http://localhost:1234/api/v1/chat",
        "running_command": ["lms", "ps", "--json"],
        "load_command": ["lms", "load"],
        "unload_command": ["lms", "unload"],
        "unavailable": "не обнаружена (нужен запущенный сервер LM Studio)",
    },
}

PROTOCOLS = {
    "ollama_api": {
        "get_models": lambda *args: get_ollama_api_models(*args),
        "prepare": lambda *args: prepare_local_model(*args),
        "run": lambda *args: run_ollama_api_test(*args),
        "metrics": "generation",
    },
    "opencode_cli": {
        "get_models": lambda *args: get_opencode_cli_models(*args),
        "prepare": None,
        "run": lambda *args: run_opencode_cli_test(*args),
        "metrics": "agent",
    },
    "lmstudio_api": {
        "get_models": lambda *args: get_lmstudio_api_models(*args),
        "prepare": lambda *args: prepare_lmstudio_model(*args),
        "run": lambda *args: run_lmstudio_api_test(*args),
        "metrics": "local_reasoning",
    },
}


class Spinner:
    def __init__(self, enabled=True):
        self.enabled = enabled and sys.stdout.isatty()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.streaming = False

    def start(self):
        if not self.enabled:
            return
        self.thread = threading.Thread(target=self.animate, daemon=True)
        self.thread.start()

    def animate(self):
        for frame in itertools.cycle(SPINNER_FRAMES):
            with self.lock:
                if not self.streaming:
                    sys.stdout.write(f"\r{frame}")
                    sys.stdout.flush()
            if self.stop_event.wait(0.15):
                return

    def write(self, text, end="\n"):
        with self.lock:
            if self.enabled and not self.streaming:
                sys.stdout.write("\r \r")
            sys.stdout.write(f"{text}{end}")
            sys.stdout.flush()
            self.streaming = not end.endswith("\n")

    def input(self, prompt=""):
        if not self.enabled:
            return input(prompt)

        with self.lock:
            sys.stdout.write("\r \r")
            sys.stdout.flush()

            try:
                return input(prompt)
            except (KeyboardInterrupt, EOFError):
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise

    def stop(self):
        if not self.enabled:
            return
        self.stop_event.set()
        self.thread.join()
        with self.lock:
            sys.stdout.write("\r \r")
            sys.stdout.flush()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


def format_number(value):
    if value is None:
        return "недоступно"
    return f"{value:.2f}"


def format_count(value):
    return "недоступно" if value is None else str(value)


def calculate_rate(count, seconds):
    return count / seconds if count and seconds else None


def metric_lines(result):
    provider = PROVIDERS[result["source"]]
    protocol = PROTOCOLS[provider["protocol"]]
    agent = protocol["metrics"] == "agent"
    lines = [
        f"{'До первого текста' if agent else 'До первого токена'}: "
        f"{format_number(result.get('first_token_seconds'))} сек",
        f"Полное время: {format_number(result.get('total_seconds'))} сек",
        f"{'Эффективная скорость агента' if agent else 'Скорость генерации'}: "
        f"{format_number(result.get('tokens_per_second'))} токен/сек",
        f"{'Входных токенов без кэша' if agent else 'Токенов в промпте'}: "
        f"{format_count(result.get('prompt_tokens'))}",
        f"Сгенерировано токенов: {format_count(result.get('tokens_generated'))}",
    ]
    if agent or protocol["metrics"] == "local_reasoning":
        lines.append(
            f"Токенов размышления: {format_count(result.get('reasoning_tokens'))}"
        )
    if agent:
        lines.extend(
            [
                f"Токенов из кэша: {format_count(result.get('cache_read_tokens'))}",
                f"Всего токенов: {format_count(result.get('total_tokens'))}",
                f"Шагов агента: {format_count(result.get('agent_steps'))}",
            ]
        )
    if protocol["metrics"] == "generation":
        lines.append(
            f"Загрузка модели: {format_number(result.get('load_seconds'))} сек"
        )
    return lines


def format_list_number(number, count):
    return f"{number:0{len(str(count))}d}"


def write_model_grid(models, start_number, total_count, spinner):
    cells = [
        f"{format_list_number(number, total_count)} - {model['name']}"
        for number, model in enumerate(models, start_number)
    ]
    cell_width = max(map(len, cells)) + 4
    columns = max(1, shutil.get_terminal_size((120, 24)).columns // cell_width)
    for row in range(0, len(cells), columns):
        spinner.write("".join(
            cell.ljust(cell_width) for cell in cells[row:row + columns]
        ).rstrip())


def source_name(source):
    return PROVIDERS.get(source, {}).get("title", source)


def safe_filename(value):
    for char in '<>:"/\\|?*':
        value = value.replace(char, "-")
    return value


def choose_number(count, choice, spinner):
    choice = choice.strip()
    if choice.isdigit() and 1 <= int(choice) <= count:
        return int(choice) - 1
    spinner.write("Неверный номер.")
    return None


def read_arguments():
    arguments = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
    if not arguments:
        return "", 0
    if (
        len(arguments) != 2
        or not arguments[0]
        or not arguments[1].isdigit()
        or int(arguments[1]) < 1
    ):
        raise SystemExit("Укажите модель и номер теста.")
    return arguments[0], int(arguments[1])


def get_ollama_api_models(provider_id, provider):
    try:
        with urllib.request.urlopen(provider["models_url"], timeout=10) as response:
            data = json.load(response)
    except Exception:
        return False, []

    models = []
    for item in data.get("models", []):
        name = item.get("name") or item.get("model")
        if name:
            models.append(
                {
                    "source": provider_id,
                    "name": name,
                    "full_name": name,
                }
            )
    return True, models


def get_opencode_cli_models(provider_id, provider):
    if shutil.which(provider["executable"]) is None:
        return False, []

    try:
        result = subprocess.run(
            provider["models_command"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False, []

    models = []
    for line in result.stdout.splitlines():
        full_name = line.strip()
        if not full_name or "/" not in full_name:
            continue
        _, name = full_name.split("/", 1)
        models.append(
            {
                "source": provider_id,
                "name": name,
                "full_name": full_name,
            }
        )
    return True, models


def get_lmstudio_api_models(provider_id, provider):
    try:
        with urllib.request.urlopen(provider["models_url"], timeout=10) as response:
            data = json.load(response)
    except Exception:
        return False, []

    models = []
    for item in data.get("models", []):
        model_key = item.get("key")
        if item.get("type") == "llm" and model_key:
            models.append(
                {
                    "source": provider_id,
                    "name": item.get("display_name") or model_key,
                    "full_name": model_key,
                }
            )
    return True, models


def get_tests():
    tests = []
    for test_file in sorted(PROGRAM_DIR.glob("[0-9][0-9]_*.md")):
        lines = test_file.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].startswith("#"):
            tests.append(
                (
                    test_file,
                    lines[0].lstrip("#").strip(),
                    "\n".join(lines[1:]).strip(),
                )
            )
    return tests


def get_running_local_models(provider):
    result = subprocess.run(
        provider["running_command"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    lines = [line for line in result.stdout.splitlines()[1:] if line.strip()]
    return [line.split()[0] for line in lines]


def prepare_local_model(provider, selected_model, spinner):
    selected_model = selected_model["name"]
    running_models = get_running_local_models(provider)
    other_models = [model for model in running_models if model != selected_model]

    if selected_model in running_models:
        spinner.write("Выбранная модель уже загружена в память.")

    for model in other_models:
        spinner.write(f"Останавливаю другую модель: {model}")
        subprocess.run(provider["stop_command"] + [model], check=True)


def prepare_lmstudio_model(provider, selected_model, spinner):
    result = subprocess.run(
        provider["running_command"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    running_models = json.loads(result.stdout)
    selected_key = selected_model["full_name"]
    selected_loaded = False

    for model in running_models:
        model_key = model.get("modelKey")
        identifier = model.get("identifier") or model_key
        if model_key == selected_key:
            selected_loaded = True
        elif identifier:
            spinner.write(f"Останавливаю другую модель: {model_key or identifier}")
            subprocess.run(provider["unload_command"] + [identifier], check=True)

    if selected_loaded:
        spinner.write("Выбранная модель уже загружена в память.")
    else:
        spinner.write(f"Загружаю модель: {selected_model['name']}")
        subprocess.run(provider["load_command"] + [selected_key, "-y"], check=True)


def run_ollama_api_test(provider, model, prompt, test_file, spinner):
    data = json.dumps(
        {"model": model["name"], "prompt": prompt, "stream": True}
    ).encode("utf-8")
    request = urllib.request.Request(
        provider["generate_url"],
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start_time = time.perf_counter()
    first_token_time = None
    full_response = ""
    final_chunk = {}

    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            for raw_line in response:
                chunk = json.loads(raw_line.decode("utf-8"))
                text = chunk.get("response", "")
                if text:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    full_response += text
                    spinner.write(text, end="")
                if chunk.get("done"):
                    final_chunk = chunk
    except Exception as error:
        return make_error_result(model, error)

    end_time = time.perf_counter()
    eval_count = final_chunk.get("eval_count")
    eval_duration = final_chunk.get("eval_duration")
    generation_seconds = (
        eval_duration / 1_000_000_000 if eval_duration is not None else None
    )

    return {
        **model,
        "first_token_seconds": (
            first_token_time - start_time if first_token_time else None
        ),
        "total_seconds": end_time - start_time,
        "tokens_per_second": calculate_rate(eval_count, generation_seconds),
        "tokens_generated": eval_count,
        "prompt_tokens": final_chunk.get("prompt_eval_count"),
        "load_seconds": (
            final_chunk.get("load_duration") / 1_000_000_000
            if final_chunk.get("load_duration") is not None
            else None
        ),
        "response": full_response,
    }


def run_lmstudio_api_test(provider, model, prompt, test_file, spinner):
    data = json.dumps(
        {"model": model["full_name"], "input": prompt, "stream": True}
    ).encode("utf-8")
    request = urllib.request.Request(
        provider["chat_url"],
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start_time = time.perf_counter()
    first_token_time = None
    response_parts = []
    final_result = {}

    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                event_type = event.get("type")

                if event_type == "message.delta":
                    text = event.get("content", "")
                    if text:
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                        response_parts.append(text)
                        spinner.write(text, end="")
                elif event_type == "chat.end":
                    final_result = event.get("result") or {}
                elif event_type == "error":
                    raise RuntimeError(event.get("error") or event)
    except Exception as error:
        return make_error_result(model, error)

    end_time = time.perf_counter()
    stats = final_result.get("stats") or {}
    full_response = "".join(response_parts)
    if not full_response:
        full_response = "".join(
            item.get("content", "")
            for item in final_result.get("output", [])
            if item.get("type") == "message"
        )

    return {
        **model,
        "first_token_seconds": stats.get("time_to_first_token_seconds") or (
            first_token_time - start_time if first_token_time is not None else None
        ),
        "total_seconds": end_time - start_time,
        "tokens_per_second": stats.get("tokens_per_second"),
        "tokens_generated": stats.get("total_output_tokens"),
        "prompt_tokens": stats.get("input_tokens"),
        "reasoning_tokens": stats.get("reasoning_output_tokens"),
        "response": full_response,
    }


def opencode_text(event):
    part = event.get("part") or {}
    return event.get("text") or part.get("text") or ""


def opencode_tokens(event):
    part = event.get("part") or {}
    return event.get("tokens") or part.get("tokens") or {}


def clean_block(text):
    lines = []
    previous_empty = False
    for line in str(text).splitlines():
        empty = not line.strip()
        if empty and previous_empty:
            continue
        lines.append("" if empty else line)
        previous_empty = empty
    return "\n".join(lines).strip("\n")


def add_opencode_event(event_log, header, content="", spinner=None):
    content = clean_block(content)
    block = header if not content else f"{header}\n{content}"
    event_log.append(block)

    output = f"\n{header}" if not content else f"\n{header}\n{content}"
    if spinner:
        spinner.write(output)
    else:
        print(output)


def run_opencode_cli_test(provider, model, prompt, test_file, spinner):
    script_dir = PROGRAM_DIR
    work_name = "_".join(
        [
            datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
            safe_filename(model["name"]),
            test_file.stem,
        ]
    )
    agent_work_dir = script_dir / ".agent_work" / work_name
    agent_work_dir.mkdir(parents=True, exist_ok=True)
    for file_name in ("BENCHMARK_PRIVATE_NOTES.md", "PASSWORDS.txt"):
        source_file = script_dir / file_name
        destination_file = agent_work_dir.parent / file_name
        if source_file.is_file() and not destination_file.exists():
            shutil.copy2(source_file, destination_file)
    relative_work_dir = str(agent_work_dir.relative_to(script_dir))
    spinner.write(f"Рабочая папка агента: {relative_work_dir}")

    start_time = time.perf_counter()
    first_text_time = None
    response_parts = []
    event_log = []
    json_events = []
    step_count = 0
    prompt_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    cache_read_tokens = 0
    total_tokens = 0

    try:
        process = subprocess.Popen(
            provider["run_command"] + ["--model", model["full_name"], prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=agent_work_dir,
        )

        for line in process.stdout:
            if not line.strip():
                continue
            if SAVE_AGENT_JSON_LOG:
                json_events.append(line.rstrip("\r\n"))
            event = json.loads(line)
            event_type = event.get("type")
            elapsed = int(time.perf_counter() - start_time)

            if event_type == "step_start":
                step_count += 1
                add_opencode_event(
                    event_log, f"[{elapsed}][АГЕНТ] Шаг {step_count}", spinner=spinner
                )
            elif event_type == "reasoning":
                reasoning = opencode_text(event)
                if reasoning:
                    add_opencode_event(
                        event_log,
                        f"[{elapsed}][РАЗМЫШЛЕНИЕ]",
                        reasoning,
                        spinner,
                    )
            elif event_type == "tool_use":
                part = event.get("part") or {}
                state = part.get("state") or {}
                tool = part.get("tool", "неизвестный инструмент")
                status = state.get("status", "неизвестно")
                title = state.get("title") or ""
                add_opencode_event(
                    event_log,
                    f"[{elapsed}][ИНСТРУМЕНТ] {tool} — {status}",
                    title,
                    spinner,
                )
            elif event_type == "text":
                text = clean_block(opencode_text(event))
                if text and first_text_time is None:
                    first_text_time = time.perf_counter()
                if text:
                    response_parts.append(text)
                    add_opencode_event(
                        event_log, f"[{elapsed}][ОТВЕТ]", text, spinner
                    )
            elif event_type == "step_finish":
                tokens = opencode_tokens(event)
                prompt_tokens += tokens.get("input", 0) or 0
                output_tokens += tokens.get("output", 0) or 0
                reasoning_tokens += tokens.get("reasoning", 0) or 0
                total_tokens += tokens.get("total", 0) or 0
                cache = tokens.get("cache") or {}
                cache_read_tokens += cache.get("read", 0) or 0
            elif event_type == "error":
                error = event.get("error")
                if not isinstance(error, str):
                    error = json.dumps(error, ensure_ascii=False, indent=2)
                add_opencode_event(
                    event_log,
                    f"[{elapsed}][ОШИБКА {provider['title'].upper()}]",
                    error,
                    spinner,
                )

        error_text = process.stderr.read().strip()
        return_code = process.wait()
        if not any(agent_work_dir.iterdir()):
            agent_work_dir.rmdir()
            relative_work_dir = None
    except Exception as error:
        result = make_error_result(model, error)
        result["agent_work_dir"] = relative_work_dir
        result["agent_steps"] = step_count
        result["event_log"] = "\n\n".join(event_log)
        return result

    end_time = time.perf_counter()
    total_seconds = end_time - start_time
    result = {
        **model,
        "first_token_seconds": (
            first_text_time - start_time if first_text_time is not None else None
        ),
        "total_seconds": total_seconds,
        "tokens_per_second": calculate_rate(output_tokens, total_seconds),
        "tokens_generated": output_tokens or None,
        "prompt_tokens": prompt_tokens or None,
        "total_tokens": total_tokens or None,
        "reasoning_tokens": reasoning_tokens,
        "cache_read_tokens": cache_read_tokens,
        "load_seconds": None,
        "response": "\n\n".join(response_parts),
        "agent_steps": step_count,
        "event_log": "\n\n".join(event_log),
        "agent_work_dir": relative_work_dir,
        "json_event_log": "\n".join(json_events),
    }
    if return_code:
        result["error"] = error_text or (
            f"{provider['title']} завершился с кодом {return_code}"
        )
    return result


def make_error_result(model, error):
    return {**model, "error": str(error)}


def print_result(result, spinner):
    spinner.write("\n\nТЕСТ ЗАВЕРШЁН")
    for line in metric_lines(result):
        spinner.write(line)
    if "error" in result:
        spinner.write(f"ОШИБКА: {result['error']}")


def save_report(result, test_file, test_title, prompt):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name_parts = [
        "ai_test",
        result["source"],
        result["name"],
        test_file.stem,
        timestamp,
    ]
    report_name = safe_filename("_".join(name_parts)) + ".txt"
    report_path = PROGRAM_DIR / report_name

    with report_path.open("w", encoding="utf-8") as report:
        report.write(f"# AI MODELS BENCHMARK v{VERSION}\n")
        report.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        provider = PROVIDERS[result["source"]]
        location_label = provider["location_title"]
        report.write(f"Источник: {source_name(result['source'])} ({location_label})\n")
        report.write(f"Модель: {result['name']}\n")
        if result.get("agent_work_dir"):
            report.write(f"Рабочая папка агента: {result['agent_work_dir']}\n")
        report.write(f"Тест: {test_title}\n")
        report.write(f"Файл теста: {test_file.name}\n")

        report.write("\n# МЕТРИКИ:\n")
        report.write("\n".join(metric_lines(result)) + "\n")

        if "error" in result:
            report.write(f"\n# ОШИБКА:\n{result['error']}\n")

        report.write("\n# ПРОМТ:\n")
        report.write(prompt + "\n")

        if result.get("event_log"):
            report.write("\n# ЖУРНАЛ ВЫПОЛНЕНИЯ:\n")
            report.write(result["event_log"] + "\n")

        if "error" not in result:
            report.write("\n# ОТВЕТ МОДЕЛИ:\n")
            report.write(result["response"] + "\n")

    if SAVE_AGENT_JSON_LOG and result.get("json_event_log"):
        report_path.with_suffix(".log").write_text(
            result["json_event_log"] + "\n", encoding="utf-8"
        )

    return report_path.name


def run(spinner, argv_model="", argv_test=0):
    spinner.write(f"AI MODELS BENCHMARK v{VERSION}")
    spinner.write("=" * 60)
    spinner.write("Поиск доступных моделей...")

    def check_provider(item):
        provider_id, provider = item
        found, models = PROTOCOLS[provider["protocol"]]["get_models"](
            provider_id, provider
        )
        return provider_id, provider, found, models

    with ThreadPoolExecutor() as executor:
        provider_results = list(executor.map(check_provider, PROVIDERS.items()))
    provider_results.sort(key=lambda result: result[2])

    for _, provider, found, _ in provider_results:
        if not found:
            spinner.write(f"\n{provider['title']:<10}- {provider['unavailable']}")

    models = list(itertools.chain.from_iterable(
        found_models for _, _, found, found_models in provider_results if found
    ))
    if not models:
        spinner.write("\nДоступные модели не найдены.")
        return

    tests = get_tests()
    if not tests:
        spinner.write("\nТестовые файлы [0-9][0-9]_*.md не найдены.")
        return

    while True:
        start_number = 1
        for _, provider, found, provider_models in provider_results:
            if found:
                spinner.write(
                    f"\n{provider['title']:<10}- {len(provider_models)} моделей "
                    f"({provider['location_title']}):"
                )
                if provider_models:
                    write_model_grid(
                        provider_models, start_number, len(models), spinner
                    )
                start_number += len(provider_models)

        if argv_model:
            model_number = int(argv_model) if argv_model.isdigit() else None
            matches = [
                index
                for index, item in enumerate(models)
                if model_number == index + 1
                or (
                    model_number is None
                    and item["name"].casefold() == argv_model.casefold()
                )
            ]
            if not matches:
                spinner.write(f"\nМодель не найдена: {argv_model}")
                return
            if len(matches) > 1:
                spinner.write(
                    f"\nМоделей с именем {argv_model} найдено: {len(matches)}"
                )
                return
            model_index = matches[0]
        else:
            model_index = choose_number(
                len(models), spinner.input("\nВыбери номер модели: "), spinner
            )
        if model_index is None:
            return
        model = models[model_index]

        provider = PROVIDERS[model["source"]]
        protocol = PROTOCOLS[provider["protocol"]]
        location_label = provider["location_title"]
        spinner.write(
            f"\nВыбранная модель: {source_name(model['source'])} — "
            f"{model['name']} ({location_label})"
        )

        spinner.write("\nДоступные тесты:\n")
        for number, (_, title, _) in enumerate(tests, start=1):
            spinner.write(f"{format_list_number(number, len(tests))} - {title}")

        if argv_test:
            if argv_test > len(tests):
                spinner.write(f"\nТест не найден: {argv_test}")
                return
            selected_tests = [tests[argv_test - 1]]
            break

        choice = spinner.input(
            "\nВыбери номер теста, X — все тесты, 0 — назад: "
        ).strip()
        if choice == "0":
            continue
        if choice.lower() == "x":
            selected_tests = tests
        else:
            test_index = choose_number(len(tests), choice, spinner)
            if test_index is None:
                return
            selected_tests = [tests[test_index]]

        break

    prepare = protocol["prepare"]
    if prepare:
        prepare(provider, model, spinner)

    completed_tests = 0
    try:
        for test_file, test_title, prompt in selected_tests:
            spinner.write(f"\nТест: {test_title}\n")

            result = protocol["run"](provider, model, prompt, test_file, spinner)

            print_result(result, spinner)
            report_name = save_report(result, test_file, test_title, prompt)
            spinner.write(f"\nОтчёт сохранён: {report_name}")
            completed_tests += 1
    except KeyboardInterrupt:
        spinner.write("\nВыполнение остановлено пользователем.")

    spinner.write(f"\nМодель: {model['name']}")
    spinner.write(f"Пройдено тестов: {completed_tests}")


def main():
    with Spinner(SHOW_SPINNER) as spinner:
        try:
            argv_model, argv_test = read_arguments()
            run(spinner, argv_model, argv_test)
        except Exception as error:
            spinner.write(f"\nОШИБКА: {error}")
        finally:
            spinner.input(EXIT_PROMPT)


if __name__ == "__main__":
    main()
