import os
import shutil
import time
from datetime import datetime

from src.tests.test_login import test_login_success, driver
from src.tests.virtual_monitoring_helpers import (
    disconnect_active_rooms,
    ensure_add_room_modal_open,
    go_to_first_page,
    handle_browser_permission_prompt,
    handle_permission_popups_on_page_load,
    open_add_new_room_section,
    open_area_list_and_select_online_rooms,
    run_monitoring_with_ptz,
    select_facility_in_modal,
    validate_video_sessions_across_pages,
)

# this file imports the original test and can be extended with additional steps

# Screenshot directory for this run (set at first use)
_screenshot_dir = None

# Keep at most this many screenshot run directories (oldest are deleted)
_MAX_SCREENSHOT_RUNS = 7


def _prune_old_screenshot_runs(screenshots_base: str) -> None:
    """Keep only the most recent _MAX_SCREENSHOT_RUNS - 1 runs so after this run we have at most _MAX_SCREENSHOT_RUNS."""
    if not os.path.isdir(screenshots_base):
        return
    try:
        subdirs = [
            os.path.join(screenshots_base, d)
            for d in os.listdir(screenshots_base)
            if os.path.isdir(os.path.join(screenshots_base, d))
        ]
        # Sort by name (timestamp YYYYMMDD_HHMMSS) descending = newest first
        subdirs.sort(key=os.path.basename, reverse=True)
        keep_count = _MAX_SCREENSHOT_RUNS - 1  # leave room for this run
        for old_dir in subdirs[keep_count:]:
            try:
                shutil.rmtree(old_dir)
                print(f"   🗑️  Removed old screenshot run: {os.path.basename(old_dir)}")
            except OSError as e:
                print(f"   ⚠️  Could not remove {old_dir}: {e}")
    except OSError:
        pass


def _screenshot(driver, step_name):
    """Save a screenshot to screenshots/<run_timestamp>/<step_name>.png"""
    global _screenshot_dir
    if _screenshot_dir is None:
        base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "screenshots",
        )
        env_run = os.environ.get("VM_SCREENSHOT_RUN_DIR")
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
    print(f"   📷 Screenshot: {path}")


