import re
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import expect
from tokenizers import Tokenizer, models, pre_tokenizers

from conftest import SHOTS, sha, shot, start_server
from tritobol import Tritobol

DOC = (
    "Please review the attached release notes and list every breaking change.\n\n"
    "Please review the attached release notes and list every breaking change.\n\n"
    "==============================================\n\n"
    "Version 2.0 removes the legacy /v1/export endpoint.   Clients must migrate.\n"
    "Version 2.0 removes the legacy /v1/export endpoint.\n"
    "Version 2.1 adds streaming 🎃 responses and a new retry policy.\n\n"
    "api_key = 'sk-abcdefghijklmnop123456'\n\n"
    "Final instruction: answer in three bullet points.\n"
)


def goto(pg, route):
    pg.click(f'nav a[data-route="{route}"]')
    expect(pg.locator(f"#view-{route}")).to_be_visible()


def optimize(pg, text=DOC, budget="", extra=None):
    goto(pg, "optimize")
    pg.fill("#input-text", text)
    pg.fill("#opt-budget", budget)
    for sel, val in (extra or {}).items():
        pg.select_option(sel, val)
    pg.click("#btn-optimize")
    pg.wait_for_selector("#result-tiles .tile", timeout=90_000)


def tile_values(pg):
    return [t.split("\n")[1] for t in pg.locator("#result-tiles .tile").all_inner_texts()]


def set_big_text(pg, text):
    """Set a very large value the way a native paste does (Playwright's fill() types it and is far slower)."""
    pg.evaluate("t => { const e = document.querySelector('#input-text'); e.value = t; e.dispatchEvent(new Event('input')); }", text)


def tiny_tokenizer() -> bytes:
    vocab = {"[UNK]": 0, "hello": 1, "world": 2, "foo": 3}
    tok = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    with tempfile.TemporaryDirectory() as d:
        tok.save(str(Path(d) / "t.json"))
        return (Path(d) / "t.json").read_bytes()


# 1-3 ------------------------------------------------------------------------------------------
def test_startup_dashboard_and_navigation(page):
    expect(page.locator("#dash-engine")).to_contain_text("ready")
    expect(page.locator("#dash-hero-stat")).to_contain_text("No run yet")  # no fabricated stats
    shot(page, "01-dashboard")
    for route in ("optimize", "analytics", "privacy", "settings", "dashboard"):
        goto(page, route)
        expect(page.locator(f'nav a[data-route="{route}"]')).to_have_attribute("aria-current", "page")
        assert sum(page.locator("[data-view]").evaluate_all("els => els.map(e => !e.hidden)")) == 1
    page.goto(page.server + "#/nonsense")
    expect(page.locator("#view-dashboard")).to_be_visible()
    assert page.problems == []


# 4-6 ------------------------------------------------------------------------------------------
def test_text_input_paste_and_clear(page):
    goto(page, "optimize")
    page.fill("#input-text", "héllo 🎃")
    expect(page.locator("#char-count")).to_have_text("7 characters")  # code points, not UTF-16 units
    page.evaluate("navigator.clipboard.writeText('pasted line one\\npasted line two')")
    page.fill("#input-text", "")
    page.focus("#input-text")
    page.keyboard.press("Control+V")
    expect(page.locator("#input-text")).to_have_value("pasted line one\npasted line two")
    expect(page.locator("#char-count")).to_have_text("31 characters")
    page.click("#btn-clear")
    expect(page.locator("#input-text")).to_have_value("")
    expect(page.locator("#char-count")).to_have_text("0 characters")


def test_empty_input_shows_error_without_calling_backend(page):
    goto(page, "optimize")
    page.click("#btn-optimize")
    expect(page.locator("#input-error")).to_contain_text("Enter or load some text")
    assert not [r for r in page.requests if r.endswith("/api/optimize")]


