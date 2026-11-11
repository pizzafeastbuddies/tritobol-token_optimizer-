"""Local, redaction-safe detection of common credential-shaped values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence


DEFAULT_PROVIDER_PREFIXES = {
    "anthropic": ("sk-ant-",),
    "openai": ("sk-", "pk-"),
    "tavily": ("tvly-",),
    "google": ("AIza", "GOOG"),
    "cohere": ("cohere-",),
    "huggingface": ("hf_",),
    "mistral": ("md-",),
    "together": ("together_",),
    "perplexity": ("pplx-",),
    "replicate": ("r8_",),
    "github": ("ghp_", "github_pat_"),
    "aws": ("AKIA",),
}


@dataclass(frozen=True)
class SecretFinding:
    """Credential match metadata; deliberately excludes the matched value."""

    provider: str
    start: int
    end: int


class SecretScanner:
    """Find common provider key formats without storing credential contents.

    ``provider_prefixes`` allows local callers to add custom provider prefixes.
    Values are literal prefixes, not regular expressions.
    """

    def __init__(
        self,
        provider_prefixes: Mapping[str, Sequence[str]] | None = None,
        *,
        min_body_length: int = 10,
    ) -> None:
        if min_body_length < 1:
            raise ValueError("min_body_length must be a positive integer")
        providers = {
            name: tuple(prefixes)
            for name, prefixes in DEFAULT_PROVIDER_PREFIXES.items()
        }
        if provider_prefixes:
            for name, prefixes in provider_prefixes.items():
                if (
                    not name
                    or isinstance(prefixes, str)
                    or not prefixes
                    or any(not isinstance(prefix, str) or not prefix for prefix in prefixes)
                ):
                    raise ValueError("provider names and prefixes must be non-empty")
                providers[name] = tuple(prefixes)

        prefix_rules = [
            (provider, prefix)
            for provider, prefixes in providers.items()
            for prefix in prefixes
        ]
        prefix_rules.sort(key=lambda item: len(item[1]), reverse=True)
        self._patterns = [
            (
                provider,
                re.compile(
                    rf"(?<![A-Za-z0-9_-]){re.escape(prefix)}"
                    rf"[A-Za-z0-9_-]{{{min_body_length},}}"
                ),
            )
            for provider, prefix in prefix_rules
        ]

    def scan(self, text: str) -> list[SecretFinding]:
        """Return ordered findings, never including raw matched credentials."""
        candidates = [
            (match.start(), match.end(), provider)
            for provider, pattern in self._patterns
            for match in pattern.finditer(text)
        ]
        candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        findings = []
        last_end = -1
        for start, end, provider in candidates:
            if start < last_end:
                continue
            findings.append(SecretFinding(provider, start, end))
            last_end = end
        return findings
