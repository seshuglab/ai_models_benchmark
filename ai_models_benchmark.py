import ctypes
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


from ai_models_benchmark_languages import (
    LanguageError,
    init_language_from_argv,
    lang,
    validate_languages,
)


VERSION = "0.9m"
PROGRAM_DIR = Path(
    sys.executable if getattr(sys, "frozen", False) else __file__
).resolve().parent
SHOW_SPINNER = "--no-spinner" not in sys.argv
SPINNER_FRAMES = "|/-\\"
SAVE_AGENT_JSON_LOG = "--opencode-json-log" in sys.argv


def set_window_title(title):
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(title)


PROVIDERS = {
    "ollama": {
        "title": "Ollama",
        "location": "local",
        "protocol": "ollama_api",
        "models_url": "http://localhost:11434/api/tags",
        "generate_url": "http://localhost:11434/api/generate",
        "running_command": ["ollama", "ps"],
        "stop_command": ["ollama", "stop"],
        "unavailable_key": "provider_unavailable_ollama",
    },
    "opencode": {
        "title": "OpenCode",
        "location": "cloud",
        "protocol": "opencode_cli",
        "executable": "opencode",
        "models_command": ["opencode", "models"],
        "run_command": ["opencode", "run", "--format", "json", "--thinking"],
        "unavailable_key": "provider_unavailable_opencode",
    },
    "lmstudio": {
        "title": "LM Studio",
        "location": "local",
        "protocol": "lmstudio_api",
        "models_url": "http://localhost:1234/api/v1/models",
        "chat_url": "http://localhost:1234/api/v1/chat",
        "running_command": ["lms", "ps", "--json"],
        "load_command": ["lms", "load"],
        "unload_command": ["lms", "unload"],
        "unavailable_key": "provider_unavailable_lmstudio",
    },
}


def provider_unavailable(provider_id):
    key = PROVIDERS.get(provider_id, {}).get(
        "unavailable_key", "unavailable_value"
    )
    return lang(key)


def location_label(location):
    if location == "local":
        return lang("location_local")
    return lang("location_cloud")


def ensure_language(argv=None):
    init_language_from_argv(argv)
    validate_languages()

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
        return lang("unavailable_value")
    return f"{value:.2f}"


def format_count(value):
    return lang("unavailable_value") if value is None else str(value)


def calculate_rate(count, seconds):
    if not seconds or count is None:
        return None
    return count / seconds


def metric_lines(result):
    provider = PROVIDERS[result["source"]]
    protocol = PROTOCOLS[provider["protocol"]]
    agent = protocol["metrics"] == "agent"
    sec = lang("sec")
    speed = lang("speed_unit")
    first_label = lang("first_text") if agent else lang("first_token")
    speed_label = lang("agent_speed") if agent else lang("generation_speed")
    prompt_label = lang("prompt_no_cache") if agent else lang("prompt_tokens")
    lines = [
        f"{first_label}: {format_number(result.get('first_token_seconds'))} {sec}",
        f"{lang('total_time')}: {format_number(result.get('total_seconds'))} {sec}",
        f"{speed_label}: {format_number(result.get('tokens_per_second'))} {speed}",
        f"{prompt_label}: {format_count(result.get('prompt_tokens'))}",
        f"{lang('generated_tokens')}: {format_count(result.get('tokens_generated'))}",
    ]
    if agent or protocol["metrics"] == "local_reasoning":
        lines.append(
            f"{lang('reasoning_tokens')}: "
            f"{format_count(result.get('reasoning_tokens'))}"
        )
    if agent:
        lines.extend(
            [
                f"{lang('cache_tokens')}: "
                f"{format_count(result.get('cache_read_tokens'))}",
                f"{lang('total_tokens')}: "
                f"{format_count(result.get('total_tokens'))}",
                f"{lang('agent_steps')}: "
                f"{format_count(result.get('agent_steps'))}",
            ]
        )
    if protocol["metrics"] == "generation":
        lines.append(
            f"{lang('load_model')}: "
            f"{format_number(result.get('load_seconds'))} {sec}"
        )
    return lines


def format_list_number(number, count):
    return f"{number:0{len(str(count))}d}"


def display_name(model, duplicated_names=frozenset()):
    if model["name"].casefold() in duplicated_names:
        return model["full_name"]
    return model["name"]


