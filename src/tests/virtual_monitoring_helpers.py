"""Helper functions for virtual monitoring tests."""

import os
import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def disconnect_active_rooms(driver):
    """
    On the Virtual Monitoring page, find Active Rooms and disconnect each by
    clicking the box to the right of each room (to uncheck it), then clicking
    Yes in the confirmation modal. Repeats until no active rooms remain.
    """
    max_rooms = 50  # safety limit
    disconnected = 0

    while disconnected < max_rooms:
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            if "Active Rooms" not in body_text:
                break
            if "Active Rooms (0)" in body_text:
                break
        except Exception:
            break

        # Strategy 1: Find checkboxes inside the Active Rooms area (by container or by row)
        # Click first visible unchecked checkbox in a room row, then Yes
        found = False

        def _is_checked(el):
            try:
                if (el.get_attribute("tagName") or "").lower() == "input" and (el.get_attribute("type") or "").lower() == "checkbox":
                    return el.is_selected()
                if (el.get_attribute("role") or "").lower() == "checkbox":
                    return (el.get_attribute("aria-checked") or "").lower() == "true"
                return True
            except Exception:
                return True

        # Try: any checked checkbox near "Active Rooms" (only disconnect rooms that are currently connected)
        for xpath in [
            "//*[contains(., 'Active Rooms')]//input[@type='checkbox']",
            "//*[contains(., 'Active Rooms')]//*[@role='checkbox']",
            "//*[contains(., 'Active Rooms')]//*[contains(@class, 'checkbox') or contains(@class, 'toggle')]",
            "//input[@type='checkbox'][ancestor::*[contains(., 'Slot') or contains(., 'Active Rooms')]]",
            "//*[@role='checkbox'][ancestor::*[contains(., 'Slot') or contains(., 'Active Rooms')]]",
        ]:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if not el.is_displayed():
                        continue
                    if not _is_checked(el):
                        continue
                    try:
                        el.click()
                        found = True
                        disconnected += 1
                        print(f"   Disconnecting room ({disconnected}): clicked box")
                        time.sleep(0.5)
                        _click_yes_in_modal(driver)
                        time.sleep(0.5)
                        break
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", el)
                            found = True
                            disconnected += 1
                            print(f"   Disconnecting room ({disconnected}): clicked box via JS")
                            time.sleep(0.5)
                            _click_yes_in_modal(driver)
                            time.sleep(0.5)
                            break
                        except Exception:
                            continue
                if found:
                    break
            except Exception:
                continue

        if not found:
            # Strategy 2: Find room rows (text like "Slot ... / Rack ...") and click rightmost control in each
            row_candidates = driver.find_elements(
                By.XPATH,
                "//*[contains(., 'Slot') and contains(., '/') and string-length(normalize-space(.)) < 80]"
            )
            for row in row_candidates:
                if not row.is_displayed():
                    continue
                txt = (row.text or "").strip()
                if "Active Rooms" in txt or "Add a New Room" in txt or "Select Facility" in txt:
                    continue
                for control_xpath in [".//input[@type='checkbox']", ".//*[@role='checkbox']", ".//button", ".//*[contains(@class, 'checkbox')]"]:
                    try:
                        controls = row.find_elements(By.XPATH, control_xpath)
                        for ctrl in reversed(controls):
                            if not ctrl.is_displayed():
                                continue
                            if (ctrl.get_attribute("type") == "checkbox" or (ctrl.get_attribute("role") or "").lower() == "checkbox") and not _is_checked(ctrl):
                                continue
                            try:
                                ctrl.click()
                                found = True
                                disconnected += 1
                                print(f"   Disconnecting room ({disconnected}): clicked control in row")
                                time.sleep(0.5)
                                _click_yes_in_modal(driver)
                                time.sleep(0.5)
                                break
                            except Exception:
                                try:
                                    driver.execute_script("arguments[0].click();", ctrl)
                                    found = True
                                    disconnected += 1
                                    print(f"   Disconnecting room ({disconnected}): clicked via JS")
                                    time.sleep(0.5)
                                    _click_yes_in_modal(driver)
                                    time.sleep(0.5)
                                    break
                                except Exception:
                                    continue
                        if found:
                            break
                    except Exception:
                        continue
                if found:
                    break

        if not found:
            break

    if disconnected > 0:
        print(f"✅ Disconnected {disconnected} active room(s)")
    else:
        print("✓ No active rooms to disconnect")


def _click_yes_in_modal(driver):
    """Click the Yes button in the disconnect confirmation modal."""
    time.sleep(0.3)
    yes_selectors = [
        "//button[contains(translate(., 'YES', 'yes'), 'yes')]",
        "//*[contains(translate(., 'YES', 'yes'), 'yes') and (self::button or self::a or @role='button')]",
        "//*[@role='dialog']//button[contains(., 'Yes')]",
        "//*[contains(@class, 'modal')]//button[contains(., 'Yes')]",
    ]
    for sel in yes_selectors:
        try:
            els = driver.find_elements(By.XPATH, sel)
            for el in els:
                if el.is_displayed() and "yes" in (el.text or "").lower():
                    el.click()
                    print("   Clicked Yes in confirmation modal")
                    time.sleep(0.3)
                    return True
        except Exception:
            continue
    try:
        driver.execute_script(
            """
            var nodes = document.querySelectorAll('button, [role="button"], a');
            for (var n of nodes) {
                if (n.offsetParent && (n.innerText || '').trim().toLowerCase() === 'yes') {
                    n.click();
                    return true;
                }
            }
            return false;
            """
        )
        time.sleep(0.3)
        return True
    except Exception:
        pass
    return False


def handle_browser_permission_prompt(driver):
    """
    Attempt to handle the browser-level permission prompt (e.g. microphone/camera).
    Native browser dialogs can't be controlled by Selenium; this tries sending
    Enter to accept, which may work on some platforms. For fully headless runs,
    launch the browser with options like --use-fake-ui-for-media-stream.
    """
    time.sleep(0.5)
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        time.sleep(0.3)
    except Exception:
        pass


