import os
import time
from datetime import datetime, date
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from browser import launch_browser, create_context, login, logout, save_session, is_logged_in
from monitor import fill_reservation_form, get_available_dates_for_months


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def load_config() -> dict:
    load_dotenv()
    return {
        "user_id": os.environ["HIKOREA_ID"],
        "password": os.environ["HIKOREA_PW"],
        "orgn_cd": os.environ.get("ORGN_CD", "1270686"),
        "desk_seq": os.environ.get("DESK_SEQ", "810"),
        "task_code": os.environ.get("TASK_CODE", "F03"),
        "visitor_name": os.environ["VISITOR_NAME"],
        "phone_number": os.environ["PHONE_NUMBER"],
        "interval_minutes": int(os.environ.get("CHECK_INTERVAL_MINUTES", "5")),
        "target_before": os.environ.get("TARGET_BEFORE_DATE", "2026-04-15"),
        "headless": os.environ.get("HEADLESS", "false").lower() == "true",
    }


def setup_form(page, config: dict):
    """Navigate to reservation page and fill the form."""
    fill_reservation_form(
        page,
        orgn_cd=config["orgn_cd"],
        desk_seq=config["desk_seq"],
        task_code=config["task_code"],
        visitor_name=config["visitor_name"],
        phone_number=config["phone_number"],
    )


def check_slots(page, config: dict) -> list[date]:
    """Run a single slot check. Returns list of available dates."""
    log("Starting slot check...")

    target = date.fromisoformat(config["target_before"])

    # Check the target month and the month before it
    months_to_check = set()
    months_to_check.add((target.year, target.month))
    if target.month == 1:
        months_to_check.add((target.year - 1, 12))
    else:
        months_to_check.add((target.year, target.month - 1))

    months_sorted = sorted(months_to_check)
    log(f"Checking months: {', '.join(f'{y}-{m:02d}' for y, m in months_sorted)}")

    try:
        all_dates = get_available_dates_for_months(page, months_sorted)
    except Exception as e:
        log(f"Error reading dates: {e}")
        all_dates = []

    if not all_dates:
        log("No slots available.")
        return []

    log(f"Available dates: {', '.join(d.isoformat() for d in all_dates)}")

    matches = [d for d in all_dates if d < target]
    if matches:
        log(f">>> MATCH FOUND: {', '.join(d.isoformat() for d in matches)} before target {config['target_before']}")

    return all_dates


def ensure_logged_in(page, config: dict, context) -> bool:
    """Ensure user is logged in, re-login if needed."""
    if is_logged_in(page):
        return True

    log("Session expired, re-logging in...")
    success = login(page, config["user_id"], config["password"])
    if success:
        save_session(context)
        log("Re-login successful.")
        setup_form(page, config)
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

        # Auto-accept any JavaScript alert/confirm dialogs
        page.on("dialog", lambda dialog: dialog.accept())

        # Initial login
        log("Logging in...")
        success = login(page, config["user_id"], config["password"])
        if not success:
            log("Initial login FAILED. Check credentials.")
            browser.close()
            return

        save_session(context)
        log("Login successful.")

        # Fill reservation form (no identity verification needed when logged in)
        log("Filling reservation form...")
        setup_form(page, config)
        log("Form filled. Starting monitoring loop...")

        # Monitoring loop
        try:
            while True:
                if not ensure_logged_in(page, config, context):
                    log(f"Waiting {config['interval_minutes']} minutes before retry...")
                    time.sleep(config["interval_minutes"] * 60)
                    continue

                check_slots(page, config)

                log(f"Next check in {config['interval_minutes']} minutes...")
                time.sleep(config["interval_minutes"] * 60)
        except KeyboardInterrupt:
            log("Shutting down...")
        finally:
            log("Logging out and closing browser...")
            try:
                logout(page)
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
            log("Done. Bye!")


if __name__ == "__main__":
    main()
