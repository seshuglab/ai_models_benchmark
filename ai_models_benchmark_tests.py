import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, call, patch

import ai_models_benchmark as benchmark


class TerminalOutput(io.StringIO):
    def isatty(self):
        return True


class FakeHttpResponse:
    def __init__(self, chunks):
        self.lines = [
            (json.dumps(chunk, ensure_ascii=False) + "\n").encode("utf-8")
            for chunk in chunks
        ]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        return iter(self.lines)


class FakeProcess:
    def __init__(self, events):
        self.stdout = io.StringIO(
            "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)
        )
        self.stderr = io.StringIO("")

    def wait(self):
        return 0


class FakeSseResponse:
    def __init__(self, events):
        self.lines = []
        for event in events:
            self.lines.extend(
                [
                    f"event: {event['type']}\n".encode("utf-8"),
                    ("data: " + json.dumps(event, ensure_ascii=False) + "\n").encode(
                        "utf-8"
                    ),
                    b"\n",
                ]
            )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        return iter(self.lines)


class SpinnerTests(unittest.TestCase):
    def test_write_preserves_streaming_output(self):
        output = TerminalOutput()
        with patch.object(benchmark.sys, "stdout", output):
            spinner = benchmark.Spinner()
            spinner.write("one", end="")
            spinner.write(" two")
            spinner.write("three")

        self.assertEqual(output.getvalue(), "\r \rone two\n\r \rthree\n")
        self.assertFalse(spinner.streaming)

    def test_disabled_when_output_is_not_terminal(self):
        output = io.StringIO()
        with patch.object(benchmark.sys, "stdout", output):
            spinner = benchmark.Spinner()
            spinner.start()

        self.assertFalse(spinner.enabled)
        self.assertIsNone(spinner.thread)
        self.assertEqual(output.getvalue(), "")

    def test_interrupted_input_adds_newline_and_reraises(self):
        for error in (KeyboardInterrupt, EOFError):
            with self.subTest(error=error.__name__):
                output = TerminalOutput()
                with patch.object(benchmark.sys, "stdout", output):
                    spinner = benchmark.Spinner()
                    with patch("builtins.input", side_effect=error):
                        with self.assertRaises(error):
                            spinner.input("Prompt: ")

                self.assertEqual(output.getvalue(), "\r \r\n")