def build_grid_sections(provider_results):
    sections = []
    for provider_id, _, found, provider_models in provider_results:
        if not found or not provider_models:
            continue
        if PROVIDERS[provider_id]["protocol"] == "opencode_cli":
            groups = {}
            for model in provider_models:
                prefix = model["full_name"].split("/", 1)[0]
                groups.setdefault(prefix, []).append(model)
            sections.extend(groups.items())
        else:
            sections.append((provider_id, provider_models))
    return sections


def write_model_grid(sections, total_count, spinner,
                     duplicated_names=frozenset()):
    items = []
    number = 0
    for source, section_models in sections:
        tag = f"{' ' * (len(str(total_count)) + 3)}{source}/"
        items.append((tag, True, tag))
        for model in section_models:
            number += 1
            items.append((
                tag,
                False,
                f"[{format_list_number(number, total_count)}] "
                f"{display_name(model, duplicated_names)}",
            ))
    available_width = shutil.get_terminal_size((120, 24)).columns - 2
    min_width = min(len(text) for _, _, text in items) + 2
    max_columns = max(1, min(len(items), available_width // min_width))
    for columns in range(max_columns, 0, -1):
        rows = max(1, (len(items) + columns - 1) // columns)
        while True:
            grid = [[]]
            for tag, is_tag, text in items:
                if len(grid[-1]) >= rows:
                    grid.append([])
                if is_tag and grid[-1] and len(grid[-1]) >= rows - 2:
                    grid.append([])
                if is_tag and grid[-1]:
                    grid[-1].append("")
                if not grid[-1] and not is_tag:
                    grid[-1].append(tag)
                grid[-1].append(text)
            if len(grid) <= columns:
                break
            rows += 1

        widths = [max(map(len, column)) + 2 for column in grid]
        if sum(widths) <= available_width or columns == 1:
            break

    for row in range(max(map(len, grid))):
        spinner.write(("  " + "".join(
            (column[row] if row < len(column) else "").ljust(width)
            for column, width in zip(grid, widths)
        )).rstrip())


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
    spinner.write(lang("invalid_number"))
    return None


def show_help(spinner):
    spinner.write(lang("help_text"))


def read_arguments(spinner):
    if "--help" in sys.argv:
        show_help(spinner)
        raise SystemExit

    arguments = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
    if not arguments:
        return "", 0
    if (
        len(arguments) == 2
        and arguments[0]
        and arguments[1].lower() == "x"
    ):
        return arguments[0], "x"
    if (
        len(arguments) != 2
        or not arguments[0]
        or not arguments[1].isdigit()
        or int(arguments[1]) < 1
    ):
        spinner.write(lang("args_error"))
        show_help(spinner)
        raise SystemExit
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
        try:
            lines = test_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise RuntimeError(f"{test_file.name}: {error}") from error
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
    try:
        result = subprocess.run(
            provider["running_command"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    lines = [line for line in result.stdout.splitlines()[1:] if line.strip()]
    return [line.split()[0] for line in lines]


def prepare_local_model(provider, selected_model, spinner):
    selected_model = selected_model["name"]
    running_models = get_running_local_models(provider)
    other_models = [model for model in running_models if model != selected_model]

    if selected_model in running_models:
        spinner.write(lang("model_already_loaded"))

    for model in other_models:
        spinner.write(lang("stopping_other_model", model=model))
        subprocess.run(provider["stop_command"] + [model], check=True)


def prepare_lmstudio_model(provider, selected_model, spinner):
    try:
        result = subprocess.run(
            provider["running_command"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        running_models = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        running_models = []
    selected_key = selected_model["full_name"]
    selected_loaded = False

    for model in running_models:
        model_key = model.get("modelKey")
        identifier = model.get("identifier") or model_key
        if model_key == selected_key:
            selected_loaded = True
        elif identifier:
            spinner.write(
                lang("stopping_other_model", model=model_key or identifier)
            )
            subprocess.run(provider["unload_command"] + [identifier], check=True)

    if selected_loaded:
        spinner.write(lang("model_already_loaded"))
    else:
        spinner.write(lang("loading_model", name=selected_model["name"]))
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
    response_parts = []
    final_chunk = {}

    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            for raw_line in response:
                chunk = json.loads(raw_line.decode("utf-8").strip() or "{}")
                text = chunk.get("response", "")
                if text:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    response_parts.append(text)
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
        "response": "".join(response_parts),
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
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:].strip())
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
    server_first_token = stats.get("time_to_first_token_seconds")
    full_response = "".join(response_parts)
    if not full_response:
        full_response = "".join(
            item.get("content", "")
            for item in final_result.get("output", [])
            if item.get("type") == "message"
        )

    return {
        **model,
        "first_token_seconds": server_first_token
        if server_first_token is not None
        else (
            first_token_time - start_time
            if first_token_time is not None
            else None
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
    return block


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
    spinner.write(lang("agent_work_dir", path=relative_work_dir))

    start_time = time.perf_counter()
    first_text_time = None
    response_parts = []
    event_log = []
    json_events = []
    json_blocks = []
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
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=agent_work_dir,
        )

        for line in process.stdout:
            if not line.strip():
                continue
            raw_event = line.rstrip("\r\n")
            if SAVE_AGENT_JSON_LOG:
                json_events.append(raw_event)
            event = json.loads(line)
            event_type = event.get("type")
            elapsed = int(time.perf_counter() - start_time)
            block = None

            if event_type == "step_start":
                step_count += 1
                block = add_opencode_event(
                    event_log,
                    lang("log_agent_step", elapsed=elapsed, step=step_count),
                    spinner=spinner,
                )
            elif event_type == "reasoning":
                reasoning = opencode_text(event)
                if reasoning:
                    block = add_opencode_event(
                        event_log,
                        lang("log_thinking", elapsed=elapsed),
                        reasoning,
                        spinner,
                    )
            elif event_type == "tool_use":
                part = event.get("part") or {}
                state = part.get("state") or {}
                tool = part.get("tool", lang("tool_unknown"))
                status = state.get("status", lang("tool_status_unknown"))
                title = state.get("title") or ""
                block = add_opencode_event(
                    event_log,
                    lang(
                        "log_tool", elapsed=elapsed, tool=tool, status=status
                    ),
                    title,
                    spinner,
                )
            elif event_type == "text":
                text = clean_block(opencode_text(event))
                if text and first_text_time is None:
                    first_text_time = time.perf_counter()
                if text:
                    response_parts.append(text)
                    block = add_opencode_event(
                        event_log, lang("log_answer", elapsed=elapsed), text, spinner
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
                block = add_opencode_event(
                    event_log,
                    lang("log_error", elapsed=elapsed, title=provider["title"].upper()),
                    error,
                    spinner,
                )

            if SAVE_AGENT_JSON_LOG:
                json_blocks.append((block, raw_event))

        return_code = process.wait()
        if not any(agent_work_dir.iterdir()):
            agent_work_dir.rmdir()
            relative_work_dir = None
    except Exception as error:
        try:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        except Exception:
            pass
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
        "reasoning_tokens": reasoning_tokens or None,
        "cache_read_tokens": cache_read_tokens or None,
        "load_seconds": None,
        "response": "\n\n".join(response_parts),
        "agent_steps": step_count,
        "event_log": "\n\n".join(event_log),
        "agent_work_dir": relative_work_dir,
        "json_event_log": "\n".join(json_events),
        "json_event_blocks": json_blocks,
    }
    if return_code:
        result["error"] = lang(
            "provider_exit_code",
            title=provider["title"],
            code=return_code,
        )
    return result


def make_error_result(model, error):
    return {**model, "error": str(error)}


def print_result(result, spinner):
    spinner.write(lang("test_completed"))
    for line in metric_lines(result):
        spinner.write(line)
    if "error" in result:
        spinner.write(f"{lang('error_label')}: {result['error']}")


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
        report.write(
            f"{lang('report_date')}: "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        provider = PROVIDERS[result["source"]]
        current_location = location_label(provider["location"])
        report.write(
            f"{lang('report_source')}: "
            f"{source_name(result['source'])} ({current_location})\n"
        )
        report.write(f"{lang('report_model')}: {result['full_name']}\n")
        if result.get("agent_work_dir"):
            report.write(
                f"{lang('report_agent_dir')}: {result['agent_work_dir']}\n"
            )
        report.write(f"{lang('report_test')}: {test_title}\n")
        report.write(f"{lang('report_test_file')}: {test_file.name}\n")

        report.write(lang("report_metrics"))
        report.write("\n".join(metric_lines(result)) + "\n")

        if "error" in result:
            report.write(lang("report_error"))
            report.write(f"{result['error']}\n")

        report.write(lang("report_prompt"))
        report.write(prompt + "\n")

        if result.get("event_log"):
            report.write(lang("report_log"))
            report.write(result["event_log"] + "\n")

        if "error" not in result:
            report.write(lang("report_answer"))
            report.write(result["response"] + "\n")

    if SAVE_AGENT_JSON_LOG and result.get("json_event_log"):
        log_head = [
            f"# AI MODELS BENCHMARK v{VERSION} LOG",
            f"{lang('report_date')}: "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{lang('report_source')}: "
            f"{source_name(result['source'])} "
            f"({location_label(provider['location'])})",
            f"{lang('report_model')}: {result['full_name']}",
            f"{lang('report_test')}: {test_title}",
            f"{lang('report_test_file')}: {test_file.name}",
        ]
        log_body = []
        for header_block, raw_json in result.get("json_event_blocks", []):
            if header_block:
                log_body.append(header_block)
            log_body.append(raw_json)
        report_path.with_suffix(".log").write_text(
            "\n".join(log_head)
            + "\n\n"
            + lang("report_log").strip()
            + "\n"
            + "\n".join(log_body)
            + "\n",
            encoding="utf-8",
        )

    return report_path.name


def run(spinner, argv_model="", argv_test=0):
    program_title = f"AI MODELS BENCHMARK v{VERSION}"
    if SAVE_AGENT_JSON_LOG:
        program_title += " [LOG]"
    searching_models = lang("searching_models")
    header = [
        program_title,
        "─" * max(len(program_title), len(searching_models)),
        searching_models,
    ]
    banner = [
        "┌─ .agent_work ────────────────────────────────────────────────┐",
        "│ TEST > MODEL > TOOLS > REPORT ? TOKENS [###..] ? [PASS] ===> │",
        "└──────────────────────────────────────────────────────────────┘",
    ]
    terminal_width = shutil.get_terminal_size((120, 24)).columns
    header_width = max(map(len, header)) + 4
    free_width = terminal_width - header_width - 2
    if len(banner[0]) <= free_width:
        banner_position = header_width + (free_width - len(banner[0])) // 2
        for text, art in zip(header, banner):
            spinner.write(text.ljust(banner_position) + art)
    else:
        for text in header:
            spinner.write(text)

    def find_models():
        set_window_title(lang("window_searching", program=program_title))

        def check_provider(item):
            provider_id, provider = item
            try:
                found, models = PROTOCOLS[provider["protocol"]]["get_models"](
                    provider_id, provider
                )
            except Exception:
                found, models = False, []
            return provider_id, provider, found, models

        with ThreadPoolExecutor() as executor:
            results = list(executor.map(check_provider, PROVIDERS.items()))
        set_window_title(program_title)
        results.sort(key=lambda result: result[2])
        width = max(len(provider["title"]) for provider in PROVIDERS.values())

        unavailable = [
            f"{provider['title'].ljust(width)} - "
            f"{provider_unavailable(provider_id)}"
            for provider_id, provider, found, _ in results
            if not found
        ]
        if unavailable:
            spinner.write("\n" + "\n".join(unavailable))

        sections = build_grid_sections(results)
        models = list(itertools.chain.from_iterable(
            section_models for _, section_models in sections
        ))
        return results, sections, models, width

    provider_results, sections, models, provider_width = find_models()
    if not models:
        spinner.write(lang("no_models"))
        return

    tests = get_tests()
    if not tests:
        spinner.write(lang("no_tests"))
        return

    while True:
        name_counts = {}
        for item in models:
            key = item["name"].casefold()
            name_counts[key] = name_counts.get(key, 0) + 1
        duplicated_names = frozenset(
            name for name, count in name_counts.items() if count > 1
        )
        for _, provider, found, provider_models in provider_results:
            if found:
                spinner.write(
                    lang(
                        "provider_models",
                        title=provider["title"].ljust(provider_width),
                        count=len(provider_models),
                        location=location_label(provider["location"]),
                    )
                )
        if sections:
            write_model_grid(
                sections, len(models), spinner, duplicated_names,
            )

        model = None
        while model is None:
            choice = argv_model or spinner.input(lang("choose_model")).strip()
            if not argv_model and choice.lower() == "r":
                spinner.write(f"\n{searching_models}")
                provider_results, sections, models, provider_width = find_models()
                if not models:
                    spinner.write(lang("no_models"))
                    return
                break

            model_number = int(choice) if choice.isdigit() else None
            matches = [
                index
                for index, item in enumerate(models)
                if model_number == index + 1
                or (
                    model_number is None
                    and item["name"].casefold() == choice.casefold()
                )
                or (
                    model_number is None
                    and item["full_name"].casefold() == choice.casefold()
                )
            ]
            if not matches:
                spinner.write(lang("model_not_found", model=choice))
                if argv_model:
                    return
                continue
            if len(matches) > 1:
                duplicates = "\n".join(
                    f"  {models[index]['full_name']}" for index in matches
                )
                spinner.write(
                    lang(
                        "duplicate_model",
                        model=choice,
                        count=len(matches),
                        models=duplicates,
                    )
                )
                if argv_model:
                    return
                continue
            model = models[matches[0]]

        if model is None:
            continue

        provider = PROVIDERS[model["source"]]
        protocol = PROTOCOLS[provider["protocol"]]
        current_location = location_label(provider["location"])
        spinner.write(
            lang(
                "selected_model",
                source=source_name(model["source"]),
                name=model["full_name"],
                location=current_location,
            )
        )

        spinner.write(lang("available_tests"))
        for number, (_, title, _) in enumerate(tests, start=1):
            spinner.write(f"  [{format_list_number(number, len(tests))}] {title}")

        if argv_test == "x":
            selected_tests = tests
            break
        if argv_test:
            if argv_test > len(tests):
                spinner.write(lang("test_not_found", test=argv_test))
                return
            selected_tests = [tests[argv_test - 1]]
            break

        while True:
            choice = spinner.input(lang("choose_test")).strip()
            if choice == "0":
                break
            if choice.lower() == "x":
                selected_tests = tests
                break
            test_index = choose_number(len(tests), choice, spinner)
            if test_index is not None:
                selected_tests = [tests[test_index]]
                break

        if choice == "0":
            continue

        break

    prepare = protocol["prepare"]
    if prepare:
        prepare(provider, model, spinner)

    completed_tests = 0
    failed = False
    selected_count = len(selected_tests)
    try:
        for position, (test_file, test_title, prompt) in enumerate(selected_tests, 1):
            test_number = tests.index((test_file, test_title, prompt)) + 1
            title_number = (
                f"{position}/{selected_count}" if selected_count > 1 else test_number
            )
            set_window_title(
                lang(
                    "window_test",
                    program=program_title,
                    model=model["name"],
                    test=title_number,
                )
            )
            if selected_count > 1:
                spinner.write(
                    lang(
                        "test_progress",
                        position=position,
                        total=selected_count,
                        title=test_title,
                    )
                )
            else:
                spinner.write(lang("test_header", title=test_title))

            result = protocol["run"](provider, model, prompt, test_file, spinner)
            failed = failed or "error" in result

            print_result(result, spinner)
            report_name = save_report(result, test_file, test_title, prompt)
            spinner.write(lang("report_saved", name=report_name))
            log_path = (PROGRAM_DIR / report_name).with_suffix(".log")
            if SAVE_AGENT_JSON_LOG and log_path.is_file():
                spinner.write(lang("log_saved"))
            completed_tests += 1
    except KeyboardInterrupt:
        spinner.write(lang("interrupted"))
        set_window_title(program_title)
    else:
        state = "window_error" if failed else "window_completed"
        set_window_title(lang(state, program=program_title))
    spinner.write(lang("final_model", name=model["full_name"]))
    spinner.write(lang("tests_completed", count=completed_tests))


def main():
    with Spinner(SHOW_SPINNER) as spinner:
        try:
            ensure_language()
        except LanguageError as error:
            spinner.input(str(error))
            raise SystemExit

        try:
            argv_model, argv_test = read_arguments(spinner)
            run(spinner, argv_model, argv_test)
        except SystemExit:
            raise
        except KeyboardInterrupt:
            spinner.write(lang("interrupted"))
        except Exception as error:
            set_window_title(
                lang(
                    "window_error",
                    program=f"AI MODELS BENCHMARK v{VERSION}",
                )
            )
            spinner.write(f"\n{lang('error_label')}: {error}")
        finally:
            spinner.input(lang("exit_prompt"))


if __name__ == "__main__":
    main()
