from selenium.webdriver.common.by import By

from .base_page import BasePage


class LoginPage(BasePage):
    """Page object representing the login page for care.ai lab."""

    # locators adjusted to actual form field names on the site
    USERNAME_INPUT = (By.NAME, "email")
    PASSWORD_INPUT = (By.NAME, "password")
    LOGIN_BUTTON = (By.NAME, "submit")

    def enter_username(self, username: str):
        # try multiple common locator strategies to be resilient to attribute differences
        candidates = [
            (By.NAME, "email"),
            (By.ID, "email"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.NAME, "username"),
            (By.ID, "username"),
        ]
        elem = None
        import time
        from src.config import settings

        end = time.time() + settings.timeout
        while time.time() < end:
            for by, val in candidates:
                elems = self.driver.find_elements(by, val)
                if elems:
                    elem = elems[0]
                    print(f"✓ Found username field using {by} = '{val}'")
                    break
            if elem:
                break
            time.sleep(0.25)

        if elem is None:
            # let the original locator raise a clear error
            print(f"✗ Could not find username field on page: {self.driver.current_url}")
            print(f"  Page title: {self.driver.title}")
            print(f"  Candidates tried: {[f'{by}={val}' for by, val in candidates]}")
            elem = self.find_element(*self.USERNAME_INPUT)
        from selenium.common.exceptions import ElementNotInteractableException

        try:
            elem.clear()
            elem.send_keys(username)
        except ElementNotInteractableException:
            try:
                # try to make it interactable
                self.driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                elem.click()
                elem.send_keys(username)
            except Exception:
                # last resort: set value via JS
                self.driver.execute_script("arguments[0].value = arguments[1];", elem, username)

    def enter_password(self, password: str):
        candidates = [
            (By.NAME, "password"),
            (By.ID, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]
        elem = None
        import time
        from src.config import settings

        end = time.time() + settings.timeout
        while time.time() < end:
            for by, val in candidates:
                elems = self.driver.find_elements(by, val)
                if elems:
                    elem = elems[0]
                    print(f"✓ Found password field using {by} = '{val}'")
                    break
            if elem:
                break
            time.sleep(0.25)

        if elem is None:
            print(f"✗ Could not find password field on page: {self.driver.current_url}")
            print(f"  Page title: {self.driver.title}")
            print(f"  Candidates tried: {[f'{by}={val}' for by, val in candidates]}")
            elem = self.find_element(*self.PASSWORD_INPUT)
        from selenium.common.exceptions import ElementNotInteractableException

        try:
            elem.clear()
            elem.send_keys(password)
        except ElementNotInteractableException:
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                elem.click()
                elem.send_keys(password)
            except Exception:
                self.driver.execute_script("arguments[0].value = arguments[1];", elem, password)

    def click_login(self):
        # try common submit button locators
        candidates = [
            (By.NAME, "submit"),
            (By.XPATH, "//button[@type='submit']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
        ]
        from selenium.common.exceptions import NoSuchElementException
        for by, val in candidates:
            try:
                btn = self.find_element(by, val)
                print(f"✓ Found submit button using {by} = '{val}', clicking it...")
                try:
                    btn.click()
                    return
                except Exception:
                    try:
                        # try scrolling then clicking
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        btn.click()
                        return
                    except Exception:
                        # try JS click
                        self.driver.execute_script("arguments[0].click();", btn)
                        return
            except NoSuchElementException:
                continue

        # fallback to configured locator
        print(f"✗ Could not find submit button on page: {self.driver.current_url}")
        print(f"  Page title: {self.driver.title}")
        print(f"  Candidates tried: {[f'{by}={val}' for by, val in candidates]}")
        try:
            self.find_element(*self.LOGIN_BUTTON).click()
        except Exception:
            # last resort: press Enter on the password field
            from selenium.webdriver.common.keys import Keys
            pwd = self.find_element(*self.PASSWORD_INPUT)
            pwd.send_keys(Keys.RETURN)

    def login(self, username: str, password: str):
        """Convenience method to perform the full login flow.

        Pause briefly before typing to allow any startup scripts to complete
        (the page often redirects as soon as an input event fires). Sleep
        between entries to give the browser time to update.
        """
        # make sure the username input exists first
        try:
            self.wait_for_element(*self.USERNAME_INPUT, timeout=10)
        except Exception:
            print(f"login(): username input never appeared; url={self.driver.current_url}")
        import time
        # give the page a slightly longer pause before typing
        time.sleep(2)

        self.enter_username(username)
        time.sleep(0.5)

        self.enter_password(password)
        time.sleep(0.5)

        self.click_login()