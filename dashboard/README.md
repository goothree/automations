# Test Runner Dashboard

Web UI to select tests, run them via pytest, and view results and screenshots.

## Run in browser (recommended)

1. **Install dependencies** (from project root):

   ```bash
   pip install -r requirements.txt
   # or: pip install Flask flask-cors
   ```

2. **Start the server** (from project root):

   ```bash
   python dashboard/server.py
   ```

   Or with the project’s venv:

   ```bash
   ./venv/bin/python dashboard/server.py
   ```

3. **Open in browser:** [http://127.0.0.1:5556](http://127.0.0.1:5556) (default port 5556; set `PORT` to use another)

Use the page to select tests, click **Run selected**, then see the output and any screenshots from the run (e.g. from `virtual_monitoring`-style tests that save screenshots under `screenshots/<timestamp>/`).

## Run on Mac (same as above)

From Terminal on your Mac:

```bash
cd /path/to/care.ai
./venv/bin/python dashboard/server.py
```

Then open **http://127.0.0.1:5556** in Safari, Chrome, or any browser. No separate “install” is required beyond having Python and the project’s dependencies.

To open the URL automatically after starting the server:

```bash
./venv/bin/python dashboard/server.py &
sleep 2 && open http://127.0.0.1:5556
```

## Notes

- Tests are discovered via `pytest --collect-only` from `src/tests` (respecting `pytest.ini`, e.g. `test_*.py`).
- Screenshots are read from the `screenshots/` directory; runs that create a new timestamped folder will show those screenshots in the UI after the run.
