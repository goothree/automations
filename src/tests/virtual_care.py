import os
import shutil
import time
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.tests.test_login import test_login_success, driver

_screenshot_dir = None
_MAX_SCREENSHOT_RUNS = 7


def _prune_old_screenshot_runs(screenshots_base: str) -> None:
    if not os.path.isdir(screenshots_base):
        return
    try:
        subdirs = [
            os.path.join(screenshots_base, d)
            for d in os.listdir(screenshots_base)
            if os.path.isdir(os.path.join(screenshots_base, d))
        ]
        subdirs.sort(key=os.path.basename, reverse=True)
        keep_count = _MAX_SCREENSHOT_RUNS - 1
        for old_dir in subdirs[keep_count:]:
            try:
                shutil.rmtree(old_dir)
                print(f"   Removed old screenshot run: {os.path.basename(old_dir)}")
            except OSError as e:
                print(f"   Could not remove {old_dir}: {e}")
    except OSError:
        pass


def _screenshot(driver, step_name):
    global _screenshot_dir
    if _screenshot_dir is None:
        base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "screenshots",
        )
        env_run = os.environ.get("VC_SCREENSHOT_RUN_DIR")
        if env_run:
            _screenshot_dir = os.path.abspath(env_run)
            _prune_old_screenshot_runs(base)
            os.makedirs(_screenshot_dir, exist_ok=True)
        else:
            _prune_old_screenshot_runs(base)
            _screenshot_dir = os.path.join(base, datetime.now().strftime("%Y%m%d_%H%M%S"))
            os.makedirs(_screenshot_dir, exist_ok=True)
    path = os.path.join(_screenshot_dir, f"{step_name}.png")
    driver.save_screenshot(path)
    print(f"   Screenshot: {path}")


def _open_overflow_menu(driver):
    """Open the upper-right overflow menu (snowman / kebab icon)."""
    kebab_span = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "span.icon-kebab-menu"))
    )
    menu_btn = kebab_span.find_element(By.XPATH, "./parent::*")
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable(menu_btn))
    menu_btn.click()
    print("Clicked overflow menu (snowman / icon-kebab-menu)")


def _select_menu_item(driver, label):
    menu_link_xpath = f"//a[contains(@class,'menu__link') and contains(.,'{label}')]"
    try:
        item = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, menu_link_xpath))
        )
        item.click()
        print(f"Selected {label} from overflow menu")
        return
    except Exception:
        pass

    clicked = driver.execute_script(
        """
        var label = arguments[0];
        var links = document.querySelectorAll('a.menu__link, [role="menuitem"], li, button');
        for (var e of links) {
            if (e.innerText && e.innerText.trim() === label) {
                e.click();
                return true;
            }
        }
        return false;
        """,
        label,
    )
    if clicked:
        print(f"Selected {label} via JS fallback")
        return
    raise AssertionError(f"Could not locate {label} menu item")


def _wait_for_continue_modal(driver, timeout=10):
    modal_xpath = (
        "//*[contains(@class,'modal') or contains(@role,'dialog') or contains(@class,'dialog')]"
        "//button[normalize-space()='Continue' or contains(., 'Continue')]"
    )
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, modal_xpath))
    )


def _click_continue_modal(driver):
    try:
        btn = _wait_for_continue_modal(driver, timeout=10)
        btn.click()
        print("Clicked Continue on popup modal")
        return
    except Exception:
        pass

    clicked = driver.execute_script(
        """
        var modals = document.querySelectorAll(
            '[role="dialog"], .modal, [class*="modal"], [class*="dialog"]'
        );
        for (var m of modals) {
            var btns = m.querySelectorAll('button,a');
            for (var b of btns) {
                if ((b.innerText || '').trim() === 'Continue') {
                    b.click();
                    return true;
                }
            }
        }
        return false;
        """
    )
    if clicked:
        print("Clicked Continue via JS fallback")
        return
    raise AssertionError("Continue button not found on Virtual Care popup modal")


_COUNT_TASK_ROWS_JS = """
var rows = document.querySelectorAll('.virtualScroll.vertical > .device-list');
var visible = 0;
for (var row of rows) {
    if (!row.offsetParent) continue;
    var text = (row.innerText || '').trim();
    if (!text) continue;
    visible++;
}
return visible;
"""


def _count_visible_task_rows(driver):
    return driver.execute_script(_COUNT_TASK_ROWS_JS)


