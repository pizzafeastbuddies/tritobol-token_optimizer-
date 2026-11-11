"""Core text-trimming and sliding-window logic for tritobol."""

from __future__ import annotations

import io
import json
import re
import sys
import tokenize
import unicodedata
from dataclasses import dataclass
from typing import List, Literal, Optional, TextIO, Tuple

from .secrets import SecretScanner
from .tokenizer import Tokenizer, WindowResult, get_default_tokenizer


# Characters that are invisible in most editors and almost always noise in a
# prompt.  They are removed before token counting.
_INVISIBLE_CHARS = dict.fromkeys(
    [
        0x200B,  # zero width space
        0x200C,  # zero width non-joiner
        0x200D,  # zero width joiner
        0x200E,  # left-to-right mark
        0x200F,  # right-to-left mark
        0x202A,  # left-to-right embedding
        0x202B,  # right-to-left embedding
        0x202C,  # pop directional formatting
        0x202D,  # left-to-right override
        0x202E,  # right-to-left override
        0x2060,  # word joiner
        0xFEFF,  # byte-order mark / zero width no-break space
    ]
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_INLINE_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_SEPARATOR_RE = re.compile(r"^[=\-*_~#+<>]{8,}$")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$", re.MULTILINE)
_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]\s+|\d{1,3}[.)]\s+|#{1,6}\s+|>\s*)+")
# Split after sentence punctuation when the next character starts a new
# sentence.  Joining the pieces with "" preserves the original spacing.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])(?=\s|[A-Z\u4e00-\u9fff])")


def _strict_json_loads(value: str):
    """Parse JSON without silently accepting duplicate keys or non-finite values."""
    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    def reject_constant(constant: str):
        raise ValueError(f"non-standard JSON constant: {constant}")

    return json.loads(
        value,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )


@dataclass(frozen=True)
class TrimStats:
    """Counts collected while removing redundant material."""

    removed_paragraphs: int = 0
    removed_lines: int = 0
    removed_sentences: int = 0
    removed_separators: int = 0


@dataclass(frozen=True)
class SegmentLog:
    """A redaction-safe record of how one input segment was handled."""

    kind: str
    status: str
    detail: str
    original_tokens: int = 0
    optimized_tokens: int = 0
    provider: Optional[str] = None


