"""Application service: validate -> call the existing tritobol engine -> shape a JSON result.

No optimization logic lives here. All trimming, duplicate removal, secret handling, token counting
and windowing is performed by :class:`tritobol.Tritobol`.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict
from pathlib import PurePath
from typing import Any, Dict, List, Tuple

from tritobol import HuggingFaceTokenizer, Tritobol, __version__ as ENGINE_VERSION
from tritobol.tokenizer import BudgetTooSmallError, get_default_tokenizer

from .diffing import build_diff
from .schemas import MAX_TOKENIZER_BYTES, AppError, OptimizeRequest

BUNDLED_ID = "deepseek-v4.1-flash"
BUNDLED_LABEL = "DeepSeek V4.1 Flash (bundled)"
MAX_CUSTOM_TOKENIZERS = 3


class TokenizerRegistry:
    """The bundled tokenizer plus tokenizers the user uploaded in this session (memory only)."""

    def __init__(self, max_custom: int = MAX_CUSTOM_TOKENIZERS) -> None:
        self._custom: "OrderedDict[str, Tuple[HuggingFaceTokenizer, str]]" = OrderedDict()
        self._max_custom = max_custom
        self._lock = threading.Lock()

    def _bundled_entry(self) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "id": BUNDLED_ID, "label": BUNDLED_LABEL, "kind": "bundled",
            "available": True, "vocab_size": None, "error": None,
        }
        try:
            entry["vocab_size"] = get_default_tokenizer().vocab_size
        except Exception as exc:  # tokenizer file missing/corrupt, dependency problem...
            entry["available"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
        return entry

    def list(self) -> List[Dict[str, Any]]:
        items = [self._bundled_entry()]
        with self._lock:
            for tid, (tok, label) in self._custom.items():
                items.append({
                    "id": tid, "label": label, "kind": "custom", "available": True,
                    "vocab_size": tok.vocab_size, "error": None,
                })
        return items

    def get(self, tokenizer_id: str):
        if tokenizer_id == BUNDLED_ID:
            try:
                return get_default_tokenizer(), BUNDLED_LABEL
            except Exception as exc:
                raise AppError(
                    "tokenizer_error",
                    f"The bundled tokenizer could not be loaded ({type(exc).__name__}: {exc}). "
                    "Check that tritobol/data/deepseek_v41_tokenizer.json exists and 'tokenizers' is installed.",
                    field="tokenizer", status=500,
                ) from exc
        with self._lock:
            found = self._custom.get(tokenizer_id)
        if found is None:
            raise AppError(
                "tokenizer_error",
                f"Unknown tokenizer '{tokenizer_id}'. Reload the page or upload the tokenizer again "
                "(uploaded tokenizers only live until the app is restarted).",
                field="tokenizer",
            )
        return found

    def add_custom(self, filename: str, data: bytes) -> Dict[str, Any]:
        """Validate and load a Hugging Face tokenizer.json. Temp files are always removed."""
        name = PurePath((filename or "").replace("\\", "/")).name
        if not name.lower().endswith(".json"):
            raise AppError("tokenizer_error", "Tokenizer file must be a .json file.", field="file", status=415)
        if len(data) == 0:
            raise AppError("tokenizer_error", "The tokenizer file is empty.", field="file")
        if len(data) > MAX_TOKENIZER_BYTES:
            raise AppError(
                "tokenizer_error",
                f"Tokenizer file is {len(data) / 1024 / 1024:.1f} MB; the limit is "
                f"{MAX_TOKENIZER_BYTES // (1024 * 1024)} MB.", field="file", status=413,
            )
        try:
            parsed = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppError("tokenizer_error", f"The file is not valid UTF-8 JSON: {exc}", field="file") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("model"), dict):
            raise AppError(
                "tokenizer_error",
                "This does not look like a Hugging Face tokenizer.json (missing a 'model' section).",
                field="file",
            )
        del parsed
        label = re.sub(r"[^\w .\-]", "_", PurePath(name).stem)[:60] or "custom"
        handle, tmp_path = tempfile.mkstemp(prefix="tritobol_tok_", suffix=".json")
        try:
            with os.fdopen(handle, "wb") as stream:  # closed before reopening (Windows-safe)
                stream.write(data)
            try:
                tokenizer = HuggingFaceTokenizer(tmp_path, model_name=label)
                sample = "Hello, world! Tritobol sanity check."
                if tokenizer.count(sample) < 1:
                    raise ValueError("tokenizer produced no tokens for a sample sentence")
                tokenizer.tail(sample, 1)
            except Exception as exc:
                raise AppError(
                    "tokenizer_error",
                    f"The tokenizer could not be loaded or failed a sanity check ({type(exc).__name__}: {exc}).",
                    field="file",
                ) from exc
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        tid = f"custom-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._custom[tid] = (tokenizer, f"{label} (uploaded)")
            while len(self._custom) > self._max_custom:
                self._custom.popitem(last=False)
        return {"id": tid, "label": f"{label} (uploaded)", "kind": "custom", "available": True,
                "vocab_size": tokenizer.vocab_size, "error": None}


def run_optimization(req: OptimizeRequest, registry: TokenizerRegistry) -> Dict[str, Any]:
    tokenizer, label = registry.get(req.tokenizer_id)
    started = time.perf_counter()
    try:
        engine = Tritobol(
            tokenizer=tokenizer,
            protect_code_blocks=req.protect_code_blocks,
            task_type=req.task_type,
            sensitive_data=req.sensitive_data,
        )
        result = engine.optimize(req.text, max_tokens=req.max_tokens, warn_on_truncation=False)
    except BudgetTooSmallError as exc:
        raise AppError(
            "budget_error",
            f"The budget of {req.max_tokens:,} token(s) is too small: not even the newest character fits "
            "(some characters need several tokens). Use a larger budget.",
            field="max_tokens", status=422,
        ) from exc
    except ValueError as exc:  # engine-side validation (messages never contain user text)
        raise AppError("validation_error", str(exc)) from exc
    except IndexError as exc:
        if req.max_tokens is None:
            raise AppError("processing_error", "The optimizer failed unexpectedly (IndexError). Your input was not changed.", status=500) from exc
        # Fallback for engines without BudgetTooSmallError: when the budget is smaller than the number of
        # byte-level tokens of one character (e.g. an emoji needs 2), no whole piece of text fits and the engine
        # raises IndexError. We report it plainly instead of faking a result. The engine is deliberately unchanged.
        raise AppError(
            "budget_error",
            f"The budget of {req.max_tokens:,} token(s) is too small: not even the newest character fits "
            "(some characters need several tokens). Use a larger budget.",
            field="max_tokens", status=422,
        ) from exc
    except Exception as exc:
        raise AppError(
            "processing_error",
            f"The optimizer failed unexpectedly ({type(exc).__name__}). Your input was not changed.",
            status=500,
        ) from exc

    s = result.stats
    stats = {**asdict(s), "saved_tokens": s.saved_tokens, "saved_percent": s.saved_percent,
             "removed_chars": s.removed_chars}

    budget: Dict[str, Any] = {"requested": req.max_tokens, "enforced": req.max_tokens is not None,
                              "verified_within_budget": None, "recount_tokens": None}
    notes: List[str] = []
    if req.max_tokens is not None:
        recount = tokenizer.count(result.text)  # independent check of the engine's own number
        budget["recount_tokens"] = recount
        budget["verified_within_budget"] = recount <= req.max_tokens
        if not budget["verified_within_budget"]:
            notes.append(
                f"The optimized text re-counts to {recount:,} tokens, above the requested budget of "
                f"{req.max_tokens:,}. The budget was not met."
            )
        if not s.truncated and req.max_tokens >= s.optimized_tokens:
            notes.append("The text already fit within the budget, so no content was cut by the budget.")
    sensitive_hits = sum(1 for seg in result.segments if seg.kind == "sensitive")
    return {
        "text": result.text,
        "tokenizer": {"id": req.tokenizer_id, "label": label},
        "stats": stats,
        "budget": budget,
        "warning": result.warning,
        "notes": notes,
        "segments": [asdict(seg) for seg in result.segments],
        "sensitive_findings": sensitive_hits,
        "options": {"task_type": req.task_type, "sensitive_data": req.sensitive_data,
                    "protect_code_blocks": req.protect_code_blocks},
        "diff": build_diff(req.text, result.text),
        "engine_version": ENGINE_VERSION,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }
