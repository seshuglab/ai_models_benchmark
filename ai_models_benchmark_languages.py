import locale
import string
import sys


LANGUAGES = {
    "ru": {
        "_locales": ("ru",),
        "_name": "Русский интерфейс",
        "exit_prompt": "\nНажми Enter для выхода...",
        "searching_models": "Поиск доступных моделей...",
        "window_searching": "{program} - поиск моделей",
        "window_test": "{program} - {model} - {test}",
        "window_completed": "{program} - завершено",
        "window_error": "{program} - ошибка",
        "no_models": "\nДоступные модели не найдены.",
        "no_tests": "\nТестовые файлы [0-9][0-9]_*.md не найдены.",
        "provider_models": "{title} - моделей: {count} ({location})",
        "provider_unavailable_ollama": "недоступен: сервис не запущен",
        "provider_unavailable_opencode": "недоступен: CLI не найден",
        "provider_unavailable_lmstudio": "недоступен: сервер не запущен",
        "location_local": "локально",
        "location_cloud": "облако",
        "unavailable_value": "недоступно",
        "first_text": "До первого текста",
        "first_token": "До первого токена",
        "total_time": "Полное время",
        "agent_speed": "Эффективная скорость агента",
        "generation_speed": "Скорость генерации",
        "prompt_no_cache": "Входных токенов без кэша",
        "prompt_tokens": "Токенов в промпте",
        "generated_tokens": "Сгенерировано токенов",
        "reasoning_tokens": "Токенов размышления",
        "cache_tokens": "Токенов из кэша",
        "cache_write_tokens": "Токенов записано в кэш",
        "total_tokens": "Всего токенов",
        "agent_steps": "Шагов агента",
        "load_model": "Загрузка модели",
        "sec": "сек",
        "speed_unit": "токен/сек",
        "invalid_number": "\nНеверный номер.",
        "help_text": (
            "Использование:\n"
            "  python ai_models_benchmark.py\n"
            "  python ai_models_benchmark.py <модель> <номер теста | X>\n\n"
            "Параметры:\n"
            "  --help                  Показать справку\n"
            "{language_options}\n"
            "  --no-spinner            Отключить спиннер\n"
            "  --opencode-json-log     Сохранять JSON-события OpenCode"
        ),
        "args_error": "Укажите модель, номер теста или X.\n",
        "unknown_option": "Неизвестный параметр: {option}\n",
        "model_already_loaded": "Выбранная модель уже загружена в память.",
        "stopping_other_model": "Останавливаю другую модель: {model}",
        "loading_model": "Загружаю модель: {name}",
        "agent_work_dir": "Рабочая папка агента: {path}",
        "agent_log_legend": (
            "Формат шага: [время](I/O/R/C)[АГЕНТ] Шаг N\n"
            "I - входные токены без кэша, O - выходные токены, "
            "R - токены размышления, C - токены чтения кэша\n"
            "Значения токенов накопительные к началу шага. "
            "K - тысячи, M - миллионы."
        ),
        "log_agent_step": "[{elapsed}]({tokens})[АГЕНТ] Шаг {step}",
        "log_thinking": "[{elapsed}][РАЗМЫШЛЕНИЕ]",
        "log_tool": "[{elapsed}][ИНСТРУМЕНТ] {tool} - {status}",
        "tool_unknown": "неизвестный инструмент",
        "tool_status_unknown": "неизвестно",
        "log_answer": "[{elapsed}][ОТВЕТ]",
        "log_error": "[{elapsed}][ОШИБКА {title}]",
        "provider_exit_code": "{title} завершился с кодом {code}",
        "test_completed": "\n\nТЕСТ ЗАВЕРШЁН",
        "error_label": "ОШИБКА",
        "report_date": "Дата",
        "report_source": "Источник",
        "report_model": "Модель",
        "report_agent_dir": "Рабочая папка агента",
        "report_test": "Тест",
        "report_test_file": "Файл теста",
        "report_metrics": "\n# МЕТРИКИ:\n",
        "report_error": "\n# ОШИБКА:\n",
        "report_prompt": "\n# ПРОМТ:\n",
        "report_log": "\n# ЖУРНАЛ ВЫПОЛНЕНИЯ:\n",
        "report_answer": "\n# ОТВЕТ МОДЕЛИ:\n",
        "model_not_found": "\nМодель не найдена: {model}",
        "duplicate_model": "\nНайдено моделей с именем {model}: {count}\n{models}",
        "choose_model": "\n> Выбери номер или имя модели, [R] - обновить список: ",
        "choose_test": "\n> Выбери номер теста, [X] - все тесты, [0] - назад: ",
        "available_tests": "\nДоступные тесты:\n",
        "selected_model": "\nВыбранная модель: {source} - {name} ({location})",
        "test_not_found": "\nТест не найден: {test}",
        "test_header": "\nТест: {title}\n",
        "test_progress": "\nТест [{position}/{total}]: {title}\n",
        "report_saved": "\nОтчёт сохранён: {name}",
        "log_saved": "Дополнительно сохранён LOG-файл.",
        "interrupted": "\nВыполнение остановлено пользователем.",
        "final_model": "\nМодель: {name}",
        "tests_completed": "Пройдено тестов: {count}",
    },
    "en": {
        "_locales": ("en",),
        "_name": "English interface",
        "exit_prompt": "\nPress Enter to exit...",
        "searching_models": "Searching for available models...",
        "window_searching": "{program} - searching for models",
        "window_test": "{program} - {model} - {test}",
        "window_completed": "{program} - completed",
        "window_error": "{program} - error",
        "no_models": "\nNo available models found.",
        "no_tests": "\nTest files [0-9][0-9]_*.md not found.",
        "provider_models": "{title} - models: {count} ({location})",
        "provider_unavailable_ollama": "unavailable: service is not running",
        "provider_unavailable_opencode": "unavailable: CLI not found",
        "provider_unavailable_lmstudio": "unavailable: server is not running",
        "location_local": "local",
        "location_cloud": "cloud",
        "unavailable_value": "unavailable",
        "first_text": "Time to first text",
        "first_token": "Time to first token",
        "total_time": "Total time",
        "agent_speed": "Agent effective speed",
        "generation_speed": "Generation speed",
        "prompt_no_cache": "Input tokens without cache",
        "prompt_tokens": "Prompt tokens",
        "generated_tokens": "Generated tokens",
        "reasoning_tokens": "Reasoning tokens",
        "cache_tokens": "Cache tokens",
        "cache_write_tokens": "Cache write tokens",
        "total_tokens": "Total tokens",
        "agent_steps": "Agent steps",
        "load_model": "Model load",
        "sec": "s",
        "speed_unit": "tokens/s",
        "invalid_number": "\nInvalid number.",
        "help_text": (
            "Usage:\n"
            "  python ai_models_benchmark.py\n"
            "  python ai_models_benchmark.py <model> <test number | X>\n\n"
            "Options:\n"
            "  --help                  Show help\n"
            "{language_options}\n"
            "  --no-spinner            Disable spinner\n"
            "  --opencode-json-log     Save OpenCode JSON events"
        ),
        "args_error": "Specify the model, test number or X.\n",
        "unknown_option": "Unknown option: {option}\n",
        "model_already_loaded": "Selected model is already loaded in memory.",
        "stopping_other_model": "Stopping another model: {model}",
        "loading_model": "Loading model: {name}",
        "agent_work_dir": "Agent work dir: {path}",
        "agent_log_legend": (
            "Step format: [time](I/O/R/C)[AGENT] Step N\n"
            "I - input without cache, O - output, R - reasoning, "
            "C - cache read tokens\n"
            "Token values are cumulative at the start of the step. "
            "K - thousands, M - millions."
        ),
        "log_agent_step": "[{elapsed}]({tokens})[AGENT] Step {step}",
        "log_thinking": "[{elapsed}][THINKING]",
        "log_tool": "[{elapsed}][TOOL] {tool} - {status}",
        "tool_unknown": "unknown tool",
        "tool_status_unknown": "unknown",
        "log_answer": "[{elapsed}][ANSWER]",
        "log_error": "[{elapsed}][{title} ERROR]",
        "provider_exit_code": "{title} exited with code {code}",
        "test_completed": "\n\nTEST COMPLETED",
        "error_label": "ERROR",
        "report_date": "Date",
        "report_source": "Source",
        "report_model": "Model",
        "report_agent_dir": "Agent work dir",
        "report_test": "Test",
        "report_test_file": "Test file",
        "report_metrics": "\n# METRICS:\n",
        "report_error": "\n# ERROR:\n",
        "report_prompt": "\n# PROMPT:\n",
        "report_log": "\n# EXECUTION LOG:\n",
        "report_answer": "\n# MODEL ANSWER:\n",
        "model_not_found": "\nModel not found: {model}",
        "duplicate_model": "\nModels named {model} found: {count}\n{models}",
        "choose_model": "\n> Choose a model number or name, [R] - refresh the list: ",
        "choose_test": "\n> Choose a test number, [X] - all tests, [0] - back: ",
        "available_tests": "\nAvailable tests:\n",
        "selected_model": "\nSelected model: {source} - {name} ({location})",
        "test_not_found": "\nTest not found: {test}",
        "test_header": "\nTest: {title}\n",
        "test_progress": "\nTest [{position}/{total}]: {title}\n",
        "report_saved": "\nReport saved: {name}",
        "log_saved": "Additionally saved LOG file.",
        "interrupted": "\nExecution stopped by user.",
        "final_model": "\nModel: {name}",
        "tests_completed": "Tests completed: {count}",
    },
}