def handle_permission_popups_on_page_load(driver):
    """
    Handle permission popups (microphone, camera, video) that appear when the 
    Virtual Monitoring page first loads (e.g., "Enable microphone to monitor rooms").
    
    This function:
    1. Detects if a permission popup is visible
    2. Clicks "Allow" to grant the permission
    3. Dismisses the modal
    
    Returns True if a popup was found and handled, False if no popup was present.
    """
    permission_keywords = ['microphone', 'camera', 'video', 'audio', 'permission', 'enable']
    max_attempts = 3
    attempt = 0
    
    while attempt < max_attempts:
        attempt += 1
        
        # Check if any permission-related text is visible on the page
        try:
            page_text = driver.find_element(By.TAG_NAME, 'body').text.lower()
            has_permission_request = any(keyword in page_text for keyword in permission_keywords)
        except:
            has_permission_request = False
        
        if not has_permission_request:
            if attempt == 1:
                print("✓ No permission popup detected")
            return attempt > 1  # Return True if we handled popups in previous attempts
        
        print(f'⏳ Permission popup detected (attempt {attempt}/{max_attempts})')
        
        # Debug: print all visible buttons and their text
        try:
            all_buttons = driver.find_elements(By.TAG_NAME, 'button')
            visible_buttons = [btn.text.strip() for btn in all_buttons if btn.is_displayed()]
            print(f"   Available buttons: {visible_buttons}")
        except:
            pass
        
        time.sleep(0.5)
        
        # First try to click Allow/Grant button to grant permission
        allow_selectors = [
            "//button[contains(text(), 'Allow')]",
            "//button[contains(text(), 'allow')]",
            "//button[contains(text(), 'Grant')]",
            "//button[contains(text(), 'grant')]",
            "//button[contains(text(), 'Yes')]",
            "//button[contains(text(), 'yes')]",
            "//button[@aria-label*='Allow']",
            "//button[@aria-label*='allow']",
        ]
        
        allow_clicked = False
        for selector in allow_selectors:
            try:
                buttons = driver.find_elements(By.XPATH, selector)
                if buttons and buttons[0].is_displayed():
                    btn_text = buttons[0].text.strip()
                    buttons[0].click()
                    print(f"✅ Clicked Allow button: '{btn_text}'")
                    allow_clicked = True
                    time.sleep(0.5)
                    break
            except Exception:
                continue
        
        if not allow_clicked:
            # Fallback: try JS-based click on Allow/Grant button
            try:
                clicked = driver.execute_script(
                    """
                    var keywords = ['Allow', 'Grant', 'Yes'];
                    var buttons = document.querySelectorAll('button');
                    for (var btn of buttons) {
                        if (!btn.offsetParent) continue;
                        var text = btn.innerText.trim();
                        for (var k of keywords) {
                            if (text.toLowerCase() === k.toLowerCase()) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                    return false;
                    """
                )
                if clicked:
                    print("✅ Clicked Allow button via JS")
                    time.sleep(0.5)
                    allow_clicked = True
            except Exception:
                pass
        
        if not allow_clicked:
            print("⚠️ Could not find Allow button, continuing with dismiss only")
        
        # Now dismiss the modal by clicking Ok
        ok_selectors = [
            "//button[contains(text(), 'Ok')]",
            "//button[contains(text(), 'OK')]",
            "//button[contains(text(), 'ok')]",
        ]
        
        ok_clicked = False
        for selector in ok_selectors:
            try:
                buttons = driver.find_elements(By.XPATH, selector)
                if buttons and buttons[0].is_displayed():
                    btn_text = buttons[0].text.strip()
                    buttons[0].click()
                    print(f"✅ Clicked Dismiss button: '{btn_text}'")
                    ok_clicked = True
                    time.sleep(0.5)
                    break
            except Exception:
                continue
        
        if not ok_clicked:
            # Fallback: try JS-based click on Ok button
            try:
                clicked = driver.execute_script(
                    """
                    var buttons = document.querySelectorAll('button');
                    for (var btn of buttons) {
                        if (!btn.offsetParent) continue;
                        var text = btn.innerText.trim();
                        if (text.toLowerCase() === 'ok') {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                    """
                )
                if clicked:
                    print("✅ Clicked Dismiss button (Ok) via JS")
                    time.sleep(0.5)
                    ok_clicked = True
            except Exception:
                pass
        
        # Brief pause before checking again
        time.sleep(0.5)


def dismiss_microphone_modal(driver):
    """
    Dismiss the "Enable microphone to monitor rooms" modal that appears after
    clicking the Add Room button. This is a warning/informational modal that
    needs to be dismissed before the facility selection modal appears.
    """
    try:
        # Look for the "Ok" button in the modal
        ok_selectors = [
            "//button[contains(text(), 'Ok')]",
            "//button[contains(text(), 'OK')]",
            "//button[contains(text(), 'ok')]",
        ]
        
        for selector in ok_selectors:
            try:
                buttons = driver.find_elements(By.XPATH, selector)
                if buttons and buttons[0].is_displayed():
                    buttons[0].click()
                    print("✅ Dismissed microphone modal by clicking Ok")
                    time.sleep(1)
                    return True
            except Exception:
                continue
        
        # Fallback: JS click on any visible Ok button
        clicked = driver.execute_script(
            """
            var buttons = document.querySelectorAll('button');
            for (var btn of buttons) {
                if (!btn.offsetParent) continue;
                var text = btn.innerText.trim();
                if (text.toLowerCase() === 'ok') {
                    btn.click();
                    return true;
                }
            }
            return false;
            """
        )
        if clicked:
            print("✅ Dismissed microphone modal via JS fallback")
            time.sleep(1)
            return True
            
        print("⚠️ Could not find Ok button to dismiss microphone modal; continuing anyway")
        time.sleep(1)
        return False
        
    except Exception as e:
        print(f"⚠️ Error dismissing microphone modal: {e}")
        return False