class RunTests(unittest.TestCase):
    def run_with_test_choice(
        self,
        choice,
        run_side_effect=None,
        input_values=None,
        argv_model="",
        argv_test=0,
        available_models=None,
    ):
        spinner = Mock()
        spinner.input.side_effect = (
            input_values if input_values is not None else ["1", choice]
        )
        model = {
            "source": "ollama",
            "name": "test-model",
            "full_name": "test-model",
        }
        tests = [
            ("01_test.md", "Первый тест", "prompt 1"),
            ("02_test.md", "Второй тест", "prompt 2"),
        ]
        result = object()
        prepare_model = Mock()
        run_test = Mock(return_value=result)
        protocol = {
            "get_models": Mock(return_value=(True, available_models or [model])),
            "prepare": prepare_model,
            "run": run_test,
            "metrics": "generation",
        }

        with (
            patch.dict(
                benchmark.PROVIDERS,
                {"ollama": benchmark.PROVIDERS["ollama"]},
                clear=True,
            ),
            patch.dict(
                benchmark.PROTOCOLS, {"ollama_api": protocol}, clear=True
            ),
            patch.object(benchmark, "get_tests", return_value=tests),
            patch.object(benchmark, "print_result"),
            patch.object(benchmark, "save_report", return_value="report.txt") as save_report,
        ):
            if run_side_effect is not None:
                run_test.side_effect = run_side_effect
            benchmark.run(spinner, argv_model, argv_test)

        return spinner, model, tests, prepare_model, run_test, save_report

    def test_x_runs_every_test_with_separate_report(self):
        spinner, model, tests, prepare_model, run_test, save_report = (
            self.run_with_test_choice("X")
        )

        prepare_model.assert_called_once_with(
            benchmark.PROVIDERS["ollama"], model, spinner
        )
        self.assertEqual(run_test.call_count, len(tests))
        self.assertEqual(save_report.call_count, len(tests))
        spinner.write.assert_any_call("Пройдено тестов: 2")

    def test_number_runs_only_selected_test(self):
        spinner, model, tests, _, run_test, save_report = self.run_with_test_choice("2")

        run_test.assert_called_once_with(
            benchmark.PROVIDERS["ollama"], model, tests[1][2], tests[1][0], spinner
        )
        save_report.assert_called_once_with(
            run_test.return_value, tests[1][0], tests[1][1], tests[1][2]
        )
        spinner.write.assert_any_call("Пройдено тестов: 1")

    def test_interruption_stops_batch_and_shows_completed_count(self):
        spinner, _, _, _, run_test, save_report = self.run_with_test_choice(
            "X", [object(), KeyboardInterrupt]
        )

        self.assertEqual(run_test.call_count, 2)
        save_report.assert_called_once()
        spinner.write.assert_any_call("\nВыполнение остановлено пользователем.")
        spinner.write.assert_any_call("Пройдено тестов: 1")

    def test_zero_returns_from_tests_to_model_selection(self):
        spinner, _, _, _, run_test, save_report = self.run_with_test_choice(
            "1", input_values=["1", "0", "1", "1"]
        )

        self.assertEqual(spinner.input.call_count, 4)
        run_test.assert_called_once()
        save_report.assert_called_once()

    def test_arguments_select_model_by_number_or_name(self):
        for model_value in ("1", "test-model"):
            with self.subTest(model=model_value):
                spinner, _, _, _, run_test, _ = self.run_with_test_choice(
                    None,
                    input_values=[],
                    argv_model=model_value,
                    argv_test=2,
                )
                spinner.input.assert_not_called()
                run_test.assert_called_once()

    def test_arguments_reject_unknown_model(self):
        spinner, _, _, prepare_model, run_test, _ = self.run_with_test_choice(
            None, input_values=[], argv_model="missing", argv_test=1
        )

        spinner.write.assert_any_call("\nМодель не найдена: missing")
        prepare_model.assert_not_called()
        run_test.assert_not_called()

    def test_arguments_reject_duplicate_model_name(self):
        models = [
            {"source": "ollama", "name": "same", "full_name": "first"},
            {"source": "ollama", "name": "same", "full_name": "second"},
        ]
        spinner, _, _, prepare_model, run_test, _ = self.run_with_test_choice(
            None,
            input_values=[],
            argv_model="same",
            argv_test=1,
            available_models=models,
        )

        spinner.write.assert_any_call("\nМоделей с именем same найдено: 2")
        prepare_model.assert_not_called()
        run_test.assert_not_called()

    def test_arguments_reject_unknown_test(self):
        spinner, _, _, prepare_model, run_test, _ = self.run_with_test_choice(
            None, input_values=[], argv_model="1", argv_test=7
        )

        spinner.write.assert_any_call("\nТест не найден: 7")
        prepare_model.assert_not_called()
        run_test.assert_not_called()


class ReadArgumentsTests(unittest.TestCase):
    def test_reads_model_and_test(self):
        with patch.object(
            benchmark.sys, "argv", ["benchmark.py", "model", "7"]
        ):
            self.assertEqual(benchmark.read_arguments(), ("model", 7))

    def test_rejects_invalid_arguments(self):
        for arguments in (["model"], ["model", "x"], ["model", "0"]):
            with self.subTest(arguments=arguments):
                with patch.object(benchmark.sys, "argv", ["benchmark.py", *arguments]):
                    with self.assertRaises(SystemExit):
                        benchmark.read_arguments()

    def test_main_waits_for_enter_after_invalid_arguments(self):
        spinner = Mock()
        spinner_context = Mock()
        spinner_context.__enter__ = Mock(return_value=spinner)
        spinner_context.__exit__ = Mock(return_value=False)

        with (
            patch.object(benchmark.sys, "argv", ["benchmark.py", "model"]),
            patch.object(benchmark, "Spinner", return_value=spinner_context),
        ):
            with self.assertRaises(SystemExit):
                benchmark.main()

        spinner.input.assert_called_once_with(benchmark.EXIT_PROMPT)


