"""Shared pytest fixtures for care.ai Selenium tests."""

import os
import time
from datetime import datetime

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.config import settings
from src.drivers.webdriver_factory import WebDriverFactory


def _set_window_size_to_fit_screen(driver, preferred_width=1920, preferred_height=1080):
    try:
        driver.get("about:blank")
        w, h = driver.execute_script(
            "return [window.screen.availWidth || 1920, window.screen.availHeight || 1080];"
        )
        width = min(preferred_width, int(w)) if w else preferred_width
        height = min(preferred_height, int(h)) if h else preferred_height
        driver.set_window_size(width, height)
    except Exception:
        driver.set_window_size(preferred_width, preferred_height)


@pytest.fixture(scope="function")
def driver():
    factory = WebDriverFactory(settings.browser, headless=settings.headless)
    driver_instance = factory.create_driver()
    _set_window_size_to_fit_screen(driver_instance, 1920, 1080)
    yield driver_instance
    driver_instance.quit()


@pytest.fixture(scope="function")
def screenshot_dir():
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "screenshots",
    )
    env_run = os.environ.get("IDA5376_SCREENSHOT_RUN_DIR") or os.environ.get("VM_SCREENSHOT_RUN_DIR")
    if env_run:
        path = os.path.abspath(env_run)
    else:
        path = os.path.join(base, datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(path, exist_ok=True)
    return path


@pytest.fixture(scope="function")
def save_screenshot(driver, screenshot_dir):
    def _save(name: str):
        path = os.path.join(screenshot_dir, f"{name}.png")
        driver.save_screenshot(path)
        print(f"   Screenshot: {path}")
        return path

    return _save


@pytest.fixture(scope="function")
def monitoring_wall(driver, save_screenshot):
    """Log in, open Virtual Monitoring, and add online rooms with live video."""
    from src.tests.test_login import test_login_success
    from src.tests.vm_session_helpers import open_monitoring_wall_with_rooms

    test_login_success(driver)
    save_screenshot("00_after_login")
    info = open_monitoring_wall_with_rooms(
        driver,
        facility=settings.ida5376_facility,
        min_rooms=settings.ida5376_min_rooms,
        vm_path=settings.ida5376_vm_path,
    )
    save_screenshot("01_monitoring_wall_ready")
    assert info["video_count"] >= 1, (
        f"Expected at least one live video stream, got {info['video_count']}"
    )
    yield info
    save_screenshot("99_session_end")


def pytest_configure(config):
    config.addinivalue_line("markers", "ida_5376: IDA-5376 auth resilience during VM")
    config.addinivalue_line("markers", "p1: priority 1 acceptance criteria")
    config.addinivalue_line("markers", "p2: priority 2 edge cases")
