class WebDriverFactory:
    def __init__(self, browser_type, headless=False):
        self.browser_type = browser_type
        self.headless = headless

    @staticmethod
    def _project_root():
        import os

        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
        )

    @classmethod
    def _edge_driver_path(cls):
        """Prefer project-local or explicit path over stale system PATH drivers."""
        import os

        candidates = [
            os.environ.get("MSEDGEDRIVER_PATH"),
            os.path.join(cls._project_root(), "drivers", "msedgedriver"),
            "/usr/local/bin/msedgedriver",
        ]
        for path in candidates:
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None

    def create_driver(self):
        if self.browser_type == 'chrome':
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            import tempfile

            options = webdriver.ChromeOptions()
            if self.headless:
                options.add_argument('--headless')
            options.add_argument('--incognito')
            profile_dir = tempfile.mkdtemp(prefix='chrome-profile-')
            options.add_argument(f'--user-data-dir={profile_dir}')
            # Avoid native microphone/camera permission prompt (use fake UI / auto-grant)
            options.add_argument('--use-fake-ui-for-media-stream')
            options.add_argument('--use-fake-device-for-media-stream')
            # Use Selenium Manager (built-in since Selenium 4.6+) to get correct ChromeDriver
            # for Chrome 115+; webdriver-manager uses deprecated storage.googleapis.com URLs
            return webdriver.Chrome(service=Service(), options=options)
        elif self.browser_type == 'firefox':
            from selenium import webdriver
            from webdriver_manager.firefox import GeckoDriverManager
            import tempfile

            options = webdriver.FirefoxOptions()
            if self.headless:
                options.add_argument('--headless')
            # use a fresh temporary profile
            profile_dir = tempfile.mkdtemp(prefix='firefox-profile-')
            options.profile = webdriver.FirefoxProfile()
            options.profile.set_preference('browser.privatebrowsing.autostart', True)
            # note: Firefox uses profiles differently; temp profile ensures clean state
            return webdriver.Firefox(executable_path=GeckoDriverManager().install(), options=options)
        elif self.browser_type == 'edge' or self.browser_type == 'msedge':
            from selenium import webdriver
            from selenium.webdriver.edge.service import Service
            import tempfile

            options = webdriver.EdgeOptions()
            if self.headless:
                options.add_argument('--headless')
            options.add_argument('--incognito')
            profile_dir = tempfile.mkdtemp(prefix='edge-profile-')
            options.add_argument(f'--user-data-dir={profile_dir}')
            # Avoid native microphone/camera permission prompt (use fake UI / auto-grant)
            options.add_argument('--use-fake-ui-for-media-stream')
            options.add_argument('--use-fake-device-for-media-stream')
            edge_driver = self._edge_driver_path()
            service = Service(executable_path=edge_driver) if edge_driver else Service()
            return webdriver.Edge(service=service, options=options)
        elif self.browser_type == 'safari':
            from selenium import webdriver
            # SafariDriver is bundled with Safari on macOS
            return webdriver.Safari()
        else:
            raise ValueError(f"Unsupported browser type: {self.browser_type}")