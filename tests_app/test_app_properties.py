"""Property checks. Only properties the engine actually guarantees are asserted as guarantees."""

from hypothesis import given, settings, strategies as st

from tritobol import Tritobol
from tritobol_app.schemas import AppError, parse_optimize_request
from tritobol_app.server import create_app
from tritobol_app.service import TokenizerRegistry, run_optimization

REGISTRY = TokenizerRegistry()
TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=400).filter(lambda s: s.strip())


def run(text, budget=None, **extra):
    return run_optimization(parse_optimize_request({"text": text, "max_tokens": budget, **extra}), REGISTRY)


def run_or_known_budget_limit(text, budget):
    """Returns None when the engine hits its documented tiny-budget limitation (reported as budget_error 422)."""
    try:
        return run(text, budget)
    except AppError as err:
        assert err.code == "budget_error" and err.status == 422 and err.field == "max_tokens"
        return None


@settings(max_examples=40, deadline=None)
@given(TEXT)
def test_deterministic(text):
    a, b = run(text), run(text)
    for r in (a, b):
        r.pop("elapsed_ms")
    assert a == b


@settings(max_examples=40, deadline=None)
@given(TEXT)
def test_counts_consistent_and_valid_structure(text):
    r = run(text)
    s = r["stats"]
    assert s["saved_tokens"] == s["original_tokens"] - s["optimized_tokens"]
    assert s["removed_chars"] == s["original_chars"] - s["optimized_chars"]
    assert s["original_chars"] == len(text) and s["optimized_chars"] == len(r["text"])
    assert s["optimized_tokens"] == Tritobol().count_tokens(r["text"])  # no fabricated numbers
    expected = 0.0 if s["original_tokens"] == 0 else s["saved_tokens"] / s["original_tokens"] * 100
    assert abs(s["saved_percent"] - expected) < 1e-9
    assert set(r) >= {"text", "stats", "budget", "warning", "notes", "segments", "diff", "tokenizer", "options"}


@settings(max_examples=40, deadline=None)
@given(TEXT, st.integers(min_value=1, max_value=60))
def test_budget_report_is_truthful(text, budget):
    r = run_or_known_budget_limit(text, budget)
    if r is None:
        return
    recount = Tritobol().count_tokens(r["text"])
    assert r["budget"]["recount_tokens"] == recount
    assert r["budget"]["verified_within_budget"] == (recount <= budget)  # the flag never lies
    assert (r["warning"] is not None) == r["stats"]["truncated"]
    if not r["stats"]["truncated"]:
        assert r["stats"]["discarded_tokens"] == 0


@settings(max_examples=25, deadline=None)
@given(TEXT)
def test_no_budget_never_truncates(text):
    r = run(text)
    assert r["warning"] is None and r["stats"]["truncated"] is False and r["budget"]["verified_within_budget"] is None
