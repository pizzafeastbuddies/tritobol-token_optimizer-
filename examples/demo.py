"""Runnable examples for tritobol.

From the project root:

    python examples/demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Allow the demo to run directly from a source checkout without installing.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tritobol import Tritobol  # noqa: E402


TOOL = Tritobol()

LOW_NOISE = """
    Alpha is the first item in the sequence and it must remain.




    Beta is the second item in the sequence and it must remain.


    Gamma is the third item in the sequence and it must remain.
"""

REPEATED_BOILERPLATE = (
    "This is a repeated boilerplate paragraph that should appear only once "
    "in the optimized prompt because it adds no new information."
)

HIGH_NOISE = (
    "Intro: unique opening sentence that must stay.\n\n"
    + "\n\n".join([REPEATED_BOILERPLATE] * 7)
    + "\n\nOutro: unique closing sentence that must stay."
)

MEDIUM_NOISE = """
Introduction: This document explains the deployment process in detail.

The deployment process starts with a backup of the production database and a
review of the release notes.

The deployment process starts with a backup of the production database and a
review of the release notes.

After the backup completes, run the migration and verify the health checks
before routing traffic.

After the backup completes, run the migration and verify the health checks
before routing traffic.

Conclusion: Keep the latest context when the input is too long.
"""

LONG_TRANSCRIPT = "\n\n".join(
    f"Section {index}: " + "detail " * 30 for index in range(20)
)


def show(label: str, text: str, max_tokens: Optional[int] = None) -> None:
    print("=" * 78)
    print(label)
    print("-" * 78, flush=True)

    result = TOOL.optimize(text, max_tokens=max_tokens)
    stats = result.stats

    print(f"original tokens : {stats.original_tokens:,}")
    print(f"optimized tokens: {stats.optimized_tokens:,}")
    print(f"saved           : {stats.saved_tokens:,} ({stats.saved_percent:.1f}%)")
    print(f"details         : {stats.summary()}")
    print(f"optimized text  : {result.text[:260]!r}")
    if len(result.text) > 260:
        print(f"                  ... {len(result.text) - 260:,} more chars")
    print()


if __name__ == "__main__":
    show("Low noise: redundant whitespace only", LOW_NOISE)
    show("Medium noise: repeated paragraphs", MEDIUM_NOISE)
    show("High noise: repeated boilerplate", HIGH_NOISE)
    show(
        "Long input: keep the newest context",
        LONG_TRANSCRIPT,
        max_tokens=80,
    )
