import re
from datetime import date
from playwright.sync_api import Page


RESERVATION_URL = "https://www.hikorea.go.kr/resv/ResvIdntR.pt"


def fill_reservation_form(page: Page, orgn_cd: str, desk_seq: str, task_code: str,
                          visitor_name: str, phone_number: str):
    """Navigate to reservation page and fill the form.

    Args:
        page: Playwright page (must be logged in)
        orgn_cd: Office code (e.g. '1270686' for Busan)
        desk_seq: Booth radio value (e.g. '810')
        task_code: Task checkbox value (e.g. 'F03' for visa extension)
        visitor_name: Full name
        phone_number: Mobile number, digits only (e.g. '01064421194')
    """
    page.goto(RESERVATION_URL, wait_until="networkidle")
    page.wait_for_timeout(1000)

    # Select office (담당기관)
    page.select_option('select#orgnCd', orgn_cd)
    page.wait_for_timeout(2000)

    # Select booth category (접수창구구분)
    page.click(f'input#deskSeq{desk_seq}')
    page.wait_for_timeout(500)

    # Select task (업무선택) - e.g. F03 = 체류기간연장 (Visa Extension)
    page.click(f'input#selBusiType1_1_{task_code}')
    page.wait_for_timeout(1000)

    # Dismiss jQuery UI dialog if it appears (e-petition info dialog)
    _dismiss_ui_dialog(page)

    # Visitor name (방문자 성명) - usually pre-filled and readonly when logged in
    name_input = page.query_selector('input#resvNm1')
    if name_input and name_input.is_editable():
        name_input.fill(visitor_name)

    # Mobile number (이동전화번호)
    phone_prefix = phone_number[:3]
    phone_mid = phone_number[3:7]
    phone_last = phone_number[7:]

    page.select_option('select#mobileTelNo1', phone_prefix)
    page.fill('input#mobileTelNo2', phone_mid)
    page.fill('input#mobileTelNo3', phone_last)


def get_available_dates_for_months(page: Page, months: list[tuple[int, int]]) -> list[date]:
    """Open date picker once, check multiple months, and return all available dates.

    Args:
        page: Playwright page (form should be filled)
        months: List of (year, month) tuples to check, e.g. [(2026, 4), (2026, 5)]

    Returns:
        List of available dates as date objects.

    Raises:
        TimeoutError: If calendar navigation gets stuck (possible session expiry).
    """
    # Click calendar icon to open popup
    try:
        page.click('#resvYmdSelect', timeout=10000)
    except Exception as e:
        raise TimeoutError(f"Failed to open date picker: {e}")

    page.wait_for_timeout(2000)

    # Get the popup page (new window)
    pages = page.context.pages
    if len(pages) < 2:
        raise TimeoutError("Date picker popup did not open — possible session expiry")
    popup = pages[-1]

    try:
        popup.wait_for_load_state("networkidle", timeout=15000)
    except Exception as e:
        popup.close()
        raise TimeoutError(f"Popup failed to load: {e}")

    popup.wait_for_timeout(1000)

    all_dates = []
    try:
        for year, month in sorted(months):
            _navigate_calendar_to_month(popup, year, month)
            all_dates.extend(_parse_calendar_dates(popup))
    finally:
        popup.close()

    return all_dates


def _dismiss_ui_dialog(page: Page):
    """Click 확인 button on jQuery UI dialog if present."""
    dialog = page.query_selector('.ui-dialog')
    if dialog and dialog.is_visible():
        confirm_btn = dialog.query_selector('button:has-text("확인"), a:has-text("확인")')
        if confirm_btn:
            confirm_btn.click()
            page.wait_for_timeout(500)
        else:
            close_btn = dialog.query_selector('.ui-dialog-titlebar-close')
            if close_btn:
                close_btn.click()
                page.wait_for_timeout(500)


def _parse_calendar_dates(popup: Page) -> list[date]:
    """Parse available (clickable) dates from the jQuery UI datepicker popup.

    Available dates have <a> links inside <td>.
    Full/disabled dates have <span> inside <td> with class 'date-resvfull' or 'ui-state-disabled'.
    """
    year, month = _read_calendar_header(popup)
    if not year or not month:
        return []

    available_dates = []

    # Available dates are td cells containing an <a> link (not disabled)
    date_cells = popup.query_selector_all('.ui-datepicker-calendar td')
    for td in date_cells:
        cls = td.get_attribute('class') or ''
        # Skip disabled, other-month, and weekend cells without links
        if 'ui-datepicker-other-month' in cls:
            continue

        link = td.query_selector('a')
        if link:
            text = link.inner_text().strip()
            if text.isdigit():
                day = int(text)
                available_dates.append(date(year, month, day))

    return available_dates


def _read_calendar_header(popup: Page) -> tuple[int | None, int | None]:
    """Read year and month from jQuery UI datepicker header."""
    year_el = popup.query_selector('.ui-datepicker-year')
    month_el = popup.query_selector('.ui-datepicker-month')

    if year_el and month_el:
        year_text = year_el.inner_text().strip()
        month_text = month_el.inner_text().strip()

        year_match = re.search(r'(\d{4})', year_text)
        month_match = re.search(r'(\d{1,2})', month_text)

        if year_match and month_match:
            return int(year_match.group(1)), int(month_match.group(1))

    return None, None


def _navigate_calendar_to_month(popup: Page, target_year: int, target_month: int):
    """Click next/prev month buttons until we reach the target month.

    Raises TimeoutError if navigation gets stuck (possible session expiry).
    """
    max_retries_per_click = 3
    for _ in range(12):
        year, month = _read_calendar_header(popup)
        if not year or not month:
            raise TimeoutError("Cannot read calendar header — possible session expiry")

        if year == target_year and month == target_month:
            return

        prev_year, prev_month = year, month

        if (year, month) < (target_year, target_month):
            next_btn = popup.query_selector('a.ui-datepicker-next')
            if not next_btn:
                raise TimeoutError("Next button not found — possible session expiry")
            next_btn.click(timeout=5000, force=True)
            popup.wait_for_timeout(1500)
        else:
            prev_btn = popup.query_selector('a.ui-datepicker-prev')
            if not prev_btn:
                raise TimeoutError("Prev button not found — possible session expiry")
            prev_btn.click(timeout=5000, force=True)
            popup.wait_for_timeout(1500)

        # Verify calendar actually moved
        new_year, new_month = _read_calendar_header(popup)
        if (new_year, new_month) == (prev_year, prev_month):
            raise TimeoutError(
                f"Calendar stuck at {prev_year}-{prev_month:02d} — possible session expiry"
            )
