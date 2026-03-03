def wait_for_element_to_be_visible(driver, by, value, timeout=10):
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, value)))

def take_screenshot(driver, file_name):
    driver.save_screenshot(file_name)

def get_current_url(driver):
    return driver.current_url

def navigate_to_url(driver, url):
    driver.get(url)


def handle_google_consent(driver, timeout=10):
    """Detect and accept Google OAuth consent screens if present.

    Tries several common button selectors (text 'Allow'/'Accept') and clicks the
    first one found. Returns True if a consent button was clicked, False otherwise.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    import time

    end = time.time() + timeout
    candidates = [
        # common Google consent button labels
        (By.XPATH, "//button[normalize-space()='Allow']"),
        (By.XPATH, "//button[normalize-space()='Accept']"),
        (By.XPATH, "//button[contains(., 'Allow') or contains(., 'Approve')]") ,
        (By.XPATH, "//input[@type='submit' and (@value='Allow' or @value='Accept') ]"),
        (By.XPATH, "//button[contains(., 'Yes') and (contains(., 'allow') or contains(., 'Approve'))]"),
    ]

    while time.time() < end:
        for by, sel in candidates:
            try:
                el = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((by, sel)))
                try:
                    el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                continue
        time.sleep(0.25)

    return False


def handle_auth0_continue(driver, timeout=10):
    """Handle Auth0/IDA intermediate pages by clicking Continue/Authorize buttons.

    Returns True if a button was clicked, False otherwise.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    import time

    end = time.time() + timeout
    candidates = [
        (By.XPATH, "//button[normalize-space()='Continue']"),
        (By.XPATH, "//button[contains(., 'Continue') or contains(., 'continue') ]"),
        (By.XPATH, "//button[contains(., 'Authorize') or contains(., 'authorize') ]"),
        (By.XPATH, "//button[contains(., 'Approve') or contains(., 'approve') ]"),
        (By.XPATH, "//button[contains(., 'Allow') or contains(., 'allow') ]"),
        (By.XPATH, "//a[contains(., 'Continue') or contains(., 'Authorize')]")
    ]

    while time.time() < end:
        for by, sel in candidates:
            try:
                el = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((by, sel)))
                try:
                    el.click()
                except Exception:
                    driver.execute_script('arguments[0].click();', el)
                return True
            except Exception:
                continue
        time.sleep(0.25)

    # fallback: try clicking any element whose text contains a keyword via JS
    try:
        script = """
        (function(){
            var keywords = ['Continue','Authorize','Approve','Allow','Accept','Proceed','Yes'];
            var els = Array.from(document.querySelectorAll('button,a,input'));
            for (var i=0;i<els.length;i++){
                var e = els[i];
                var text = (e.innerText || e.value || '').trim();
                if(!text) continue;
                for (var k=0;k<keywords.length;k++){
                    if (text.indexOf(keywords[k]) !== -1){ try{ e.click(); }catch(e){} return true; }
                }
            }
            return false;
        })();
        """
        clicked = driver.execute_script(script)
        if clicked:
            return True
    except Exception:
        pass

    return False


def handle_google_oauth_flow(driver, email: str, password: str, timeout=20):
    """Handle Google OAuth sign-in flow when redirected to accounts.google.com.

    - Enters the email/identifier if present and clicks Next
    - Enters the password if prompted and clicks Next
    - Calls `handle_google_consent` to accept scopes if shown

    Returns True if it progressed through the flow, False if no Google flow detected.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    import time

    if 'accounts.google.com' not in driver.current_url:
        return False

    end = time.time() + timeout

    # step 1: find and fill identifier (email) field
    id_el = None
    id_candidates = [
        (By.ID, 'identifierId'),
        (By.NAME, 'identifier'),
        (By.XPATH, "//input[@type='email']"),
        (By.CSS_SELECTOR, "input[aria-label*='email'], input[aria-label*='Email']")
    ]

    while time.time() < end and not id_el:
        for by, sel in id_candidates:
            try:
                els = driver.find_elements(by, sel)
                if els and els[0].is_displayed():
                    id_el = els[0]
                    break
            except Exception:
                continue
        if not id_el:
            time.sleep(0.25)

    if id_el:
        try:
            id_el.click()
            id_el.clear()
            id_el.send_keys(email)
            time.sleep(0.5)

            # click Next after identifier
            next_candidates = [
                (By.ID, 'identifierNext'),
                (By.XPATH, "//button[.//span[normalize-space()='Next']]"),
                (By.XPATH, "//*[contains(text(), 'Next')]/ancestor::button"),
            ]
            for by, sel in next_candidates:
                try:
                    btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
                    try:
                        btn.click()
                    except Exception:
                        driver.execute_script('arguments[0].click();', btn)
                    time.sleep(0.5)
                    break
                except Exception:
                    continue
        except Exception as e:
            pass

    # step 2: wait for and fill password field
    while time.time() < end:
        # check if redirected away from Google accounts
        if 'accounts.google.com' not in driver.current_url:
            handle_google_consent(driver, timeout=3)
            return True

        pwd_candidates = [
            (By.NAME, 'password'),
            (By.ID, 'password'),
            (By.XPATH, "//input[@type='password']"),
            (By.CSS_SELECTOR, "input[aria-label*='password'], input[aria-label*='Password']")
        ]

        pwd_el = None
        for by, sel in pwd_candidates:
            try:
                els = driver.find_elements(by, sel)
                if els and els[0].is_displayed():
                    pwd_el = els[0]
                    break
            except Exception:
                continue

        if pwd_el:
            try:
                pwd_el.click()
                pwd_el.clear()
                pwd_el.send_keys(password)
                time.sleep(0.5)

                # click Next/Sign In after password
                submit_candidates = [
                    (By.ID, 'passwordNext'),
                    (By.XPATH, "//button[.//span[normalize-space()='Next']]"),
                    (By.XPATH, "//*[contains(text(), 'Next')]/ancestor::button"),
                    (By.XPATH, "//*[contains(text(), 'Sign in')]/ancestor::button"),
                ]
                for by, sel in submit_candidates:
                    try:
                        btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
                        try:
                            btn.click()
                        except Exception:
                            driver.execute_script('arguments[0].click();', btn)
                        time.sleep(1)
                        break
                    except Exception:
                        continue

                # wait for redirect away
                try:
                    WebDriverWait(driver, 10).until(lambda d: 'accounts.google.com' not in d.current_url)
                    handle_google_consent(driver, timeout=5)
                    return True
                except Exception:
                    pass
            except Exception as e:
                pass

        time.sleep(0.5)

    return False