# 7-8 ------------------------------------------------------------------------------------------
def test_utf8_file_loading_original_unchanged(page, tmp_path):
    src = tmp_path / "prompt.txt"
    src.write_bytes("Héllo 🎃\r\n日本語 text".encode("utf-8"))
    before = sha(src)
    goto(page, "optimize")
    page.set_input_files("#file-input", str(src))
    expect(page.locator("#file-info")).to_contain_text("Loaded prompt.txt")
    expect(page.locator("#input-text")).to_have_value("Héllo 🎃\r\n日本語 text".replace("\r\n", "\n"))
    assert sha(src) == before


@pytest.mark.parametrize("name,data,fragment", [
    ("latin1.txt", "café".encode("latin-1"), "not valid UTF-8"),
    ("empty.txt", b"", "empty"),
    ("blank.txt", b"  \n ", "whitespace"),
    ("bin.txt", b"ab\x00cd", "binary"),
    ("pic.png", b"\x89PNG....", "Unsupported"),
    ("huge.txt", b"a" * (2 * 1024 * 1024 + 10), "limit"),
])
def test_invalid_files_show_error_and_keep_text(page, name, data, fragment):
    goto(page, "optimize")
    page.fill("#input-text", "MY DRAFT")
    page.set_input_files("#file-input", files=[{"name": name, "mimeType": "text/plain", "buffer": data}])
    expect(page.locator("#input-error")).to_contain_text(fragment)
    expect(page.locator("#input-text")).to_have_value("MY DRAFT")  # never silently discarded
    if name == "latin1.txt":
        shot(page, "02-invalid-file-error", full=False)


# 9 --------------------------------------------------------------------------------------------
def test_tokenizer_selection_and_custom_upload(page):
    goto(page, "optimize")
    opts = page.locator("#opt-tokenizer option").all_inner_texts()
    assert opts == ["DeepSeek V4.1 Flash (bundled)"]  # only tokenizers that really exist
    expect(page.locator("#tok-status")).to_contain_text("Active: DeepSeek V4.1 Flash")
    page.set_input_files("#tok-file", files=[{"name": "bad.json", "mimeType": "application/json", "buffer": b"nope"}])
    expect(page.locator("#tok-status")).to_contain_text("Tokenizer not loaded")
    page.set_input_files("#tok-file", files=[{"name": "tiny.json", "mimeType": "application/json", "buffer": tiny_tokenizer()}])
    expect(page.locator("#opt-tokenizer")).to_have_value(re.compile("custom-"))
    page.fill("#input-text", "hello world foo hello")
    page.click("#btn-optimize")
    page.wait_for_selector("#result-tiles .tile")
    assert tile_values(page)[0] == "4"  # counted with the uploaded tokenizer
    page.click("#tab-details")
    expect(page.locator("#panel-details")).to_contain_text("tiny (uploaded)")


# 10 -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value,fragment", [("abc", "whole number"), ("0", "1 or more"), ("-5", "1 or more"), ("1.5", "whole number"), ("1e3", "whole number")])
def test_budget_validation(page, value, fragment):
    goto(page, "optimize")
    page.fill("#input-text", "hello there world")
    page.fill("#opt-budget", value)
    expect(page.locator("#budget-error")).to_contain_text(fragment)
    page.click("#btn-optimize")
    assert not [r for r in page.requests if r.endswith("/api/optimize")]  # blocked before any request
    page.fill("#opt-budget", "")
    expect(page.locator("#budget-error")).to_be_hidden()


def test_budget_smaller_than_one_character_reports_engine_limit(page):
    goto(page, "optimize")
    page.fill("#input-text", "🎃")
    page.fill("#opt-budget", "1")
    page.click("#btn-optimize")
    expect(page.locator("#budget-error")).to_contain_text("too small")
    expect(page.locator("#results")).to_be_hidden()


