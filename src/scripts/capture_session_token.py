"""
Script to manually log in and capture the session token/cookies.

Run this once to authenticate, then it will save the session cookies
to a JSON file that the test can use for future runs.
"""
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Create an Edge driver with a persistent (non-incognito) profile so cookies are saved
options = webdriver.EdgeOptions()
# DO NOT use incognito or temp profile - we want cookies to persist
driver = webdriver.Edge('/usr/local/bin/msedgedriver', options=options)

try:
    # Navigate to the app
    print("Navigating to https://lab.care.ai/?scope=lab-auth-db")
    driver.get("https://lab.care.ai/?scope=lab-auth-db")
    print(f"Current URL: {driver.current_url}")
    
    input(">>> Please log in manually in the browser window, then press ENTER here to capture the session...")
    
    # Give the page a moment to settle after you finish logging in
    time.sleep(2)
    
    # Check if we made it to Command Center
    try:
        command_center = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Command Center')]"))
        )
        print("✓ Successfully reached Command Center!")
    except:
        print(f"⏳ Not yet at Command Center. Current URL: {driver.current_url}")
    
    # Extract all cookies
    cookies = driver.get_cookies()
    print(f"\n✓ Captured {len(cookies)} cookies:")
    for cookie in cookies:
        print(f"  - {cookie['name']}: {cookie['value'][:50]}..." if len(cookie['value']) > 50 else f"  - {cookie['name']}: {cookie['value']}")
    
    # Save cookies to file
    cookies_file = "session_cookies.json"
    with open(cookies_file, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"\n✓ Session cookies saved to {cookies_file}")
    
    print("\nTo use these cookies in the test:")
    print(f"  1. Set environment variable: export SESSION_COOKIES_FILE=session_cookies.json")
    print(f"  2. Run tests normally - they will inject these cookies automatically")

finally:
    input("Press ENTER to close the browser...")
    driver.quit()