def select_facility_in_modal(driver, facility_name):
    """
    In the Add Room modal, find and select the specified facility.
    
    Args:
        driver: Selenium WebDriver
        facility_name: Name of the facility to select (e.g., "Vineland Rack Room")
    """
    facility_name_lower = facility_name.lower()
    # Partial match for flexibility (e.g. "vineland" matches "Vineland Rack Room Facility")
    search_bits = facility_name_lower.replace(",", " ").split()
    search_bits = [b for b in search_bits if len(b) > 1]

    # Wait for the modal to appear
    try:
        WebDriverWait(driver, 5).until(
            lambda d: "facility" in d.find_element(By.TAG_NAME, 'body').text.lower() or
                      "select" in d.find_element(By.TAG_NAME, 'body').text.lower()
        )
        print("✓ Add Room modal appeared")
    except Exception:
        print("⚠️ Could not confirm modal appearance, continuing anyway...")
    
    time.sleep(0.25)

    def _commit_facility_selection(facility_trigger=None):
        """Try to commit the facility selection (dropdown may only apply on close or on a button)."""
        time.sleep(0.15)
        # 1. Press Enter (focus may be on the option)
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            time.sleep(0.1)
        except Exception:
            pass
        # 2. Click the Facility trigger again to close dropdown (many UIs commit on close)
        if facility_trigger is not None:
            try:
                facility_trigger.click()
                time.sleep(0.15)
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", facility_trigger)
                    time.sleep(0.15)
                except Exception:
                    pass
        # 3. Look for Select / Apply / Done button in the modal
        for btn_text in ("Select", "Apply", "Done", "OK", "Confirm"):
            try:
                btns = driver.find_elements(
                    By.XPATH,
                    f"//*[contains(translate(., 'SELECT', 'select'), '{btn_text.lower()}') and (self::button or self::a or @role='button')]"
                )
                for b in btns:
                    if b.is_displayed() and btn_text.lower() in (b.text or "").lower():
                        b.click()
                        time.sleep(0.15)
                        return
            except Exception:
                continue

    def _click_element(elem, description, facility_trigger=None):
        """Click the option; then try to commit selection (close dropdown, Enter, or Select button)."""
        from selenium.webdriver.common.action_chains import ActionChains
        try:
            elem.click()
            time.sleep(0.1)
            _commit_facility_selection(facility_trigger)
            print(f"✅ Selected facility: {description}")
            time.sleep(0.25)
            return True
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].click();", elem)
            time.sleep(0.1)
            _commit_facility_selection(facility_trigger)
            print(f"✅ Selected facility (via JS): {description}")
            time.sleep(0.25)
            return True
        except Exception:
            pass
        try:
            ActionChains(driver).double_click(elem).perform()
            time.sleep(0.1)
            _commit_facility_selection(facility_trigger)
            print(f"✅ Selected facility (double-click): {description}")
            return True
        except Exception:
            try:
                driver.execute_script("var e=arguments[0]; var ev=new MouseEvent('dblclick',{bubbles:true}); e.dispatchEvent(ev);", elem)
                time.sleep(0.1)
                _commit_facility_selection(facility_trigger)
                print(f"✅ Selected facility (double-click JS): {description}")
                return True
            except Exception:
                return False

    # Scope to modal if present (so we don't click page-level elements)
    modal = None
    for modal_sel in [
        "//*[@role='dialog']",
        "//*[contains(@class, 'modal') or contains(@class, 'Modal')]",
        "//*[contains(@class, 'dialog') or contains(@class, 'Dialog')]",
    ]:
        try:
            modals = driver.find_elements(By.XPATH, modal_sel)
            for m in modals:
                if m.is_displayed() and "facility" in (m.text or "").lower():
                    modal = m
                    break
            if modal:
                break
        except Exception:
            continue
    search_root = modal if modal else driver

    # Approach ng-select: Open facility dropdown, then select "Vineland Rack Room"
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        for trigger_text in ("Select Facility", "Select facility"):
            triggers = search_root.find_elements(
                By.XPATH,
                f".//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{trigger_text.lower()}')]"
            )
            for tr in triggers:
                if not tr.is_displayed():
                    continue
                txt = (tr.text or "").strip()
                if trigger_text.lower() in txt.lower() and len(txt) < 80:
                    tr.click()
                    time.sleep(0.35)
                    # A) Type to filter then Enter (ng-select supports search) — fastest path
                    try:
                        search_input = driver.find_element(By.CSS_SELECTOR, "ng-dropdown-panel input, .ng-dropdown-panel input, [role='listbox'] input, .ng-select input")
                        search_input.clear()
                        search_input.send_keys("Vineland Rack Room")
                        time.sleep(0.2)
                        search_input.send_keys(Keys.ENTER)
                        print("✅ Selected facility (ng-select type + Enter): Vineland Rack Room")
                        time.sleep(0.25)
                        return
                    except Exception:
                        pass
                    try:
                        ActionChains(driver).send_keys("Vineland Rack Room").send_keys(Keys.ENTER).perform()
                        time.sleep(0.2)
                        print("✅ Selected facility (ng-select keys + Enter): Vineland Rack Room")
                        return
                    except Exception:
                        pass
                    # B) Arrow down to index 80 (Vineland Rack Room in the list) then Enter — minimal delay
                    try:
                        for _ in range(80):
                            ActionChains(driver).send_keys(Keys.ARROW_DOWN).perform()
                            time.sleep(0.01)
                        time.sleep(0.1)
                        ActionChains(driver).send_keys(Keys.ENTER).perform()
                        print("✅ Selected facility (ng-select arrow 80 + Enter): Vineland Rack Room")
                        time.sleep(0.25)
                        return
                    except Exception:
                        pass
                    for option_xpath in [
                        "//*[local-name()='ng-dropdown-panel']//div[contains(@class,'ng-option') and .//span[normalize-space()='Vineland Rack Room']]",
                        "//*[@role='listbox']//div[contains(@class,'ng-option') and .//span[normalize-space()='Vineland Rack Room']]",
                        "//*[@role='listbox']//*[@role='option'][.//span[normalize-space()='Vineland Rack Room']]",
                        "//*[local-name()='ng-dropdown-panel']//*[@role='option'][.//span[contains(.,'Vineland Rack Room')]]",
                    ]:
                        opts = driver.find_elements(By.XPATH, option_xpath)
                        for opt in opts:
                            if not opt.is_displayed():
                                continue
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", opt)
                                time.sleep(0.1)
                            except Exception:
                                pass
                            # ng-select often listens for mousedown; dispatch full sequence
                            def try_select():
                                try:
                                    opt.click()
                                    return True
                                except Exception:
                                    return False
                            if try_select():
                                print("✅ Selected facility (ng-select click): Vineland Rack Room")
                                time.sleep(0.25)
                                return
                            try:
                                driver.execute_script("""
                                    var el = arguments[0];
                                    el.scrollIntoView({block:'center'});
                                    var rect = el.getBoundingClientRect();
                                    var x = rect.left + rect.width/2, y = rect.top + rect.height/2;
                                    ['mousedown','mouseup','click'].forEach(function(type) {
                                        var ev = new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0, buttons: 1 });
                                        el.dispatchEvent(ev);
                                    });
                                """, opt)
                                time.sleep(0.15)
                                print("✅ Selected facility (ng-select mouse events): Vineland Rack Room")
                                return
                            except Exception:
                                pass
                            try:
                                from selenium.webdriver.common.action_chains import ActionChains
                                ActionChains(driver).move_to_element(opt).pause(0.05).click().perform()
                                time.sleep(0.15)
                                print("✅ Selected facility (ng-select ActionChains): Vineland Rack Room")
                                return
                            except Exception:
                                pass
                            try:
                                driver.execute_script("arguments[0].click();", opt)
                                time.sleep(0.15)
                                print("✅ Selected facility (ng-select JS click): Vineland Rack Room")
                                return
                            except Exception:
                                pass
                            try:
                                span = opt.find_element(By.XPATH, ".//span[contains(.,'Vineland Rack Room')]")
                                driver.execute_script("""
                                    var el = arguments[0];
                                    var rect = el.getBoundingClientRect();
                                    var x = rect.left + rect.width/2, y = rect.top + rect.height/2;
                                    ['mousedown','mouseup','click'].forEach(function(type) {
                                        var ev = new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0, buttons: 1 });
                                        el.dispatchEvent(ev);
                                    });
                                """, span)
                                time.sleep(0.15)
                                print("✅ Selected facility (ng-select span mouse events): Vineland Rack Room")
                                return
                            except Exception:
                                pass
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    except Exception:
                        pass
                    break
            else:
                continue
            break
    except Exception:
        pass

    # Approach keyboard: Open facility dropdown, arrow down to "Vineland Rack Room", then Enter to select
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        for trigger_text in ("Select Facility", "Select facility"):
            triggers = search_root.find_elements(
                By.XPATH,
                f".//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{trigger_text.lower()}')]"
            )
            for tr in triggers:
                if not tr.is_displayed():
                    continue
                txt = (tr.text or "").strip()
                if trigger_text.lower() in txt.lower() and len(txt) < 80:
                    tr.click()
                    time.sleep(0.35)
                    # Find all options in the dropdown (prefer within modal/listbox)
                    opts = search_root.find_elements(By.XPATH, ".//*[@role='option']")
                    if not opts:
                        opts = driver.find_elements(By.XPATH, "//*[@role='option']")
                    if not opts:
                        opts = search_root.find_elements(By.XPATH, ".//*[contains(., 'Vineland Rack Room') and not(contains(., 'Slot'))]")
                    if not opts:
                        opts = driver.find_elements(By.XPATH, "//*[contains(., 'Vineland Rack Room') and not(contains(., 'Slot'))]")
                    target_index = None
                    for i, o in enumerate(opts):
                        if not o.is_displayed():
                            continue
                        if "vineland" in (o.text or "").lower() and "slot" not in (o.text or "").lower():
                            target_index = i
                            break
                    if target_index is not None:
                        opt = opts[target_index]
                        # Try: focus option and send Enter to it (some dropdowns commit only when option receives key)
                        try:
                            driver.execute_script("arguments[0].focus();", opt)
                            time.sleep(0.05)
                            opt.send_keys(Keys.ENTER)
                            print("✅ Selected facility (focus + Enter on option): Vineland Rack Room")
                            time.sleep(0.25)
                            return
                        except Exception:
                            pass
                        # Try: arrow down to the option, then Enter
                        for _ in range(target_index):
                            ActionChains(driver).send_keys(Keys.ARROW_DOWN).perform()
                            time.sleep(0.03)
                        time.sleep(0.1)
                        ActionChains(driver).send_keys(Keys.ENTER).perform()
                        print("✅ Selected facility (keyboard): Vineland Rack Room")
                        time.sleep(0.25)
                        return
                    # Fallback: keep arrowing down until active element contains Vineland, then Enter
                    body = driver.find_element(By.TAG_NAME, "body")
                    for _ in range(25):
                        try:
                            active = driver.switch_to.active_element
                            if active and "vineland" in (active.get_attribute("innerText") or active.text or "").lower():
                                ActionChains(driver).send_keys(Keys.ENTER).perform()
                                print("✅ Selected facility (keyboard nav): Vineland Rack Room")
                                time.sleep(0.25)
                                return
                        except Exception:
                            pass
                        body.send_keys(Keys.ARROW_DOWN)
                        time.sleep(0.05)
                    break
            else:
                continue
            break
    except Exception:
        pass

    # Approach 0: Click "Select Facility" to open dropdown, then pick option and commit (close trigger or Select button)
    try:
        for trigger_text in ("Select Facility", "Select facility", "Facility"):
            triggers = search_root.find_elements(
                By.XPATH,
                f".//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{trigger_text.lower()}')]"
            )
            for tr in triggers:
                if not tr.is_displayed():
                    continue
                txt = (tr.text or "").strip()
                if trigger_text.lower() in txt.lower() and len(txt) < 100:
                    tr.click()
                    time.sleep(0.35)
                    facility_trigger = tr  # use to close dropdown after selection
                    for opt_xpath in [
                        "//*[@role='option'][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'vineland')]",
                        "//*[@role='listbox']//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'vineland')]",
                        "//*[contains(., 'Vineland Rack Room') and not(contains(., 'Slot')) and not(contains(., 'Rack 6')) and not(contains(., 'Rack 7'))]",
                        "//*[contains(., 'Vineland Rack Room')]",
                    ]:
                        opts = driver.find_elements(By.XPATH, opt_xpath)
                        for opt in opts:
                            if not opt.is_displayed():
                                continue
                            ot = (opt.text or "").strip()
                            if "slot" in ot.lower() or ("rack" in ot.lower() and any(c.isdigit() for c in ot)):
                                continue
                            if "vineland" in ot.lower() and len(ot) < 80:
                                # Prefer clicking a checkbox/radio inside the row (many UIs select only when that is clicked)
                                for input_xpath in [".//input[@type='checkbox']", ".//input[@type='radio']", ".//*[@role='checkbox']"]:
                                    try:
                                        inputs = opt.find_elements(By.XPATH, input_xpath)
                                        for inp in inputs:
                                            if inp.is_displayed():
                                                if _click_element(inp, ot or facility_name, facility_trigger):
                                                    return
                                                break
                                    except Exception:
                                        continue
                                if _click_element(opt, ot or facility_name, facility_trigger):
                                    return
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    except Exception:
                        pass
                    time.sleep(0.2)
                    break
            else:
                continue
            break
    except Exception:
        pass

    # Approach 1: Open facility dropdown (combobox etc.), then pick option and commit
    try:
        for trigger_selector in [
            ".//*[@role='combobox']",
            ".//*[contains(translate(@aria-label, 'FACILITY', 'facility'), 'facility')]",
            ".//*[contains(translate(@placeholder, 'FACILITY', 'facility'), 'facility')]",
            ".//select",
        ]:
            try:
                triggers = search_root.find_elements(By.XPATH, trigger_selector)
                for tr in triggers:
                    if not tr.is_displayed():
                        continue
                    tr.click()
                    time.sleep(0.3)
                    facility_trigger = tr
                    for xpath in [
                        f"//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{facility_name_lower}')]",
                        "//*[@role='option'][contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'vineland')]",
                        "//*[contains(., 'vineland')]",
                        "//li[contains(., 'vineland')]",
                        "//div[contains(., 'vineland')]",
                    ]:
                        opts = driver.find_elements(By.XPATH, xpath)
                        for opt in opts:
                            if not opt.is_displayed():
                                continue
                            ot = (opt.text or "").lower()
                            if facility_name_lower in ot or all(b in ot for b in search_bits):
                                for input_xpath in [".//input[@type='checkbox']", ".//input[@type='radio']", ".//*[@role='checkbox']"]:
                                    try:
                                        for inp in opt.find_elements(By.XPATH, input_xpath):
                                            if inp.is_displayed() and _click_element(inp, opt.text.strip() or facility_name, facility_trigger):
                                                return
                                    except Exception:
                                        continue
                                if _click_element(opt, opt.text.strip() or facility_name, facility_trigger):
                                    return
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    except Exception:
                        pass
                    time.sleep(0.1)
            except Exception:
                continue
    except Exception:
        pass

    # Approach 2: Native <select>
    try:
        from selenium.webdriver.support.select import Select
        select_elems = search_root.find_elements(By.TAG_NAME, 'select')
        if not select_elems:
            select_elems = driver.find_elements(By.TAG_NAME, 'select')
        select_elem = select_elems[0] if select_elems else None
        if not select_elem:
            raise ValueError("no select")
        select = Select(select_elem)
        for option in select.options:
            if facility_name_lower in option.text.lower() or all(b in option.text.lower() for b in search_bits):
                select.select_by_visible_text(option.text)
                print(f"✅ Selected facility via select: {option.text}")
                time.sleep(0.25)
                return
        for option in select.options:
            val = (option.get_attribute('value') or '').lower()
            if facility_name_lower in val or all(b in val for b in search_bits):
                select.select_by_value(option.get_attribute('value'))
                print(f"✅ Selected facility by value: {option.get_attribute('value')}")
                time.sleep(0.25)
                return
    except Exception:
        pass

    # Approach 3: Any visible element whose text (including children) contains the facility name
    for xpath in [
        f"//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{facility_name_lower}')]",
        "//*[contains(., 'vineland')]",
    ]:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
            for elem in elements:
                if not elem.is_displayed():
                    continue
                txt = (elem.text or "").strip().lower()
                if not txt or len(txt) > 500:  # skip huge containers
                    continue
                if facility_name_lower in txt or all(b in txt for b in search_bits):
                    if _click_element(elem, elem.text.strip()[:80] or facility_name):
                        return
        except Exception:
            continue

    # Approach 4: Input field to type facility name (search/filter)
    try:
        for inp in driver.find_elements(By.TAG_NAME, 'input'):
            if not inp.is_displayed():
                continue
            ph = (inp.get_attribute('placeholder') or '').lower()
            if 'facility' in ph or 'room' in ph or 'search' in ph:
                inp.click()
                inp.clear()
                inp.send_keys("vineland")
                time.sleep(0.25)
                # Then click the matching option that appears
                for opt_sel in ["//*[@role='option'][contains(., 'vineland')]", "//*[contains(., 'vineland rack')]"]:
                    opts = driver.find_elements(By.XPATH, opt_sel)
                    for opt in opts:
                        if opt.is_displayed() and facility_name_lower in (opt.text or "").lower():
                            if _click_element(opt, opt.text.strip() or facility_name):
                                return
                break
    except Exception:
        pass

    # Debug: what's actually on the page
    try:
        body_text = driver.find_element(By.TAG_NAME, 'body').text
        print(f"   Modal content (last 600 chars): {body_text[-600:]}")
    except Exception:
        pass
    print(f"⚠️ Could not find facility '{facility_name}' in Add Room modal")
    raise AssertionError(f"Could not select facility '{facility_name}' in Add Room modal")