# 11-17 ----------------------------------------------------------------------------------------
def test_full_workflow_with_budget_truncation(page):
    goto(page, "optimize")
    page.fill("#input-text", DOC)
    page.fill("#opt-budget", "40")
    page.click("#btn-optimize")
    page.wait_for_selector("#result-tiles .tile")
    direct = Tritobol().optimize(DOC, max_tokens=40, warn_on_truncation=False)  # ground truth from the engine
    orig, opt, saved, pct = tile_values(page)
    assert (orig, opt, saved) == (str(direct.stats.original_tokens), str(direct.stats.optimized_tokens), str(direct.stats.saved_tokens))
    assert pct == f"{direct.stats.saved_percent:.1f}%"
    banner = page.locator("#result-banner")
    expect(banner).to_contain_text("Older content was removed")
    expect(banner).to_contain_text("not a summary")
    expect(banner).to_contain_text("Verified by re-counting")
    shot(page, "03-results-truncation")
    expect(page.locator("#input-text")).to_have_value(DOC)  # original input untouched
    # compare
    panes = page.locator("#panel-compare pre")
    assert panes.nth(0).inner_text() == DOC.replace("\r\n", "\n")
    assert panes.nth(1).inner_text() == direct.text
    # diff
    page.click("#tab-diff")
    expect(page.locator("#panel-diff .drow.removed, #panel-diff .drow.changed").first).to_be_visible()
    expect(page.locator("#panel-diff .drow.equal").first).to_be_visible()
    shot(page, "04-diff")
    page.click("#tab-details")
    expect(page.locator("#panel-details")).to_contain_text("Segments")
    # analytics
    goto(page, "analytics")
    expect(page.locator("#analytics-body")).to_contain_text(f"{direct.stats.saved_tokens} tokens saved")
    expect(page.locator("#analytics-body")).to_contain_text("before budget cut")
    shot(page, "05-analytics")
    goto(page, "dashboard")
    expect(page.locator("#dash-session")).to_contain_text("Runs")
    assert page.problems == []
    assert [r for r in page.requests if not r.startswith(page.server.rstrip("/"))] == []  # no external requests


def test_no_budget_no_truncation_and_credential_banner(page):
    optimize(page, DOC)
    expect(page.locator("#result-banner")).to_contain_text("No token budget set")
    expect(page.locator("#result-banner")).to_contain_text("left in the optimized text")  # sensitive finding is not hidden
    expect(page.locator("#result-banner")).not_to_contain_text("Older content was removed")
    optimize(page, DOC, extra={"#opt-sensitive": "mask"})
    expect(page.locator("#result-banner")).to_contain_text("replaced with [REDACTED]")
    assert "sk-abcdefghijklmnop123456" not in page.locator("#panel-compare pre").nth(1).inner_text()


def test_zero_savings_is_shown_truthfully(page):
    optimize(page, "One short unique line.")
    orig, opt, saved, pct = tile_values(page)
    assert saved == "0" and pct == "0.0%" and orig == opt


def test_identical_output_diff_message(page):
    optimize(page, "One short unique line.")
    page.click("#tab-diff")
    expect(page.locator("#panel-diff")).to_contain_text("No differences")


def test_large_input_is_handled_without_freezing(page):
    text = "".join(f"Paragraph {i}: unique content about topic {i % 977} with words.\n\n" for i in range(9000))  # ~0.6 MB
    goto(page, "optimize")
    set_big_text(page, text)
    page.click("#btn-optimize")
    expect(page.locator("#btn-optimize")).to_have_text("Optimizing…")
    expect(page.locator("#btn-cancel")).to_be_visible()
    assert page.evaluate("1 + 1") == 2  # page thread still responsive while the backend works
    page.wait_for_selector("#result-tiles .tile", timeout=120_000)
    page.click("#tab-diff")
    assert page.locator("#panel-diff .drow").count() <= 800  # rendered in bounded chunks