class ProviderFlowIntegrationTests(unittest.TestCase):
    ollama_model = {
        "source": "local_test",
        "name": "test-ollama",
        "full_name": "test-ollama",
    }
    opencode_model = {
        "source": "agent_test",
        "name": "test-agent",
        "full_name": "test/test-agent",
    }
    lmstudio_model = {
        "source": "lmstudio_test",
        "name": "Test LM",
        "full_name": "test/lm-model",
    }

    def run_isolated(self, model_choice, provider_patch, timer_values):
        spinner = Mock()
        spinner.input.side_effect = [model_choice, "1"]
        providers = {
            "local_test": {
                **benchmark.PROVIDERS["ollama"],
                "title": "Local Test",
            },
            "agent_test": {
                **benchmark.PROVIDERS["opencode"],
                "title": "Agent Test",
            },
            "lmstudio_test": {
                **benchmark.PROVIDERS["lmstudio"],
                "title": "LM Test",
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            program_dir = Path(directory)
            (program_dir / "01_test.md").write_text(
                "# Интеграционный тест\nВерни однозначный ответ.", encoding="utf-8"
            )
            with (
                patch.object(benchmark, "PROGRAM_DIR", program_dir),
                patch.dict(benchmark.PROVIDERS, providers, clear=True),
                patch.dict(
                    benchmark.PROTOCOLS["ollama_api"],
                    {
                        "get_models": Mock(return_value=(True, [self.ollama_model])),
                        "prepare": Mock(),
                    },
                ),
                patch.dict(
                    benchmark.PROTOCOLS["opencode_cli"],
                    {"get_models": Mock(return_value=(True, [self.opencode_model]))},
                ),
                patch.dict(
                    benchmark.PROTOCOLS["lmstudio_api"],
                    {
                        "get_models": Mock(
                            return_value=(True, [self.lmstudio_model])
                        ),
                        "prepare": Mock(),
                    },
                ),
                patch.object(
                    benchmark.time, "perf_counter", side_effect=timer_values
                ),
                provider_patch,
            ):
                benchmark.run(spinner)

            reports = list(program_dir.glob("ai_test_*.txt"))
            self.assertEqual(len(reports), 1)
            return reports[0].read_text(encoding="utf-8")

    def test_ollama_flow_creates_expected_report(self):
        response = FakeHttpResponse(
            [
                {"response": "Тестовый ", "done": False},
                {
                    "response": "ответ",
                    "done": True,
                    "prompt_eval_count": 10,
                    "eval_count": 2,
                    "eval_duration": 1_000_000_000,
                    "load_duration": 500_000_000,
                },
            ]
        )

        report = self.run_isolated(
            "1",
            patch.object(benchmark.urllib.request, "urlopen", return_value=response),
            [100.0, 101.0, 104.0],
        )

        self.assertIn("Источник: Local Test (локально)", report)
        self.assertIn("Модель: test-ollama", report)
        self.assertIn("До первого токена: 1.00 сек", report)
        self.assertIn("Полное время: 4.00 сек", report)
        self.assertIn("Скорость генерации: 2.00 токен/сек", report)
        self.assertIn("Токенов в промпте: 10", report)
        self.assertIn("Сгенерировано токенов: 2", report)
        self.assertIn("# ОТВЕТ МОДЕЛИ:\nТестовый ответ", report)

    def test_opencode_flow_creates_expected_report(self):
        process = FakeProcess(
            [
                {"type": "step_start"},
                {"type": "reasoning", "text": "Проверяю условие"},
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "read",
                        "state": {"status": "completed", "title": "Прочитан файл"},
                    },
                },
                {
                    "type": "text",
                    "text": "\n\nОднозначный тестовый ответ\n\n\nВторая строка\n\n",
                },
                {
                    "type": "step_finish",
                    "tokens": {
                        "input": 10,
                        "output": 4,
                        "reasoning": 2,
                        "total": 19,
                        "cache": {"read": 3},
                    },
                },
            ]
        )

        report = self.run_isolated(
            "2",
            patch.object(benchmark.subprocess, "Popen", return_value=process),
            [100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 104.5, 105.0],
        )

        self.assertIn("Источник: Agent Test (облако)", report)
        self.assertIn("Модель: test-agent", report)
        self.assertIn("До первого текста: 4.00 сек", report)
        self.assertIn("Полное время: 5.00 сек", report)
        self.assertIn("Эффективная скорость агента: 0.80 токен/сек", report)
        self.assertIn("Входных токенов без кэша: 10", report)
        self.assertIn("Сгенерировано токенов: 4", report)
        self.assertIn("Токенов размышления: 2", report)
        self.assertIn("Токенов из кэша: 3", report)
        self.assertIn("Всего токенов: 19", report)
        self.assertIn("Шагов агента: 1", report)
        self.assertIn("[0][АГЕНТ] Шаг 1", report)
        self.assertIn("[1][РАЗМЫШЛЕНИЕ]\nПроверяю условие", report)
        self.assertIn("[2][ИНСТРУМЕНТ] read — completed\nПрочитан файл", report)
        cleaned_response = "Однозначный тестовый ответ\n\nВторая строка"
        self.assertIn(f"[3][ОТВЕТ]\n{cleaned_response}", report)
        self.assertIn(f"# ОТВЕТ МОДЕЛИ:\n{cleaned_response}\n", report)

    def test_lmstudio_flow_creates_expected_report(self):
        response = FakeSseResponse(
            [
                {"type": "chat.start", "model_instance_id": "test/lm-model"},
                {"type": "message.start"},
                {"type": "message.delta", "content": "Тестовый "},
                {"type": "message.delta", "content": "ответ"},
                {"type": "message.end"},
                {
                    "type": "chat.end",
                    "result": {
                        "output": [{"type": "message", "content": "Тестовый ответ"}],
                        "stats": {
                            "input_tokens": 12,
                            "total_output_tokens": 4,
                            "reasoning_output_tokens": 1,
                            "tokens_per_second": 8.5,
                            "time_to_first_token_seconds": 0.45,
                        },
                    },
                },
            ]
        )

        report = self.run_isolated(
            "3",
            patch.object(benchmark.urllib.request, "urlopen", return_value=response),
            [100.0, 101.0, 104.0],
        )

        self.assertIn("Источник: LM Test (локально)", report)
        self.assertIn("Модель: Test LM", report)
        self.assertIn("До первого токена: 0.45 сек", report)
        self.assertIn("Полное время: 4.00 сек", report)
        self.assertIn("Скорость генерации: 8.50 токен/сек", report)
        self.assertIn("Токенов в промпте: 12", report)
        self.assertIn("Сгенерировано токенов: 4", report)
        self.assertIn("Токенов размышления: 1", report)
        self.assertIn("# ОТВЕТ МОДЕЛИ:\nТестовый ответ\n", report)


