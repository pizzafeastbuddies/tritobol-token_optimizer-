"""Real SQLite account journey against the local Flask app. No external auth provider."""
from playwright.sync_api import expect

PASSWORD = "Longerphrase1"
CREATED = "Your account has been created successfully. Please sign in."


def test_register_sign_in_refresh_sign_out_and_protected_route(anonymous):
    page = anonymous
    expect(page.locator("#view-home")).to_be_visible()
    expect(page.locator("#view-dashboard")).to_be_hidden()
    expect(page.locator("nav.site-nav")).not_to_contain_text("Privacy")
    expect(page.locator("#site-footer")).not_to_contain_text("hosted separately")

    page.click("#link-get-started")
    expect(page.locator("#view-signup")).to_be_visible()
    expect(page.locator("#view-signup")).to_contain_text("Already have an account?")
    page.click("#signup-submit")
    expect(page.locator("#signup-name-error")).to_be_visible()
    page.fill("#signup-name", "Ada Lovelace")
    page.fill("#signup-email", "not-an-email")
    page.fill("#signup-password", PASSWORD)
    page.fill("#signup-confirm", PASSWORD)
    page.click("#signup-submit")
    expect(page.locator("#signup-email-error")).to_be_visible()
    page.fill("#signup-email", "ada@example.com")
    page.fill("#signup-confirm", "Differentphrase1")
    page.click("#signup-submit")
    expect(page.locator("#signup-confirm-error")).to_contain_text("do not match")
    page.fill("#signup-password", "short")
    page.fill("#signup-confirm", "short")
    page.click("#signup-submit")
    expect(page.locator("#signup-password-error")).to_contain_text("12 characters")
    page.fill("#signup-password", PASSWORD)
    page.fill("#signup-confirm", PASSWORD)
    page.click("#signup-submit")
    expect(page.locator("#view-signin")).to_be_visible()
    expect(page.locator("#view-dashboard")).to_be_hidden()
    expect(page.locator("#signin-banner")).to_have_text(CREATED)
    expect(page.locator("#signin-email")).to_have_value("ada@example.com")
    expect(page.locator("#signin-password")).to_have_value("")

    page.goto(page.server + "#/signup")
    page.fill("#signup-name", "Ada Lovelace")
    page.fill("#signup-email", "ada@example.com")
    page.fill("#signup-password", PASSWORD)
    page.fill("#signup-confirm", PASSWORD)
    page.click("#signup-submit")
    expect(page.locator("#signup-status")).to_contain_text("already exists")

    page.goto(page.server + "#/signin")
    page.fill("#signin-email", "ada@example.com")
    page.fill("#signin-password", "Wrongphrase1")
    page.click("#signin-submit")
    expect(page.locator("#signin-status")).to_have_text("Email or password is incorrect.")
    page.fill("#signin-password", PASSWORD)
    page.click("#signin-submit")
    expect(page.locator("#view-dashboard")).to_be_visible()
    page.reload()
    expect(page.locator("#view-dashboard")).to_be_visible()
    expect(page.locator("#profile-email")).to_have_text("ada@example.com")

    page.click('nav a[data-route="optimize"]')
    page.fill("#input-text", "UNIQUE_PROMPT_NEEDLE")
    page.click("#btn-optimize")
    page.wait_for_selector("#result-tiles .tile")
    stored = page.evaluate("() => JSON.stringify(localStorage)")
    assert PASSWORD not in stored

    page.click("#profile-open")
    page.click("#btn-sign-out")
    expect(page.locator("#view-home")).to_be_visible()
    expect(page.locator("#input-text")).to_have_value("")
    page.goto(page.server + "#/dashboard")
    expect(page.locator("#view-signin")).to_be_visible()
    assert "next=dashboard" in page.evaluate("() => location.hash")
    page.fill("#signin-email", "ada@example.com")
    page.fill("#signin-password", PASSWORD)
    page.click("#signin-submit")
    expect(page.locator("#view-dashboard")).to_be_visible()


def test_forgot_password_is_honest_and_change_password_works(anonymous):
    page = anonymous
    page.goto(page.server + "#/signup")
    page.fill("#signup-name", "Grace Hopper")
    page.fill("#signup-email", "grace@example.com")
    page.fill("#signup-password", PASSWORD)
    page.fill("#signup-confirm", PASSWORD)
    page.click("#signup-submit")
    expect(page.locator("#signin-banner")).to_have_text(CREATED)
    page.goto(page.server + "#/forgot")
    expect(page.locator("#view-forgot")).to_contain_text("Email-based password recovery is not configured")
    expect(page.locator("#forgot-submit")).to_have_count(0)
    page.goto(page.server + "#/signin")
    page.fill("#signin-email", "grace@example.com")
    page.fill("#signin-password", PASSWORD)
    page.click("#signin-submit")
    expect(page.locator("#view-dashboard")).to_be_visible()
    page.click('nav a[data-route="settings"]')
    page.fill("#account-current", PASSWORD)
    page.fill("#account-new", "Newerphrase1")
    page.fill("#account-confirm", "Newerphrase1")
    page.click("#account-submit")
    expect(page.locator("#account-status")).to_have_text("Password updated.")
    page.click("#profile-open")
    page.click("#btn-sign-out")
    expect(page.locator("#view-home")).to_be_visible()
    page.goto(page.server + "#/signin")
    page.fill("#signin-email", "grace@example.com")
    page.fill("#signin-password", PASSWORD)
    page.click("#signin-submit")
    expect(page.locator("#signin-status")).to_have_text("Email or password is incorrect.")
    page.fill("#signin-password", "Newerphrase1")
    page.click("#signin-submit")
    expect(page.locator("#view-dashboard")).to_be_visible()


def test_theme_toggle_persists_and_mobile_navigation(anonymous):
    page = anonymous
    page.set_viewport_size({"width": 1360, "height": 900})
    toggle = page.locator(".site-header .theme-toggle")
    expect(toggle).to_be_visible()
    toggle.click()
    first = page.evaluate("() => document.documentElement.dataset.theme")
    assert first in ("light", "dark")
    toggle.click()
    second = page.evaluate("() => document.documentElement.dataset.theme")
    assert {first, second} == {"light", "dark"}
    page.reload()
    assert page.evaluate("() => document.documentElement.dataset.theme") == second
    if page.evaluate("() => document.documentElement.dataset.theme") != "light":
        page.locator(".site-header .theme-toggle").click()
    assert page.evaluate("() => getComputedStyle(document.documentElement).backgroundColor") == "rgb(250, 248, 245)"
    page.locator(".site-header .theme-toggle").click()
    assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
    assert page.evaluate("() => getComputedStyle(document.documentElement).backgroundColor") == "rgb(21, 19, 29)"

    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(page.server + "#/home")
    expect(page.locator(".site-header")).to_be_visible()
    page.get_by_role("link", name="Get Started").first.click()
    expect(page.locator("#view-signup")).to_be_visible()
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 1