def test_login_with_extra_step(driver):
    """Wrapper around base login that performs another validation afterwards.

    After the standard login flow completes, open the user/menu control in the
    upper right of the page and select the "Virtual Monitoring" item.  This
    emulates the user navigating to that section of the application.
    """
    # perform the base login sequence
    test_login_success(driver)
    _screenshot(driver, "01_after_login")

    # now click the top‑right kebab menu (three stacked dots) and choose Virtual Monitoring
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # open the "more" menu via the kebab icon: <span class="initials-icon icon-kebab-menu"></span>
    clicked_menu = False
    try:
        kebab_span = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.icon-kebab-menu"))
        )
        # click the clickable parent (button/wrapper) that contains the icon
        menu_btn = kebab_span.find_element(By.XPATH, "./parent::*")
        WebDriverWait(driver, 3).until(EC.element_to_be_clickable(menu_btn))
        menu_btn.click()
        print("Clicked overflow menu (icon-kebab-menu)")
        clicked_menu = True
    except Exception:
        pass
    if not clicked_menu:
        raise AssertionError(
            "Could not find kebab menu (span.icon-kebab-menu). "
            "Ensure Command Center page is loaded."
        )

    time.sleep(1)
    _screenshot(driver, "02_menu_open")

    # once menu is visible, click the Virtual Monitoring item
    vm_xpath = "//*[contains(text(), 'Virtual Monitoring')]"
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, vm_xpath))).click()
        print('✅ Selected Virtual Monitoring from overflow menu')
    except Exception:
        # fallback click by text via JS again
        clicked = driver.execute_script(
            "var els=document.querySelectorAll('*');"
            "for(var e of els){ if(e.innerText && e.innerText.includes('Virtual Monitoring')){e.click();return true;}} return false;"
        )
        if clicked:
            print('✅ Selected Virtual Monitoring via JS fallback')
        else:
            raise AssertionError('Could not locate Virtual Monitoring menu item')
    _screenshot(driver, "03_virtual_monitoring_selected")

    # verify we navigated away - new URL should mention virtual
    time.sleep(2)
    # after attempting the click try to detect navigation
    if 'virtual' in driver.current_url.lower():
        print(f"✅ on Virtual Monitoring page: {driver.current_url}")
    else:
        # if menu interaction didn't work, directly visit expected path
        print(f"⚠️ after click still on {driver.current_url}, forcing direct navigation")
        driver.get('https://lab.care.ai/virtual-monitoring')
        time.sleep(2)
        if 'virtual' in driver.current_url.lower():
            print(f"✅ navigated to virtual-monitoring via URL: {driver.current_url}")
        else:
            raise AssertionError(f"Unable to reach virtual-monitoring page, current URL {driver.current_url}")

    # wait for page to fully load - look for common indicators
    try:
        WebDriverWait(driver, 5).until(
            lambda d: len(d.find_elements(By.TAG_NAME, 'button')) > 0
        )
        print("✓ Virtual Monitoring page loaded (buttons detected)")
    except:
        print("⚠️ Timeout waiting for buttons to appear on Virtual Monitoring page")
    
    time.sleep(1)
    _screenshot(driver, "04_virtual_monitoring_page")

    # now verify "Add Room" button exists in upper right and is active
    add_room_locators = [
        "//button[contains(text(), 'Add Room')]",
        "//button[contains(., 'Add Room')]",
        "//button[@aria-label*='Add' and @aria-label*='Room']",
        "//a[contains(text(), 'Add Room')]",
        "//button[contains(text(), 'add room')]",  # case-insensitive variant
    ]
    add_room_btn = None
    for sel in add_room_locators:
        try:
            elements = driver.find_elements(By.XPATH, sel)
            if elements:
                add_room_btn = elements[0]
                print(f"✓ Found Add Room button using {sel}")
                break
        except Exception:
            continue

    if not add_room_btn:
        # Debug: print all buttons and text on the page
        all_buttons = driver.find_elements(By.TAG_NAME, 'button')
        button_texts = [btn.text for btn in all_buttons]
        print(f"⚠️ Add Room button not found")
        print(f"   All buttons on page ({len(all_buttons)} total): {button_texts}")
        print(f"   Current URL: {driver.current_url}")
        print(f"   Page title: {driver.title}")
        
        # Try to print page body text to diagnose
        body_text = driver.find_element(By.TAG_NAME, 'body').text[:500]
        print(f"   Page text (first 500 chars): {body_text}")
        
        raise AssertionError('Add Room button not found on Virtual Monitoring page')

    # check if button is enabled/active
    is_enabled = add_room_btn.is_enabled()
    is_displayed = add_room_btn.is_displayed()

    if not is_displayed:
        raise AssertionError('Add Room button is not visible')
    if not is_enabled:
        raise AssertionError('Add Room button is disabled/inactive')

    print('✅ Add Room button is visible and active')
    add_room_btn.click()
    print('✅ Clicked Add Room button (first click)')
    time.sleep(1)
    _screenshot(driver, "05_add_room_first_click")

    # If there are Active Rooms, disconnect each (uncheck box to the right of room, then Yes in modal)
    print("⏳ Checking for Active Rooms to disconnect...")
    disconnect_active_rooms(driver)
    time.sleep(0.5)
    # After disconnecting, menus may collapse; expand "Add a New Room" so Facility selection is visible
    print("⏳ Expanding Add a New Room section (menus may have collapsed after disconnect)...")
    open_add_new_room_section(driver)
    time.sleep(0.5)

    # After clicking Add Room:
    # 1. Browser-level permission prompt appears (microphone)
    # 2. App modal appears with "Enable microphone to monitor rooms" and "Ok" button
    # We need to handle both before clicking Add Room again
    
    print("⏳ Handling browser permission prompt...")
    handle_browser_permission_prompt(driver)
    print("✅ Browser permission prompt handled")
    
    print("⏳ Handling app permission modal...")
    handle_permission_popups_on_page_load(driver)
    print("✅ App permission modal handled")
    
    time.sleep(1)
    _screenshot(driver, "06_after_permissions")

    # Modal may have closed (e.g. after permissions or when there were no active rooms). Reopen if needed.
    print("⏳ Ensuring Add Room modal is open...")
    ensure_add_room_modal_open(driver)
    time.sleep(0.5)

    # Move to Add a New Room section (facility + area); works whether we had active rooms or not
    print("⏳ Ensuring Add a New Room section is selected...")
    open_add_new_room_section(driver)
    time.sleep(0.5)
    _screenshot(driver, "07_add_new_room_section")

    # Select Facility -> Vineland Rack Room
    print("⏳ Selecting facility (Vineland Rack Room)...")
    select_facility_in_modal(driver, "Vineland Rack Room")
    print("✅ Facility selection completed")
    time.sleep(0.5)
    _screenshot(driver, "08_facility_selected")

    # Open Area list and select ALL items that show online (green cloud) by clicking the box on the right
    print("⏳ Opening Area list and selecting first 12 online rooms (green cloud)...")
    open_area_list_and_select_online_rooms(driver)
    print("✅ Area selection completed")
    _screenshot(driver, "09_areas_selected")

    # Dismiss the Add Room modal by clicking the Add Room button again (before starting the monitor timer)
    print("⏳ Dismissing Add Room modal...")
    dismiss_add_room_btn = None
    for sel in add_room_locators:
        try:
            elements = driver.find_elements(By.XPATH, sel)
            if elements and elements[0].is_displayed() and elements[0].is_enabled():
                dismiss_add_room_btn = elements[0]
                break
        except Exception:
            continue
    if dismiss_add_room_btn:
        dismiss_add_room_btn.click()
        print("✅ Add Room modal dismissed")
        time.sleep(0.5)
    else:
        print("⚠️ Add Room button not found to dismiss modal; continuing anyway")

    # Wait for video grid to load, then validate each session shows video (before the long monitoring period)
    time.sleep(2)
    _screenshot(driver, "10_after_modal_dismissed")
    print("⏳ Validating video sessions across all pages...")
    validation = validate_video_sessions_across_pages(
        driver, check_quality=True, screenshot_dir=_screenshot_dir
    )
    _screenshot(driver, "11_after_video_validation")
    if validation["errors"]:
        print(f"   ⚠️ Validation notes: {validation['errors']}")
    if validation["total_sessions_no_video"] > 0 and validation["total_sessions_with_video"] == 0:
        raise AssertionError(
            f"No sessions had video. Checked {validation['pages_checked']} page(s). "
            f"Errors: {validation['errors']}"
        )

    # Return to page 1 before starting the monitoring timer
    print("⏳ Going back to page 1...")
    go_to_first_page(driver)
    time.sleep(0.5)
    _screenshot(driver, "11b_page1_before_monitoring")

    # Monitor for 3 minutes; every 10s randomly select a room and run random PTZ (up/down/left/right)
    monitor_seconds = 180
    interval_seconds = 10
    print(f"⏳ Monitoring selected rooms for {monitor_seconds}s with PTZ every {interval_seconds}s...")
    run_monitoring_with_ptz(driver, duration_seconds=monitor_seconds, interval_seconds=interval_seconds)
    _screenshot(driver, "12_after_three_minute_monitoring")

    # Run through videos again after monitoring; ensure they're still good and capture any that aren't
    print("⏳ Re-validating video sessions across all pages (post-monitoring)...")
    post_validation = validate_video_sessions_across_pages(
        driver, check_quality=True, screenshot_dir=_screenshot_dir
    )
    _screenshot(driver, "13_after_post_monitoring_validation")
    if post_validation["errors"]:
        print(f"   ⚠️ Post-monitoring validation notes: {post_validation['errors']}")
    if post_validation["quality_issues"]:
        print(f"   ⚠️ Post-monitoring quality issues: {post_validation['quality_issues']}")
    if post_validation["total_sessions_no_video"] > 0 and post_validation["total_sessions_with_video"] == 0:
        raise AssertionError(
            f"After monitoring: no sessions had video. Checked {post_validation['pages_checked']} page(s). "
            f"Errors: {post_validation['errors']}"
        )