class LmStudioPreparationTests(unittest.TestCase):
    model = {
        "source": "lmstudio",
        "name": "Selected Model",
        "full_name": "selected/model",
    }

    def test_keeps_selected_model_and_unloads_another(self):
        spinner = Mock()
        running = Mock(
            stdout=json.dumps(
                [
                    {"modelKey": "selected/model", "identifier": "selected/model"},
                    {"modelKey": "other/model", "identifier": "other-instance"},
                ]
            )
        )

        with patch.object(
            benchmark.subprocess, "run", side_effect=[running, Mock()]
        ) as run:
            benchmark.prepare_lmstudio_model(
                benchmark.PROVIDERS["lmstudio"], self.model, spinner
            )

        self.assertEqual(
            run.call_args_list,
            [
                call(
                    ["lms", "ps", "--json"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                ),
                call(["lms", "unload", "other-instance"], check=True),
            ],
        )
        spinner.write.assert_any_call("Выбранная модель уже загружена в память.")

    def test_loads_selected_model_when_not_running(self):
        spinner = Mock()
        running = Mock(stdout="[]")

        with patch.object(
            benchmark.subprocess, "run", side_effect=[running, Mock()]
        ) as run:
            benchmark.prepare_lmstudio_model(
                benchmark.PROVIDERS["lmstudio"], self.model, spinner
            )

        self.assertEqual(
            run.call_args_list[-1],
            call(["lms", "load", "selected/model", "-y"], check=True),
        )
        spinner.write.assert_any_call("Загружаю модель: Selected Model")


class LmStudioModelsTests(unittest.TestCase):
    def test_returns_only_llm_models(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "models": [
                        {
                            "type": "llm",
                            "key": "test/model",
                            "display_name": "Test Model",
                        },
                        {"type": "embedding", "key": "test/embedding"},
                    ]
                }
            ).encode("utf-8")
        )

        with patch.object(benchmark.urllib.request, "urlopen", return_value=response):
            found, models = benchmark.get_lmstudio_api_models(
                "lmstudio", benchmark.PROVIDERS["lmstudio"]
            )

        self.assertTrue(found)
        self.assertEqual(
            models,
            [
                {
                    "source": "lmstudio",
                    "name": "Test Model",
                    "full_name": "test/model",
                }
            ],
        )

