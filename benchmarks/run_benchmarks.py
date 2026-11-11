"""Run deterministic synthetic token-savings and marker-retention benchmarks."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Dict, Tuple

from tritobol import Tritobol


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    text: str
    required_phrases: Tuple[str, ...]


CASES = (
    BenchmarkCase(
        name="repeated deployment guidance",
        text=(
            "Release checklist: verify the staging environment before deployment.\n\n"
            "Keep the database backup until rollback is no longer needed.\n\n"
            "Keep the database backup until rollback is no longer needed.\n\n"
            "The release owner is Maya Chen.\n\n"
            "Keep the database backup until rollback is no longer needed."
        ),
        required_phrases=(
            "Release checklist: verify the staging environment before deployment.",
            "The release owner is Maya Chen.",
        ),
    ),
    BenchmarkCase(
        name="unique operational facts with whitespace noise",
        text=(
            "\n\n  Service: inventory-api\n\n\n"
            "  Primary region: ap-southeast-2\n\n\n"
            "  Rollback command: deployctl rollback inventory-api\n\n\n"
            "  Alert channel: #ops-inventory\n\n"
        ),
        required_phrases=(
            "Service: inventory-api",
            "Primary region: ap-southeast-2",
            "Rollback command: deployctl rollback inventory-api",
            "Alert channel: #ops-inventory",
        ),
    ),
    BenchmarkCase(
        name="mixed unique and repeated incident notes",
        text=(
            "Incident ID: INC-4821\n\n"
            "The cache was cleared at 14:32 UTC.\n\n"
            "The cache was cleared at 14:32 UTC.\n\n"
            "Customer impact ended at 14:47 UTC.\n\n"
            "The mitigation owner is Priya Shah."
        ),
        required_phrases=(
            "Incident ID: INC-4821",
            "Customer impact ended at 14:47 UTC.",
            "The mitigation owner is Priya Shah.",
        ),
    ),
)


def run_benchmarks() -> Dict[str, object]:
    """Return token and literal evidence-retention results for fixed fixtures."""
    optimizer = Tritobol()
    rows = []
    total_original_tokens = 0
    total_optimized_tokens = 0
    total_required = 0
    total_retained = 0

    for case in CASES:
        result = optimizer.optimize(case.text, warn_on_truncation=False)
        retained = [
            phrase for phrase in case.required_phrases if phrase in result.text
        ]
        original_tokens = result.stats.original_tokens
        optimized_tokens = result.stats.optimized_tokens
        total_original_tokens += original_tokens
        total_optimized_tokens += optimized_tokens
        total_required += len(case.required_phrases)
        total_retained += len(retained)
        rows.append(
            {
                "name": case.name,
                "original_tokens": original_tokens,
                "optimized_tokens": optimized_tokens,
                "saved_tokens": original_tokens - optimized_tokens,
                "saved_percent": result.stats.saved_percent,
                "required_phrases": len(case.required_phrases),
                "retained_phrases": len(retained),
                "retention_percent": (
                    len(retained) / len(case.required_phrases) * 100.0
                    if case.required_phrases
                    else 100.0
                ),
                "missing_phrases": [
                    phrase
                    for phrase in case.required_phrases
                    if phrase not in result.text
                ],
            }
        )

    return {
        "methodology": (
            "Fixed synthetic inputs; no token budget; token counts use the bundled "
            "DeepSeek V4.1 Flash tokenizer. Retention is exact substring presence "
            "for listed phrases, not semantic or model-quality evaluation."
        ),
        "tokenizer": optimizer.tokenizer.model_name,
        "cases": rows,
        "totals": {
            "original_tokens": total_original_tokens,
            "optimized_tokens": total_optimized_tokens,
            "saved_tokens": total_original_tokens - total_optimized_tokens,
            "saved_percent": (
                (total_original_tokens - total_optimized_tokens)
                / total_original_tokens
                * 100.0
                if total_original_tokens
                else 0.0
            ),
            "required_phrases": total_required,
            "retained_phrases": total_retained,
            "retention_percent": (
                total_retained / total_required * 100.0 if total_required else 100.0
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON rather than a concise table",
    )
    args = parser.parse_args(argv)
    report = run_benchmarks()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print(f"Tokenizer: {report['tokenizer']}")
    print("Synthetic benchmark (exact phrase retention; not semantic accuracy)")
    for case in report["cases"]:
        print(
            f"{case['name']}: {case['original_tokens']} -> "
            f"{case['optimized_tokens']} tokens "
            f"({case['saved_percent']:.1f}% saved); "
            f"phrases {case['retained_phrases']}/{case['required_phrases']} retained"
        )
    totals = report["totals"]
    print(
        f"Total: {totals['original_tokens']} -> {totals['optimized_tokens']} tokens "
        f"({totals['saved_percent']:.1f}% saved); "
        f"phrases {totals['retained_phrases']}/{totals['required_phrases']} retained"
    )
    print(report["methodology"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