_GET_TASK_STATUS_COUNTS_JS = """
var ribbon = {};
var tiles = document.querySelectorAll('.task-status-ribbon__tile');
for (var tile of tiles) {
    if (!tile.offsetParent) continue;
    var label = tile.querySelector('.task-status-ribbon__label');
    var count = tile.querySelector('.task-status-ribbon__count');
    if (!label || !count) continue;
    var name = (label.innerText || '').trim();
    var value = parseInt((count.innerText || '0').trim(), 10);
    if (name) ribbon[name] = isNaN(value) ? 0 : value;
}

var rowCounts = {};
var statusClassMap = [
    ['in-progress', 'In Progress'],
    ['incomplete', 'Incomplete'],
    ['ready', 'Ready'],
    ['completed', 'Completed'],
    ['deferred', 'Deferred'],
    ['documentation', 'Documentation'],
    ['queued', 'Queued'],
    ['declined', 'Patient Declined'],
    ['chart-review', 'Chart Review'],
];
var rows = document.querySelectorAll('.virtualScroll.vertical > .device-list');
for (var row of rows) {
    if (!row.offsetParent) continue;
    var cls = ' ' + (row.className || '').toLowerCase() + ' ';
    var status = null;
    for (var pair of statusClassMap) {
        if (cls.indexOf(' ' + pair[0] + ' ') !== -1) {
            status = pair[1];
            break;
        }
    }
    if (!status) continue;
    rowCounts[status] = (rowCounts[status] || 0) + 1;
}
return { ribbon: ribbon, rows: rowCounts };
"""


def _get_task_status_counts(driver):
    return driver.execute_script(_GET_TASK_STATUS_COUNTS_JS)


def _format_status_counts(counts):
    if not counts:
        return "none"
    return ", ".join(f"{status}: {count}" for status, count in counts.items())


def _log_vc_result(message):
    print(message)
    _append_run_vc_log(message)


def _log_task_status_summary(driver):
    """Read ribbon and visible-row status counts and write them to the log."""
    status_data = _get_task_status_counts(driver)
    ribbon_counts = status_data.get("ribbon") or {}
    row_counts = status_data.get("rows") or {}

    _log_vc_result("VC status ribbon counts: " + _format_status_counts(ribbon_counts))
    _log_vc_result("VC visible task row counts by status: " + _format_status_counts(row_counts))
    return {"ribbon": ribbon_counts, "rows": row_counts}


def _wait_for_task_list_loaded(driver, timeout=30):
    """Wait for the VC task list to finish loading."""
    print("Waiting for Virtual Care task list to finish loading...")
    _wait_for_task_table_ready(driver, timeout=timeout)


def _wait_for_task_table_ready(driver, timeout=30):
    def list_ready(d):
        return d.execute_script(
            """
            var busy = document.querySelector('[aria-busy="true"]');
            if (busy) {
                var busyStyle = window.getComputedStyle(busy);
                if (busyStyle.display !== 'none' && busyStyle.visibility !== 'hidden') {
                    return false;
                }
            }

            var loaders = document.querySelectorAll(
                '.loading, .loader, [class*="loading"], [class*="loader"], [class*="spinner"]'
            );
            for (var el of loaders) {
                var style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                if (parseFloat(style.opacity || '1') < 0.1) continue;
                var rect = el.getBoundingClientRect();
                if (rect.width > 80 && rect.height > 80) return false;
            }

            var rows = document.querySelectorAll('.virtualScroll.vertical > .device-list');
            for (var row of rows) {
                if (!row.offsetParent) continue;
                var text = (row.innerText || '').trim();
                if (!text) continue;
                return true;
            }

            var body = document.body.innerText || '';
            return body.indexOf('No tasks found') !== -1;
            """
        )

    try:
        WebDriverWait(driver, timeout).until(list_ready)
        time.sleep(1)
        print("Task list finished loading")
    except Exception:
        print(f"Task list wait timed out after {timeout}s; capturing screenshot anyway")
        time.sleep(3)


def _location_filter_is_active(driver):
    return driver.execute_script(
        """
        var loc = document.querySelector('div.dropdown.location');
        if (!loc) return false;
        return !!loc.querySelector('.icon-wrap.highlight');
        """
    )


def _clear_location_filter(driver):
    """Open the Location filter and choose Clear All (+ Ok) when a filter is active."""
    if not _location_filter_is_active(driver):
        message = "Location filter not set; skipping Clear All"
        print(message)
        _log_vc_result(message)
        return False

    location_dropdown = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "div.dropdown.location"))
    )
    location_dropdown.click()
    print("Opened Location filter dropdown")
    time.sleep(0.5)

    clear_btn = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "div.dropdown.location button.app-tree-tool-set-reset")
        )
    )
    clear_btn.click()
    print("Selected Clear All in Location filter")

    ok_btn = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//div[contains(@class,'dropdown location')]//button[normalize-space()='Ok']")
        )
    )
    ok_btn.click()
    message = "Cleared location filter (Clear All + Ok)"
    print(message)
    _log_vc_result(message)
    time.sleep(0.5)
    return True