def ensure_add_room_modal_open(driver):
    """
    If the Add Room modal is not open, click the Add Room button to open it.
    Call this after disconnect/perm handling so we can continue in the modal
    (e.g. when there are no active rooms we go straight to Add a New Room section).
    """
    time.sleep(0.3)
    # Check if Add Room modal is already visible (dialog/modal containing key text)
    try:
        for modal_sel in [
            "//*[@role='dialog']",
            "//*[contains(@class, 'modal') or contains(@class, 'Modal')]",
            "//*[contains(@class, 'dialog') or contains(@class, 'Dialog')]",
        ]:
            modals = driver.find_elements(By.XPATH, modal_sel)
            for m in modals:
                if not m.is_displayed():
                    continue
                txt = (m.text or "").lower()
                if "add a new room" in txt or "select facility" in txt or ("facility" in txt and "area" in txt):
                    print("✓ Add Room modal is open")
                    return True
        # Also check body for modal content (in case modal has no role/class)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "add a new room" in body and "facility" in body:
            # Could be open but we didn't find a container; assume open
            print("✓ Add Room modal content visible")
            return True
    except Exception:
        pass

    # Modal not open: click Add Room button to reopen
    add_room_locators = [
        "//button[contains(text(), 'Add Room')]",
        "//button[contains(., 'Add Room')]",
        "//button[@aria-label*='Add' and @aria-label*='Room']",
        "//a[contains(text(), 'Add Room')]",
    ]
    for xpath in add_room_locators:
        try:
            btns = driver.find_elements(By.XPATH, xpath)
            for btn in btns:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    print("✅ Reopened Add Room modal")
                    time.sleep(1)
                    return True
        except Exception:
            continue
    print("⚠️ Could not reopen Add Room modal (button not found?)")
    return False