def test_cancel_running_optimization_keeps_text(page):
    text = "".join(f"Paragraph {i}: unique content about topic {i % 977} with words.\n\n" for i in range(20000))
    goto(page, "optimize")
    set_big_text(page, text)
    page.click("#btn-optimize")
    page.click("#btn-cancel")
    expect(page.locator("#run-status")).to_contain_text("Cancelled")
    assert len(page.input_value("#input-text")) == len(text)


def test_over_2mb_input_blocked_in_ui(page):
    goto(page, "optimize")
    page.evaluate("document.querySelector('#input-text').value = 'a'.repeat(2*1024*1024 + 1)")
    page.dispatch_event("#input-text", "input")
    expect(page.locator("#input-error")).to_contain_text("limit is 2 MB")
    page.click("#btn-optimize")
    assert not [r for r in page.requests if r.endswith("/api/optimize")]


# 18-19 ----------------------------------------------------------------------------------------
def test_privacy_page_states_limitations(page):
    goto(page, "privacy")
    body = page.locator("#view-privacy")
    expect(body).to_contain_text("127.0.0.1")
    expect(body).to_contain_text("not complete secret detection")
    expect(body).to_contain_text("no outbound network requests")
    shot(page, "06-privacy")


def test_settings_persist_and_reset(page):
    goto(page, "settings")
    page.select_option("#set-task", "coding")
    page.select_option("#set-sensitive", "mask")
    page.fill("#set-budget", "123")
    page.click("#btn-save-settings")
    expect(page.locator("#set-status")).to_contain_text("saved")
    page.reload()
    goto(page, "optimize")
    expect(page.locator("#opt-task")).to_have_value("coding")
    expect(page.locator("#opt-sensitive")).to_have_value("mask")
    expect(page.locator("#opt-budget")).to_have_value("123")
    goto(page, "settings")
    page.fill("#set-budget", "abc")
    page.click("#btn-save-settings")
    expect(page.locator("#set-budget-error")).to_be_visible()
    page.click("#btn-reset-settings")
    expect(page.locator("#set-task")).to_have_value("auto")
    shot(page, "07-settings")
    assert page.evaluate("localStorage.getItem('tritobol.settings.v1')") is None  # reset removes the stored settings


def test_history_stores_numbers_never_text_and_can_be_erased(page):
    optimize(page, DOC)
    stored = page.evaluate("JSON.stringify(Object.fromEntries(Object.entries(localStorage)))")
    assert "Please review" not in stored and "sk-abcdefghijklmnop" not in stored
    goto(page, "settings")
    page.click("#btn-clear-history")
    assert page.evaluate("localStorage.getItem('tritobol.history.v1')") is None


# 20 -------------------------------------------------------------------------------------------
def test_export_new_file_never_overwrites_and_original_unchanged(page, tmp_path):
    original = tmp_path / "prompt.txt"
    original.write_text(DOC, encoding="utf-8")
    digest = sha(original)
    goto(page, "optimize")
    page.set_input_files("#file-input", str(original))
    page.click("#btn-optimize")
    page.wait_for_selector("#result-tiles .tile")
    expect(page.locator("#export-name")).to_have_value("prompt.optimized.txt")
    out = tmp_path / "out"
    page.fill("#export-dir", str(out))
    page.click("#btn-save-copy")
    expect(page.locator("#export-status")).to_contain_text("Saved a new file")
    first = out / "prompt.optimized.txt"
    assert first.exists() and first.read_text(encoding="utf-8") == Tritobol().optimize(DOC, warn_on_truncation=False).text
    first_digest = sha(first)
    page.click("#btn-save-copy")  # same name again
    expect(page.locator("#export-status")).to_contain_text("numbered name")
    assert (out / "prompt.optimized (1).txt").exists() and sha(first) == first_digest
    page.fill("#export-name", "prompt.txt")  # even a name equal to the original is never overwritten
    page.fill("#export-dir", str(tmp_path))
    page.click("#btn-save-copy")
    expect(page.locator("#export-status")).to_contain_text("numbered name")
    assert sha(original) == digest
    shot(page, "08-export")
    with page.expect_download() as dl:
        page.click("#btn-download")
    assert dl.value.suggested_filename == "prompt.txt"
    assert Path(dl.value.path()).read_text(encoding="utf-8") == Tritobol().optimize(DOC, warn_on_truncation=False).text