@dataclass(frozen=True)
class OptimizationStats:
    """Token and character savings for one ``optimize`` call."""

    original_tokens: int
    optimized_tokens: int
    original_chars: int
    optimized_chars: int
    removed_paragraphs: int
    removed_lines: int
    removed_sentences: int
    removed_separators: int
    truncated: bool
    discarded_tokens: int

    @property
    def saved_tokens(self) -> int:
        return self.original_tokens - self.optimized_tokens

    @property
    def removed_chars(self) -> int:
        return self.original_chars - self.optimized_chars

    @property
    def saved_percent(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return self.saved_tokens / self.original_tokens * 100.0

    def summary(self) -> str:
        """Return a compact, human-readable one-line report."""
        parts = [
            f"tokens {self.original_tokens:,} -> {self.optimized_tokens:,}",
            f"saved {self.saved_tokens:,} ({self.saved_percent:.1f}%)",
            f"chars {self.original_chars:,} -> {self.optimized_chars:,}",
        ]
        duplicates = (
            self.removed_paragraphs
            + self.removed_lines
            + self.removed_sentences
            + self.removed_separators
        )
        if duplicates:
            parts.append(
                "removed "
                f"{self.removed_paragraphs} paragraph(s), "
                f"{self.removed_lines} line(s), "
                f"{self.removed_sentences} sentence(s), "
                f"{self.removed_separators} separator(s)"
            )
        if self.truncated:
            parts.append(
                f"window kept the latest tokens and discarded {self.discarded_tokens:,}"
            )
        return " | ".join(parts)


@dataclass(frozen=True)
class OptimizationResult:
    """The optimized text, its statistics, and any truncation warning."""

    text: str
    stats: OptimizationStats
    warning: Optional[str] = None
    segments: Tuple[SegmentLog, ...] = ()

    def __str__(self) -> str:
        return self.text


class Tritobol:
    """Trim redundant text and fit long inputs into a token budget.

    Parameters
    ----------
    tokenizer:
        A tokenizer implementing ``count(text)`` and ``tail(text, max_tokens)``.
        The bundled DeepSeek V4.1 Flash tokenizer is used by default.
    min_duplicate_chars:
        Only repeated paragraphs, lines, and sentences at least this long are
        treated as duplicate noise.  This protects short labels and bullets.
    remove_html_comments:
        Remove ``<!-- ... -->`` blocks, which are normally not meant for the
        model.
    protect_code_blocks:
        Recognize fenced Markdown code blocks and selectively compress only
        supported, validated Python and JSON segments.
    task_type:
        ``"auto"`` selects conservative coding behavior for code-like content
        and more aggressive document behavior for plain prose.
    sensitive_data:
        ``"skip"`` preserves credential-shaped values, ``"mask"`` replaces
        them with ``[REDACTED]``, and ``"off"`` disables local scanning.
    """

    def __init__(
        self,
        tokenizer: Optional[Tokenizer] = None,
        *,
        min_duplicate_chars: int = 24,
        remove_html_comments: bool = True,
        protect_code_blocks: bool = True,
        task_type: Literal["auto", "coding", "document"] = "auto",
        sensitive_data: Literal["skip", "mask", "off"] = "skip",
        secret_scanner: Optional[SecretScanner] = None,
    ) -> None:
        if min_duplicate_chars < 1:
            raise ValueError("min_duplicate_chars must be a positive integer")
        if task_type not in {"auto", "coding", "document"}:
            raise ValueError("task_type must be 'auto', 'coding', or 'document'")
        if sensitive_data not in {"skip", "mask", "off"}:
            raise ValueError("sensitive_data must be 'skip', 'mask', or 'off'")
        self.tokenizer = (
            tokenizer if tokenizer is not None else get_default_tokenizer()
        )
        self.min_duplicate_chars = min_duplicate_chars
        self.remove_html_comments = remove_html_comments
        self.protect_code_blocks = protect_code_blocks
        self.task_type = task_type
        self.sensitive_data = sensitive_data
        self.secret_scanner = secret_scanner or SecretScanner()

    def count_tokens(self, text: str) -> int:
        """Count tokens with the configured tokenizer."""
        return self.tokenizer.count(text)

    def trim(self, text: str) -> str:
        """Remove redundant whitespace, separators, and repeated content."""
        return self._trim(text, self._resolve_task_type(text))[0]

    def fit_window(self, text: str, max_tokens: int) -> WindowResult:
        """Keep the newest context when ``text`` exceeds ``max_tokens``.

        This method only performs the sliding-window step; use
        :meth:`optimize` to trim redundancy first and emit a warning.
        """
        return self.tokenizer.tail(text, max_tokens)

    def optimize(
        self,
        text: str,
        max_tokens: Optional[int] = None,
        *,
        warn_on_truncation: bool = True,
        warning_stream: Optional[TextIO] = None,
        task_type: Optional[Literal["auto", "coding", "document"]] = None,
    ) -> OptimizationResult:
        """Trim redundancy, then apply a token-budget sliding window.

        Parameters
        ----------
        text:
            Raw input text.
        max_tokens:
            Optional hard limit.  If the trimmed text is still too long, the
            earliest tokens are discarded and the newest context is kept.
        warn_on_truncation:
            Print a warning to ``warning_stream`` when the window drops content.
        warning_stream:
            Destination for the warning; defaults to ``sys.stderr``.
        task_type:
            Override the instance strategy for this call. ``"auto"`` uses
            lightweight local syntax cues; no network classifier is used.

        Returns
        -------
        OptimizationResult
            ``result.text`` is the optimized text and ``result.stats`` contains
            the original/optimized token counts and saved percentage.
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if max_tokens is not None and max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")
        if task_type is not None and task_type not in {"auto", "coding", "document"}:
            raise ValueError("task_type must be 'auto', 'coding', or 'document'")

        original_tokens = self.count_tokens(text)
        original_chars = len(text)

        resolved_task_type = self._resolve_task_type(text, task_type)
        trimmed_text, trim_stats, segment_logs = self._trim(text, resolved_task_type)

        window: Optional[WindowResult] = None
        if max_tokens is not None:
            window = self.tokenizer.tail(trimmed_text, max_tokens)
            final_text = window.text
            optimized_tokens = window.kept_tokens
        else:
            final_text = trimmed_text
            optimized_tokens = self.count_tokens(final_text)

        warning = window.warning if window is not None else None
        if warning and warn_on_truncation:
            stream = warning_stream if warning_stream is not None else sys.stderr
            print(f"WARNING: {warning}", file=stream)

        stats = OptimizationStats(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            original_chars=original_chars,
            optimized_chars=len(final_text),
            removed_paragraphs=trim_stats.removed_paragraphs,
            removed_lines=trim_stats.removed_lines,
            removed_sentences=trim_stats.removed_sentences,
            removed_separators=trim_stats.removed_separators,
            truncated=bool(window and window.truncated),
            discarded_tokens=window.discarded_tokens if window else 0,
        )
        return OptimizationResult(
            text=final_text,
            stats=stats,
            warning=warning,
            segments=tuple(segment_logs),
        )

    def _trim(
        self,
        text: str,
        task_type: Optional[str] = None,
    ) -> Tuple[str, TrimStats, List[SegmentLog]]:
        """Internal trimming pipeline.  Returns text and removal counts."""
        segment_logs: List[SegmentLog] = []
        text, sensitive_values = self._handle_sensitive_data(
            text,
            segment_logs,
        )
        protected_blocks: List[Tuple[str, str]] = []
        if self.protect_code_blocks:
            text = self._protect_fenced_code_blocks(
                text,
                protected_blocks,
                segment_logs,
            )
        prose_before = text
        text = self._normalize_text(text)
        if not text:
            return "", TrimStats(), segment_logs

        # 1. Drop decorative separator lines.  Markdown front-matter markers
        #    (---) are shorter than the threshold and therefore preserved.
        kept_lines: List[str] = []
        removed_separators = 0
        for line in text.split("\n"):
            if _SEPARATOR_RE.match(line):
                removed_separators += 1
                continue
            kept_lines.append(line)
        text = "\n".join(kept_lines)

        duplicate_threshold = self.min_duplicate_chars
        if task_type == "document":
            duplicate_threshold = min(duplicate_threshold, 12)

        # 2. Remove exact duplicate paragraphs, keeping their first occurrence.
        paragraphs = self._split_paragraphs(text)
        unique_paragraphs: List[str] = []
        seen_paragraphs = set()
        removed_paragraphs = 0
        for paragraph in paragraphs:
            key = self._canonical(paragraph)
            if len(key) >= duplicate_threshold and key in seen_paragraphs:
                removed_paragraphs += 1
                continue
            seen_paragraphs.add(key)
            unique_paragraphs.append(paragraph)

        # 3. Remove repeated lines across the remaining paragraphs.  Keeping the
        #    first occurrence preserves document order and the original wording.
        seen_lines = set()
        deduped_paragraphs: List[str] = []
        removed_lines = 0
        for paragraph in unique_paragraphs:
            lines: List[str] = []
            for line in paragraph.split("\n"):
                key = self._canonical(line, strip_list_prefix=True)
                if len(key) >= duplicate_threshold and key in seen_lines:
                    removed_lines += 1
                    continue
                seen_lines.add(key)
                lines.append(line)
            paragraph = "\n".join(lines).strip()
            if paragraph:
                deduped_paragraphs.append(paragraph)

        # 4. Remove repeated sentences, including sentences inside a paragraph
        #    that differ only in surrounding formatting.
        seen_sentences = set()
        cleaned_paragraphs: List[str] = []
        removed_sentences = 0
        for paragraph in deduped_paragraphs:
            sentences = _SENTENCE_SPLIT_RE.split(paragraph)
            kept_sentences: List[str] = []
            for sentence in sentences:
                key = self._canonical(sentence)
                if len(key) >= duplicate_threshold and key in seen_sentences:
                    removed_sentences += 1
                    continue
                seen_sentences.add(key)
                kept_sentences.append(sentence)
            paragraph = "".join(kept_sentences).strip()
            if paragraph:
                cleaned_paragraphs.append(paragraph)

        cleaned = "\n\n".join(cleaned_paragraphs)
        if cleaned != prose_before:
            segment_logs.append(
                SegmentLog(
                    kind="prose",
                    status="compressed",
                    detail="Normalized text and removed configured redundant material.",
                    original_tokens=self.count_tokens(prose_before),
                    optimized_tokens=self.count_tokens(cleaned),
                )
            )
        else:
            segment_logs.append(
                SegmentLog(
                    kind="prose",
                    status="protected",
                    detail="No configured redundant material was found.",
                    original_tokens=self.count_tokens(prose_before),
                    optimized_tokens=self.count_tokens(cleaned),
                )
            )
        for marker, optimized in protected_blocks:
            cleaned = cleaned.replace(marker, optimized)
        for marker, value in sensitive_values:
            cleaned = cleaned.replace(marker, value)
        return cleaned, TrimStats(
            removed_paragraphs=removed_paragraphs,
            removed_lines=removed_lines,
            removed_sentences=removed_sentences,
            removed_separators=removed_separators,
        ), segment_logs

    def _protect_fenced_code_blocks(
        self,
        text: str,
        protected_blocks: List[Tuple[str, str]],
        segment_logs: List[SegmentLog],
    ) -> str:
        """Compress supported fenced code, validate it, then shield it from prose cleanup."""
        lines = text.splitlines(keepends=True)
        spans: List[Tuple[int, int]] = []
        active_start: Optional[int] = None
        active_fence: Optional[str] = None
        active_length = 0
        offset = 0

        for line in lines:
            content = line.rstrip("\r\n")
            if active_start is None:
                match = _FENCE_OPEN_RE.match(content)
                if match:
                    fence = match.group(1)
                    info = match.group(2)
                    if fence[0] != "`" or "`" not in info:
                        active_start = offset
                        active_fence = fence[0]
                        active_length = len(fence)
            elif re.fullmatch(
                rf" {{0,3}}{re.escape(active_fence or '')}"
                rf"{{{active_length},}}[ \t]*",
                content,
            ):
                spans.append((active_start, offset + len(line)))
                active_start = None
                active_fence = None
                active_length = 0
            offset += len(line)

        if active_start is not None:
            spans.append((active_start, len(text)))

        block_logs: List[Tuple[int, SegmentLog]] = []
        for index, (start, end) in reversed(list(enumerate(spans))):
            marker = f"TRITOBOLPROTECTEDCODEBLOCK{index}END"
            while marker in text:
                marker = "_" + marker
            original = text[start:end]
            optimized, status, detail = self._compress_fenced_block(
                original,
            )
            protected_blocks.append((marker, optimized))
            block_logs.append(
                (
                    start,
                    SegmentLog(
                        kind="code",
                        status=status,
                        detail=detail,
                        original_tokens=self.count_tokens(original),
                        optimized_tokens=self.count_tokens(optimized),
                    ),
                )
            )
            text = text[:start] + marker + text[end:]

        segment_logs.extend(log for _, log in sorted(block_logs, key=lambda item: item[0]))
        return text

    def _compress_fenced_block(
        self,
        block: str,
    ) -> Tuple[str, str, str]:
        """Apply narrowly scoped compression and rollback invalid candidates."""
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)\r?\n", block)
        if opening is None:
            return block, "protected", "Unrecognized fenced block format."
        fence, info = opening.groups()
        closing_start = block.rfind(fence[0] * len(fence))
        if closing_start < opening.end():
            return block, "protected", "Unclosed code fence."

        language = info.strip().split(maxsplit=1)[0].lower() if info.strip() else ""
        body = block[opening.end():closing_start]
        code_lines = sum(bool(line.strip()) for line in body.splitlines())

        candidate = body
        validator = None
        if language in {"json", "jsonc"}:
            if language == "jsonc":
                return block, "protected", "JSONC comments are preserved without an optional parser."
            try:
                candidate = json.dumps(
                    _strict_json_loads(body),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                validator = _strict_json_loads
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                return block, "rollback", (
                    f"JSON parsing failed ({type(exc).__name__}); original segment restored."
                )
        elif language in {"yaml", "yml"}:
            try:
                import yaml
            except ImportError:
                return block, "protected", (
                    "YAML parser unavailable; install PyYAML to validate compression."
                )
            try:
                original_data = yaml.safe_load(body)
                candidate = "\n".join(
                    line
                    for line in body.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                )
                validator = lambda value: yaml.safe_load(value)
                if validator(candidate) != original_data:
                    return block, "rollback", (
                        "YAML data changed during compression; original segment restored."
                    )
            except yaml.YAMLError as exc:
                return block, "rollback", (
                    f"YAML parsing failed ({type(exc).__name__}); original segment restored."
                )
        elif language in {"python", "py", "python3"}:
            if code_lines <= 4:
                return block, "protected", "Short Python snippet kept unchanged."
            try:
                candidate = self._compress_python_body(body)
                validator = lambda value: compile(
                    value,
                    "<tritobol>",
                    "exec",
                )
            except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
                return block, "rollback", (
                    f"Python tokenization failed ({type(exc).__name__}); "
                    "original segment restored."
                )
        else:
            return block, "protected", "No safe local compressor/parser for this language."

        try:
            validator(candidate)
        except (SyntaxError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return block, "rollback", (
                f"Validation failed ({type(exc).__name__}); original segment restored."
            )

        if body.endswith(("\n", "\r")) and not candidate.endswith(("\n", "\r")):
            candidate += "\n"
        result = block[:opening.end()] + candidate + block[closing_start:]
        if result == block:
            return block, "protected", "Validated segment needed no compression."
        return result, "compressed", "Compressed and validated locally."

    @staticmethod
    def _compress_python_body(body: str) -> str:
        """Drop blank and ordinary comment-only lines without touching code tokens."""
        try:
            tokens = tokenize.generate_tokens(io.StringIO(body).readline)
            comment_lines = {}
            string_lines = set()
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    comment = token.string.lstrip("# ").lower()
                    if token.string.startswith("#!") or comment.startswith(
                        (
                            "type:",
                            "noqa",
                            "pylint:",
                            "pragma:",
                            "pyright:",
                            "mypy:",
                            "ruff:",
                            "isort:",
                            "fmt:",
                            "-*- coding:",
                            "coding:",
                            "coding=",
                            "nosec",
                            "coverage:",
                            "cython:",
                        )
                    ):
                        continue
                    comment_lines[token.start[0]] = token.string
                elif token.type == tokenize.STRING:
                    string_lines.update(
                        range(token.start[0], token.end[0] + 1)
                    )
        except (tokenize.TokenError, IndentationError):
            raise

        kept_lines = []
        previous_comment = None
        for number, line in enumerate(body.splitlines(), start=1):
            if number in comment_lines and line.lstrip().startswith("#"):
                comment = comment_lines[number].lstrip("#").strip().casefold()
                if comment == previous_comment:
                    continue
                kept_lines.append(line)
                previous_comment = comment
                continue
            if not line.strip() and number not in string_lines:
                previous_comment = None
                continue
            kept_lines.append(line)
            previous_comment = None
        candidate = "\n".join(kept_lines)
        if body.endswith(("\n", "\r")):
            candidate += "\n"
        return candidate

    def _handle_sensitive_data(
        self,
        text: str,
        segment_logs: List[SegmentLog],
    ) -> Tuple[str, List[Tuple[str, str]]]:
        """Locally protect common credential-shaped values without logging them."""
        if self.sensitive_data == "off":
            return text, []

        patterns = (
            re.compile(
                r"""(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|"""
                r"""client[_-]?secret|password|passwd|secret)\b"""
                r"""(\s*[:=]\s*)(['"]?)([^\s'"`]{12,})(\3)"""
            ),
            re.compile(
                r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
                r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                re.DOTALL,
            ),
            re.compile(r"(?is)BEGIN CONFIDENTIAL\b.*?END CONFIDENTIAL\b"),
            re.compile(
                r"(?im)^.{0,80}(?:CONFIDENTIAL|INTERNAL ONLY|DO NOT DISTRIBUTE)"
                r"\s*:\s*.+$"
            ),
        )
        sensitive_values: List[Tuple[str, str]] = []
        matches = []
        provider_findings = self.secret_scanner.scan(text)
        for pattern in patterns:
            for match in pattern.finditer(text):
                provider = next(
                    (
                        finding.provider
                        for finding in provider_findings
                        if match.start() <= finding.start
                        and finding.end <= match.end()
                    ),
                    "sensitive",
                )
                matches.append((match.start(), match.end(), provider, match, None))
        matches.extend(
            (finding.start, finding.end, finding.provider, None, None)
            for finding in provider_findings
        )
        matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        non_overlapping = []
        last_end = -1
        for start, end, provider, match, value in matches:
            if start < last_end:
                continue
            non_overlapping.append((start, end, provider, match, value))
            last_end = end

        for index, (start, end, provider, match, _) in reversed(
            list(enumerate(non_overlapping))
        ):
            matched_text = text[start:end]
            value = (
                match.group(4)
                if match is not None and match.lastindex and match.lastindex >= 4
                else matched_text
            )
            if self.sensitive_data == "mask":
                replacement = matched_text.replace(value, "[REDACTED]")
                text = text[:start] + replacement + text[end:]
                optimized_segment = replacement
            else:
                marker = f"TRITOBOLSENSITIVEVALUE{index}END"
                while marker in text:
                    marker = "_" + marker
                sensitive_values.append((marker, value))
                text = text[:start] + matched_text.replace(value, marker) + text[end:]
                optimized_segment = matched_text
            segment_logs.append(
                SegmentLog(
                    kind="sensitive",
                    status="masked" if self.sensitive_data == "mask" else "protected",
                    detail="Sensitive pattern detected; matched content omitted from logs.",
                    original_tokens=self.count_tokens(matched_text),
                    optimized_tokens=self.count_tokens(optimized_segment),
                    provider=provider,
                )
            )
        return text, sensitive_values

    def _resolve_task_type(
        self,
        text: str,
        task_type: Optional[str] = None,
    ) -> str:
        selected = task_type or self.task_type
        if selected != "auto":
            return selected
        if _FENCE_OPEN_RE.search(text) or re.search(
            r"(?m)^\s*(?:def |class |import |from |function |const |let |var )",
            text,
        ):
            return "coding"
        return "document"

    def _normalize_text(self, text: str) -> str:
        """Normalize newlines, strip invisible characters, and tidy lines."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.translate(_INVISIBLE_CHARS)
        if self.remove_html_comments:
            text = _HTML_COMMENT_RE.sub(" ", text)
        text = _CONTROL_RE.sub("", text)

        lines: List[str] = []
        for raw_line in text.split("\n"):
            line = _INLINE_WHITESPACE_RE.sub(" ", raw_line).strip()
            if line:
                lines.append(line)
            elif lines and lines[-1] != "":
                # Collapse any run of blank lines into a single paragraph break.
                lines.append("")

        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    def _canonical(self, text: str, *, strip_list_prefix: bool = False) -> str:
        """Create a comparison key without changing the text that is kept."""
        value = unicodedata.normalize("NFKC", text)
        if strip_list_prefix:
            value = _LIST_PREFIX_RE.sub("", value)
        return re.sub(r"\s+", " ", value).strip().casefold()

    @staticmethod
    def _split_paragraphs(text: str) -> List[str]:
        """Split on blank lines and discard empty blocks."""
        return [part.strip() for part in text.split("\n\n") if part.strip()]


def optimize_text(
    text: str,
    max_tokens: Optional[int] = None,
    *,
    warn_on_truncation: bool = True,
    tokenizer: Optional[Tokenizer] = None,
    task_type: Optional[Literal["auto", "coding", "document"]] = None,
) -> OptimizationResult:
    """Convenience wrapper around :meth:`Tritobol.optimize`."""
    return Tritobol(tokenizer=tokenizer).optimize(
        text,
        max_tokens=max_tokens,
        warn_on_truncation=warn_on_truncation,
        task_type=task_type,
    )