_LANGUAGE = "en"


class LanguageError(Exception):
    def __str__(self):
        return f"{super().__str__()}\n\nPress Enter to exit..."


def get_language():
    return _LANGUAGE


def set_language(code):
    global _LANGUAGE
    if code not in LANGUAGES:
        raise LanguageError(f"Localization error: unknown language '{code}'")
    _LANGUAGE = code


def lang(key, **values):
    table = LANGUAGES.get(_LANGUAGE, {})
    if key not in table:
        raise LanguageError(
            f"Localization error: language '{_LANGUAGE}', unknown key '{key}'"
        )
    template = table[key]
    if key == "help_text":
        values["language_options"] = "\n".join(
            f"  --{code:<22}{LANGUAGES[code]['_name']}"
            for code in sorted(LANGUAGES)
        )
    if values:
        return template.format(**values)
    missing = _format_fields(template)
    if missing:
        raise LanguageError(
            f"Localization error: language '{_LANGUAGE}', key '{key}', "
            f"missing values {sorted(missing)}"
        )
    return template


def detect_system_language():
    try:
        code, _ = locale.getdefaultlocale()
    except Exception:
        return "en"
    if not code:
        return "en"
    normalized = code.casefold()
    for language, table in LANGUAGES.items():
        if any(
            normalized.startswith(value.casefold())
            for value in table["_locales"]
        ):
            return language
    return "en"


