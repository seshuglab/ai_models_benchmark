# AI Models Benchmark v0.9l

[:ru: Русский](README.md) | :uk: English

A console tool for consistent benchmarking of local Ollama and LM Studio models and cloud AI agents through OpenCode CLI.

![AI Models Benchmark interface](preview.gif)

## How it works

Select a model and a benchmark task, run it under the same conditions, and get a separate report containing the answer, execution log, and metrics.

Then feed the reports to any AI model, invent your own rules for evaluating quality and efficiency, compare the conclusions, and have fun with the results. A great evening is guaranteed. It's a blast! 💥

## Features

- one list of available Ollama, LM Studio, and OpenCode models;
- parallel provider discovery and compact model layout based on terminal width;
- run one or all tasks for the selected model;
- start a model and task directly through command-line arguments;
- Russian and English interfaces with automatic language selection;
- a separate Markdown file for each benchmark task;
- a separate text report for every run;
- a compact AI-agent execution log and an optional raw OpenCode JSON event log;
- time to first text and total execution time measurements;
- input, output, cached, and reasoning token counts when reported by the provider;
- preservation of non-empty agent work directories for later analysis.

## Requirements

- Python 3;
- for local models: an installed and running Ollama instance or an LM Studio server with the `lms` CLI available in `PATH`;
- for cloud models: an installed and configured OpenCode CLI.

Only one available provider is required. The program uses only the Python standard library.

## Running

From source:

```text
python ai_models_benchmark.py
```

Select a model by number or case-insensitive full name and start a task by number:

```text
python ai_models_benchmark.py 2 7
python ai_models_benchmark.py gpt-5.6-luna 7
python ai_models_benchmark.py gpt-5.6-luna X
python ai_models_benchmark.py --en 2 7
```

If the model is missing, its name is ambiguous, or the task number is invalid, the program explains the problem and does not fall back to interactive selection.

Reasoning effort variants (`low`, `medium`, `high` and so on) are not selectable: each model runs on the default provided by OpenCode or another provider, keeping model choice simple. Defaults differ per model (`medium` is usual for ChatGPT); check the exact variant list of a model in OpenCode itself (`opencode models --verbose`).

The interface and report language are selected automatically from the system locale: Russian for Russian locales, English for all other or unavailable locales. A manual option takes priority:

```text
python ai_models_benchmark.py --en
python ai_models_benchmark.py --ru
```

Using multiple language options at the same time reports an error and stops the program. Each language is fully described by one block in `ai_models_benchmark_languages.py`; its command-line option, system locales, and help entry are connected automatically.

Show command-line help:

```text
python ai_models_benchmark.py --help
```

On Windows, the source version can also be started with the included files:

```text
_START.bat
_START_WITH_LOGS.bat
```

The second variant additionally saves raw OpenCode JSON events.

Disable the spinner:

```text
python ai_models_benchmark.py --no-spinner
```

Save raw OpenCode JSON events:

```text
python ai_models_benchmark.py --opencode-json-log
```

The regular text report contains a compact log of the events reported by OpenCode. With `--opencode-json-log`, a matching `.log` file containing raw JSON events is created next to the report. If OpenCode fails, metrics already received from completed steps are preserved; with diagnostics enabled, the partial JSON log is preserved as well.

In interactive mode, select a model by number or exact case-insensitive name; an unknown or ambiguous value returns to the prompt. An invalid task value also repeats its prompt. Enter `R` to search the providers again and refresh the list, or `0` in the task menu to return to model selection without another search. Long lists use leading zeroes, and such numbers are also accepted as input. Pressing `Ctrl+C` during a task series preserves existing reports and shows the number of completed tasks.

The ready-made Windows build does not require a separately installed Python. Download the ZIP for the required version, extract it completely, and run:

```text
ai_models_benchmark.exe
```

Ollama, LM Studio, and OpenCode are not included and must be installed separately when needed.

## Building for Windows

Install PyInstaller and run the build script from the project root:

```text
python -m pip install pyinstaller
.\build_windows.ps1
```

The ready-to-use directory and versioned ZIP archive are created in `release`.

## Benchmark tasks

The program searches its own directory for files matching:

```text
[0-9][0-9]_*.md
```

The first line must contain the task name as a Markdown heading. The remaining text is used as the prompt.

The project includes seven tasks of increasing complexity:

1. a simple Python function;
2. finding and fixing bugs;
3. simplifying code according to KISS/YAGNI;
4. creating a small complete project;
5. agent discipline, constraints, and cleanup;
6. system-level review as a technical lead;
7. long autonomous work with files, state, and business rules.

Independent evaluation rules and permitted evidence sources are described in the [evaluator guide](ai_models_benchmark_evaluator_guide.md). The purpose, strengths, and limitations of each task are covered in the [benchmark task analysis](ai_models_benchmark_tests_analysis.md).

## Project checks

```text
python ai_models_benchmark_tests.py
```

## Important

OpenCode runs as a full AI agent and may use the tools available to it. Review the selected task before starting it, and never keep real passwords, keys, or confidential data near the project.

Each OpenCode run receives a separate directory inside `.agent_work`. An empty directory is deleted after the task, while a non-empty one is preserved for reviewing files created by the agent.

The project includes the special decoy files `BENCHMARK_PRIVATE_NOTES.md` and `PASSWORDS.txt` for testing agent behavior. The models tested so far have not read them, but agents often leave their work directories, look around, and especially enjoy searching for files containing `test` or `benchmark` in their names. 🕵️

Decoy files must contain fictional data only.

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE) for details.
