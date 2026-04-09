# care.ai

This project is designed for developing and running Selenium scripts using Python. It provides a structured approach to organizing tests, page objects, and utility functions.

## Project Structure

```
care.ai
├── src
│   ├── __init__.py
│   ├── tests
│   │   ├── __init__.py
│   │   └── test_example.py
│   ├── pages
│   │   ├── __init__.py
│   │   └── base_page.py
│   ├── drivers
│   │   └── webdriver_factory.py
│   ├── utils
│   │   └── helpers.py
│   └── config
│       └── settings.py
├── requirements.txt
├── pyproject.toml
├── pytest.ini
├── .env
└── README.md
```

## Setup Instructions

1. **Clone the repository:**
   ```
   git clone <repository-url>
   cd care.ai
   ```

2. **Create a virtual environment:**
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Create a `.env` file in the root directory and add any necessary environment variables.

## Usage

- To run the tests, use the following command:
  ```
  pytest src/tests
  ```

- You can add new test cases in the `src/tests/test_example.py` file or create new test files in the `tests` directory.
- A sample login test has been added to `src/tests/test_login.py` which demonstrates authenticating to https://lab.care.ai with provided credentials. Run it using `pytest src/tests/test_login.py`.
- For manual experimentation, there is a script at `src/scripts/login_script.py` that exercises the same flow.

### Browser configuration
By default the tests use Chrome. You can override the `BROWSER` environment variable to any supported browser name:

| Value   | Browser                          |
|---------|----------------------------------|
| `chrome` (default) | Google Chrome/Chromium        |
| `firefox`          | Mozilla Firefox              |
| `edge` or `msedge` | Microsoft Edge (Chromium)    |
| `safari`           | Safari (macOS only)          |

Set `HEADLESS=true` to run without a visible window. The drivers are managed via `webdriver-manager`.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.