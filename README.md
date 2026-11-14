# tritobol

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Multi-model compatible](https://img.shields.io/badge/Tokenizer-Multi--model%20compatible-6C5CE7)
![CLI app](https://img.shields.io/badge/Interface-CLI%20app-2D3436)
![Token and prompt optimizer](https://img.shields.io/badge/Tool-Token%20%26%20prompt%20optimizer-00B894)
![Build for the Future 2026 Hackathon](https://img.shields.io/badge/Build%20for%20the%20Future-2026%20Hackathon-F39C12)
![Built with heart while learning](https://img.shields.io/badge/Built%20with%20heart-While%20learning-E84393)

**trim + token + bolster** — a lightweight Python token preprocessor that removes
redundant prompt text and keeps the most recent context when an input is too
long.

`tritobol` does **not** summarize or rewrite your content. It removes repeated
material, whitespace noise, and decorative separators. It conservatively
compresses supported code/configuration blocks only when local validation
passes, and — only if a hard token budget is still exceeded — slides the window
forward so the newest tokens survive.

By default, token counts use the bundled **DeepSeek V4.1 Flash** tokenizer
(129,280-token vocabulary). To optimize for another model, load its compatible
tokenizer locally; the optimizer, trimming pipeline, and token-budget logic are
independent of any one provider.

## Install

From a local project checkout, install in editable mode and run `tritobol` with
no arguments in a terminal to start the guided workflow:

```bash
git clone https://github.com/memostudycode/tritobol.git
cd tritobol
python -m pip install -e .
tritobol
```

If the `tritobol` command is not recognized, start the same guide with
`python -m tritobol` from the project folder.

The guide asks for one UTF-8 text file, optionally asks for a maximum token
budget, and shows token counts plus a unified diff before saving. A budget may
discard the oldest text when the optimized result is still too long; a blank
budget keeps the normal no-hard-limit behavior. The suggested output is a
separate `*.optimized.*` file; Tritobol never overwrites the source and will
not replace an existing output. Saving requires an explicit confirmation.
The prompts are numbered: enter the text-file path, optionally enter a budget
(or press Enter for no limit), review the token counts and diff, then press
Enter to use the suggested output path and type `yes` to save.
Press Enter at the file prompt or use Ctrl+C/Ctrl+D (Ctrl+Z then Enter on
Windows) to cancel. The same flow can be started with `tritobol --interactive`.
When stdin is redirected, no-argument invocation continues to read the piped
text as before.

The only runtime dependency is [`tokenizers`](https://pypi.org/project/tokenizers/).
The tokenizer JSON is bundled with the package (about 6 MB); no model weights are
downloaded.

## Use another model's tokenizer

`HuggingFaceTokenizer` loads a local `tokenizer.json` supported by the
[`tokenizers`](https://pypi.org/project/tokenizers/) library. Supply a tokenizer
file that matches the model you intend to use; there is no automatic model-name
lookup or network download.

```python
from tritobol import HuggingFaceTokenizer, Tritobol

tokenizer = HuggingFaceTokenizer(
    "path/to/model/tokenizer.json",
    model_name="my-model",  # optional label for logs and inspection
)
tool = Tritobol(tokenizer=tokenizer)

result = tool.optimize(prompt, max_tokens=8192)
print(tool.count_tokens(prompt))  # counted with my-model's tokenizer
```

The CLI accepts the same local tokenizer file:

```bash
tritobol prompt.txt --tokenizer path/to/tokenizer.json --model-name my-model --max-tokens 8192
```

Applications can also provide a custom tokenizer object implementing
`count(text)` and `tail(text, max_tokens)`; `tail` should return a
`WindowResult`. Token counts cover the supplied text only. They do not include
provider-specific chat templates, message framing, tools, or API-side overhead.
Use a tokenizer compatible with the target model and account for those additional
inputs separately when enforcing a request's actual context limit.

## Code and configuration safety

The default strategy is `task_type="auto"`: code-like inputs use a more
conservative duplicate threshold, while long-form documents use a lower
threshold to remove more repeated prose. You can explicitly select
`"coding"` or `"document"` on `Tritobol.optimize()` or `optimize_text()`.

Fenced Python blocks longer than four non-empty lines have blank lines and
immediately repeated ordinary comment-only lines removed; unique explanatory
comments are kept. `# type:`, `# noqa`, `# pylint:`, and
`# pragma:` directives are retained. The candidate must pass Python's local
syntax compiler or that segment is restored. JSON blocks are compacted only
after a successful parse. YAML blocks are changed only when PyYAML is already
installed and both parsed values match; otherwise they remain unchanged.
Short snippets and unsupported languages remain protected. Repeated code blocks
are not deduplicated. A caller-supplied hard token limit may still truncate any
final output, so avoid setting one below the size needed for a complete code
segment.

Each `OptimizationResult` includes redaction-safe `segments` logs with status,
reason, and token counts. The CLI also supports a JSON report with
`--report report.json`.

## Important implementation sections

- `tritobol/core.py` contains the deterministic optimization pipeline, token
  statistics, segment logs, and the optional tail-window behavior.
- `tritobol/tokenizer.py` provides the bundled and local-tokenizer adapters;
  token counts are based on the configured tokenizer, not an estimate.
- `tritobol/batch.py` handles local files and project trees, validates
  supported code/configuration output, and writes to a separate destination.
- `tritobol/__main__.py` implements the CLI, including preview diffs and JSON
  reports.
- `benchmarks/run_benchmarks.py` contains fixed synthetic benchmark inputs and
  the calculations for token savings and designated-phrase retention.

## Sensitive values

Credential-shaped values such as common API-key/token assignments, recognizable
key prefixes, PEM private-key blocks, and explicit `CONFIDENTIAL:` or
`BEGIN/END CONFIDENTIAL` markers are scanned locally by default.
`sensitive_data="skip"` protects detected values from text normalization and
duplicate removal while leaving them unchanged in the output (unless a hard
token window later discards that part).
`sensitive_data="mask"` replaces detections with `[REDACTED]`; `"off"` disables
the scanner. This is a conservative pattern scanner, not a general detector of
confidential prose, and it is not a substitute for a dedicated secret scanner.
Sensitive values are never included in segment log details.

## Quick start

```python
from tritobol import Tritobol

tool = Tritobol()

raw = """
    The deployment checklist starts with a database backup.




    The deployment checklist starts with a database backup.

    After the backup, run the migrations and check the health endpoint.
"""

result = tool.optimize(raw, max_tokens=4096)

print(result.text)
print(result.stats.summary())
# tokens 36 -> 22 | saved 14 (38.9%) | chars 198 -> 124 | ...
```

`optimize()` always returns an `OptimizationResult` with:

| Field | Meaning |
| --- | --- |
| `result.text` | Cleaned and possibly windowed text |
| `result.stats.original_tokens` | Token count before optimization |
| `result.stats.optimized_tokens` | Token count after optimization |
| `result.stats.saved_tokens` | Absolute token reduction |
| `result.stats.saved_percent` | Reduction as a percentage |
| `result.stats.truncated` | Whether the sliding window ran |
| `result.warning` | The warning text, even if printing was disabled |

## How it works

tritobol normalizes text, removes redundant content, counts tokens with the
configured tokenizer, and keeps the newest context if the optional token budget
is exceeded. See the [runnable demo](examples/demo.py) for complete examples.
From the project root, run it with:

```bash
python examples/demo.py
```

## Sliding window for long texts

When the trimmed text is still longer than `max_tokens`, tritobol discards the
**earliest** tokens and keeps the **latest** context. It prints one clear
warning to stderr:

```text
WARNING: tritobol truncated the input because it exceeded max_tokens=80: kept the latest 80 tokens and discarded the earliest 619 tokens (input was 699 tokens).
```

```python
long_transcript = "\n\n".join(
    f"Section {i}: " + "detail " * 30 for i in range(20)
)

result = tool.optimize(long_transcript, max_tokens=80)
print(result.stats.truncated)       # True
print(result.stats.discarded_tokens)  # 619
print("Section 19" in result.text)  # True - newest context survives
print("Section 0" in result.text)   # False - oldest context was dropped
```

The cut is made at a tokenizer character offset, so the returned text is not
decoded through token IDs and does not acquire replacement characters.

To suppress the print while still receiving `result.warning`, pass
`warn_on_truncation=False`. To capture the warning yourself, pass a text stream
with `warning_stream=my_stream`.

## Roadmap

The current release focuses on local text cleanup, token counting, prompt
optimization, preview, and JSON reporting. Planned areas for future development
include:

- CLI conventions and machine-readable output suitable for standalone use and
  optional integration with the KeyShield workflow.
- More conservative code and security-audit handling, with tests for preserving
  identifiers, file paths, vulnerability descriptions, and key findings.
- Compression-risk assessment and rollback to the original input when a result
  fails validation or is judged too risky.
- Project-level caching and Markdown report export.
- Lower-friction installation across local machines, WSL, and CI, while being
  explicit that accurate model-specific token counts require the matching
  tokenizer.

These are goals, not features of the current release. Tritobol does not yet
provide risk-scored rollback, project caching, Markdown reports, or automatic
model/vocabulary selection. Review previews and test outputs before using
optimized text in security-sensitive workflows.

## Command line

For an interactive, single-file walkthrough, run `tritobol` with no arguments
in a terminal (or pass `--interactive`). It uses Tritobol's default tokenizer
and optimization settings, and does not set a token budget unless you enter
one in response to the optional prompt.

```bash
# Read a file, write optimized text to stdout, stats to stderr
tritobol prompt.txt

# Apply an 8,192-token budget and write to a file
tritobol prompt.txt --max-tokens 8192 -o optimized.txt

# Read from stdin
type prompt.txt | tritobol --max-tokens 4096

# Explicitly allow trimming inside fenced Markdown code blocks
tritobol prompt.txt --no-protect-code-blocks

# Process a project into a separate output directory, honoring .gitignore
tritobol . --output optimized --report optimization-report.json

# Explicitly mask detected credential-shaped values
tritobol prompt.txt --sensitive-data mask

# Preview the changes without writing an optimized file
tritobol prompt.txt --diff
```

If `-o` is omitted, only the optimized text goes to stdout. Warnings and token
statistics go to stderr, so shell pipelines remain clean.
`--diff` instead writes a unified diff to stdout and never writes an output
file; it accepts one file or stdin, and cannot be combined with `-o` or project
directory processing. Review the diff before explicitly running again with
`-o optimized.txt` to save a separate copy.

Project mode writes supported text/configuration files into a separate output
tree, copies unsupported files unchanged, skips symbolic links, and reports
per-file token savings and protected/compressed segments. Aggregate token
counts cover optimized supported text files; copied unsupported files are
listed as protected but are not token-counted. Report paths are project-relative
to avoid including the user's full local filesystem path. The sensitive scanner
applies only to files that are optimized. It recognizes common
`.gitignore` globs, directory patterns, negation, and nested ignore files; it
does not claim complete parity with every Git ignore edge case. The processing
is local and makes no network requests. Supported optimization file types are
Markdown/plain-text documents, Python, JSON, and YAML. YAML validation is
available only when PyYAML is already installed; Tritobol does not install or
download it automatically.

## What gets trimmed

The default pipeline is deterministic and conservative:

1. **Fenced Markdown code blocks** — short snippets and unsupported languages
   are preserved; supported Python and JSON blocks are selectively compressed
   and parsed before acceptance. A hard token budget can still truncate final
   text; disable code handling with `Tritobol(protect_code_blocks=False)` or
   `--no-protect-code-blocks`.
2. **Invisible characters** — BOM, zero-width characters, and control bytes in
   prose.
3. **HTML comments** — `<!-- ... -->` blocks in prose.
4. **Whitespace noise** — indentation, trailing spaces, and repeated blank lines
   in prose.
5. **Decorative separators** — lines made only of `=`, `-`, `*`, `_`, `#`, etc.
6. **Duplicate paragraphs** — exact repeats after whitespace/case normalization.
7. **Duplicate lines** — repeated substantive lines; the first occurrence wins.
8. **Duplicate sentences** — repeated sentences, including inside paragraphs.
9. **Sliding window** — only when `max_tokens` is supplied and still exceeded.

Short strings are protected from duplicate removal. The default threshold is
24 characters for coding-oriented input and 12 for document-oriented input; you
can explicitly adjust the base threshold:

```python
tool = Tritobol(min_duplicate_chars=40)
```

Because only redundant material is removed, savings depend on the input. Noisy
prompts may save more than already-clean prose, which may save nothing. The
included synthetic benchmark gives reproducible measurements for its fixed
examples; those results should not be generalized to arbitrary prompts or
treated as a semantic-quality guarantee. A hard `max_tokens` budget can
produce a larger reduction by discarding earlier context.

## Reproducible benchmark

Run the bundled local benchmark from the project root:

```bash
python -m benchmarks.run_benchmarks
python -m benchmarks.run_benchmarks --json
```

It uses three fixed, synthetic examples and the bundled DeepSeek V4.1 Flash
tokenizer, with no model/API calls and no hard token budget. For each example
and in aggregate it reports original and optimized token counts, saved tokens
and percentage, plus retention of explicitly listed phrases. Phrase retention
is a literal substring check, not an assessment of meaning, factual accuracy,
or model performance. This small fixture suite is useful for detecting
behavior changes against stable examples; it is not a representative corpus or
a claim about real-world savings or information preservation.

## API surface

```python
from tritobol import (
    DeepSeekTokenizer,
    HuggingFaceTokenizer,
    Tritobol,
    optimize_text,
)

tool = Tritobol()

tool.count_tokens(text)              # exact count for the configured tokenizer
tool.trim(text)                      # redundancy removal only
tool.fit_window(text, max_tokens)    # sliding window only
tool.optimize(text, max_tokens=None) # trim + optional window + stats

optimize_text(text, max_tokens=1024) # convenience wrapper

# Existing DeepSeekTokenizer remains available; HuggingFaceTokenizer accepts
# another compatible local tokenizer.json.
other_tool = Tritobol(
    tokenizer=HuggingFaceTokenizer("path/to/tokenizer.json")
)
```

Process a project tree locally from Python:

```python
from pathlib import Path
from tritobol import process_path

report = process_path(
    "my-project",
    "optimized-project",
    respect_gitignore=True,
    task_type="auto",
    sensitive_data="skip",
)
print(report.summary())
report.write_json(Path("optimization-report.json"))
```

## Tests

```bash
python -m unittest discover -s tests -v
```

The test cases print original token count, optimized token count, and saved
percentage for each scenario:

```text
[low noise / whitespace] original=45 optimized=39 saved=13.3%
[duplicate paragraphs] original=112 optimized=62 saved=44.6%
[high noise / repeated blocks] original=180 optimized=42 saved=76.7%
[long text / sliding window] original=700 optimized=80 saved=88.6%
```

A runnable demonstration is also included:

```bash
python examples/demo.py
```

## Bundled tokenizer provenance

The bundled file is `tokenizer.json` from the official
[`deepseek-ai/DeepSeek-V4.1-Flash`](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash)
checkpoint:

- Vocabulary: 129,280 tokens
- License: MIT, Copyright (c) 2023 DeepSeek

See `tritobol/data/README.md` and `tritobol/data/LICENSE.deepseek-tokenizer` for
details.

## Analysis & details

Please click [project_overview](PROJECT_OVERVIEW.md) for analyses & details.

## License

The tritobol source is MIT licensed. The bundled tokenizer retains DeepSeek's
MIT license notice.

## Web application (local UI)

A local-first browser interface lives in `tritobol_app/`. On Windows, double-click `start.bat` (needs Python 3.10+).
Everything runs on your computer; the optimizer engine above is unchanged. Prompt text is saved in browser-local history only when you choose **Save to history** and confirm; it is not encrypted by Tritobol or synced to other devices. See [`docs/APPLICATION.md`](docs/APPLICATION.md).
