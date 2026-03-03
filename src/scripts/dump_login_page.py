"""Open the site and dump page source + screenshot for debugging."""
from src.drivers.webdriver_factory import WebDriverFactory
from src.config import settings

factory = WebDriverFactory('edge', headless=False)
driver = factory.create_driver()
try:
    driver.get('https://lab.care.ai')
    print('title:', driver.title)
    html = driver.page_source
    with open('page_dump.html', 'w', encoding='utf-8') as f:
        f.write(html)
    driver.save_screenshot('page_dump.png')
    print('Wrote page_dump.html and page_dump.png')
finally:
    driver.quit()
