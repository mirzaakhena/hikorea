import re
from datetime import datetime, date
from playwright.sync_api import Page


RESERVATION_URL = "https://www.hikorea.go.kr/resv/ResvIdntR.pt"


def complete_identity_verification(page: Page, reg_number: str, issue_date: str):
    """Navigate to reservation page and complete foreign registration identity verification.

    Args:
        page: Playwright page
        reg_number: 13-digit foreign registration number (no dash)
        issue_date: Issue date in YYYYMMDD format
    """
    page.goto(RESERVATION_URL, wait_until="networkidle")

    # Click on ID card authentication tab (신분증 신원인증)
    # and select Foreign resident tab
    page.click('text=신분증 신원인증')
    page.wait_for_timeout(500)

    # Click Foreign tab if available
    foreign_tab = page.query_selector('text=외국인')
    if foreign_tab:
        foreign_tab.click()
        page.wait_for_timeout(500)

    # Fill registration number (split into two fields: first 6 + last 7)
    reg_first = reg_number[:6]
    reg_last = reg_number[6:]

    # These selectors will need verification against the actual DOM
    reg_inputs = page.query_selector_all('input[type="text"][maxlength="6"], input[type="text"][maxlength="7"]')
    if len(reg_inputs) >= 2:
        reg_inputs[0].fill(reg_first)
        reg_inputs[1].fill(reg_last)

    # Fill issue date
    issue_input = page.query_selector('input[placeholder*="발급일자"], input[name*="issueDate"], input[maxlength="8"]')
    if issue_input:
        issue_input.fill(issue_date)

    # CAPTCHA — pause for manual input
    print("[CAPTCHA] Please solve the CAPTCHA in the browser, then press Enter here...")
    input()

    # Click confirm button (확인)
    page.click('button:has-text("확인"), input[value="확인"], a:has-text("확인")')
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)


def fill_reservation_form(page: Page, visitor_name: str, phone_number: str):
    """Fill the reservation form fields.

    Args:
        page: Playwright page (should be on reservation form after identity verification)
        visitor_name: Full name as on registration card
        phone_number: Mobile number, digits only (e.g. '01064421194')
    """
    # Select Booth Category: General Civil Service Center (Others)
    booth_radio = page.query_selector('input[type="radio"][value*="General"], label:has-text("General Civil Service Center")')
    if booth_radio:
        booth_radio.click()
    else:
        page.click('text=General Civil Service Center')
    page.wait_for_timeout(500)

    # Visitor Name — may be pre-filled, update if needed
    name_input = page.query_selector('input[name*="visitNm"], input[name*="visitorName"]')
    if name_input:
        name_input.fill(visitor_name)

    # Select Task: Visa Extension
    task_radio = page.query_selector('input[type="radio"][value*="visa extension"], label:has-text("visa extension")')
    if task_radio:
        task_radio.click()
    else:
        page.click('text=visa extension', timeout=3000)
    page.wait_for_timeout(500)

    # Phone number — split into parts (010, middle 4, last 4)
    phone_prefix = phone_number[:3]
    phone_mid = phone_number[3:7]
    phone_last = phone_number[7:]

    phone_inputs = page.query_selector_all('select[name*="phone"], input[name*="phone"]')
    if len(phone_inputs) >= 3:
        phone_inputs[0].select_option(phone_prefix)
        phone_inputs[1].fill(phone_mid)
        phone_inputs[2].fill(phone_last)


def get_available_dates(page: Page) -> list[date]:
    """Click the date selection button and parse available dates from the popup.

    Returns:
        List of available dates as date objects.
    """
    # Click the date selection button (날짜 선택)
    page.click('button:has-text("날짜 선택"), input[value="날짜 선택"], a:has-text("날짜 선택")')

    # Wait for popup window
    with page.expect_popup() as popup_info:
        pass
    popup = popup_info.value
    popup.wait_for_load_state("networkidle")

    # Click "다음 달" (next month) to go to the target month
    next_month_btn = popup.query_selector('a:has-text("다음 달"), button:has-text("다음 달")')
    if next_month_btn:
        next_month_btn.click()
        popup.wait_for_timeout(1000)

    # Parse available dates from the calendar
    available_dates = []

    # Look for clickable date cells
    date_links = popup.query_selector_all('a[href*="selDate"], td.able a, td:not(.disabled) a')

    for link in date_links:
        text = link.inner_text().strip()
        if text.isdigit():
            day = int(text)
            header = popup.query_selector('.month, .cal_title, th[colspan]')
            if header:
                header_text = header.inner_text()
                year_match = re.search(r'(\d{4})', header_text)
                month_match = re.search(r'(\d{1,2})월', header_text)
                if not month_match:
                    month_names = {
                        'January': 1, 'February': 2, 'March': 3, 'April': 4,
                        'May': 5, 'June': 6, 'July': 7, 'August': 8,
                        'September': 9, 'October': 10, 'November': 11, 'December': 12
                    }
                    for name, num in month_names.items():
                        if name in header_text:
                            month = num
                            break
                else:
                    month = int(month_match.group(1))

                if year_match:
                    year = int(year_match.group(1))
                    available_dates.append(date(year, month, day))

    popup.close()
    return available_dates


def navigate_calendar_to_month(popup: Page, target_year: int, target_month: int):
    """Click next/prev month buttons until we reach the target month."""
    for _ in range(12):
        header = popup.query_selector('.month, .cal_title, th[colspan]')
        if not header:
            break
        header_text = header.inner_text()

        year_match = re.search(r'(\d{4})', header_text)
        month_match = re.search(r'(\d{1,2})월', header_text)

        if year_match and month_match:
            current_year = int(year_match.group(1))
            current_month = int(month_match.group(1))

            if current_year == target_year and current_month == target_month:
                return

            if (current_year, current_month) < (target_year, target_month):
                popup.click('a:has-text("다음 달"), button:has-text("다음")')
            else:
                popup.click('a:has-text("이전 달"), button:has-text("이전")')
            popup.wait_for_timeout(1000)
