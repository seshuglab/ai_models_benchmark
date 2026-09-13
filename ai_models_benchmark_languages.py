import locale
import string
import sys


LANGUAGES = {
    "ru": {
        "exit_prompt": "\nНажми Enter для выхода...",
        "searching_models": "Поиск доступных моделей...",
        "no_models": "\nДоступные модели не найдены.",
        "no_tests": "\nТестовые файлы [0-9][0-9]_*.md не найдены.",
        "provider_models": "\n{title:<10}- {count} моделей ({location}):",
        "provider_unavailable_ollama": "не обнаружена (нужен запущенный Ollama)",
        "provider_unavailable_opencode": "не обнаружен (нужен OpenCode CLI, команда 'opencode')",
        "provider_unavailable_lmstudio": "не обнаружена (нужен запущенный сервер LM Studio)",
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
        "total_tokens": "Всего токенов",
        "agent_steps": "Шагов агента",
        "load_model": "Загрузка модели",
        "sec": "сек",
        "speed_unit": "токен/сек",
        "invalid_number": "Неверный номер.",
        "help_text": (
            "Использование:\n"
            "  python ai_models_benchmark.py\n"
            "  python ai_models_benchmark.py <модель> <номер теста>\n\n"
            "Параметры:\n"
            "  --help                  Показать справку\n"
            "  --en                    English interface\n"
            "  --ru                    Русский интерфейс\n"
            "  --no-spinner            Отключить спиннер\n"
            "  --opencode-json-log     Сохранять JSON-события OpenCode"
        ),
        "args_error": "Укажите модель и номер теста.\n",
        "model_already_loaded": "Выбранная модель уже загружена в память.",
        "stopping_other_model": "Останавливаю другую модель: {model}",
        "loading_model": "Загружаю модель: {name}",
        "agent_work_dir": "Рабочая папка агента: {path}",
        "log_agent_step": "[{elapsed}][АГЕНТ] Шаг {step}",
        "log_thinking": "[{elapsed}][РАЗМЫШЛЕНИЕ]",
        "log_tool": "[{elapsed}][ИНСТРУМЕНТ] {tool} — {status}",
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
        "duplicate_model": "\nМоделей с именем {model} найдено: {count}",
        "choose_model": "\nВыбери номер модели: ",
        "choose_test": "\nВыбери номер теста, X — все тесты, 0 — назад: ",
        "available_tests": "\nДоступные тесты:\n",
        "selected_model": "\nВыбранная модель: {source} — {name} ({location})",
        "test_not_found": "\nТест не найден: {test}",
        "test_header": "\nТест: {title}\n",
        "report_saved": "\nОтчёт сохранён: {name}",
        "interrupted": "\nВыполнение остановлено пользователем.",
        "final_model": "\nМодель: {name}",
        "tests_completed": "Пройдено тестов: {count}",
    },
    "en": {
        "exit_prompt": "\nPress Enter to exit...",
        "searching_models": "Searching for available models...",
        "no_models": "\nNo available models found.",
        "no_tests": "\nTest files [0-9][0-9]_*.md not found.",
        "provider_models": "\n{title:<10}- {count} models ({location}):",
        "provider_unavailable_ollama": "not found (running Ollama is required)",
        "provider_unavailable_opencode": "not found (OpenCode CLI is required, command 'opencode')",
        "provider_unavailable_lmstudio": "not found (running LM Studio server is required)",
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
        "total_tokens": "Total tokens",
        "agent_steps": "Agent steps",
        "load_model": "Model load",
        "sec": "s",
        "speed_unit": "tokens/s",
        "invalid_number": "Invalid number.",
        "help_text": (
            "Usage:\n"
            "  python ai_models_benchmark.py\n"
            "  python ai_models_benchmark.py <model> <test number>\n\n"
            "Options:\n"
            "  --help                  Show help\n"
            "  --en                    English interface\n"
            "  --ru                    Русский интерфейс\n"
            "  --no-spinner            Disable spinner\n"
            "  --opencode-json-log     Save OpenCode JSON events"
        ),
        "args_error": "Specify the model and test number.\n",
        "model_already_loaded": "Selected model is already loaded in memory.",
        "stopping_other_model": "Stopping another model: {model}",
        "loading_model": "Loading model: {name}",
        "agent_work_dir": "Agent work dir: {path}",
        "log_agent_step": "[{elapsed}][AGENT] Step {step}",
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
        "duplicate_model": "\nModels named {model} found: {count}",
        "choose_model": "\nChoose a model number: ",
        "choose_test": "\nChoose a test number, X - all tests, 0 - back: ",
        "available_tests": "\nAvailable tests:\n",
        "selected_model": "\nSelected model: {source} - {name} ({location})",
        "test_not_found": "\nTest not found: {test}",
        "test_header": "\nTest: {title}\n",
        "report_saved": "\nReport saved: {name}",
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
    if values:
        return template.format(**values)
    return template


def detect_system_language():
    try:
        code, _ = locale.getdefaultlocale()
    except Exception:
        return "en"
    if not code:
        return "en"
    normalized = code.lower()
    if normalized.startswith("ru"):
        return "ru"
    return "en"


def init_language_from_argv(argv=None):
    if argv is None:
        argv = sys.argv
    has_ru = "--ru" in argv
    has_en = "--en" in argv
    if has_ru and has_en:
        raise LanguageError(
            "Localization error: cannot use --ru and --en together / "
            "Нельзя одновременно использовать --ru и --en"
        )
    if has_ru:
        set_language("ru")
    elif has_en:
        set_language("en")
    else:
        set_language(detect_system_language())
    return _LANGUAGE


def _format_fields(template):
    fields = set()
    for _, name, _, _ in string.Formatter().parse(template):
        if name is not None and name != "":
            fields.add(name.split(".")[0].split("[")[0])
    return fields


def validate_languages():
    ru_keys = set(LANGUAGES.get("ru", {}))
    en_keys = set(LANGUAGES.get("en", {}))
    for key in sorted(ru_keys - en_keys):
        raise LanguageError(
            f"Localization error: language 'en', missing key '{key}'"
        )
    for key in sorted(en_keys - ru_keys):
        raise LanguageError(
            f"Localization error: language 'ru', missing key '{key}'"
        )
    for key in sorted(ru_keys & en_keys):
        ru_fields = _format_fields(LANGUAGES["ru"][key])
        en_fields = _format_fields(LANGUAGES["en"][key])
        if ru_fields != en_fields:
            missing = sorted(ru_fields - en_fields)
            extra = sorted(en_fields - ru_fields)
            raise LanguageError(
                f"Localization error: key '{key}', "
                f"ru fields {sorted(ru_fields)}, en fields {sorted(en_fields)}, "
                f"missing in en {missing}, extra in en {extra}"
            )
