import os
import re
import shutil
import time
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.config import settings
from src.tests.ida_5376_helpers import get_video_playback_state
from src.tests.test_login import test_login_success, driver
from src.tests.virtual_monitoring_helpers import handle_permission_popups_on_page_load

_screenshot_dir = None
_MAX_SCREENSHOT_RUNS = 7
VM_BETA_MENU_LABEL = "Virtual Monitoring *"


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
        env_run = os.environ.get("VMBETA_SCREENSHOT_RUN_DIR")
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


def _log_vmbeta_result(message):
    print(message)
    _append_run_vmbeta_log(message)


def _append_run_vmbeta_log(message):
    log_dir = os.environ.get("VMBETA_SCREENSHOT_RUN_DIR")
    if not log_dir:
        return
    log_file = os.path.join(log_dir, "run_vmbeta.log")
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{message}\n")
    except OSError as e:
        print(f"   Could not write to run_vmbeta.log: {e}")


def _open_overflow_menu(driver):
    """Open the upper-right overflow menu (snowman / kebab icon)."""
    kebab_span = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "span.icon-kebab-menu"))
    )
    menu_btn = kebab_span.find_element(By.XPATH, "./parent::*")
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable(menu_btn))
    menu_btn.click()
    print("Clicked overflow menu (snowman / icon-kebab-menu)")


def _select_vm_beta_menu_item(driver):
    """Select Virtual Monitoring * from the overflow menu (not standard Virtual Monitoring)."""
    menu_link_xpath = (
        f"//a[contains(@class,'menu__link') and normalize-space(.)='{VM_BETA_MENU_LABEL}']"
    )
    try:
        item = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, menu_link_xpath))
        )
        item.click()
        print(f"Selected {VM_BETA_MENU_LABEL} from overflow menu")
        return
    except Exception:
        pass

    clicked = driver.execute_script(
        """
        var label = arguments[0];
        var links = document.querySelectorAll('a.menu__link, [role="menuitem"], li, button, a');
        for (var e of links) {
            if (e.innerText && e.innerText.trim() === label) {
                e.click();
                return true;
            }
        }
        return false;
        """,
        VM_BETA_MENU_LABEL,
    )
    if clicked:
        print(f"Selected {VM_BETA_MENU_LABEL} via JS fallback")
        return

    raise AssertionError(f"Could not locate {VM_BETA_MENU_LABEL} menu item")


def _click_continue_modal(driver):
    """Dismiss the leave-module confirmation dialog if it appears."""
    modal_xpath = (
        "//*[contains(@class,'modal') or contains(@role,'dialog') or contains(@class,'dialog')]"
        "//button[normalize-space()='Continue' or contains(., 'Continue')]"
    )
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, modal_xpath))
        )
        btn.click()
        print("Clicked Continue on navigation confirmation modal")
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
        print("Clicked Continue on navigation confirmation modal via JS fallback")
        return

    body = driver.find_element(By.TAG_NAME, "body").text
    if "Confirm Navigation" in body or "leave this module" in body.lower():
        raise AssertionError("Navigation confirmation modal visible but Continue not found")


