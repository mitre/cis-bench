"""Authentication and cookie management for CIS WorkBench."""

import http.cookiejar
import logging
import platform
import threading
import time
from pathlib import Path

import browser_cookie3
import requests

# Enable system certificate store usage (macOS Keychain, Windows cert store, Linux /etc/ssl)
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    # truststore not installed, will use certifi bundle
    pass

from cis_bench.catalog.parser import WorkBenchCatalogParser
from cis_bench.config import Config

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages authentication for CIS WorkBench."""

    # Windows-specific error patterns that indicate permission/encryption issues
    WINDOWS_PERMISSION_PATTERNS = [
        "requires admin",
        "access is denied",
        "permission denied",
        "being used by another process",
        "winerror 5",
        "winerror 32",
    ]

    # Browsers that use Chromium's App-Bound Encryption on Windows
    CHROMIUM_BROWSERS = ["chrome", "edge", "brave", "chromium", "vivaldi", "opera"]

    @staticmethod
    def _is_windows_permission_error(error: Exception) -> bool:
        """Check if an error is a Windows-specific permission/encryption issue.

        Args:
            error: The exception to check

        Returns:
            True if this appears to be a Windows cookie access permission error
        """
        error_str = str(error).lower()
        return any(pattern in error_str for pattern in AuthManager.WINDOWS_PERMISSION_PATTERNS)

    @staticmethod
    def _get_fallback_browser(failed_browser: str) -> str | None:
        """Get a fallback browser when the primary browser fails on Windows.

        Firefox doesn't use App-Bound Encryption and works without admin on Windows.

        Args:
            failed_browser: The browser that failed

        Returns:
            Fallback browser name, or None if no fallback available
        """
        # Firefox is the fallback for all Chromium-based browsers
        if failed_browser.lower() in AuthManager.CHROMIUM_BROWSERS:
            return "firefox"
        # No fallback for Firefox or Safari
        return None

    @staticmethod
    def _format_windows_cookie_error(browser: str, error: Exception) -> str:
        """Format a helpful error message for Windows cookie extraction failures.

        Args:
            browser: The browser that failed
            error: The exception that occurred

        Returns:
            Formatted error message with actionable workarounds
        """
        return f"""Failed to extract cookies from {browser}: {error}

This is likely due to Chrome's App-Bound Encryption (Chrome 127+) on Windows,
which requires administrator privileges to decrypt cookies.

Workarounds:
1. Use Firefox instead (recommended - works without admin):
   cis-bench auth login --browser firefox

2. Close {browser} completely before running:
   (Chrome locks the cookie file while running)

3. Export cookies to a file manually:
   - Install a browser extension like "Get cookies.txt LOCALLY"
   - Export cookies for workbench.cisecurity.org
   - Use: cis-bench download <id> --cookies cookies.txt

