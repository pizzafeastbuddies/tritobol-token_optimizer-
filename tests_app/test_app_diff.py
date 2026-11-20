import time

from hypothesis import HealthCheck, given, settings, strategies as st

from conftest import SAMPLE
from tritobol import Tritobol
from tritobol_app.diffing import MAX_DIFF_LINES, build_diff


def rebuild(diff, side):
    lines = []
    for op in diff["ops"]:
        if side == "a" and op["tag"] in ("equal", "delete", "replace"):
            lines += op["a"]
        if side == "b" and op["tag"] == "equal":
            lines += op["a"]
        if side == "b" and op["tag"] in ("insert", "replace"):
            lines += op["b"]
    return "\n".join(lines)


def test_identical():
    d = build_diff("same\ntext", "same\ntext")
    assert d["identical"] and d["available"] and d["ops"] == []


def test_diff_reproduces_both_sides_for_real_optimizer_output():
    out = Tritobol().optimize(SAMPLE, warn_on_truncation=False).text
    d = build_diff(SAMPLE, out)
    assert rebuild(d, "a") == SAMPLE.replace("\r\n", "\n") and rebuild(d, "b") == out
    assert any(o["tag"] in ("delete", "replace") for o in d["ops"])


def test_word_level_detail_for_paired_lines():
    d = build_diff("alpha   beta gamma", "alpha beta gamma")
    op = d["ops"][0]
    assert op["tag"] == "replace" and op["words"][0] is not None
    assert "".join(w["a"] for w in op["words"][0]) == "alpha   beta gamma"
    assert "".join(w["b"] for w in op["words"][0]) == "alpha beta gamma"


def test_empty_optimized_text():
    d = build_diff("a\nb", "")
    assert d["available"] and rebuild(d, "a") == "a\nb" and rebuild(d, "b") == ""


def test_too_many_lines_is_reported_not_hidden(monkeypatch):
    import tritobol_app.diffing as dm
    monkeypatch.setattr(dm, "MAX_DIFF_LINES", 100)
    big = "\n".join(f"line {i}" for i in range(105))
    d = build_diff(big, big[:-10])
    assert d["available"] is False and "skipped" in d["reason"] and "still shown" in d["reason"]


def test_time_limit_reports_unavailable_instead_of_hanging(monkeypatch):
    import tritobol_app.diffing as dm
    monkeypatch.setattr(dm, "DIFF_TIME_LIMIT_S", -1.0)  # deadline already passed
    d = build_diff("a\nb\nc", "a\nc")
    assert d["available"] is False and "took too long" in d["reason"]


def test_pathological_alternating_short_lines_finish_fast_and_stay_correct():
    a = "\n".join("x" if i % 2 else "y" for i in range(3000))
    b = "\n".join("y" if i % 3 else "x" for i in range(3000))
    t = time.perf_counter()
    d = build_diff(a, b)
    assert time.perf_counter() - t < 15  # bounded by DIFF_TIME_LIMIT_S plus overhead (was 34 s unbounded for 2k lines)
    if d["available"]:  # whichever way it ends, it must be truthful
        assert rebuild(d, "a") == a and rebuild(d, "b") == b


def test_large_typical_diff_is_correct_and_bounded():
    a = "\n".join(f"Paragraph {i} has some content" for i in range(12000))
    b = "\n".join(l for i, l in enumerate(a.split("\n")) if i % 7)
    t = time.perf_counter()
    d = build_diff(a, b)
    assert time.perf_counter() - t < 15
    if d["available"]:
        assert rebuild(d, "a") == a and rebuild(d, "b") == b
        assert d["summary"]["lines_removed_or_changed"] == 12000 - len(b.split("\n"))


@settings(max_examples=60, deadline=None)
@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=300), st.text(max_size=300))
def test_property_diff_reconstructs_inputs(a, b):
    d = build_diff(a, b)
    norm = lambda s: s.replace("\r\n", "\n").replace("\r", "\n")
    if d["identical"]:
        assert a == b
    else:
        assert rebuild(d, "a") == norm(a) and rebuild(d, "b") == norm(b)