def _select_all_pending_tasks(driver):
    """Open the nursing date picker and choose All Pending Tasks."""
    picker_locators = [
        (
            By.XPATH,
            "//div[contains(@class,'nursingDatePicker') and contains(., 'All Pending Tasks')]",
        ),
        (By.CSS_SELECTOR, "div.nursingDatePicker"),
        (By.XPATH, "//div[contains(@class,'nursingDatePicker')]"),
    ]

    picker = None
    for by, sel in picker_locators:
        try:
            for element in driver.find_elements(by, sel):
                if element.is_displayed():
                    picker = element
                    break
            if picker:
                break
        except Exception:
            continue

    if not picker:
        raise AssertionError("Could not find nursingDatePicker (All Pending Tasks) dropdown")

    WebDriverWait(driver, 5).until(EC.element_to_be_clickable(picker))
    picker.click()
    print("Opened nursingDatePicker dropdown")
    time.sleep(0.5)

    option_locators = [
        (By.XPATH, "//*[normalize-space()='All Pending Tasks']"),
        (
            By.XPATH,
            "//*[contains(@class,'dropdown') or contains(@class,'menu') or contains(@class,'option')]"
            "[normalize-space()='All Pending Tasks']",
        ),
    ]

    selected = False
    for by, sel in option_locators:
        try:
            options = driver.find_elements(by, sel)
            for option in options:
                if not option.is_displayed():
                    continue
                if option == picker:
                    continue
                WebDriverWait(driver, 3).until(EC.element_to_be_clickable(option))
                option.click()
                selected = True
                print("Selected All Pending Tasks from dropdown")
                break
            if selected:
                break
        except Exception:
            continue

    if not selected:
        if "All Pending Tasks" in picker.text:
            print("All Pending Tasks already selected in nursingDatePicker")
            return
        raise AssertionError("Could not select All Pending Tasks from dropdown")


def _append_run_vc_log(message):
    """Append a line to the run_vc.log file for this test run."""
    log_dir = os.environ.get("VC_SCREENSHOT_RUN_DIR")
    if not log_dir:
        return
    log_file = os.path.join(log_dir, "run_vc.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{message}\n")
    except OSError as e:
        print(f"   Could not write to run_vc.log: {e}")


def _wait_for_pending_tasks_populated(driver, timeout=30):
    """Wait for the All Pending Tasks filter to finish loading task rows."""
    print("Waiting for All Pending Tasks to populate...")
    _wait_for_task_table_ready(driver, timeout=timeout)

    row_count = _count_visible_task_rows(driver)
    body = driver.find_element(By.TAG_NAME, "body").text
    if row_count > 0:
        message = f"All Pending Tasks populated with {row_count} visible task row(s)"
    elif "No tasks found" in body:
        message = "All Pending Tasks loaded (no tasks found)"
        row_count = 0
    else:
        message = "All Pending Tasks loaded (0 visible task rows)"
        row_count = 0

    print(message)
    return row_count


def _verify_virtual_care_page(driver):
    deadline = time.time() + 20
    while time.time() < deadline:
        url = driver.current_url.lower()
        body = driver.find_element(By.TAG_NAME, "body").text
        on_task_queue = "virtual-care" in url and "Virtual Care" in body
        on_call_page = (
            "/rooms/" in url
            and "Drop In" in body
            and "Video Call" in body
        )
        if on_task_queue or on_call_page:
            if on_task_queue:
                print("Virtual Care task queue page loaded")
            else:
                print("Virtual Care call page loaded (room with Drop In)")
            print(f"On Virtual Care page: {driver.current_url}")
            return
        time.sleep(0.5)

    body_preview = driver.find_element(By.TAG_NAME, "body").text[:500]
    raise AssertionError(
        f"Expected Virtual Care page, got URL={driver.current_url}. "
        f"Body preview={body_preview!r}"
    )


def test_vc(driver):
    """Log in, open Virtual Care from the overflow menu, and verify arrival."""
    test_login_success(driver)
    _screenshot(driver, "01_after_login")

    _open_overflow_menu(driver)
    time.sleep(1)
    _screenshot(driver, "02_menu_open")

    _select_menu_item(driver, "Virtual Care")
    _screenshot(driver, "03_virtual_care_selected")

    _click_continue_modal(driver)
    _screenshot(driver, "04_after_continue")

    _verify_virtual_care_page(driver)
    _wait_for_task_list_loaded(driver)
    _screenshot(driver, "05_virtual_care_page")

    _clear_location_filter(driver)
    _screenshot(driver, "06_location_filter_cleared")
    _wait_for_task_list_loaded(driver)

    _select_all_pending_tasks(driver)
    _screenshot(driver, "07_all_pending_tasks_selected")
    pending_task_count = _wait_for_pending_tasks_populated(driver)
    _screenshot(driver, "08_all_pending_tasks_populated")
    _log_task_status_summary(driver)
    _log_vc_result(
        f"VC test result: {pending_task_count} pending task(s) in All Pending Tasks"
    )
