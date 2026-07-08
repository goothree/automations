"""Reusable Virtual Monitoring session setup for automated tests."""

import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.config import settings
from src.tests.virtual_monitoring_helpers import (
    disconnect_active_rooms,
    ensure_add_room_modal_open,
    handle_browser_permission_prompt,
    handle_permission_popups_on_page_load,
    open_add_new_room_section,
    open_area_list_and_select_online_rooms,
    select_facility_in_modal,
)


ADD_ROOM_LOCATORS = [
    "//button[contains(text(), 'Add Room')]",
    "//button[contains(., 'Add Room')]",
    "//button[@aria-label*='Add' and @aria-label*='Room']",
    "//a[contains(text(), 'Add Room')]",
]


def _click_add_room_button(driver):
    for sel in ADD_ROOM_LOCATORS:
        try:
            elements = driver.find_elements(By.XPATH, sel)
            for el in elements:
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    return True
        except Exception:
            continue
    return False


def navigate_to_virtual_monitoring(driver, vm_path=None):
    """Open Virtual Monitoring from Command Center or direct URL."""
    vm_path = vm_path or settings.ida5376_vm_path
    base = settings.base_url.rstrip("/")
    target_url = f"{base}{vm_path}"

    clicked_menu = False
    try:
        kebab_span = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span.icon-kebab-menu"))
        )
        menu_btn = kebab_span.find_element(By.XPATH, "./parent::*")
        WebDriverWait(driver, 3).until(EC.element_to_be_clickable(menu_btn))
        menu_btn.click()
        clicked_menu = True
    except Exception:
        pass

    if clicked_menu:
        vm_xpath = "//*[contains(text(), 'Virtual Monitoring')]"
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, vm_xpath))
            ).click()
        except Exception:
            clicked = driver.execute_script(
                "var els=document.querySelectorAll('*');"
                "for(var e of els){ if(e.innerText && e.innerText.includes('Virtual Monitoring')){e.click();return true;}} return false;"
            )
            if not clicked:
                driver.get(target_url)
    else:
        driver.get(target_url)

    time.sleep(2)
    if "virtual" not in driver.current_url.lower():
        driver.get(target_url)
        time.sleep(2)

    if "virtual" not in driver.current_url.lower():
        raise AssertionError(
            f"Unable to reach Virtual Monitoring page, current URL: {driver.current_url}"
        )

    WebDriverWait(driver, 10).until(
        lambda d: len(d.find_elements(By.TAG_NAME, "button")) > 0
    )


def add_rooms_via_modal(driver, facility, min_rooms=2):
    """Use Add Room modal to connect online rooms to the monitoring wall."""
    if not _click_add_room_button(driver):
        raise AssertionError("Add Room button not found on Virtual Monitoring page")

    time.sleep(1)
    disconnect_active_rooms(driver)
    open_add_new_room_section(driver)
    handle_browser_permission_prompt(driver)
    handle_permission_popups_on_page_load(driver)
    ensure_add_room_modal_open(driver)
    open_add_new_room_section(driver)
    select_facility_in_modal(driver, facility)
    open_area_list_and_select_online_rooms(driver)

    dismiss_btn = None
    for sel in ADD_ROOM_LOCATORS:
        try:
            elements = driver.find_elements(By.XPATH, sel)
            for el in elements:
                if el.is_displayed() and el.is_enabled():
                    dismiss_btn = el
                    break
            if dismiss_btn:
                break
        except Exception:
            continue
    if dismiss_btn:
        dismiss_btn.click()
        time.sleep(1)


def count_videos_with_frames(driver):
    """Return count of visible video elements that have decoded frames."""
    return driver.execute_script(
        """
        var videos = document.querySelectorAll('video');
        var count = 0;
        for (var i = 0; i < videos.length; i++) {
            var v = videos[i];
            if (!v.offsetParent) continue;
            var w = v.videoWidth || 0;
            var h = v.videoHeight || 0;
            if (v.readyState >= 2 && w > 0 && h > 0) count++;
        }
        return count;
        """
    )


def wait_for_videos(driver, min_count=1, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = count_videos_with_frames(driver)
        if count >= min_count:
            return count
        time.sleep(1)
    return count_videos_with_frames(driver)


def open_monitoring_wall_with_rooms(driver, facility=None, min_rooms=2, vm_path=None):
    """Navigate to VM, add rooms, and wait for live video tiles."""
    facility = facility or settings.ida5376_facility
    navigate_to_virtual_monitoring(driver, vm_path=vm_path)
    add_rooms_via_modal(driver, facility, min_rooms=min_rooms)
    time.sleep(2)
    video_count = wait_for_videos(driver, min_count=1, timeout=45)
    return {
        "url": driver.current_url,
        "facility": facility,
        "video_count": video_count,
    }
