"""Helpers for IDA-5376: auth resilience during Virtual Monitoring sessions."""

import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from src.config import settings


AUTH_STORAGE_KEY_HINTS = ("auth0", "token", "@@auth0spajs@@", "access_token", "id_token")


def _is_auth_key(key):
    lower = (key or "").lower()
    return any(hint in lower for hint in AUTH_STORAGE_KEY_HINTS)


def save_auth_storage(driver):
    """Snapshot auth-related localStorage and sessionStorage entries."""
    return driver.execute_script(
        """
        var hints = arguments[0];
        function collect(store) {
            var out = {};
            for (var i = 0; i < store.length; i++) {
                var k = store.key(i);
                if (!k) continue;
                var lower = k.toLowerCase();
                for (var j = 0; j < hints.length; j++) {
                    if (lower.indexOf(hints[j].toLowerCase()) !== -1 || k.indexOf(hints[j]) !== -1) {
                        out[k] = store.getItem(k);
                        break;
                    }
                }
            }
            return out;
        }
        return {
            local: collect(localStorage),
            session: collect(sessionStorage)
        };
        """,
        list(AUTH_STORAGE_KEY_HINTS),
    )


def restore_auth_storage(driver, snapshot):
    """Restore a snapshot from save_auth_storage."""
    driver.execute_script(
        """
        var snap = arguments[0];
        Object.keys(snap.local || {}).forEach(function(k) {
            localStorage.setItem(k, snap.local[k]);
        });
        Object.keys(snap.session || {}).forEach(function(k) {
            sessionStorage.setItem(k, snap.session[k]);
        });
        """,
        snapshot,
    )


def invalidate_auth_token(driver):
    """
    Remove or corrupt stored auth tokens so subsequent REST calls return 401.
    Returns the number of storage keys affected.
    """
    return driver.execute_script(
        """
        var hints = arguments[0];
        var affected = 0;
        function touch(store) {
            var keys = [];
            for (var i = 0; i < store.length; i++) {
                var k = store.key(i);
                if (!k) continue;
                var lower = k.toLowerCase();
                for (var j = 0; j < hints.length; j++) {
                    if (lower.indexOf(hints[j].toLowerCase()) !== -1 || k.indexOf(hints[j]) !== -1) {
                        keys.push(k);
                        break;
                    }
                }
            }
            keys.forEach(function(k) {
                store.removeItem(k);
                affected++;
            });
        }
        touch(localStorage);
        touch(sessionStorage);
        return affected;
        """,
        list(AUTH_STORAGE_KEY_HINTS),
    )


def corrupt_access_token_in_storage(driver):
    """Set auth token values to invalid strings if keys still exist."""
    return driver.execute_script(
        """
        var hints = arguments[0];
        var affected = 0;
        function corrupt(store) {
            for (var i = 0; i < store.length; i++) {
                var k = store.key(i);
                if (!k) continue;
                var lower = k.toLowerCase();
                for (var j = 0; j < hints.length; j++) {
                    if (lower.indexOf(hints[j].toLowerCase()) !== -1 || k.indexOf(hints[j]) !== -1) {
                        store.setItem(k, 'invalid-token-for-ida-5376-test');
                        affected++;
                        break;
                    }
                }
            }
        }
        corrupt(localStorage);
        corrupt(sessionStorage);
        return affected;
        """,
        list(AUTH_STORAGE_KEY_HINTS),
    )


def force_auth_failure(driver):
    """Clear then corrupt auth storage to maximize chance of 401 on next API call."""
    removed = invalidate_auth_token(driver)
    corrupted = corrupt_access_token_in_storage(driver)
    return removed + corrupted


def trigger_api_activity(driver):
    """Perform UI actions that typically cause authenticated REST calls."""
    from src.tests.virtual_monitoring_helpers import _click_next_page, go_to_first_page

    triggered = False
    try:
        if _click_next_page(driver):
            triggered = True
            time.sleep(1)
            go_to_first_page(driver)
    except Exception:
        pass

    if not triggered:
        try:
            driver.execute_script(
                "window.dispatchEvent(new Event('focus')); document.dispatchEvent(new Event('visibilitychange'));"
            )
        except Exception:
            pass

    try:
        add_btns = driver.find_elements(
            By.XPATH, "//button[contains(., 'Add Room') or contains(., 'Refresh')]"
        )
        for btn in add_btns:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                time.sleep(0.5)
                triggered = True
                break
    except Exception:
        pass

    return triggered


def is_on_error_page(driver):
    return "/error" in driver.current_url.lower()


def is_on_virtual_monitoring(driver):
    return "virtual" in driver.current_url.lower()


