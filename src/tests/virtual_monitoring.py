import os
import time
from datetime import datetime

from src.tests.test_login import test_login_success, driver
from src.tests.virtual_monitoring_helpers import (
    disconnect_active_rooms,
    ensure_add_room_modal_open,
    handle_browser_permission_prompt,
    handle_permission_popups_on_page_load,
    open_add_new_room_section,
    open_area_list_and_select_online_rooms,
    select_facility_in_modal,
)

# this file imports the original test and can be extended with additional steps

# Screenshot directory for this run (set at first use)
_screenshot_dir = None


def _screenshot(driver, step_name):
    """Save a screenshot to screenshots/<run_timestamp>/<step_name>.png"""
    global _screenshot_dir
    if _screenshot_dir is None:
        _screenshot_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "screenshots",
            datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
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

    # now click the top‑right menu (if present) and choose Virtual Monitoring
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # open the "more" menu - usually three stacked dots in upper right
    dot_locators = [
        # unicode vertical ellipsis, three dots, aria-label hints
        "//button[contains(., '⋮')]",
        "//button[contains(., '...')]",
        "//button[@aria-label='More']",
        "//button[contains(@class,'ellipsis') or contains(@class,'more')]",
    ]
    clicked_menu = False
    for sel in dot_locators:
        try:
            btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, sel)))
            btn.click()
            print(f"Clicked overflow menu using {sel}")
            clicked_menu = True
            break
        except Exception:
            continue
    if not clicked_menu:
        print('⚠️ overflow menu button not found; attempting JS fallback')
        driver.execute_script(
            "var els=document.querySelectorAll('button');"
            "for(var e of els){ if(e.innerText && (e.innerText.trim()==='⋮' || e.innerText.trim()==='...')){e.click();return;} }"
        )
        time.sleep(1)

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
    print("⏳ Opening Area list and selecting all online rooms (green cloud)...")
    open_area_list_and_select_online_rooms(driver)
    print("✅ Area selection completed")
    _screenshot(driver, "09_areas_selected")

    # Monitor the selected rooms for at least one minute
    monitor_seconds = 60
    print(f"⏳ Monitoring selected rooms for {monitor_seconds} seconds...")
    time.sleep(monitor_seconds)
    print("✅ Monitoring period completed (1 minute)")
    _screenshot(driver, "10_after_one_minute_monitoring")
