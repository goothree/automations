"""Simple script demonstrating a login flow using the page objects.

Usage:
    python src/scripts/login_script.py

This is meant for manual execution/debugging rather than automated tests.
"""

from src.drivers.webdriver_factory import WebDriverFactory
from src.pages.login_page import LoginPage


def main():
    factory = WebDriverFactory("chrome")
    driver = factory.create_driver()
    driver.get("https://lab.care.ai")

    login_page = LoginPage(driver)
    login_page.login("michael.guthrie+automation@care.ai", "P0rc(p1ne")

    print("Logged in, current URL:", driver.current_url)
    # take a screenshot for verification
    driver.save_screenshot("login_result.png")
    driver.quit()


if __name__ == "__main__":
    main()