class FormatNumberTests(unittest.TestCase):
    def test_none_returns_unavailable(self):
        self.assertEqual(benchmark.format_number(None), "недоступно")

    def test_formats_to_two_decimals(self):
        cases = [
            (0, "0.00"),
            (1.5, "1.50"),
            (2.345, "2.35"),
            (-0.554, "-0.55"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(benchmark.format_number(value), expected)


class FormatCountTests(unittest.TestCase):
    def test_none_returns_unavailable(self):
        self.assertEqual(benchmark.format_count(None), "недоступно")

    def test_converts_to_string(self):
        cases = [(0, "0"), (11, "11"), (1986, "1986")]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(benchmark.format_count(value), expected)


class CalculateRateTests(unittest.TestCase):
    def test_calculates_rate(self):
        self.assertEqual(benchmark.calculate_rate(120, 4), 30)

    def test_unavailable_without_count_or_time(self):
        for count, seconds in [(None, 1), (1, None), (0, 1), (1, 0)]:
            with self.subTest(count=count, seconds=seconds):
                self.assertIsNone(benchmark.calculate_rate(count, seconds))


class PrintResultTests(unittest.TestCase):
    def test_opencode_uses_agent_metric_labels(self):
        spinner = Mock()
        result = {
            "source": "opencode",
            "first_token_seconds": 2, "total_seconds": 10,
            "tokens_per_second": 5, "prompt_tokens": 20,
            "tokens_generated": 50, "reasoning_tokens": 3,
            "cache_read_tokens": 40, "total_tokens": 113,
            "agent_steps": 2,
        }

        benchmark.print_result(result, spinner)

        spinner.write.assert_any_call("До первого текста: 2.00 сек")
        spinner.write.assert_any_call(
            "Эффективная скорость агента: 5.00 токен/сек"
        )
        spinner.write.assert_any_call("Входных токенов без кэша: 20")

    def test_ollama_keeps_generation_metric_labels(self):
        spinner = Mock()
        result = {
            "source": "ollama",
            "first_token_seconds": 2, "total_seconds": 10,
            "tokens_per_second": 5, "prompt_tokens": 20,
            "tokens_generated": 50, "load_seconds": 1,
        }

        benchmark.print_result(result, spinner)

        spinner.write.assert_any_call("До первого токена: 2.00 сек")
        spinner.write.assert_any_call("Скорость генерации: 5.00 токен/сек")
        spinner.write.assert_any_call("Токенов в промпте: 20")


class FormatListNumberTests(unittest.TestCase):
    def test_keeps_plain_numbers_for_short_list(self):
        self.assertEqual(benchmark.format_list_number(1, 9), "1")

    def test_pads_numbers_for_long_list(self):
        cases = [(1, 10, "01"), (10, 10, "10"), (1, 100, "001")]
        for number, count, expected in cases:
            with self.subTest(number=number, count=count):
                self.assertEqual(
                    benchmark.format_list_number(number, count), expected
                )


class WriteModelGridTests(unittest.TestCase):
    def test_wraps_models_and_keeps_continuous_numbering(self):
        spinner = Mock()
        models = [{"name": name} for name in ("one", "two", "three")]

        with patch.object(
            benchmark.shutil, "get_terminal_size", return_value=Mock(columns=30)
        ):
            benchmark.write_model_grid(models, 8, 10, spinner)

        self.assertEqual(
            spinner.write.call_args_list,
            [call("08 - one      09 - two"), call("10 - three")],
        )


class ChooseNumberTests(unittest.TestCase):
    def test_accepts_leading_zero(self):
        spinner = Mock()
        cases = [("01", 0), ("00001", 0), ("005", 4)]

        for choice, expected in cases:
            with self.subTest(choice=choice):
                self.assertEqual(
                    benchmark.choose_number(5, choice, spinner), expected
                )
        spinner.write.assert_not_called()


class SourceNameTests(unittest.TestCase):
    def test_opencode(self):
        self.assertEqual(benchmark.source_name("opencode"), "OpenCode")

    def test_ollama(self):
        self.assertEqual(benchmark.source_name("ollama"), "Ollama")

    def test_unknown_source_keeps_identifier(self):
        self.assertEqual(benchmark.source_name("other"), "other")


class SafeFilenameTests(unittest.TestCase):
    def test_replaces_forbidden_characters(self):
        self.assertEqual(
            benchmark.safe_filename('a<>:"/\\|?*b'), "a---------b"
        )

    def test_keeps_allowed_characters(self):
        self.assertEqual(
            benchmark.safe_filename("gpt-5.6-sol_05 test"), "gpt-5.6-sol_05 test"
        )


class CleanBlockTests(unittest.TestCase):
    def test_strips_outer_empty_lines(self):
        self.assertEqual(benchmark.clean_block("\n  text  \n\n"), "  text  ")
        self.assertEqual(
            benchmark.clean_block("a\n  indented  \nb"), "a\n  indented  \nb"
        )

    def test_keeps_first_line_indentation(self):
        self.assertEqual(
            benchmark.clean_block(" \t\n\n    code\n    next\n \t\n"),
            "    code\n    next",
        )

    def test_empty_content(self):
        for text in ["", "\n\n", " \t\n \t"]:
            with self.subTest(text=text):
                self.assertEqual(benchmark.clean_block(text), "")

    def test_collapses_consecutive_empty_lines(self):
        self.assertEqual(
            benchmark.clean_block("a\n\n\nb\n\nc"), "a\n\nb\n\nc"
        )

    def test_keeps_single_empty_lines(self):
        self.assertEqual(benchmark.clean_block("a\n\nb"), "a\n\nb")

    def test_non_string_input(self):
        self.assertEqual(benchmark.clean_block(None), "None")
        self.assertEqual(benchmark.clean_block(123), "123")


class OpencodeTextTests(unittest.TestCase):
    def test_event_text_has_priority(self):
        event = {"text": "from event", "part": {"text": "from part"}}
        self.assertEqual(benchmark.opencode_text(event), "from event")

    def test_falls_back_to_part_text(self):
        event = {"part": {"text": "from part"}}
        self.assertEqual(benchmark.opencode_text(event), "from part")

    def test_missing_text_returns_empty_string(self):
        for event in [{}, {"part": {}}, {"text": "", "part": {"text": ""}}]:
            with self.subTest(event=event):
                self.assertEqual(benchmark.opencode_text(event), "")


class OpencodeTokensTests(unittest.TestCase):
    def test_event_tokens_have_priority(self):
        event = {"tokens": {"input": 1}, "part": {"tokens": {"input": 2}}}
        self.assertEqual(benchmark.opencode_tokens(event), {"input": 1})

    def test_falls_back_to_part_tokens(self):
        event = {"part": {"tokens": {"output": 5}}}
        self.assertEqual(benchmark.opencode_tokens(event), {"output": 5})

    def test_missing_tokens_return_empty_dict(self):
        for event in [{}, {"part": {}}]:
            with self.subTest(event=event):
                self.assertEqual(benchmark.opencode_tokens(event), {})


class AddOpencodeEventTests(unittest.TestCase):
    def test_header_only_without_content(self):
        event_log = []
        output = io.StringIO()
        with redirect_stdout(output):
            benchmark.add_opencode_event(event_log, "[АГЕНТ] Шаг 1")
        self.assertEqual(event_log, ["[АГЕНТ] Шаг 1"])
        self.assertEqual(output.getvalue(), "\n[АГЕНТ] Шаг 1\n")

    def test_header_with_cleaned_content(self):
        event_log = []
        output = io.StringIO()
        with redirect_stdout(output):
            benchmark.add_opencode_event(
                event_log, "[ОТВЕТ]", "a\n\n\nb\n"
            )
        self.assertEqual(event_log, ["[ОТВЕТ]\na\n\nb"])
        self.assertEqual(output.getvalue(), "\n[ОТВЕТ]\na\n\nb\n")


if __name__ == "__main__":
    unittest.main()