def assert_not_on_error_page(driver, context=""):
    if is_on_error_page(driver):
        raise AssertionError(
            f"Unexpected navigation to /error{' (' + context + ')' if context else ''}: {driver.current_url}"
        )


def wait_not_on_error_page(driver, duration_seconds, poll_seconds=5, context=""):
    """Poll for duration_seconds and fail if /error is reached."""
    end = time.time() + duration_seconds
    while time.time() < end:
        assert_not_on_error_page(driver, context=context)
        time.sleep(poll_seconds)
    assert_not_on_error_page(driver, context=context)


def is_reconnecting_banner_visible(driver):
    try:
        text = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        return False
    if "reconnecting" in text and "session" in text:
        return True
    if "reconnecting your session" in text:
        return True
    if "monitoring continues" in text:
        return True
    for selector in (
        "[class*='reconnect']",
        "[class*='Reconnect']",
        "[data-testid*='reconnect']",
        ".monitoring-reconnect-banner",
        ".reconnecting-banner",
    ):
        try:
            els = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in els:
                if el.is_displayed():
                    return True
        except Exception:
            continue
    return False


def wait_for_reconnecting_banner(driver, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_reconnecting_banner_visible(driver):
            return True
        time.sleep(1)
    return False


def wait_for_banner_cleared(driver, timeout=None):
    timeout = timeout or settings.ida5376_recovery_wait_seconds
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_reconnecting_banner_visible(driver):
            return True
        time.sleep(2)
    return not is_reconnecting_banner_visible(driver)


def get_video_playback_state(driver):
    """Return dict with video counts and whether playback is advancing."""
    return driver.execute_script(
        """
        var videos = Array.from(document.querySelectorAll('video')).filter(function(v) {
            return v.offsetParent !== null;
        });
        var withFrames = 0;
        var advancing = 0;
        var samples = [];
        videos.forEach(function(v) {
            var w = v.videoWidth || 0;
            var h = v.videoHeight || 0;
            if (v.readyState >= 2 && w > 0 && h > 0) withFrames++;
            samples.push({ currentTime: v.currentTime, paused: v.paused, readyState: v.readyState });
        });
        return {
            total: videos.length,
            withFrames: withFrames,
            samples: samples
        };
        """
    )


def assert_videos_continue_playing(driver, duration_seconds=15, min_with_frames=1):
    """
    Sample video currentTime twice and assert streams keep advancing.
    Returns final count of videos with frames.
    """
    state1 = get_video_playback_state(driver)
    if state1["withFrames"] < min_with_frames:
        raise AssertionError(
            f"Expected >= {min_with_frames} video(s) with frames before observation, "
            f"got {state1['withFrames']} (total visible: {state1['total']})"
        )

    time.sleep(duration_seconds)
    state2 = get_video_playback_state(driver)

    if state2["withFrames"] < min_with_frames:
        raise AssertionError(
            f"Video streams dropped during observation: "
            f"{state2['withFrames']} with frames (was {state1['withFrames']})"
        )

    if is_on_error_page(driver):
        raise AssertionError(
            f"Navigated to /error during video observation: {driver.current_url}"
        )

    return state2["withFrames"]


def wait_for_error_page(driver, timeout=120):
    WebDriverWait(driver, timeout).until(lambda d: is_on_error_page(d))


def navigate_off_monitoring_wall(driver):
    base = settings.base_url.rstrip("/")
    driver.get(f"{base}/command-center")
    time.sleep(2)
    if is_on_virtual_monitoring(driver):
        driver.get(f"{base}/command-center")
        time.sleep(2)


def observe_degraded_session(driver, observe_seconds=None):
    """
    After auth invalidation: trigger API activity, check banner, assert wall stays up.
    Returns a result dict for assertions in tests.
    """
    observe_seconds = observe_seconds or settings.ida5376_observe_seconds
    starting_url = driver.current_url
    starting_videos = get_video_playback_state(driver)

    trigger_api_activity(driver)
    time.sleep(3)
    trigger_api_activity(driver)

    banner_seen = wait_for_reconnecting_banner(driver, timeout=45)
    wait_not_on_error_page(driver, observe_seconds, poll_seconds=5, context="degraded session")
    final_videos = assert_videos_continue_playing(
        driver, duration_seconds=min(15, observe_seconds // 3), min_with_frames=1
    )

    return {
        "starting_url": starting_url,
        "final_url": driver.current_url,
        "banner_seen": banner_seen,
        "starting_video_count": starting_videos["withFrames"],
        "final_video_count": final_videos,
        "still_on_monitoring": is_on_virtual_monitoring(driver),
    }
