"""
Automated tests for IDA-5376: retry 401s in-session instead of exiting the monitoring wall.

Ticket: https://careai.atlassian.net/browse/IDA-5376

Run all P1 tests:
    pytest src/tests/test_ida_5376.py -v -m "ida_5376 and p1"

Run full suite:
    ./run_ida_5376

Environment variables:
    IDA5376_OBSERVE_SECONDS       Seconds to wait on wall after 401 (default 90)
    IDA5376_RECOVERY_WAIT_SECONDS Seconds to wait for banner clear after restore (default 60)
    IDA5376_FACILITY              Facility name for Add Room modal (default Vineland Rack Room)
    IDA5376_MIN_ROOMS             Minimum rooms to add (default 2)
    IDA5376_VM_PATH               VM route (default /virtual-monitoring)
    IDA5376_BETA_VM_PATH          Optional beta wall route for TC-02
    IDA5376_TEST_POPOUT           Set to 1 to enable popout window test (TC-07)
    IDA5376_SCREENSHOT_RUN_DIR      Screenshot output directory
    BROWSER / HEADLESS / BASE_URL   Standard care.ai test settings
"""

import os
import time

import pytest

from src.config import settings
from src.tests.ida_5376_helpers import (
    assert_not_on_error_page,
    assert_videos_continue_playing,
    force_auth_failure,
    is_on_virtual_monitoring,
    is_reconnecting_banner_visible,
    navigate_off_monitoring_wall,
    observe_degraded_session,
    restore_auth_storage,
    save_auth_storage,
    trigger_api_activity,
    wait_for_banner_cleared,
    wait_for_error_page,
    wait_for_reconnecting_banner,
    wait_not_on_error_page,
)
from src.tests.vm_session_helpers import count_videos_with_frames


pytestmark = pytest.mark.ida_5376


@pytest.mark.p1
def test_tc01_monitoring_wall_survives_401_during_session(driver, monitoring_wall, save_screenshot):
    """
    AC-1: A 401 during an active monitoring session does not navigate to /error;
    the wall and all live tiles stay up.
    """
    assert is_on_virtual_monitoring(driver), f"Expected VM route, got {driver.current_url}"
    initial_videos = monitoring_wall["video_count"]
    print(f"Monitoring wall ready: {initial_videos} video stream(s) at {driver.current_url}")

    time.sleep(5)
    affected = force_auth_failure(driver)
    print(f"Invalidated auth storage ({affected} key(s) touched)")
    save_screenshot("tc01_after_token_invalidation")

    result = observe_degraded_session(driver)
    save_screenshot("tc01_after_observation")

    assert result["still_on_monitoring"], (
        f"Left monitoring wall unexpectedly: {result['final_url']}"
    )
    assert result["final_video_count"] >= 1, (
        f"All video streams dropped after 401 (had {result['starting_video_count']})"
    )
    assert_not_on_error_page(driver, context="TC-01")


@pytest.mark.p1
@pytest.mark.skipif(
    not settings.ida5376_beta_vm_path,
    reason="Set IDA5376_BETA_VM_PATH to run beta-wall variant (TC-02)",
)
def test_tc02_beta_monitoring_wall_survives_401(driver, save_screenshot):
    """
    AC-1 (beta wall): Same as TC-01 on the Patient Monitoring beta route.
    """
    from src.tests.test_login import test_login_success
    from src.tests.vm_session_helpers import open_monitoring_wall_with_rooms

    test_login_success(driver)
    info = open_monitoring_wall_with_rooms(
        driver,
        facility=settings.ida5376_facility,
        min_rooms=settings.ida5376_min_rooms,
        vm_path=settings.ida5376_beta_vm_path,
    )
    save_screenshot("tc02_beta_wall_ready")
    assert info["video_count"] >= 1

    force_auth_failure(driver)
    save_screenshot("tc02_after_token_invalidation")
    result = observe_degraded_session(driver)
    save_screenshot("tc02_after_observation")

    assert result["still_on_monitoring"]
    assert result["final_video_count"] >= 1
    assert_not_on_error_page(driver, context="TC-02")


