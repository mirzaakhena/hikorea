import os
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

STATE_FILE = Path("state.json")

LOGIN_URL = "https://www.hikorea.go.kr/memb/MembLoginR.pt"
MAIN_URL = "https://www.hikorea.go.kr/Main.pt"
LOGOUT_URL = "https://www.hikorea.go.kr/memb/MembLogout.pt"


def launch_browser(playwright, headless: bool = False):
    """Launch chromium browser."""
    browser = playwright.chromium.launch(headless=headless)
    return browser


def create_context(browser: Browser) -> BrowserContext:
    """Create browser context, loading saved state if available."""
    if STATE_FILE.exists():
        context = browser.new_context(storage_state=str(STATE_FILE))
    else:
        context = browser.new_context()
    return context


def save_session(context: BrowserContext):
    """Save browser session state to file."""
    context.storage_state(path=str(STATE_FILE))


def login(page: Page, user_id: str, password: str):
    """Login to HiKorea. Returns True if login succeeded."""
    page.goto(LOGIN_URL, wait_until="networkidle")

    # Fill login form
    page.fill('input[name="userId"], input[id="userId"]', user_id)
    page.fill('input[name="userPasswd"], input[type="password"]', password)

    # Click login button
    page.click('input[type="submit"], button:has-text("Log in"), a:has-text("Log in")')

    # Wait for navigation after login
    page.wait_for_load_state("networkidle")

    # Check if login succeeded by looking for logout link
    return is_logged_in(page)


def is_logged_in(page: Page) -> bool:
    """Check if user is currently logged in by looking for logout element."""
    try:
        logout_el = page.query_selector('a:has-text("로그아웃"), a:has-text("Log out")')
        return logout_el is not None
    except Exception:
        return False


def logout(page: Page):
    """Logout from HiKorea."""
    page.goto(LOGOUT_URL, wait_until="networkidle")
