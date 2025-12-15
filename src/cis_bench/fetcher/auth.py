"""Authentication and cookie management for CIS WorkBench."""

import http.cookiejar
import logging
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

    @staticmethod
    def load_cookies_from_browser(browser="chrome", verify_ssl=None) -> requests.Session:
        """Load cookies from browser using browser-cookie3.

        Args:
            browser: Browser name ('chrome', 'firefox', 'edge', 'safari')
            verify_ssl: SSL verification setting (None = use Config default)

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
            # Catch browser-specific exceptions (database locked, etc.)
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