def _wait_for_vm_beta_page(driver, timeout=20):
    """Wait until Virtual Monitoring * page indicators are present."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = driver.current_url.lower()
        body = driver.find_element(By.TAG_NAME, "body").text
        on_vm_route = "virtual" in url
        has_vm_ui = (
            "Add Room" in body
            or "Active Rooms" in body
            or len(driver.find_elements(By.TAG_NAME, "video")) > 0
        )
        if on_vm_route and has_vm_ui:
            print(f"Virtual Monitoring * page loaded: {driver.current_url}")
            return
        time.sleep(0.5)

    beta_path = settings.ida5376_beta_vm_path
    if beta_path:
        target = f"{settings.base_url.rstrip('/')}{beta_path}"
        print(f"VM* page not detected; navigating directly to {target}")
        driver.get(target)
        time.sleep(2)
        if "virtual" in driver.current_url.lower():
            print(f"Virtual Monitoring * page loaded via fallback URL: {driver.current_url}")
            return

    body_preview = driver.find_element(By.TAG_NAME, "body").text[:500]
    raise AssertionError(
        f"Expected Virtual Monitoring * page, got URL={driver.current_url}. "
        f"Body preview={body_preview!r}"
    )


_GET_ACTIVE_SESSIONS_JS = """
var sessions = [];
var videos = document.querySelectorAll('video');
for (var v of videos) {
    if (!v.offsetParent) continue;
    var tile = v;
    for (var i = 0; i < 6 && tile; i++) {
        var cls = (tile.className || '').toLowerCase();
        if (cls.indexOf('tile') !== -1 || cls.indexOf('room') !== -1
            || cls.indexOf('card') !== -1 || cls.indexOf('session') !== -1) {
            break;
        }
        tile = tile.parentElement;
    }
    var label = '';
    if (tile && tile !== document.body) {
        label = (tile.innerText || '').trim().split('\\n').filter(Boolean)[0] || '';
    }
    sessions.push({
        label: label.substring(0, 120),
        hasLiveVideo: v.readyState >= 2 && (v.videoWidth || 0) > 0 && (v.videoHeight || 0) > 0,
        videoWidth: v.videoWidth || 0,
        videoHeight: v.videoHeight || 0,
        paused: !!v.paused,
        readyState: v.readyState || 0,
    });
}
return sessions;
"""


def _parse_active_rooms_count(body_text):
    match = re.search(r"Active Rooms\s*\((\d+)\)", body_text)
    if match:
        return int(match.group(1))
    return None


def _inspect_active_monitoring_sessions(driver):
    """Detect active monitoring sessions on the VM* wall and return a summary dict."""
    time.sleep(2)
    handle_permission_popups_on_page_load(driver)

    playback = get_video_playback_state(driver)
    session_details = driver.execute_script(_GET_ACTIVE_SESSIONS_JS) or []
    body_text = driver.find_element(By.TAG_NAME, "body").text
    active_rooms_count = _parse_active_rooms_count(body_text)

    live_sessions = [s for s in session_details if s.get("hasLiveVideo")]
    visible_tiles = len(session_details)

    summary = {
        "url": driver.current_url,
        "visible_video_tiles": visible_tiles,
        "live_video_sessions": len(live_sessions),
        "total_visible_videos": playback.get("total", 0),
        "videos_with_frames": playback.get("withFrames", 0),
        "active_rooms_count": active_rooms_count,
        "sessions": session_details,
    }
    return summary


def _format_session_labels(sessions):
    if not sessions:
        return "none"
    labels = []
    for index, session in enumerate(sessions, start=1):
        label = (session.get("label") or "").strip()
        if not label:
            label = f"Session {index}"
        status = "live" if session.get("hasLiveVideo") else "no video"
        labels.append(f"{label} ({status})")
    return "; ".join(labels)


def _log_active_session_summary(summary):
    active_rooms = summary.get("active_rooms_count")
    active_rooms_text = (
        str(active_rooms) if active_rooms is not None else "not shown in UI"
    )

    if summary["live_video_sessions"] > 0 or summary["visible_video_tiles"] > 0:
        status = "active monitoring sessions detected"
    else:
        status = "no active monitoring sessions detected"

    _log_vmbeta_result(f"VM* result: {status}")
    _log_vmbeta_result(f"VM* URL: {summary['url']}")
    _log_vmbeta_result(
        "VM* session counts: "
        f"visible tiles={summary['visible_video_tiles']}, "
        f"live video={summary['live_video_sessions']}, "
        f"videos with frames={summary['videos_with_frames']}, "
        f"Active Rooms={active_rooms_text}"
    )
    _log_vmbeta_result(
        "VM* monitored sessions: " + _format_session_labels(summary.get("sessions") or [])
    )


def test_vmbeta(driver):
    """Log in, open Virtual Monitoring * from the overflow menu, and log active sessions."""
    test_login_success(driver)
    _screenshot(driver, "01_after_login")

    _open_overflow_menu(driver)
    time.sleep(1)
    _screenshot(driver, "02_menu_open")

    _select_vm_beta_menu_item(driver)
    _screenshot(driver, "03_virtual_monitoring_star_selected")

    _click_continue_modal(driver)
    _screenshot(driver, "04_after_continue")

    time.sleep(2)
    _wait_for_vm_beta_page(driver)
    _screenshot(driver, "05_vm_beta_page")

    summary = _inspect_active_monitoring_sessions(driver)
    _screenshot(driver, "06_active_sessions_checked")
    _log_active_session_summary(summary)