4. Run as Administrator (not recommended for security reasons)
"""

    @staticmethod
    def load_cookies_from_browser(
        browser="chrome", verify_ssl=None, try_fallback: bool = False
    ) -> requests.Session:
        """Load cookies from browser using browser-cookie3.

        Args:
            browser: Browser name ('chrome', 'firefox', 'edge', 'safari')
            verify_ssl: SSL verification setting (None = use Config default)
            try_fallback: If True and on Windows, try Firefox if Chromium browser fails

        Returns:
            requests.Session with cookies loaded and SSL verification configured

        Raises:
            ValueError: If browser is not supported
            Exception: If cookie extraction fails
        """
        session = requests.Session()

        # Configure SSL verification globally for this session
        if verify_ssl is None:
            session.verify = Config.get_verify_ssl()
        else:
            session.verify = verify_ssl

        try:
            logger.debug(f"Extracting cookies from {browser}...")

            if browser.lower() == "chrome":
                cj = browser_cookie3.chrome(domain_name="workbench.cisecurity.org")
            elif browser.lower() == "firefox":
                cj = browser_cookie3.firefox(domain_name="workbench.cisecurity.org")
            elif browser.lower() == "edge":
                cj = browser_cookie3.edge(domain_name="workbench.cisecurity.org")
            elif browser.lower() == "safari":
                cj = browser_cookie3.safari(domain_name="workbench.cisecurity.org")
            else:
                raise ValueError(
                    f"Unsupported browser: {browser}. Use chrome, firefox, edge, or safari"
                )

            session.cookies = cj

            # Count cookies extracted
            cookie_count = len([c for c in cj if "workbench.cisecurity.org" in c.domain])
            logger.debug(f"Extracted {cookie_count} cookies from {browser}")

            return session

        except ValueError:
            # Re-raise ValueError as-is (for unsupported browser)
            raise
        except Exception as e:
            # Check if we should try a fallback browser on Windows
            is_windows = platform.system() == "Windows"
            is_permission_error = AuthManager._is_windows_permission_error(e)

            if try_fallback and is_windows and is_permission_error:
                fallback = AuthManager._get_fallback_browser(browser)
                if fallback:
                    logger.warning(
                        f"{browser} failed with permission error on Windows, "
                        f"trying {fallback} as fallback"
                    )
                    # Recursive call with fallback browser (no further fallback)
                    return AuthManager.load_cookies_from_browser(
                        fallback, verify_ssl=verify_ssl, try_fallback=False
                    )

            # No fallback available or not on Windows - raise with helpful message
            raise Exception(f"Failed to extract cookies from {browser}: {e}") from e

    @staticmethod
    def load_cookies_from_file(cookies_file: str, verify_ssl=None) -> requests.Session:
        """Load cookies from Netscape format cookies.txt file.

        Args:
            cookies_file: Path to cookies.txt file
            verify_ssl: SSL verification setting (None = use Config default)

        Returns:
            requests.Session with cookies loaded and SSL verification configured

        Raises:
            FileNotFoundError: If cookies file doesn't exist
            Exception: If cookie loading fails
        """
        session = requests.Session()

        # Configure SSL verification globally for this session
        if verify_ssl is None:
            session.verify = Config.get_verify_ssl()
        else:
            session.verify = verify_ssl

        try:
            logger.debug(f"Loading cookies from {cookies_file}...")
            cj = http.cookiejar.MozillaCookieJar(cookies_file)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj

            cookie_count = len(list(cj))
            logger.debug(f"Loaded {cookie_count} cookies from file")

            return session

        except FileNotFoundError as e:
            raise FileNotFoundError(f"Cookies file not found: {cookies_file}") from e
        except Exception as e:
            raise Exception(f"Failed to load cookies from file: {e}") from e

    @staticmethod
    def create_session_with_cookies(cookies_dict: dict) -> requests.Session:
        """Create session with cookie dictionary (for backward compatibility).

        Args:
            cookies_dict: Dictionary of cookie name/value pairs

        Returns:
            requests.Session with cookies loaded and SSL verification configured
        """
        session = requests.Session()

        # Configure SSL verification globally for this session
        session.verify = Config.get_verify_ssl()

        session.cookies.update(cookies_dict)

        logger.debug(f"Created session with {len(cookies_dict)} cookies")

        return session

    @staticmethod
    def get_authenticated_session(
        browser=None, cookies_file=None, cookies_dict=None
    ) -> requests.Session:
        """Get an authenticated session using the best available method.

        Priority:
        1. Browser cookies (if browser specified)
        2. Cookies file (if file specified)
        3. Cookie dictionary (if dict specified)

        Args:
            browser: Browser name to extract cookies from
            cookies_file: Path to cookies.txt file
            cookies_dict: Dictionary of cookies (fallback)

        Returns:
            requests.Session with cookies loaded

        Raises:
            ValueError: If no cookie source provided
        """
        if browser:
            return AuthManager.load_cookies_from_browser(browser)
        elif cookies_file:
            return AuthManager.load_cookies_from_file(cookies_file)
        elif cookies_dict:
            return AuthManager.create_session_with_cookies(cookies_dict)
        else:
            raise ValueError(
                "No cookie source provided. Specify browser, cookies_file, or cookies_dict"
            )

    @staticmethod
    def get_session_file_path() -> Path:
        """Get path to saved session cookies file.

        Returns:
            Path to session.cookies file in user's config directory
        """
        return Config.get_data_dir() / "session.cookies"

    @staticmethod
    def save_session(session: requests.Session) -> None:
        """Save session cookies to persistent file.

        Args:
            session: requests.Session with cookies to save

        Raises:
            Exception: If saving fails
        """
        session_path = AuthManager.get_session_file_path()

        try:
            # Ensure directory exists
            session_path.parent.mkdir(parents=True, exist_ok=True)

            # Create cookie jar and save
            cj = http.cookiejar.MozillaCookieJar(str(session_path))
            for cookie in session.cookies:
                cj.set_cookie(cookie)

            cj.save(ignore_discard=True, ignore_expires=True)

            cookie_count = len(list(session.cookies))
            logger.debug(f"Saved {cookie_count} cookies to {session_path}")

        except Exception as e:
            raise Exception(f"Failed to save session: {e}") from e

    @staticmethod
    def load_saved_session(verify_ssl=None) -> requests.Session:
        """Load previously saved session from persistent storage.

        Args:
            verify_ssl: SSL verification setting (None = use Config default)

        Returns:
            requests.Session with loaded cookies, or None if no saved session

        Raises:
            Exception: If loading fails (but not if file doesn't exist)
        """
        session_path = AuthManager.get_session_file_path()

        if not session_path.exists():
            logger.debug("No saved session found")
            return None

        try:
            logger.debug(f"Loading saved session from {session_path}")
            return AuthManager.load_cookies_from_file(str(session_path), verify_ssl=verify_ssl)

        except Exception as e:
            logger.warning(f"Failed to load saved session: {e}")
            # Return None instead of raising - let caller handle re-auth
            return None

    @staticmethod
    def clear_saved_session() -> bool:
        """Clear/delete saved session cookies.

        Returns:
            True if session was cleared, False if no session existed
        """
        session_path = AuthManager.get_session_file_path()

        if session_path.exists():
            try:
                session_path.unlink()
                logger.debug("Cleared saved session")
                return True
            except Exception as e:
                logger.error(f"Failed to clear session: {e}")
                raise Exception(f"Failed to clear session: {e}") from e
        else:
            logger.debug("No saved session to clear")
            return False

    @staticmethod
    def validate_session(session: requests.Session, verify_ssl: bool = True) -> bool:
        """Validate that session cookies are still valid.

        Args:
            session: Session to validate
            verify_ssl: Whether to verify SSL certificates (default: True)

        Returns:
            True if session is valid, False otherwise
        """
        if not session or not session.cookies:
            return False

        try:
            # Test session by making a simple request to CIS WorkBench
            response = session.get(
                "https://workbench.cisecurity.org/benchmarks",
                timeout=10,
                allow_redirects=False,
                verify=verify_ssl,
            )

            # If we get redirected (any 3xx), session is likely invalid
            # CIS WorkBench redirects to homepage (302) when unauthenticated
            if 300 <= response.status_code < 400:
                location = response.headers.get("Location", "")
                logger.debug(f"Session invalid - redirected to {location}")
                return False

            # Check if response is the login page (even with 200 OK status)
            if 200 <= response.status_code < 300:
                # Check if we got the login page instead of actual content
                if WorkBenchCatalogParser.is_login_page(response.text):
                    logger.debug("Session invalid - received login page")
                    return False

                logger.debug("Session validated successfully")
                return True

            logger.warning(f"Session validation returned status {response.status_code}")
            return False

        except Exception as e:
            logger.warning(f"Session validation failed: {e}")
            return False

    @staticmethod
    def get_or_create_session(
        browser=None, force_refresh=False, verify_ssl=True
    ) -> requests.Session:
        """Get authenticated session, using saved session if available.

        This is the main entry point for getting an authenticated session.
        It tries saved session first, then falls back to browser extraction.

        Args:
            browser: Browser to extract cookies from if needed
            force_refresh: Force refresh from browser even if saved session exists
            verify_ssl: Whether to verify SSL certificates (default: True)

        Returns:
            Authenticated requests.Session

        Raises:
            ValueError: If no saved session and no browser specified
            Exception: If authentication fails
        """
        # If force refresh, skip saved session
        if not force_refresh:
            # Try to load saved session
            saved_session = AuthManager.load_saved_session(verify_ssl=verify_ssl)

            if saved_session:
                # Validate the saved session
                if AuthManager.validate_session(saved_session, verify_ssl=verify_ssl):
                    logger.debug("Using saved session")
                    return saved_session
                else:
                    logger.info("Saved session invalid, need to re-authenticate")
                    # Clear invalid session
                    AuthManager.clear_saved_session()

        # No valid saved session, need to authenticate
        if not browser:
            raise ValueError(
                "No saved session found. Please run 'cis-bench auth login --browser <browser>' to authenticate"
            )

        # Extract fresh cookies from browser
        logger.debug(f"Authenticating via {browser}")
        session = AuthManager.load_cookies_from_browser(browser, verify_ssl=verify_ssl)

        # Validate new session
        if not AuthManager.validate_session(session, verify_ssl=verify_ssl):
            raise Exception(
                f"Failed to authenticate. Please ensure you are logged into workbench.cisecurity.org in {browser}"
            )

        # Save for future use
        AuthManager.save_session(session)

        return session


class SessionKeepAlive:
    """Background service to keep CIS WorkBench session alive.

    Runs periodic pings to prevent session timeout during long TUI sessions.

    Usage:
        session = AuthManager.get_or_create_session()
        keep_alive = SessionKeepAlive(session, interval_minutes=5)
        keep_alive.start()
        try:
            # ... long-running TUI session ...
        finally:
            keep_alive.stop()

    Or as context manager:
        with SessionKeepAlive(session) as ka:
            # ... TUI session ...
    """

    # Default interval between pings (5 minutes)
    DEFAULT_INTERVAL_MINUTES = 5

    def __init__(
        self,
        session: requests.Session,
        interval_minutes: float = DEFAULT_INTERVAL_MINUTES,
        verify_ssl: bool = True,
        on_session_expired: callable = None,
    ):
        """Initialize session keep-alive service.

        Args:
            session: Authenticated requests.Session to keep alive
            interval_minutes: Minutes between keep-alive pings (default: 5)
            verify_ssl: Whether to verify SSL certificates
            on_session_expired: Optional callback when session expires
        """
        self.session = session
        self.interval_seconds = interval_minutes * 60
        self.verify_ssl = verify_ssl
        self.on_session_expired = on_session_expired

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_ping: float = 0
        self._ping_count: int = 0
        self._is_healthy: bool = True

    def start(self) -> None:
        """Start the keep-alive background thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.debug("SessionKeepAlive already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="session-keep-alive",
            daemon=True,  # Don't prevent app exit
        )
        self._thread.start()
        logger.debug(f"SessionKeepAlive started (interval: {self.interval_seconds}s)")

    def stop(self) -> None:
        """Stop the keep-alive background thread."""
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join(timeout=2)
        self._thread = None
        logger.debug(f"SessionKeepAlive stopped (total pings: {self._ping_count})")

    def _run_loop(self) -> None:
        """Main loop - runs in background thread."""
        while not self._stop_event.is_set():
            # Wait for interval (or stop signal)
            if self._stop_event.wait(timeout=self.interval_seconds):
                break  # Stop was requested

            # Perform ping
            self._ping()

    def _ping(self) -> bool:
        """Ping CIS WorkBench to keep session alive.

        Returns:
            True if session is still valid, False if expired
        """
        try:
            is_valid = AuthManager.validate_session(
                self.session,
                verify_ssl=self.verify_ssl,
            )

            self._last_ping = time.time()
            self._ping_count += 1

            if is_valid:
                self._is_healthy = True
                logger.debug(f"Session keep-alive ping #{self._ping_count} successful")
            else:
                self._is_healthy = False
                logger.warning("Session expired during keep-alive ping")
                if self.on_session_expired:
                    try:
                        self.on_session_expired()
                    except Exception as e:
                        logger.error(f"Error in on_session_expired callback: {e}")

            return is_valid

        except Exception as e:
            logger.warning(f"Session keep-alive ping failed: {e}")
            self._is_healthy = False
            return False

    @property
    def is_running(self) -> bool:
        """Check if keep-alive thread is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_healthy(self) -> bool:
        """Check if last ping was successful."""
        return self._is_healthy

    @property
    def ping_count(self) -> int:
        """Get total number of pings performed."""
        return self._ping_count

    def __enter__(self) -> "SessionKeepAlive":
        """Context manager entry - starts keep-alive."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - stops keep-alive."""
        self.stop()
