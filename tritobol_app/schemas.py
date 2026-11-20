"""Request validation and structured application errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

MAX_INPUT_BYTES = 2 * 1024 * 1024  # 2 MB of UTF-8 text
MAX_TOKENIZER_BYTES = 25 * 1024 * 1024  # 25 MB tokenizer.json
MAX_BUDGET = 100_000_000
TASK_TYPES = ("auto", "coding", "document")
SENSITIVE_MODES = ("skip", "mask", "off")


class AppError(Exception):
    """An error that maps to a structured JSON response."""

    def __init__(
        self, code: str, message: str, *, field: Optional[str] = None, status: int = 400
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.status = status

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "error": {"code": self.code, "message": self.message, "field": self.field},
        }


@dataclass(frozen=True)
class OptimizeRequest:
    text: str
    tokenizer_id: str
    max_tokens: Optional[int]
    task_type: str
    sensitive_data: str
    protect_code_blocks: bool


def parse_budget(value: Any) -> Optional[int]:
    """Return a positive int budget or None. Rejects zero, negatives and non-integers."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    if isinstance(value, bool):
        raise AppError("budget_error", "Token budget must be a whole number.", field="max_tokens")
    if isinstance(value, float):
        if not value.is_integer():
            raise AppError("budget_error", "Token budget must be a whole number.", field="max_tokens")
        value = int(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("_", "")
        if not text.lstrip("-").isdigit():
            raise AppError("budget_error", "Token budget must be a whole number.", field="max_tokens")
        value = int(text)
    if not isinstance(value, int):
        raise AppError("budget_error", "Token budget must be a whole number.", field="max_tokens")
    if value < 1:
        raise AppError(
            "budget_error",
            "Token budget must be a positive whole number (1 or more). Leave it empty for no budget.",
            field="max_tokens",
        )
    if value > MAX_BUDGET:
        raise AppError("budget_error", f"Token budget must be at most {MAX_BUDGET:,}.", field="max_tokens")
    return value


def parse_optimize_request(payload: Any) -> OptimizeRequest:
    if not isinstance(payload, Mapping):
        raise AppError("validation_error", "Request body must be a JSON object.")
    text = payload.get("text")
    if not isinstance(text, str):
        raise AppError("validation_error", "'text' must be a string.", field="text")
    size = len(text.encode("utf-8", errors="surrogatepass"))
    if size > MAX_INPUT_BYTES:
        raise AppError(
            "input_too_large",
            f"Input is {size / 1024 / 1024:.2f} MB; the limit is "
            f"{MAX_INPUT_BYTES // (1024 * 1024)} MB. Shorten the text or split it.",
            field="text",
            status=413,
        )
    if text.strip() == "":
        raise AppError("validation_error", "Input is empty. Paste or load some text first.", field="text")

    tokenizer_id = payload.get("tokenizer", "deepseek-v4.1-flash")
    if not isinstance(tokenizer_id, str) or not tokenizer_id:
        raise AppError("validation_error", "'tokenizer' must be a tokenizer id.", field="tokenizer")

    task_type = payload.get("task_type", "auto")
    if task_type not in TASK_TYPES:
        raise AppError("validation_error", f"task_type must be one of {', '.join(TASK_TYPES)}.", field="task_type")
    sensitive = payload.get("sensitive_data", "skip")
    if sensitive not in SENSITIVE_MODES:
        raise AppError(
            "validation_error", f"sensitive_data must be one of {', '.join(SENSITIVE_MODES)}.", field="sensitive_data"
        )
    protect = payload.get("protect_code_blocks", True)
    if not isinstance(protect, bool):
        raise AppError("validation_error", "protect_code_blocks must be true or false.", field="protect_code_blocks")

    return OptimizeRequest(
        text=text,
        tokenizer_id=tokenizer_id,
        max_tokens=parse_budget(payload.get("max_tokens")),
        task_type=task_type,
        sensitive_data=sensitive,
        protect_code_blocks=protect,
    )
