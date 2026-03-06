import os

base_url = os.getenv("BASE_URL", "http://example.com")
# number of seconds to wait when explicit waits are needed
try:
    timeout = int(os.getenv("TIMEOUT", "10"))
except ValueError:
    timeout = 10

# browser configuration
browser = os.getenv("BROWSER", "edge")  # Options: chrome, firefox, edge, safari
headless = os.getenv("HEADLESS", "False").lower() in ("true", "1", "yes")  # run in headless mode if set