def test_export_error_is_shown(page, tmp_path):
    optimize(page, DOC)
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    page.fill("#export-dir", str(blocker))
    page.click("#btn-save-copy")
    expect(page.locator("#export-status")).to_contain_text("Export failed")


# 21-22 ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("width,height", [(375, 812), (768, 1024), (320, 640)])
def test_responsive_no_horizontal_scroll(browser, server, width, height):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    pg = ctx.new_page()
    pg.goto(server)
    pg.wait_for_selector("#dash-engine p")
    for route in ("dashboard", "optimize", "analytics", "privacy", "settings"):
        pg.click(f'nav a[data-route="{route}"]')
        dims = pg.evaluate("({s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth})")
        assert dims["s"] <= dims["c"], f"{route} overflows at {width}px: {dims}"
    pg.click('nav a[data-route="optimize"]')
    pg.fill("#input-text", DOC)
    pg.fill("#opt-budget", "40")
    pg.click("#btn-optimize")
    pg.wait_for_selector("#result-tiles .tile")
    pg.click("#tab-diff")
    dims = pg.evaluate("({s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth})")
    assert dims["s"] <= dims["c"], f"results overflow at {width}px: {dims}"
    if width == 375:
        shot(pg, "09-mobile-results")
        pg.click("#tab-compare")
    ctx.close()


def test_keyboard_navigation_and_visible_focus(page):
    goto(page, "optimize")
    page.fill("#input-text", "keyboard text")
    page.focus("#input-text")
    seen = []
    for _ in range(14):
        page.keyboard.press("Tab")
        info = page.evaluate("""() => { const e = document.activeElement; const s = getComputedStyle(e);
            return {id: e.id || e.tagName, outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0}; }""")
        seen.append(info)
    interactive = [i for i in seen if i["id"] not in ("BODY",)]
    assert len(interactive) >= 8
    assert all(i["outline"] for i in interactive), f"focus not visible on: {[i['id'] for i in interactive if not i['outline']]}"
    page.focus("#input-text")
    page.keyboard.press("Control+Enter")  # keyboard shortcut runs the optimizer
    page.wait_for_selector("#result-tiles .tile")
    page.focus("#tab-compare")
    page.keyboard.press("ArrowRight")
    expect(page.locator("#tab-diff")).to_have_attribute("aria-selected", "true")
    page.keyboard.press("ArrowRight")
    expect(page.locator("#tab-details")).to_have_attribute("aria-selected", "true")


# 24 -------------------------------------------------------------------------------------------
def test_backend_unavailable_shows_clear_message(browser, tmp_path):
    proc, url = start_server(tmp_path)
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(url)
    pg.wait_for_selector("#dash-engine p")
    proc.terminate()
    proc.wait(timeout=10)
    goto(pg, "optimize")
    pg.fill("#input-text", "some text to optimize")
    pg.click("#btn-optimize")
    expect(pg.locator("#run-status")).to_contain_text("Cannot reach the Tritobol backend")
    expect(pg.locator("#input-text")).to_have_value("some text to optimize")
    expect(pg.locator("#results")).to_be_hidden()
    ctx.close()


def test_backend_down_at_page_load(browser, tmp_path):
    proc, url = start_server(tmp_path)
    proc.terminate()
    proc.wait(timeout=10)
    ctx = browser.new_context()
    pg = ctx.new_page()
    with pytest.raises(Exception):
        pg.goto(url, timeout=5000)  # browser itself reports the connection refusal; nothing fake is shown
    ctx.close()
