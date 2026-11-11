"""Command-line interface for tritobol.

Examples
--------
    python -m tritobol prompt.txt
    python -m tritobol prompt.txt --max-tokens 4096 -o optimized.txt
    type prompt.txt | python -m tritobol --max-tokens 1024
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .batch import process_path
from .core import Tritobol
from .tokenizer import HuggingFaceTokenizer


def _guided_workflow() -> int:
    """Run a local, confirmation-based workflow for one UTF-8 text file."""
    print("Tritobol guided mode (text files only; processing stays on this machine).")
    try:
        source_value = input("Text file path (or blank to cancel): ").strip()
        if not source_value:
            print("Cancelled.")
            return 0

        source = Path(source_value).expanduser().resolve()
        if not source.is_file():
            print(f"tritobol: error: not a file: {source}", file=sys.stderr)
            return 1
        text = source.read_text(encoding="utf-8")

        budget_value = input(
            "Optional maximum token budget (may discard oldest text; Enter to skip): "
        ).strip()
        if budget_value:
            try:
                max_tokens = int(budget_value)
            except ValueError:
                print(
                    "tritobol: error: token budget must be a positive integer.",
                    file=sys.stderr,
                )
                return 1
            if max_tokens <= 0:
                print(
                    "tritobol: error: token budget must be a positive integer.",
                    file=sys.stderr,
                )
                return 1
        else:
            max_tokens = None

        result = Tritobol().optimize(text, max_tokens=max_tokens)
        print(
            f"\nTokens: {result.stats.original_tokens:,} -> "
            f"{result.stats.optimized_tokens:,} "
            f"({result.stats.saved_tokens:,} saved, "
            f"{result.stats.saved_percent:.1f}%)."
        )
        diff = difflib.unified_diff(
            text.splitlines(keepends=True),
            result.text.splitlines(keepends=True),
            fromfile=str(source),
            tofile=f"{source} (optimized preview)",
        )
        print("\nPreview (unified diff; no files have been changed):")
        preview = "".join(diff)
        print(preview if preview else "(No text changes.)")

        default_output = source.with_name(f"{source.stem}.optimized{source.suffix}")
        output_value = input(
            f"Save to a separate file [{default_output}]: "
        ).strip()
        destination = Path(output_value).expanduser() if output_value else default_output
        destination = destination.resolve()
        if destination == source:
            print(
                "tritobol: error: output must not overwrite the source file.",
                file=sys.stderr,
            )
            return 1
        if destination.exists():
            print(f"tritobol: error: output already exists: {destination}", file=sys.stderr)
            return 1

        confirmation = input(f"Save optimized text to {destination}? [y/N]: ").strip().lower()
        if confirmation not in {"y", "yes"}:
            print("Cancelled; no output file was written.")
            return 0

        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="") as stream:
            stream.write(result.text)
        print(f"Saved optimized text to {destination}")
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"tritobol: error: {exc}", file=sys.stderr)
        return 1


def _read_input(path: Optional[str]) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tritobol",
        description=(
            "Trim redundant text and keep the latest context within a "
            "token budget using the selected tokenizer."
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="UTF-8 input file; omit or use '-' to read stdin",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="start the guided single-text-file workflow",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="write optimized text to this file instead of stdout",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="show a unified diff instead of optimized text; does not write output",
    )
    parser.add_argument(
        "-m",
        "--max-tokens",
        type=int,
        default=None,
        metavar="N",
        help="hard token limit; keeps the newest N tokens when needed",
    )
    parser.add_argument(
        "--tokenizer",
        metavar="JSON",
        help="local Hugging Face tokenizer.json; defaults to the bundled DeepSeek tokenizer",
    )
    parser.add_argument(
        "--model-name",
        metavar="NAME",
        help="label for the custom tokenizer (defaults to its filename)",
    )
    parser.add_argument(
        "--no-protect-code-blocks",
        action="store_true",
        help="allow trimming inside fenced Markdown code blocks",
    )
    parser.add_argument(
        "--task-type",
        choices=("auto", "coding", "document"),
        default="auto",
        help="compression strategy; auto selects conservative coding or document mode",
    )
    parser.add_argument(
        "--sensitive-data",
        choices=("skip", "mask", "off"),
        default="skip",
        help="locally protect credential-shaped values, mask them, or disable scanning",
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="do not apply .gitignore patterns during project processing",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="process only the top-level files in a project directory",
    )
    parser.add_argument(
        "--report",
        metavar="JSON",
        help="write detailed per-file and segment logs to a JSON report",
    )
    parser.add_argument(
        "--no-warn",
        action="store_true",
        help="do not print the sliding-window truncation warning",
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="do not print token statistics to stderr",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    command_line = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(command_line)
    if args.interactive or (not command_line and sys.stdin.isatty()):
        if args.input is not None:
            print("tritobol: error: --interactive cannot be combined with an input path.", file=sys.stderr)
            return 1
        if (
            args.output
            or args.diff
            or args.max_tokens is not None
            or args.tokenizer
            or args.model_name
            or args.no_protect_code_blocks
            or args.task_type != "auto"
            or args.sensitive_data != "skip"
            or args.no_gitignore
            or args.no_recursive
            or args.report
            or args.no_warn
            or args.no_stats
        ):
            print("tritobol: error: --interactive cannot be combined with file-processing options.", file=sys.stderr)
            return 1
        return _guided_workflow()

    try:
        if args.diff and args.output:
            raise ValueError("--diff cannot be combined with --output")
        if args.input not in {None, "-"} and Path(args.input).is_dir():
            if args.diff:
                raise ValueError("--diff supports a single input file or stdin, not a project directory")
            if not args.output:
                raise ValueError(
                    "project processing requires -o/--output to select a separate output directory"
                )
            if args.model_name and not args.tokenizer:
                raise ValueError("--model-name requires --tokenizer")
            tokenizer = (
                HuggingFaceTokenizer(args.tokenizer, model_name=args.model_name)
                if args.tokenizer
                else None
            )
            report = process_path(
                args.input,
                args.output,
                recursive=not args.no_recursive,
                respect_gitignore=not args.no_gitignore,
                tokenizer=tokenizer,
                task_type=args.task_type,
                sensitive_data=args.sensitive_data,
                max_tokens=args.max_tokens,
                protect_code_blocks=not args.no_protect_code_blocks,
                warn_on_truncation=not args.no_warn,
            )
            print(report.summary(), file=sys.stderr)
            for item in report.items:
                print(
                    f"{item.status}: {item.source} -> {item.output} "
                    f"({item.original_tokens:,} -> {item.optimized_tokens:,} tokens, "
                    f"{item.saved_percent:.1f}% saved)"
                    + (f" | {item.error}" if item.error else ""),
                    file=sys.stderr,
                )
                for segment in item.logs:
                    print(
                        f"  segment {segment.kind}: {segment.status} | {segment.detail}",
                        file=sys.stderr,
                    )
            if args.report:
                report.write_json(Path(args.report))
            return 1 if report.failed_files else 0

        text = _read_input(args.input)
        if args.model_name and not args.tokenizer:
            raise ValueError("--model-name requires --tokenizer")
        tokenizer = (
            HuggingFaceTokenizer(args.tokenizer, model_name=args.model_name)
            if args.tokenizer
            else None
        )
        result = Tritobol(
            tokenizer=tokenizer,
            protect_code_blocks=not args.no_protect_code_blocks,
            task_type=args.task_type,
            sensitive_data=args.sensitive_data,
        ).optimize(
            text,
            max_tokens=args.max_tokens,
            warn_on_truncation=not args.no_warn,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(f"tritobol: error: {exc}", file=sys.stderr)
        return 1

    if not args.no_stats:
        print(result.stats.summary(), file=sys.stderr)
        for segment in result.segments:
            print(
                f"segment {segment.kind}: {segment.status} — {segment.detail}",
                file=sys.stderr,
            )

    if args.report:
        report_data = {
            "original_tokens": result.stats.original_tokens,
            "optimized_tokens": result.stats.optimized_tokens,
            "saved_tokens": result.stats.saved_tokens,
            "saved_percent": result.stats.saved_percent,
            "segments": [asdict(segment) for segment in result.segments],
        }
        try:
            Path(args.report).write_text(
                json.dumps(report_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"tritobol: error: could not write report: {exc}", file=sys.stderr)
            return 1

    if args.diff:
        source_name = args.input if args.input not in {None, "-"} else "stdin"
        diff = difflib.unified_diff(
            text.splitlines(keepends=True),
            result.text.splitlines(keepends=True),
            fromfile=source_name,
            tofile=f"{source_name} (optimized)",
        )
        sys.stdout.writelines(diff)
    elif args.output:
        try:
            Path(args.output).write_text(result.text, encoding="utf-8")
        except OSError as exc:
            print(f"tritobol: error: could not write output: {exc}", file=sys.stderr)
            return 1
        if not args.no_stats:
            print(f"wrote {args.output}", file=sys.stderr)
    else:
        # Keep stdout clean for pipelines; warnings and stats go to stderr.
        sys.stdout.write(result.text)
        if result.text and not result.text.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