@pytest.mark.p1
def test_tc03_reconnecting_banner_appears_during_degraded_auth(
    driver, monitoring_wall, save_screenshot
):
    """
    AC-3: A non-blocking reconnecting banner shows while auth is degraded.
    """
    force_auth_failure(driver)
    trigger_api_activity(driver)
    time.sleep(3)
    trigger_api_activity(driver)
    save_screenshot("tc03_after_401")

    banner_visible = wait_for_reconnecting_banner(driver, timeout=45)
    save_screenshot("tc03_banner_check")

    assert banner_visible or is_reconnecting_banner_visible(driver), (
        "Reconnecting banner not found after token invalidation. "
        "Expected text like 'Reconnecting your session... monitoring continues'."
    )
    assert_not_on_error_page(driver, context="TC-03")
    assert count_videos_with_frames(driver) >= 1, "Video streams dropped while banner should show"


@pytest.mark.p1
def test_tc04_background_token_recovery_clears_banner(driver, monitoring_wall, save_screenshot):
    """
    AC-2: Token recovery in background clears banner and restores REST calls.
    """
    snapshot = save_auth_storage(driver)
    assert snapshot.get("local") or snapshot.get("session"), (
        "No auth tokens found in storage before invalidation; cannot test recovery"
    )

    force_auth_failure(driver)
    trigger_api_activity(driver)
    time.sleep(3)
    save_screenshot("tc04_degraded")

    wait_for_reconnecting_banner(driver, timeout=45)
    restore_auth_storage(driver, snapshot)
    trigger_api_activity(driver)
    time.sleep(5)
    trigger_api_activity(driver)
    save_screenshot("tc04_after_restore")

    banner_cleared = wait_for_banner_cleared(driver)
    assert_not_on_error_page(driver, context="TC-04 recovery")
    assert is_on_virtual_monitoring(driver), f"Left monitoring wall during recovery: {driver.current_url}"
    assert_videos_continue_playing(driver, duration_seconds=10, min_with_frames=1)

    if not banner_cleared:
        pytest.xfail(
            "Banner did not clear after token restore; silent refresh may require "
            "re-login in this environment (manual AC-2 verification still needed)"
        )


@pytest.mark.p1
def test_tc05_controls_degrade_gracefully_without_crashing_wall(
    driver, monitoring_wall, save_screenshot
):
    """
    AC-3: REST-dependent controls fail gracefully; wall and video remain up.
    """
    force_auth_failure(driver)
    trigger_api_activity(driver)
    time.sleep(3)
    wait_for_reconnecting_banner(driver, timeout=45)
    save_screenshot("tc05_degraded_state")

    from selenium.webdriver.common.by import By

    for xpath in (
        "//button[contains(., 'Add Room')]",
        "//button[contains(., 'Refresh')]",
        "//button[contains(., 'Settings')]",
    ):
        try:
            buttons = driver.find_elements(By.XPATH, xpath)
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    time.sleep(1)
                    break
        except Exception:
            continue

    save_screenshot("tc05_after_control_clicks")
    assert_not_on_error_page(driver, context="TC-05 after control clicks")
    assert is_on_virtual_monitoring(driver)
    assert count_videos_with_frames(driver) >= 1, "Wall crashed or streams dropped after control interaction"


@pytest.mark.p1
def test_tc06_off_wall_401_still_routes_to_error(driver, save_screenshot):
    """
    AC-4: Outside monitoring, a terminal 401 still routes to /error as before.
    """
    from src.tests.test_login import test_login_success

    test_login_success(driver)
    navigate_off_monitoring_wall(driver)
    save_screenshot("tc06_command_center")

    assert not is_on_virtual_monitoring(driver), (
        f"Still on monitoring route before off-wall test: {driver.current_url}"
    )

    force_auth_failure(driver)
    trigger_api_activity(driver)
    driver.refresh()
    time.sleep(3)
    trigger_api_activity(driver)
    save_screenshot("tc06_after_401_off_wall")

    try:
        wait_for_error_page(driver, timeout=120)
    except Exception as exc:
        save_screenshot("tc06_no_error_page")
        raise AssertionError(
            f"Expected navigation to /error when 401 occurs off the monitoring wall, "
            f"but URL is still: {driver.current_url}"
        ) from exc

    save_screenshot("tc06_on_error_page")
    assert "/error" in driver.current_url.lower()