def _is_add_new_room_section_expanded(driver):
    """
    Return True only if we see aria-expanded="true" on the Add a New Room trigger or its parent.
    Do not use body text (e.g. "Select Facility") to decide—that can be present when section is collapsed.
    """
    try:
        for el in driver.find_elements(By.XPATH, "//*[contains(translate(., 'ADD A NEW ROOM', 'add a new room'), 'add a new room')]"):
            if not el.is_displayed():
                continue
            expanded = (el.get_attribute("aria-expanded") or "").strip().lower()
            if expanded == "true":
                return True
            parent = el
            for _ in range(5):
                try:
                    parent = parent.find_element(By.XPATH, "..")
                except Exception:
                    break
                if (parent.get_attribute("aria-expanded") or "").strip().lower() == "true":
                    return True
    except Exception:
        pass
    return False


def open_add_new_room_section(driver):
    """
    In the Add Room modal, find and click the "Add a New Room" dropdown only if it is collapsed.
    If it is already expanded, do not click (clicking would collapse it). Call this after
    disconnecting rooms since the menus often collapse and the Facility selection is hidden.
    """
    time.sleep(0.3)
    if _is_add_new_room_section_expanded(driver):
        print("✓ Add a New Room section already expanded")
        return True

    # Click the accordion expand icon (fa-caret-right = collapsed; caret-down = expanded; only click when collapsed)
    for selector in [
        "span.add-room-accordion-expand-collapse-icon",
        ".add-room-accordion-expand-collapse-icon",
        "i.fa-caret-right",
        "[class*='add-room-accordion']",
    ]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in els:
                if not el.is_displayed():
                    continue
                cls = (el.get_attribute("class") or "").lower()
                if "caret-down" in cls:
                    continue
                if el.tag_name.lower() == "i" and "caret-right" not in cls:
                    continue
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.15)
                except Exception:
                    pass
                try:
                    el.click()
                    print("✅ Opened Add a New Room section (accordion icon)")
                    time.sleep(0.5)
                    return True
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", el)
                        print("✅ Opened Add a New Room section (accordion icon, JS)")
                        time.sleep(0.5)
                        return True
                    except Exception:
                        continue
        except Exception:
            continue

    for text in ("Add a New Room", "Add a new room", "add a new room"):
        try:
            els = driver.find_elements(
                By.XPATH,
                f"//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{text.strip().lower()}')]"
            )
            for el in els:
                if not el.is_displayed():
                    continue
                if (el.get_attribute("aria-expanded") or "").lower() == "true":
                    continue
                t = (el.text or "").strip().lower()
                if text.strip().lower() in t and len(t) < 50:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        time.sleep(0.15)
                    except Exception:
                        pass
                    try:
                        el.click()
                        print("✅ Opened Add a New Room section (was collapsed)")
                        time.sleep(0.5)
                        return True
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", el)
                            print("✅ Opened Add a New Room section (JS, was collapsed)")
                            time.sleep(0.5)
                            return True
                        except Exception:
                            continue
        except Exception:
            continue
    try:
        for xpath in [
            "//*[@role='button'][contains(translate(., 'ADD A NEW ROOM', 'add a new room'), 'add a new room')]",
            "//*[contains(@class, 'accordion') or contains(@class, 'collapse') or contains(@class, 'dropdown')]//*[contains(translate(., 'ADD A NEW ROOM', 'add a new room'), 'add a new room')]",
            "//button[contains(translate(., 'ADD A NEW ROOM', 'add a new room'), 'add a new room')]",
        ]:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                if not el.is_displayed():
                    continue
                if (el.get_attribute("aria-expanded") or "").lower() == "true":
                    continue
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.15)
                except Exception:
                    pass
                try:
                    el.click()
                    print("✅ Opened Add a New Room section (dropdown, was collapsed)")
                    time.sleep(0.5)
                    return True
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", el)
                        print("✅ Opened Add a New Room section (JS)")
                        time.sleep(0.5)
                        return True
                    except Exception:
                        continue
    except Exception:
        pass
    print("⚠️ Could not find Add a New Room dropdown or section already expanded")
    return False


