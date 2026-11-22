"""Public pages, the labeled test session, themes, and account-form validation."""
from playwright.sync_api import expect


def test_public_pages(page):
    for route in ("home", "features", "about", "privacy", "contact"):
        page.goto(page.server + f"#/{route}")
        expect(page.locator(f"#view-{route}")).to_be_visible()
    expect(page.locator("#view-privacy")).to_contain_text("127.0.0.1")
    expect(page.locator("#view-privacy")).to_contain_text("no outbound network requests")
    expect(page.locator("#view-privacy")).to_contain_text("not complete secret detection")
    assert page.problems == []


def test_labeled_test_session_reaches_the_workspace(page):
    page.goto(page.server + "#/home")
    expect(page.locator("#view-home")).to_be_visible()
    page.goto(page.server + "#/dashboard")
    expect(page.locator("#view-dashboard")).to_be_visible()
    expect(page.locator("#profile-menu")).to_be_visible()
    page.click('nav a[data-route="optimize"]')
    expect(page.locator("#view-optimize")).to_be_visible()
    page.click('nav a[data-route="results"]')
    expect(page.locator("#view-results")).to_be_visible()
    page.click('nav a[data-route="history"]')
    expect(page.locator("#view-history")).to_be_visible()
    page.click('nav a[data-route="analytics"]')
    expect(page.locator("#view-analytics")).to_be_visible()
    page.click('nav a[data-route="settings"]')
    expect(page.locator("#view-settings")).to_be_visible()


def test_authenticated_test_session_skips_the_account_forms(page):
    page.goto(page.server + "#/signin")
    expect(page.locator("#view-dashboard")).to_be_visible()
    page.goto(page.server + "#/signup")
    expect(page.locator("#view-dashboard")).to_be_visible()


def show(page, route):
    link = page.locator(f'nav a[data-route="{route}"]')
    if link.count() and link.is_visible():
        link.click()
    else:
        page.evaluate("(name) => { location.hash = '#/' + name; }", route)
    expect(page.locator(f"#view-{route}")).to_be_visible()


def test_light_and_dark_themes(page):
    show(page, "settings")
    expect(page.locator("#set-theme")).to_be_visible()
    for choice in ("light", "dark"):
        show(page, "settings")
        page.select_option("#set-theme", choice)
        assert page.evaluate("() => document.documentElement.dataset.theme") == choice
        for route in ("home", "features", "dashboard", "optimize", "analytics"):
            show(page, route)
            assert page.evaluate("() => document.documentElement.dataset.theme") == choice


def test_layouts_do_not_overflow(page):
    for width in (1440, 1280, 768, 390, 320):
        page.set_viewport_size({"width": width, "height": 800})
        for route in ("home", "features", "optimize", "history", "analytics"):
            page.goto(page.server + f"#/{route}")
            expect(page.locator(f"#view-{route}")).to_be_visible()
            overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert overflow <= 1, f"{route} overflows by {overflow}px at {width}px"