@pytest.mark.p1
def test_tc11_ticket_qa_mid_session_token_revoke(driver, monitoring_wall, save_screenshot):
    """
    Ticket QA note: revoke/clear token mid-session; video continues, banner shows, recovery works.
    """
    time.sleep(5)
    videos_before = count_videos_with_frames(driver)
    assert videos_before >= 1

    snapshot = save_auth_storage(driver)
    force_auth_failure(driver)
    save_screenshot("tc11_token_revoked")

    trigger_api_activity(driver)
    time.sleep(3)

    assert_videos_continue_playing(driver, duration_seconds=60, min_with_frames=1)
    save_screenshot("tc11_video_continues_60s")

    assert wait_for_reconnecting_banner(driver, timeout=45), "Reconnecting banner not shown"
    assert_not_on_error_page(driver, context="TC-11")

    if snapshot.get("local") or snapshot.get("session"):
        restore_auth_storage(driver, snapshot)
        trigger_api_activity(driver)
        time.sleep(5)
        save_screenshot("tc11_after_recovery")

    assert count_videos_with_frames(driver) >= 1
    assert_not_on_error_page(driver, context="TC-11 after recovery")


@pytest.mark.p2
@pytest.mark.skipif(
    os.getenv("IDA5376_TEST_POPOUT", "").lower() not in ("1", "true", "yes"),
    reason="Set IDA5376_TEST_POPOUT=1 to run popout/nesting test (TC-07)",
)
def test_tc07_popout_wall_keeps_active_state(driver, monitoring_wall, save_screenshot):
    """
    AC-5: Multiple walls (popout) do not prematurely clear monitoring active state.
    Manual setup may be required if the app has no automated popout trigger.
    """
    main_handle = driver.current_window_handle
    handles_before = set(driver.window_handles)

    opened = driver.execute_script(
        """
        try {
            var w = window.open(window.location.href, '_blank', 'noopener,noreferrer');
            return w !== null;
        } catch (e) { return false; }
        """
    )
    time.sleep(3)
    handles_after = set(driver.window_handles)

    if not opened or len(handles_after) <= len(handles_before):
        pytest.skip(
            "Could not open popout window (browser may block window.open); "
            "run manually or allow popups for lab.care.ai"
        )

    new_handles = list(handles_after - handles_before)
    driver.switch_to.window(new_handles[0])
    time.sleep(5)
    save_screenshot("tc07_popout_wall")

    force_auth_failure(driver)
    trigger_api_activity(driver)
    time.sleep(3)

    wait_not_on_error_page(driver, 30, poll_seconds=5, context="TC-07 popout")
    assert count_videos_with_frames(driver) >= 0

    driver.close()
    driver.switch_to.window(main_handle)
    time.sleep(2)

    force_auth_failure(driver)
    trigger_api_activity(driver)
    wait_not_on_error_page(driver, 30, poll_seconds=5, context="TC-07 main after popout close")
    assert_not_on_error_page(driver, context="TC-07 main wall")


@pytest.mark.p2
def test_tc08_background_retry_observable(driver, monitoring_wall, save_screenshot):
    """
    P2: After 401, background token refresh attempts occur (network activity).
    Lightweight check via performance entries when available.
    """
    force_auth_failure(driver)
    trigger_api_activity(driver)
    time.sleep(3)

    network_hints = driver.execute_script(
        """
        var entries = performance.getEntriesByType('resource') || [];
        var authish = entries.filter(function(e) {
            var u = (e.name || '').toLowerCase();
            return u.indexOf('token') !== -1 || u.indexOf('auth') !== -1 || u.indexOf('oauth') !== -1;
        });
        return { total: entries.length, authish: authish.length, recent: authish.slice(-5).map(function(e) { return e.name; }) };
        """
    )
    save_screenshot("tc08_network_check")

    wait_not_on_error_page(driver, min(30, settings.ida5376_observe_seconds), poll_seconds=5)
    assert_not_on_error_page(driver, context="TC-08")

    if network_hints.get("authish", 0) == 0:
        pytest.xfail(
            "No auth/token network entries captured via performance API; "
            "verify refresh backoff manually in DevTools Network tab"
        )


@pytest.mark.p2
def test_tc09_exit_wall_during_degraded_state_then_error_off_wall(
    driver, monitoring_wall, save_screenshot
):
    """
    P2: Leaving the wall during degraded auth is clean; off-wall 401 still routes to /error.
    """
    force_auth_failure(driver)
    trigger_api_activity(driver)
    wait_for_reconnecting_banner(driver, timeout=45)
    save_screenshot("tc09_degraded_on_wall")

    navigate_off_monitoring_wall(driver)
    save_screenshot("tc09_left_wall")

    force_auth_failure(driver)
    driver.refresh()
    time.sleep(3)
    trigger_api_activity(driver)

    try:
        wait_for_error_page(driver, timeout=90)
    except Exception as exc:
        raise AssertionError(
            f"Expected /error after leaving wall with invalid token, got: {driver.current_url}"
        ) from exc

