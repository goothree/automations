class WebDriverFactory:
    def __init__(self, browser_type, headless=False):
        self.browser_type = browser_type
        self.headless = headless

    def create_driver(self):
        # using webdriver-manager to automatically manage driver binaries
        if self.browser_type == 'chrome':
            from selenium import webdriver
            from webdriver_manager.chrome import ChromeDriverManager
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
            return webdriver.Chrome(ChromeDriverManager().install(), options=options)
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
            import tempfile
            import shutil

            options = webdriver.EdgeOptions()
            if self.headless:
                options.add_argument('--headless')
            options.add_argument('--incognito')
            profile_dir = tempfile.mkdtemp(prefix='edge-profile-')
            options.add_argument(f'--user-data-dir={profile_dir}')
            # Avoid native microphone/camera permission prompt (use fake UI / auto-grant)
            options.add_argument('--use-fake-ui-for-media-stream')
            options.add_argument('--use-fake-device-for-media-stream')

            import os
            driver_path = None
            # Prefer local msedgedriver (e.g. /usr/local/bin/msedgedriver)
            for path in ('/usr/local/bin/msedgedriver', '/opt/homebrew/bin/msedgedriver'):
                if os.path.isfile(path):
                    driver_path = path
                    break
            if not driver_path:
                driver_path = shutil.which('msedgedriver')
            if not driver_path:
                try:
                    from webdriver_manager.microsoft import EdgeChromiumDriverManager
                    driver_path = EdgeChromiumDriverManager().install()
                except Exception:
                    pass
            if not driver_path:
                raise RuntimeError(
                    'Could not get EdgeDriver (network failed and no local msedgedriver found). '
                    'Install msedgedriver (e.g. brew install msedgedriver) or check network.'
                )
            from selenium.webdriver.edge.service import Service
            return webdriver.Edge(service=Service(executable_path=driver_path), options=options)
        elif self.browser_type == 'safari':
            from selenium import webdriver
            # SafariDriver is bundled with Safari on macOS
            return webdriver.Safari()
        else:
            raise ValueError(f"Unsupported browser type: {self.browser_type}")