def init_language_from_argv(argv=None):
    if argv is None:
        argv = sys.argv
    selected = [code for code in LANGUAGES if f"--{code}" in argv]
    if len(selected) > 1:
        raise LanguageError(
            "Localization error: cannot use language options together: "
            + ", ".join(f"--{code}" for code in selected)
        )
    set_language(selected[0] if selected else detect_system_language())
    return _LANGUAGE


def _format_fields(template):
    fields = set()
    for _, name, _, _ in string.Formatter().parse(template):
        if name is not None and name != "":
            fields.add(name.split(".")[0].split("[")[0])
    return fields


def validate_languages():
    reference = {key for key in LANGUAGES["en"] if not key.startswith("_")}
    for language, table in LANGUAGES.items():
        for field in ("_locales", "_name"):
            if not table.get(field):
                raise LanguageError(
                    f"Localization error: language '{language}', missing field '{field}'"
                )
        keys = {key for key in table if not key.startswith("_")}
        for key in sorted(reference - keys):
            raise LanguageError(
                f"Localization error: language '{language}', missing key '{key}'"
            )
        for key in sorted(keys - reference):
            raise LanguageError(
                f"Localization error: language '{language}', extra key '{key}'"
            )
        for key in sorted(reference):
            expected = _format_fields(LANGUAGES["en"][key])
            actual = _format_fields(table[key])
            if actual != expected:
                raise LanguageError(
                    f"Localization error: language '{language}', key '{key}', "
                    f"fields {sorted(actual)}, expected {sorted(expected)}"
                )
