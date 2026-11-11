"""Local multi-file and project processing."""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from .core import SegmentLog, Tritobol
from .tokenizer import Tokenizer


_DOCUMENT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".adoc"}
_CONFIG_LANGUAGES = {".json": "json", ".yaml": "yaml", ".yml": "yaml"}
_SUPPORTED_SUFFIXES = _DOCUMENT_SUFFIXES | set(_CONFIG_LANGUAGES) | {".py"}
_ALWAYS_IGNORED_DIRS = {".git"}


@dataclass(frozen=True)
class FileReport:
    """Processing outcome for one project file."""

    source: str
    output: str
    status: str
    original_tokens: int = 0
    optimized_tokens: int = 0
    saved_percent: float = 0.0
    logs: Tuple[SegmentLog, ...] = ()
    error: Optional[str] = None

    @property
    def saved_tokens(self) -> int:
        return self.original_tokens - self.optimized_tokens

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "output": self.output,
            "status": self.status,
            "original_tokens": self.original_tokens,
            "optimized_tokens": self.optimized_tokens,
            "saved_tokens": self.saved_tokens,
            "saved_percent": self.saved_percent,
            "logs": [asdict(log) for log in self.logs],
            "error": self.error,
        }


@dataclass(frozen=True)
class BatchReport:
    """Aggregate and per-file details for a local batch run."""

    input_path: str
    output_path: str
    items: Tuple[FileReport, ...] = field(default_factory=tuple)

    @property
    def original_tokens(self) -> int:
        return sum(item.original_tokens for item in self.items)

    @property
    def optimized_tokens(self) -> int:
        return sum(item.optimized_tokens for item in self.items)

    @property
    def saved_tokens(self) -> int:
        return self.original_tokens - self.optimized_tokens

    @property
    def saved_percent(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return (
            (self.original_tokens - self.optimized_tokens)
            / self.original_tokens
            * 100.0
        )

    @property
    def failed_files(self) -> int:
        return sum(item.status == "failed" for item in self.items)

    @property
    def processed_files(self) -> int:
        return sum(item.status in {"processed", "protected"} for item in self.items)

    def summary(self) -> str:
        return (
            f"files {self.processed_files} processed, {self.failed_files} failed | "
            f"tokens {self.original_tokens:,} -> {self.optimized_tokens:,} | "
            f"saved {self.saved_percent:.1f}%"
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "original_tokens": self.original_tokens,
            "optimized_tokens": self.optimized_tokens,
            "saved_tokens": self.saved_tokens,
            "saved_percent": self.saved_percent,
            "items": [item.to_dict() for item in self.items],
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def process_path(
    input_path: str | Path,
    output_path: str | Path,
    *,
    recursive: bool = True,
    respect_gitignore: bool = True,
    tokenizer: Optional[Tokenizer] = None,
    task_type: Literal["auto", "coding", "document"] = "auto",
    sensitive_data: Literal["skip", "mask", "off"] = "skip",
    max_tokens: Optional[int] = None,
    protect_code_blocks: bool = True,
    warn_on_truncation: bool = True,
) -> BatchReport:
    """Optimize one supported text file or a local project tree.

    Project traversal and filtering are entirely local. The output tree mirrors
    the input's relative paths. Unsupported file types are copied unchanged and
    reported as protected; files are never overwritten in place.
    """
    source = Path(input_path).resolve()
    destination = Path(output_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"input path does not exist: {source}")
    if source.is_dir():
        if source == destination:
            raise ValueError("output_path must differ from the input project directory")
        if _is_within(source, destination):
            raise ValueError("output_path cannot be an ancestor of the input project")
        destination.mkdir(parents=True, exist_ok=True)
        files = _project_files(source, destination, recursive, respect_gitignore)
    elif source.is_file():
        files = [(source, source.name, [])]
        if destination.exists() and destination.is_dir():
            destination = destination / source.name
    else:
        raise ValueError("input_path must be a regular file or directory")

    optimizer = Tritobol(
        tokenizer=tokenizer,
        task_type=task_type,
        sensitive_data=sensitive_data,
        protect_code_blocks=protect_code_blocks,
    )
    reports: List[FileReport] = []
    for file_path, relative, _rules in files:
        target = destination / relative if source.is_dir() else destination
        source_label = relative
        output_label = relative if source.is_dir() else destination.name
        if source.is_dir() and target.resolve() == file_path.resolve():
            reports.append(
                FileReport(
                    source=source_label,
                    output=output_label,
                    status="skipped",
                    error="Output is inside source tree; skipped to prevent reprocessing.",
                )
            )
            continue
        if file_path.is_symlink():
            reports.append(
                FileReport(
                    source=source_label,
                    output=output_label,
                    status="skipped",
                    error="Symbolic link skipped to keep project processing within the selected tree.",
                )
            )
            continue
        suffix = file_path.suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file_path, target)
                reports.append(
                    FileReport(
                        source=source_label,
                        output=output_label,
                        status="protected",
                        logs=(
                            SegmentLog(
                                kind="file",
                                status="protected",
                                detail="Unsupported file type copied without optimization.",
                            ),
                        ),
                    )
                )
            except OSError as exc:
                reports.append(
                    FileReport(
                        source=source_label,
                        output=output_label,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc.strerror or 'file copy failed'}",
                    )
                )
            continue
        try:
            raw = file_path.read_text(encoding="utf-8")
            language = _CONFIG_LANGUAGES.get(suffix)
            if suffix == ".py":
                language = "python"
            if language:
                wrapped = _wrap_code(raw, language)
                result = optimizer.optimize(
                    wrapped,
                    max_tokens=max_tokens,
                    warn_on_truncation=warn_on_truncation,
                )
                optimized = _unwrap_code(result.text, language, raw)
                if result.stats.truncated:
                    optimized = raw
                    result_segments = tuple(result.segments) + (
                        SegmentLog(
                            kind="code",
                            status="rollback",
                            detail=(
                                "Token budget would cut source/configuration; original file restored."
                            ),
                            original_tokens=optimizer.count_tokens(raw),
                            optimized_tokens=optimizer.count_tokens(raw),
                        ),
                    )
                elif not _validate_source(language, optimized):
                    optimized = raw
                    result_segments = tuple(result.segments) + (
                        SegmentLog(
                            kind="code",
                            status="rollback",
                            detail=(
                                "Post-optimization validation failed; original file restored."
                            ),
                            original_tokens=optimizer.count_tokens(raw),
                            optimized_tokens=optimizer.count_tokens(raw),
                        ),
                    )
                else:
                    result_segments = tuple(result.segments)
            else:
                result = optimizer.optimize(
                    raw,
                    max_tokens=max_tokens,
                    warn_on_truncation=warn_on_truncation,
                )
                optimized = result.text
                result_segments = tuple(result.segments)
            _atomic_write(target, optimized)
            original_tokens = optimizer.count_tokens(raw)
            optimized_tokens = optimizer.count_tokens(optimized)
            logs = result_segments or (
                SegmentLog(
                    kind="prose",
                    status="compressed" if optimized != raw else "protected",
                    detail="Text optimized." if optimized != raw else "No changes required.",
                    original_tokens=original_tokens,
                    optimized_tokens=optimized_tokens,
                ),
            )
            reports.append(
                FileReport(
                    source=source_label,
                    output=output_label,
                    status="processed",
                    original_tokens=original_tokens,
                    optimized_tokens=optimized_tokens,
                    saved_percent=_saved_percent(original_tokens, optimized_tokens),
                    logs=tuple(logs),
                )
            )
        except (OSError, UnicodeError, ValueError) as exc:
            reports.append(
                FileReport(
                    source=source_label,
                    output=output_label,
                    status="failed",
                    error=f"{type(exc).__name__}: file processing failed",
                )
            )

    return BatchReport(
        input_path=source.name,
        output_path=destination.name,
        items=tuple(reports),
    )


