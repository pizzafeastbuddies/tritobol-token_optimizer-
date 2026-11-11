"""Tokenizer adapters and token-budget helpers.

The bundled DeepSeek tokenizer remains the default. Other Hugging Face
``tokenizer.json`` files can be loaded locally for model-specific token counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Optional, Protocol, Union

try:
    from tokenizers import Tokenizer as HFTokenizer
except ImportError as exc:  # pragma: no cover - only hit without dependencies
    raise ImportError(
        "tritobol requires the 'tokenizers' package. "
        "Install it with: pip install tokenizers"
    ) from exc


TOKENIZER_FILENAME = "deepseek_v41_tokenizer.json"


class Tokenizer(Protocol):
    """Interface required by :class:`tritobol.Tritobol`."""

    def count(self, text: str) -> int: ...

    def tail(self, text: str, max_tokens: int) -> "WindowResult": ...


@dataclass(frozen=True)
class WindowResult:
    """The result of fitting a text into a token budget."""

    text: str
    original_tokens: int
    kept_tokens: int
    discarded_tokens: int
    truncated: bool
    max_tokens: int

    @property
    def warning(self) -> Optional[str]:
        """A human-readable warning, or ``None`` when no truncation occurred."""
        if not self.truncated:
            return None
        return (
            "tritobol truncated the input because it exceeded "
            f"max_tokens={self.max_tokens:,}: kept the latest "
            f"{self.kept_tokens:,} tokens and discarded the earliest "
            f"{self.discarded_tokens:,} tokens (input was "
            f"{self.original_tokens:,} tokens)."
        )


class HuggingFaceTokenizer:
    """Load a compatible Hugging Face tokenizer JSON from a local file.

    Token counts are exact for the supplied tokenizer. No model is downloaded,
    and no provider-specific chat template or request overhead is included.
    """

    def __init__(
        self,
        tokenizer_path: Union[str, Path],
        *,
        model_name: Optional[str] = None,
    ) -> None:
        self.model_name = model_name or Path(tokenizer_path).stem
        self._tokenizer = HFTokenizer.from_file(str(tokenizer_path))

    @property
    def vocab_size(self) -> int:
        """Number of tokens in the vocabulary, including added special tokens."""
        return self._tokenizer.get_vocab_size(with_added_tokens=True)

    def encode(self, text: str):
        """Encode text without adding sentence-boundary special tokens."""
        return self._tokenizer.encode(text, add_special_tokens=False)

    def count(self, text: str) -> int:
        """Return the exact number of tokens in ``text``."""
        return len(self.encode(text).ids)

    def tail(self, text: str, max_tokens: int) -> WindowResult:
        """Keep the newest ``max_tokens`` tokens instead of the oldest ones.

        Character offsets from the tokenizer are used to cut the original text
        at a token boundary.  That keeps the returned text byte-for-byte intact
        (no decoded replacement characters) and avoids re-tokenization noise at
        the new start of the string.
        """
        if max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")

        encoding = self.encode(text)
        total_tokens = len(encoding.ids)
        if total_tokens <= max_tokens:
            return WindowResult(
                text=text,
                original_tokens=total_tokens,
                kept_tokens=total_tokens,
                discarded_tokens=0,
                truncated=False,
                max_tokens=max_tokens,
            )

        # Start with the last max_tokens tokens.  Re-encoding the resulting
        # character suffix can occasionally produce a token or two more because
        # of a BPE merge at the boundary.  If that happens, move the boundary
        # forward with a binary search until the suffix respects the budget.
        first_candidate = total_tokens - max_tokens

        def suffix_at(token_index: int) -> str:
            start_char = encoding.offsets[token_index][0]
            return text[start_char:]

        candidate = suffix_at(first_candidate)
        kept_tokens = self.count(candidate)

        if kept_tokens > max_tokens:
            low, high = first_candidate + 1, total_tokens - 1
            while low < high:
                middle = (low + high) // 2
                if self.count(suffix_at(middle)) <= max_tokens:
                    high = middle
                else:
                    low = middle + 1
            candidate = suffix_at(low)
            kept_tokens = self.count(candidate)
        else:
            # Keep the largest possible suffix.  Try earlier boundaries when a
            # merge allows more than max_tokens tokens to fit.
            low, high = first_candidate, total_tokens - 1
            best_text = candidate
            while low <= high:
                middle = (low + high) // 2
                middle_text = suffix_at(middle)
                middle_count = self.count(middle_text)
                if middle_count <= max_tokens:
                    best_text = middle_text
                    high = middle - 1
                else:
                    low = middle + 1
            candidate = best_text
            kept_tokens = self.count(candidate)

        return WindowResult(
            text=candidate,
            original_tokens=total_tokens,
            kept_tokens=kept_tokens,
            discarded_tokens=max(0, total_tokens - kept_tokens),
            truncated=True,
            max_tokens=max_tokens,
        )


class DeepSeekTokenizer(HuggingFaceTokenizer):
    """Backwards-compatible adapter for the bundled DeepSeek V4.1 tokenizer."""

    model_name = "deepseek-v4.1-flash"

    def __init__(self, tokenizer_path: Optional[Union[str, Path]] = None) -> None:
        if tokenizer_path is None:
            tokenizer_path = resources.files("tritobol").joinpath(
                "data", TOKENIZER_FILENAME
            )
        super().__init__(tokenizer_path, model_name=self.model_name)


@lru_cache(maxsize=1)
def get_default_tokenizer() -> DeepSeekTokenizer:
    """Load the bundled tokenizer once and reuse it across calls."""
    return DeepSeekTokenizer()
