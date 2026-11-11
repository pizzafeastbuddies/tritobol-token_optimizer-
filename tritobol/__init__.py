"""tritobol: trim redundant text, then bolster the latest context.

The name is a blend of **trim** and **bolster**.  The library removes redundant
material from raw prompts and, when a hard token budget is supplied, keeps the
newest context instead of cutting off the end of the text.

Token counts use the official DeepSeek V4.1 Flash tokenizer bundled with the
package by default. Local Hugging Face tokenizer JSON files and compatible
custom tokenizer implementations can be selected per instance.
"""

from .core import (
    OptimizationResult,
    OptimizationStats,
    SegmentLog,
    Tritobol,
    TrimStats,
    optimize_text,
)
from .batch import BatchReport, FileReport, process_path
from .tokenizer import (
    DeepSeekTokenizer,
    HuggingFaceTokenizer,
    Tokenizer,
    WindowResult,
    get_default_tokenizer,
)
from .secrets import SecretFinding, SecretScanner

__all__ = [
    "DeepSeekTokenizer",
    "BatchReport",
    "FileReport",
    "HuggingFaceTokenizer",
    "OptimizationResult",
    "OptimizationStats",
    "SegmentLog",
    "SecretFinding",
    "SecretScanner",
    "TrimStats",
    "Tokenizer",
    "Tritobol",
    "WindowResult",
    "get_default_tokenizer",
    "optimize_text",
    "process_path",
]

__version__ = "0.1.0"