def _project_files(
    root: Path,
    output_root: Path,
    recursive: bool,
    respect_gitignore: bool,
) -> List[Tuple[Path, str, List[Tuple[Path, str]]]]:
    result = []
    for current, dirs, filenames in os.walk(root, topdown=True):
        current_path = Path(current)
        if not recursive and current_path != root:
            dirs[:] = []
            continue
        dirs[:] = [
            name
            for name in dirs
            if name not in _ALWAYS_IGNORED_DIRS
            and not (current_path / name).is_symlink()
            and not _is_within((current_path / name).resolve(), output_root)
        ]
        rules = _gitignore_rules(root, current_path) if respect_gitignore else []
        kept_dirs = []
        for name in dirs:
            directory = current_path / name
            relative = directory.relative_to(root).as_posix()
            if respect_gitignore and _is_ignored(relative, True, rules, root):
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs

        for name in filenames:
            path = current_path / name
            if name == ".gitignore" or _is_within(path.resolve(), output_root):
                continue
            relative = path.relative_to(root).as_posix()
            if respect_gitignore and _is_ignored(relative, False, rules, root):
                continue
            result.append((path, relative, rules))
    return result


def _gitignore_rules(root: Path, directory: Path) -> List[Tuple[Path, str]]:
    ancestors = [directory, *directory.parents]
    relevant = [path for path in reversed(ancestors) if _is_within(path, root)]
    rules: List[Tuple[Path, str]] = []
    for base in relevant:
        ignore_file = base / ".gitignore"
        try:
            lines = ignore_file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            pattern = line.strip()
            if not pattern or pattern.startswith("#"):
                continue
            rules.append((base, pattern))
    return rules


def _is_ignored(
    relative_path: str,
    is_directory: bool,
    rules: Sequence[Tuple[Path, str]],
    root: Path,
) -> bool:
    ignored = False
    relative = Path(relative_path)
    for base, raw_pattern in rules:
        negated = raw_pattern.startswith("!")
        pattern = raw_pattern[1:] if negated else raw_pattern
        if not pattern:
            continue
        anchored = pattern.startswith("/")
        base_relative = base.relative_to(root)
        try:
            path_from_base = relative.relative_to(base_relative)
        except ValueError:
            continue
        candidate = path_from_base.as_posix()
        directory_only = pattern.endswith("/")
        pattern = pattern.lstrip("/").rstrip("/")
        prefixes = candidate.split("/")
        candidates = ["/".join(prefixes[:index]) for index in range(1, len(prefixes) + 1)]
        if not candidates:
            continue
        matched = False
        for prefix in candidates:
            if directory_only and prefix == candidate and not is_directory:
                continue
            if "/" in pattern or anchored:
                matched = fnmatch.fnmatchcase(prefix, pattern)
            else:
                matched = any(
                    fnmatch.fnmatchcase(part, pattern)
                    for part in prefix.split("/")
                )
            if matched:
                break
        if matched:
            ignored = not negated
    return ignored


def _wrap_code(text: str, language: str) -> str:
    if text.endswith(("\n", "\r")):
        return f"```{language}\n{text}```"
    return f"```{language}\n{text}\n```"


def _unwrap_code(text: str, language: str, original: str) -> str:
    prefix = f"```{language}\n"
    suffix = "```"
    if not text.startswith(prefix) or not text.endswith(suffix):
        return original
    content = text[len(prefix):-len(suffix)]
    if not original.endswith(("\n", "\r")) and content.endswith("\n"):
        content = content[:-1]
    return content


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(text)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _saved_percent(original_tokens: int, optimized_tokens: int) -> float:
    if original_tokens == 0:
        return 0.0
    return (original_tokens - optimized_tokens) / original_tokens * 100.0


def _validate_source(language: str, text: str) -> bool:
    if language == "python":
        try:
            compile(text, "<tritobol>", "exec")
        except SyntaxError:
            return False
    elif language == "json":
        try:
            json.loads(text)
        except json.JSONDecodeError:
            return False
    elif language == "yaml":
        try:
            import yaml
        except ImportError:
            return True
        try:
            yaml.safe_load(text)
        except yaml.YAMLError:
            return False
    return True
