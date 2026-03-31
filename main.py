import os
import time
from datetime import datetime, date
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from browser import launch_browser, create_context, login, save_session, is_logged_in
from monitor import complete_identity_verification, fill_reservation_form, get_available_dates


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def load_config() -> dict:
    load_dotenv()
    return {
        "user_id": os.environ["HIKOREA_ID"],
        "password": os.environ["HIKOREA_PW"],
        "reg_number": os.environ["FOREIGN_REG_NUMBER"],
        "issue_date": os.environ["REG_ISSUE_DATE"],
        "visitor_name": os.environ["VISITOR_NAME"],
        "phone_number": os.environ["PHONE_NUMBER"],
        "interval_minutes": int(os.environ.get("CHECK_INTERVAL_MINUTES", "5")),
        "target_before": os.environ.get("TARGET_BEFORE_DATE", "2026-04-15"),
        "headless": os.environ.get("HEADLESS", "false").lower() == "true",
    }


def check_slots(page, config: dict) -> list[date]:
    """Run a single slot check. Returns list of available dates."""
    log("Starting slot check...")

    try:
        dates = get_available_dates(page)
    except Exception as e:
        log(f"Error reading dates: {e}")
        return []

    if not dates:
        log("No slots available.")
        return []

    log(f"Available dates: {', '.join(d.isoformat() for d in dates)}")

    # Check against target
    target = date.fromisoformat(config["target_before"])
    matches = [d for d in dates if d < target]
    if matches:
        log(f">>> MATCH FOUND: {', '.join(d.isoformat() for d in matches)} before target {config['target_before']}")

    return dates


def ensure_logged_in(page, config: dict, context) -> bool:
    """Ensure user is logged in, re-login if needed."""
    if is_logged_in(page):
        return True

    log("Session expired, re-logging in...")
    success = login(page, config["user_id"], config["password"])
    if success:
        save_session(context)
        log("Re-login successful.")

        # Need to redo identity verification and form fill
        complete_identity_verification(page, config["reg_number"], config["issue_date"])
        fill_reservation_form(page, config["visitor_name"], config["phone_number"])
    else:
        log("Re-login FAILED. Will retry next cycle.")

    return success


def main():
    config = load_config()

    log("HiKorea Slot Monitor starting...")
    log(f"Target: find slots before {config['target_before']}")
    log(f"Check interval: {config['interval_minutes']} minutes")
    log(f"Headless: {config['headless']}")

    with sync_playwright() as p:
        browser = launch_browser(p, headless=config["headless"])
        context = create_context(browser)
        page = context.new_page()

        # Initial login
        log("Logging in...")
        success = login(page, config["user_id"], config["password"])
        if not success:
            log("Initial login FAILED. Check credentials.")
            browser.close()
            return

        save_session(context)
        log("Login successful.")

        # Identity verification (requires manual CAPTCHA first time)
        log("Starting identity verification...")
        complete_identity_verification(page, config["reg_number"], config["issue_date"])

        # Fill reservation form
        log("Filling reservation form...")
        fill_reservation_form(page, config["visitor_name"], config["phone_number"])

        log("Setup complete. Starting monitoring loop...")

        # Monitoring loop
        while True:
            if not ensure_logged_in(page, config, context):
                log(f"Waiting {config['interval_minutes']} minutes before retry...")
                time.sleep(config["interval_minutes"] * 60)
                continue

            check_slots(page, config)

            log(f"Next check in {config['interval_minutes']} minutes...")
            time.sleep(config["interval_minutes"] * 60)


if __name__ == "__main__":
    main()