def open_area_list_and_select_online_rooms(driver):
    """
    Open the Area list in the Add Room modal, then select up to the first 12
    area items that show a green cloud icon (room is online) by clicking the
    box on the right for each.
    """
    time.sleep(0.2)
    # Open the Area list (click "Area" label or "All" / dropdown trigger)
    area_triggers = [
        "//*[contains(translate(., 'AREA', 'area'), 'area') and not(contains(., 'Facility'))]",
        "//*[@aria-label and contains(translate(@aria-label, 'AREA', 'area'), 'area')]",
        "//*[contains(@placeholder, 'Area') or contains(@placeholder, 'area')]",
        "//*[contains(., 'Area') and contains(., 'All')]",
    ]
    opened = False
    for xpath in area_triggers:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                if not el.is_displayed():
                    continue
                # Prefer the one that looks like dropdown (e.g. contains "All" or is a combobox)
                el.click()
                opened = True
                print("✅ Opened Area list")
                time.sleep(0.25)
                break
            if opened:
                break
        except Exception:
            continue
    if not opened:
        print("⚠️ Could not open Area list; attempting to find area items anyway")

    time.sleep(0.2)

    def _is_checked(box):
        """True if checkbox/control is already checked (we should NOT click it when adding rooms - would disconnect)."""
        try:
            tag = (box.get_attribute("tagName") or "").lower()
            role = (box.get_attribute("role") or "").lower()
            if tag == "input" and (box.get_attribute("type") or "").lower() == "checkbox":
                return box.is_selected()
            if role == "checkbox":
                return (box.get_attribute("aria-checked") or "").lower() == "true"
            return False
        except Exception:
            return False

    # Text that indicates a row is a patient/resident, not a room — do not add these.
    NON_ROOM_ROW_TEXT = frozenset({
        "test user", "patient", "resident", "guest", "occupant",
    })

    def _is_room_row(row_text):
        """True if row_text looks like a room/area name; False if it's a patient or other non-room."""
        t = (row_text or "").strip().lower()
        if not t or len(t) < 2:
            return False
        # Skip rows that are exactly a known patient/non-room label (e.g. "Test User").
        if t in NON_ROOM_ROW_TEXT:
            return False
        return True

    def _scroll_area_list(steps=1):
        """Scroll the area list container so more items load (virtualized/long lists)."""
        scroll_amount = 280
        for _ in range(max(1, steps)):
            try:
                for sel in [
                    "//*[contains(@class, 'scroll-host') or contains(@class, 'ng-dropdown-panel')]",
                    "//*[local-name()='ng-dropdown-panel']//*[contains(@class, 'scroll')]",
                    "//*[@role='listbox']",
                    "//*[contains(@class, 'overflow') and (contains(@class, 'auto') or contains(@class, 'scroll'))]",
                    "//*[contains(@class, 'scroll')]",
                ]:
                    els = driver.find_elements(By.XPATH, sel)
                    for el in els:
                        if not el.is_displayed():
                            continue
                        try:
                            driver.execute_script("arguments[0].scrollTop += %d;" % scroll_amount, el)
                            time.sleep(0.12)
                        except Exception:
                            pass
            except Exception:
                pass

    # Find all rows with green cloud (online). Click every UNchecked box in one pass; only scroll when no more found.
    green_cloud_indicators = [
        "//*[contains(@class, 'online') or contains(@class, 'cloud') or contains(@class, 'green')]",
        "//*[contains(@aria-label, 'online') or contains(@title, 'online')]",
        "//svg[contains(@class, 'cloud') or contains(@class, 'online')]",
        "//*[name()='svg' or name()='img'][contains(@class, 'cloud')]",
    ]

    selected_count = 0
    max_select = 12
    scroll_passes = 0
    max_scroll_passes = 8
    clicked_ids = set()

    while selected_count < max_select and scroll_passes < max_scroll_passes:
        found_any = False
        for indicator_xpath in green_cloud_indicators:
            try:
                indicators = driver.find_elements(By.XPATH, indicator_xpath)
                for ind in indicators:
                    if not ind.is_displayed():
                        continue
                    row = ind
                    for _ in range(5):
                        try:
                            row = row.find_element(By.XPATH, "..")
                        except Exception:
                            break
                        if not row or row.get_attribute("tagName") == "body":
                            break
                        row_text = (row.text or "").strip()
                        if len(row_text) > 3 and len(row_text) < 150 and _is_room_row(row_text):
                            for box_xpath in [
                                ".//input[@type='checkbox']",
                                ".//*[@role='checkbox']",
                                ".//*[contains(@class, 'checkbox') or contains(@class, 'toggle')]",
                                ".//button",
                                ".//*[@role='button']",
                            ]:
                                try:
                                    boxes = row.find_elements(By.XPATH, box_xpath)
                                    for box in reversed(boxes):
                                        if not box.is_displayed():
                                            continue
                                        if _is_checked(box):
                                            continue
                                        try:
                                            box_id = box.get_attribute("id") or id(box)
                                            if box_id in clicked_ids:
                                                continue
                                        except Exception:
                                            pass
                                        try:
                                            box.click()
                                            selected_count += 1
                                            found_any = True
                                            try:
                                                clicked_ids.add(box.get_attribute("id") or id(box))
                                            except Exception:
                                                pass
                                            print(f"   Added room to monitoring session ({selected_count}): {row_text}")
                                            time.sleep(0.08)
                                            break
                                        except Exception:
                                            try:
                                                driver.execute_script("arguments[0].click();", box)
                                                selected_count += 1
                                                found_any = True
                                                try:
                                                    clicked_ids.add(box.get_attribute("id") or id(box))
                                                except Exception:
                                                    pass
                                                print(f"   Added room to monitoring session via JS ({selected_count}): {row_text}")
                                                time.sleep(0.08)
                                                break
                                            except Exception:
                                                continue
                                    if found_any:
                                        break
                                except Exception:
                                    continue
                            if found_any:
                                break
                        if found_any:
                            break
            except Exception:
                continue
        if not found_any:
            scroll_passes += 1
            _scroll_area_list(2)
            time.sleep(0.15)
        else:
            scroll_passes = 0

    if selected_count > 0:
        print(f"✅ Selected {selected_count} online area(s) (green cloud)")
    else:
        print("✓ No online areas to select (or Area list not found)")


def _scroll_to_bottom(driver):
    """Scroll the page to the bottom so pagination controls are in view."""
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.3)
    except Exception:
        pass


def _scroll_to_top(driver):
    """Scroll the page to the top so the video grid is in view."""
    try:
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.2)
    except Exception:
        pass


def _get_room_pagination_root(driver):
    """Return the room-pagination container element or None."""
    try:
        for sel in [
            (By.CSS_SELECTOR, "div.room-pagination"),
            (By.XPATH, "//div[contains(@class, 'room-pagination')]"),
        ]:
            els = driver.find_elements(*sel)
            for el in els:
                if el.is_displayed():
                    return el
    except Exception:
        pass
    return None


