"""
Test Runner Dashboard – Flask backend.
Discovers tests, runs selected ones via pytest, returns results and serves screenshots.
Run from project root: python dashboard/server.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Project root (parent of dashboard/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots"

# Prefer project venv for running tests so Selenium and deps are always available
def _pytest_python():
    venv_py = PROJECT_ROOT / "venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)


def _collect_from_output(out):
    """Parse pytest collect output and return list of node ids."""
    node_ids = []
    current_module = None
    for line in out.splitlines():
        mod_match = re.match(r"\s*<Module ([^>]+\.py)>", line)
        if mod_match:
            current_module = "src/tests/" + mod_match.group(1).strip()
            continue
        func_match = re.match(r"\s*<Function (\w+)>", line)
        if func_match and current_module:
            node_ids.append(f"{current_module}::{func_match.group(1)}")
    return node_ids


def _run_pytest_collect():
    """Run pytest --collect-only and return list of test node ids.
    Includes tests from test_*.py (per pytest.ini) and from virtual_monitoring.py."""
    node_ids = []
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT), env.get("PYTHONPATH", "")])
    py = _pytest_python()
    # Collect from default testpaths (respects python_files = test_*.py)
    result = subprocess.run(
        [py, "-m", "pytest", "src/tests", "--collect-only", "-p", "no:warnings"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = (result.stdout or "") + (result.stderr or "")
    node_ids.extend(_collect_from_output(out))
    # Also collect from virtual_monitoring.py (not matched by test_*.py in pytest.ini)
    result2 = subprocess.run(
        [py, "-m", "pytest", "src/tests/virtual_monitoring.py", "--collect-only", "-p", "no:warnings"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out2 = (result2.stdout or "") + (result2.stderr or "")
    node_ids.extend(_collect_from_output(out2))
    return sorted(set(node_ids))


@app.route("/api/tests", methods=["GET"])
def list_tests():
    """Return list of discoverable test node ids (e.g. src/tests/test_example.py::test_example)."""
    try:
        node_ids = _run_pytest_collect()
        return jsonify({"tests": node_ids })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/run", methods=["POST"])
def run_tests():
    """Run selected tests. Body: { \"tests\": [ \"node_id1\", \"node_id2\" ] }. Returns log and screenshot folder."""
    data = request.get_json() or {}
    selected = data.get("tests") or []
    if not selected:
        return jsonify({"error": "No tests selected", "passed": False, "output": ""}), 400

    # Ensure screenshots dir exists so we can detect new runs
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    # Remember dirs before run so we only show screenshots from *this* run
    before_dirs = set()
    if SCREENSHOTS_DIR.exists():
        before_dirs = {p.name for p in SCREENSHOTS_DIR.iterdir() if p.is_dir()}

    # Force a fresh run (no cache), use project venv if present
    # HEADLESS: set to "true" when starting the server if you want headless from the dashboard
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT), env.get("PYTHONPATH", "")])
    cmd = [
        _pytest_python(), "-m", "pytest",
        "-v", "--tb=short", "-s",
        "--cache-clear",  # ensure tests actually execute, not cached state
    ] + selected
    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return jsonify({
            "passed": False,
            "output": "Test run timed out (600s).",
            "screenshot_folders": [],
        }), 200
    except Exception as e:
        return jsonify({"passed": False, "output": str(e), "screenshot_folders": []}), 200

    out = (proc.stdout or "") + (proc.stderr or "")
    # Only include screenshot folders created during *this* run (never show old runs)
    after_dirs = set()
    if SCREENSHOTS_DIR.exists():
        after_dirs = {p.name for p in SCREENSHOTS_DIR.iterdir() if p.is_dir()}
    new_folders = sorted(after_dirs - before_dirs)

    return jsonify({
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "output": out,
        "screenshot_folders": new_folders,
    })


@app.route("/api/screenshots/<folder>")
def list_screenshots(folder):
    """List screenshot filenames in a run folder (e.g. 20260303_131327)."""
    # Security: only allow folder names that look like our timestamp format
    if not re.match(r"^\d{8}_\d{6}$", folder):
        return jsonify({"error": "Invalid folder"}), 400
    path = SCREENSHOTS_DIR / folder
    if not path.exists() or not path.is_dir():
        return jsonify({"error": "Folder not found", "files": []}), 404
    files = sorted([p.name for p in path.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
    return jsonify({"folder": folder, "files": files})


@app.route("/api/screenshots/<folder>/<filename>")
def get_screenshot(folder, filename):
    """Serve a single screenshot file."""
    if not re.match(r"^\d{8}_\d{6}$", folder):
        return "Invalid folder", 400
    path = SCREENSHOTS_DIR / folder
    if not path.exists() or not path.is_dir():
        return "Not found", 404
    return send_from_directory(path, filename, mimetype="image/png")


@app.route("/api/terminal", methods=["POST"])
def run_terminal_command():
    """Run a shell command in the project root. Body: { \"command\": \"pytest -v\" }."""
    data = request.get_json() or {}
    command = (data.get("command") or "").strip()
    if not command:
        return jsonify({"error": "No command provided", "output": "", "exit_code": None}), 400

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT), env.get("PYTHONPATH", "")])
    max_output_len = 200_000
    timeout_sec = 600
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > max_output_len:
            out = out[:max_output_len] + "\n\n... (output truncated)"
        return jsonify({
            "output": out,
            "exit_code": proc.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            "output": f"Command timed out after {timeout_sec}s.",
            "exit_code": None,
        })
    except Exception as e:
        return jsonify({"output": str(e), "exit_code": None})


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    port = int(os.environ.get("PORT", 5556))
    print(f"Test Runner Dashboard: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