def _try_click_el(driver, el):
    """Try Selenium click, then JS click, then ActionChains. Return True if any succeeds."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", el)
        time.sleep(0.2)
    except Exception:
        pass
    try:
        WebDriverWait(driver, 2).until(EC.element_to_be_clickable(el))
        el.click()
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        pass
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(driver).move_to_element(el).pause(0.1).click().perform()
        return True
    except Exception:
        pass
    try:
        driver.execute_script(
            """
            var el = arguments[0];
            var r = el.getBoundingClientRect();
            var x = r.left + r.width/2, y = r.top + r.height/2;
            ['mousedown','mouseup','click'].forEach(function(t){
                el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y, button:0}));
            });
            """,
            el,
        )
        return True
    except Exception:
        pass
    return False


def _click_next_page(driver):
    """
    Click to go to the next page. Uses structure:
    div.room-pagination > div.pages > span.icon-right-chev (no disabled), or span with page number (2, 3, ...).
    """
    time.sleep(0.2)
    _scroll_to_bottom(driver)
    time.sleep(0.4)

    root = _get_room_pagination_root(driver)
    if root:
        # 1) Click page number "2" (or next number) — most reliable when structure is span with text
        try:
            for page_num in ["2", "3", "4", "5"]:
                spans = root.find_elements(By.XPATH, f".//span[normalize-space(.)='{page_num}']")
                for span in spans:
                    if not span.is_displayed():
                        continue
                    if "active" in (span.get_attribute("class") or ""):
                        continue
                    if _try_click_el(driver, span):
                        print(f"   📄 Clicked page {page_num}")
                        time.sleep(0.5)
                        return True
        except Exception:
            pass

        # 2) Click span.icon.icon-right-chev that does NOT have class "disabled"
        try:
            right_chevrons = root.find_elements(By.CSS_SELECTOR, "span.icon-right-chev")
            for span in right_chevrons:
                if not span.is_displayed():
                    continue
                cls = (span.get_attribute("class") or "")
                if "disabled" in cls:
                    continue
                if _try_click_el(driver, span):
                    print("   📄 Clicked Next (right-chev)")
                    time.sleep(0.5)
                    return True
        except Exception:
            pass

        # 3) Same via XPath (no disabled)
        try:
            right_chevrons = root.find_elements(
                By.XPATH,
                ".//span[contains(@class, 'icon-right-chev') and not(contains(@class, 'disabled'))]"
            )
            for span in right_chevrons:
                if not span.is_displayed():
                    continue
                if _try_click_el(driver, span):
                    print("   📄 Clicked Next (right-chev)")
                    time.sleep(0.5)
                    return True
        except Exception:
            pass

    # Fallback without scoping to room-pagination
    try:
        for xpath in [
            "//div[contains(@class, 'room-pagination')]//span[contains(@class, 'icon-right-chev') and not(contains(@class, 'disabled'))]",
            "//div[contains(@class, 'room-pagination')]//span[normalize-space(.)='2']",
        ]:
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed() and _try_click_el(driver, el):
                    print("   📄 Clicked Next page")
                    time.sleep(0.5)
                    return True
    except Exception:
        pass
    return False


def _is_next_page_available(driver):
    """Return True if there is a next page (room-pagination: right-chev without disabled, or page number 2)."""
    _scroll_to_bottom(driver)
    time.sleep(0.2)
    root = _get_room_pagination_root(driver)
    if root:
        try:
            for span in root.find_elements(
                By.XPATH,
                ".//span[contains(@class, 'icon-right-chev') and not(contains(@class, 'disabled'))]"
            ):
                if span.is_displayed():
                    return True
        except Exception:
            pass
        try:
            for span in root.find_elements(By.XPATH, ".//span[normalize-space(.)='2']"):
                if span.is_displayed() and "active" not in (span.get_attribute("class") or ""):
                    return True
        except Exception:
            pass
    try:
        for xpath in [
            "//div[contains(@class, 'room-pagination')]//span[contains(@class, 'icon-right-chev') and not(contains(@class, 'disabled'))]",
        ]:
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed():
                    return True
    except Exception:
        pass
    return False


def go_to_first_page(driver):
    """
    Navigate back to page 1. Uses div.room-pagination > div.pages > span with "1".
    If <span class="active">1</span> is present we're already on page 1.
    """
    _scroll_to_bottom(driver)
    time.sleep(0.2)
    root = _get_room_pagination_root(driver)
    if root:
        try:
            for span in root.find_elements(By.XPATH, ".//span[normalize-space(.)='1']"):
                if not span.is_displayed():
                    continue
                if "active" in (span.get_attribute("class") or ""):
                    print("   📄 Already on page 1")
                    _scroll_to_top(driver)
                    return True
                if _try_click_el(driver, span):
                    print("   📄 Clicked page 1")
                    time.sleep(0.5)
                    _scroll_to_top(driver)
                    return True
        except Exception:
            pass
    for xpath in [
        "//div[contains(@class, 'room-pagination')]//span[normalize-space(.)='1']",
        "//span[normalize-space(.)='1']/parent::*",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                if not el.is_displayed():
                    continue
                if "active" in (el.get_attribute("class") or ""):
                    print("   📄 Already on page 1")
                    _scroll_to_top(driver)
                    return True
                if _try_click_el(driver, el):
                    print("   📄 Clicked page 1")
                    time.sleep(0.5)
                    _scroll_to_top(driver)
                    return True
        except Exception:
            continue
    _scroll_to_top(driver)
    return False


def _get_room_tiles_for_ptz(driver):
    """
    Return a list of elements that represent room tiles (video or its clickable container)
    so we can select a room before using PTZ. Prefer the video's parent container if it
    looks like a card/tile; otherwise the video itself.
    """
    tiles = []
    videos = driver.find_elements(By.TAG_NAME, "video")
    for v in videos:
        try:
            if not v.is_displayed():
                continue
            parent = v.find_element(By.XPATH, "..")
            if parent and parent.is_displayed() and parent.get_attribute("tagName") and parent.get_attribute("tagName").upper() != "BODY":
                tiles.append(parent)
            else:
                tiles.append(v)
        except Exception:
            try:
                tiles.append(v)
            except Exception:
                continue
    return tiles


def _get_video_from_tile(tile_el):
    """Return the video element from a room tile (tile may be the video's parent or the video itself)."""
    try:
        if tile_el.tag_name.lower() == "video":
            return tile_el
        videos = tile_el.find_elements(By.TAG_NAME, "video")
        for v in videos:
            if v.is_displayed():
                return v
    except Exception:
        pass
    return None


def _ptz_drag_on_video(driver, video_el, direction, drag_pixels=60):
    """
    Perform PTZ by dragging on the video element. Prefers Selenium ActionChains so the
    app receives real mouse events (React and other frameworks often ignore synthetic
    dispatchEvent). Falls back to JS dispatchEvent if ActionChains fails.
    Returns True if the drag was performed.
    """
    direction = direction.lower()
    dx, dy = 0, 0
    if direction == "up":
        dy = -drag_pixels
    elif direction == "down":
        dy = drag_pixels
    elif direction == "left":
        dx = -drag_pixels
    elif direction == "right":
        dx = drag_pixels
    else:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", video_el)
        time.sleep(0.1)
    except Exception:
        pass
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(driver)
        actions.move_to_element(video_el).pause(0.05)
        actions.click_and_hold().pause(0.05)
        actions.move_by_offset(dx, dy).pause(0.05)
        actions.release()
        actions.perform()
        return True
    except Exception:
        pass
    try:
        success = driver.execute_script(
            """
            var video = arguments[0];
            var dx = arguments[1], dy = arguments[2];
            var rect = video.getBoundingClientRect();
            var startX = rect.left + rect.width / 2;
            var startY = rect.top + rect.height / 2;
            var endX = startX + dx;
            var endY = startY + dy;
            if (rect.width < 10 || rect.height < 10) return false;

            var preventScroll = function(e) {
                if (video.contains(e.target) || e.target === video) e.preventDefault();
            };
            var types = ['mousedown', 'mousemove', 'mouseup'];
            types.forEach(function(t) { document.addEventListener(t, preventScroll, true); });

            try {
                var opts = { bubbles: true, cancelable: true, view: window };
                video.dispatchEvent(new MouseEvent('mousedown', Object.assign({}, opts, { clientX: startX, clientY: startY, button: 0, buttons: 1 })));
                video.dispatchEvent(new MouseEvent('mousemove', Object.assign({}, opts, { clientX: endX, clientY: endY, button: 0, buttons: 1 })));
                video.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, opts, { clientX: endX, clientY: endY, button: 0, buttons: 0 })));
                return true;
            } finally {
                types.forEach(function(t) { document.removeEventListener(t, preventScroll, true); });
            }
            """,
            video_el,
            dx,
            dy,
        )
        return bool(success)
    except Exception:
        return False


def _wait_for_ptz_ready(driver, timeout=2):
    """Wait for PTZ controls to be visible so the selected stream is ready for PTZ commands."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".ptz-arrows, [class*='ptz'], [class*='PTZ']"))
        )
        time.sleep(0.2)
        return True
    except Exception:
        return False


def _click_ptz_direction(driver, direction, context_el=None):
    """
    Find and click a PTZ control for the given direction ('up', 'down', 'left', 'right').
    Uses structure: div.ptz-arrows > div.<direction>.control-icon > span.icon-<direction>-chev
    Scoped to .ptz-arrows to avoid clicking pagination arrows. If context_el is given,
    search for PTZ controls within that element first (e.g. the selected stream panel).
    Returns True if a control was clicked.
    """
    direction_lower = direction.lower()
    # App structure: .ptz-arrows .up.control-icon, .down.control-icon, etc.
    # with inner span .icon-up-chev, .icon-down-chev, ...
    base_selectors = [
        (By.CSS_SELECTOR, f"div.ptz-arrows div.{direction_lower}.control-icon"),
        (By.CSS_SELECTOR, f"div.ptz-arrows span.icon-{direction_lower}-chev"),
        (By.CSS_SELECTOR, f".ptz-arrows .control-icon.{direction_lower}"),
        (By.XPATH, f"//div[contains(@class, 'ptz-arrows')]//div[contains(@class, 'control-icon') and contains(@class, '{direction_lower}')]"),
        (By.XPATH, f"//div[contains(@class, 'ptz-arrows')]//span[contains(@class, 'icon-{direction_lower}-chev')]"),
        (By.XPATH, f"//*[contains(@class, 'ptz') or contains(@class, 'PTZ')]//*[contains(@aria-label, '{direction}') or contains(@title, '{direction}')]"),
        (By.CSS_SELECTOR, f"[class*='ptz'] [class*='{direction_lower}']"),
    ]
    search_roots = [context_el] if context_el else [None]
    for root in search_roots:
        for by, selector in base_selectors:
            try:
                els = root.find_elements(by, selector) if root else driver.find_elements(by, selector)
                for el in els:
                    if not el.is_displayed():
                        continue
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", el)
                        time.sleep(0.05)
                    except Exception:
                        pass
                    try:
                        el.click()
                        return True
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", el)
                            return True
                        except Exception:
                            continue
            except Exception:
                continue
    return False


def run_monitoring_with_ptz(driver, duration_seconds=180, interval_seconds=10):
    """
    Run the monitoring session for duration_seconds. Every interval_seconds, randomly
    select a room and trigger random PTZ directions (up, down, left, right) several times.
    """
    directions = ["up", "down", "left", "right"]
    elapsed = 0
    interval_count = 0
    intervals_total = max(1, duration_seconds // interval_seconds)
    while elapsed < duration_seconds:
        time.sleep(interval_seconds)
        elapsed += interval_seconds
        interval_count += 1
        remaining = max(0, duration_seconds - elapsed)
        print(f"   ⏱️  Monitoring {elapsed}s / {duration_seconds}s — PTZ interval {interval_count}/{intervals_total} (remaining {remaining}s)")

        tiles = _get_room_tiles_for_ptz(driver)
        if not tiles:
            continue
        room = random.choice(tiles)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", room)
            time.sleep(0.15)
        except Exception:
            pass
        try:
            room.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", room)
            except Exception:
                pass
        time.sleep(0.4)
        _wait_for_ptz_ready(driver)

        video_el = _get_video_from_tile(room)
        num_ptz_moves = random.randint(2, 5)
        for _ in range(num_ptz_moves):
            d = random.choice(directions)
            if video_el and _ptz_drag_on_video(driver, video_el, d):
                print(f"      PTZ {d} (drag on video)")
            elif _click_ptz_direction(driver, d, context_el=room):
                print(f"      PTZ {d} (arrows)")
            elif _click_ptz_direction(driver, d):
                print(f"      PTZ {d} (arrows)")
            time.sleep(0.25 + random.uniform(0, 0.25))

    print(f"✅ Monitoring with PTZ completed ({duration_seconds}s)")


def _get_visible_video_elements(driver):
    """Return list of visible video elements that are likely session streams."""
    videos = driver.find_elements(By.TAG_NAME, "video")
    visible = []
    for v in videos:
        try:
            if not v.is_displayed():
                continue
            visible.append(v)
        except Exception:
            continue
    return visible


def _video_element_has_content(driver, video_el):
    """Return (has_video: bool, label: str) by checking readyState and dimensions via JS."""
    try:
        result = driver.execute_script(
            """
            var v = arguments[0];
            if (!v || v.tagName.toLowerCase() !== 'video') return { hasVideo: false, reason: 'not video' };
            var rs = v.readyState;
            var w = v.videoWidth || 0;
            var h = v.videoHeight || 0;
            var hasFrame = rs >= 2 && w > 0 && h > 0;
            var playing = !v.paused && !v.ended && v.currentTime > 0;
            var reason = hasFrame ? (playing ? 'playing' : 'paused') : 'no data';
            return { hasVideo: hasFrame, readyState: rs, width: w, height: h, playing: playing, reason: reason };
            """,
            video_el,
        )
        if result is None:
            return False, "js_error"
        has_video = result.get("hasVideo", False)
        reason = result.get("reason", "unknown")
        return bool(has_video), reason
    except Exception:
        return False, "error"


def _assess_video_quality_from_element(driver, video_el):
    """
    Take a screenshot of the video element and assess if it looks blurry or pixelated.
    Returns one of: 'ok', 'blurry', 'pixelated', 'unknown'.
    Uses Laplacian variance as a sharpness metric (low = blurry). Requires Pillow (PIL).
    """
    try:
        from PIL import Image, ImageFilter
        import io
    except ImportError:
        return "unknown"

    try:
        png_bytes = video_el.screenshot_as_png
        if not png_bytes or len(png_bytes) < 100:
            return "unknown"
        img = Image.open(io.BytesIO(png_bytes)).convert("L")
        w, h = img.size
        if w < 10 or h < 10:
            return "unknown"
        lap = img.filter(ImageFilter.LAPLACIAN)
        pixels = list(lap.getdata())
        if not pixels:
            return "unknown"
        mean = sum(pixels) / len(pixels)
        lap_variance = sum((x - mean) ** 2 for x in pixels) / len(pixels)
        if lap_variance < 100:
            return "blurry"
        if lap_variance > 3000 and w * h < 80000:
            return "pixelated"
        return "ok"
    except Exception:
        return "unknown"


def _screenshot_bad_video(video_el, screenshot_dir, page_num, session_ordinal, reason):
    """Save a screenshot of the video element to screenshot_dir. reason: 'no_video', 'blurry', 'pixelated'."""
    if not screenshot_dir:
        return
    try:
        os.makedirs(screenshot_dir, exist_ok=True)
        safe_reason = reason.replace(" ", "_").replace("/", "_")
        filename = f"bad_video_page{page_num}_session{session_ordinal}_{safe_reason}.png"
        filepath = os.path.join(screenshot_dir, filename)
        video_el.screenshot(filepath)
        print(f"      📷 Screenshot: {filepath}")
    except Exception as e:
        print(f"      ⚠️ Could not save screenshot: {e}")


def validate_video_sessions_across_pages(driver, check_quality=True, screenshot_dir=None):
    """
    After rooms are added to the monitoring session, validate that each visible
    session is showing video. Use pagination at the bottom to switch pages and
    check all sessions. Optionally assess whether video is blurry or pixelated.
    When a bad video is found (no video, blurry, or pixelated), a screenshot
    of that video element is saved to screenshot_dir if provided.

    Returns a dict: {
        'pages_checked': int,
        'total_sessions_with_video': int,
        'total_sessions_no_video': int,
        'quality_issues': list of (session_index_or_label, 'blurry'|'pixelated'),
        'errors': list of str
    }
    """
    results = {
        "pages_checked": 0,
        "total_sessions_with_video": 0,
        "total_sessions_no_video": 0,
        "quality_issues": [],
        "errors": [],
    }
    page_num = 0
    session_ordinal = 0

    while True:
        page_num += 1
        _scroll_to_top(driver)
        time.sleep(0.3)
        videos = _get_visible_video_elements(driver)
        if not videos:
            if page_num == 1:
                results["errors"].append("No video elements found on first page")
                print("⚠️ No video elements found on this page")
            break

        results["pages_checked"] += 1
        print(f"   Page {page_num}: found {len(videos)} video element(s)")

        for i, video_el in enumerate(videos):
            session_ordinal += 1
            has_video, reason = _video_element_has_content(driver, video_el)
            if has_video:
                results["total_sessions_with_video"] += 1
                quality = _assess_video_quality_from_element(driver, video_el) if check_quality else "unknown"
                if quality == "blurry":
                    results["quality_issues"].append((session_ordinal, "blurry"))
                    print(f"      Session {session_ordinal}: ✅ video present — ⚠️ blurry")
                    _screenshot_bad_video(video_el, screenshot_dir, page_num, session_ordinal, "blurry")
                elif quality == "pixelated":
                    results["quality_issues"].append((session_ordinal, "pixelated"))
                    print(f"      Session {session_ordinal}: ✅ video present — ⚠️ pixelated")
                    _screenshot_bad_video(video_el, screenshot_dir, page_num, session_ordinal, "pixelated")
                else:
                    print(f"      Session {session_ordinal}: ✅ video present ({reason})" + (f" — {quality}" if quality != "unknown" else ""))
            else:
                results["total_sessions_no_video"] += 1
                print(f"      Session {session_ordinal}: ❌ no video ({reason})")
                _screenshot_bad_video(video_el, screenshot_dir, page_num, session_ordinal, "no_video")

        if not _is_next_page_available(driver):
            break
        if not _click_next_page(driver):
            break

    print(f"✅ Validated across {results['pages_checked']} page(s): {results['total_sessions_with_video']} with video, {results['total_sessions_no_video']} without")
    if results["quality_issues"]:
        print(f"   Quality issues: {results['quality_issues']}")
    return results
