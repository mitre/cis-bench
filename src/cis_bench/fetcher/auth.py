"""Authentication and cookie management for CIS WorkBench."""

import http.cookiejar
import logging
import platform
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import browser_cookie3
import requests
from bs4 import BeautifulSoup

# Enable system certificate store usage (macOS Keychain, Windows cert store, Linux /etc/ssl)
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    # truststore not installed, will use certifi bundle
    pass

from cis_bench.config import (
    CIS_ROOT_DOMAIN,
    MAX_SSO_REDIRECTS,
    RETRYABLE_STATUS_CODES,
    TRUSTED_SSO_HOSTS,
    RequestPolicy,
    is_cis_domain,
)
from cis_bench.exceptions import (
    AuthenticationError,
    FetchError,
    NoSavedSessionError,
    TLSVerificationError,
)
from cis_bench.fetcher.http import attempts_allowed, new_workbench_session
from cis_bench.utils.workbench_urls import catalog_listing_url

logger = logging.getLogger(__name__)


def is_workbench_login_page(html: str) -> bool:
    """Return True if HTML represents a CIS WorkBench login page."""
    if not html:
        return False

    soup = BeautifulSoup(html, "html.parser")
    login_indicators = [
        soup.find("form", action=re.compile(r"/login")),
        soup.find("input", {"name": "login"}),
        soup.find("input", {"name": "password"}),
        soup.find("div", class_="index-signin-wrapper"),
        soup.find(string=re.compile(r"E-Mail or Username", re.I)),
    ]
    return any(indicator is not None for indicator in login_indicators)


def _is_a_rejection(status: int) -> bool:
    """Whether this answer to the session check means WorkBench does not accept the session.

    A redirect (to the login page, or one more after the SSO handshake) and 401/403 do; any
    other error status only means WorkBench did not answer the question.
    """
    return 300 <= status < 400 or status in (401, 403)


def _no_answer(session: requests.Session, url: str, response: requests.Response) -> FetchError:
    """The error for a session check WorkBench answered with an error status."""
    retried = response.status_code in RETRYABLE_STATUS_CODES
    attempts = attempts_allowed(session, url) if retried else 1
    return FetchError(url, attempts, f"HTTP {response.status_code}")


class AuthManager:
    """Authentication for CIS WorkBench: browser and file cookies, the saved session, its check.

    Built with everything it depends on, so it reads no settings itself: the CLI builds one
    per command from the run's settings (cli/helpers/services.py).
    """

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

    def __init__(
        self,
        *,
        workbench_url: str,
        verify_ssl: bool,
        session_file: Path,
        request_policy: RequestPolicy,
        timeout: tuple[float, float],
    ):
        """
        Args:
            workbench_url: The WorkBench origin (already validated), e.g. https://workbench.cisecurity.org
            verify_ssl: Whether every session this manager makes verifies TLS certificates
            session_file: Where the saved session's cookies live
            request_policy: Pacing and retries of every session it makes, from the session
                check on
            timeout: (connect, read) seconds each request of the session check may take
        """
        self.workbench_url = workbench_url
        self.verify_ssl = verify_ssl
        self.session_file = session_file
        self.request_policy = request_policy
        self.timeout = timeout

    @property
    def workbench_host(self) -> str:
        return urlparse(self.workbench_url).netloc

    def _new_session(self) -> requests.Session:
        session = new_workbench_session(self.request_policy)
        session.verify = self.verify_ssl
        return session

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

    def _format_windows_cookie_error(self, browser: str, error: Exception) -> str:
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
   - Export cookies for {self.workbench_host}
   - Use: cis-bench auth login --cookies cookies.txt

4. Run as Administrator (not recommended for security reasons)
"""

    def load_cookies_from_browser(
        self, browser: str = "chrome", try_fallback: bool = False
    ) -> requests.Session:
        """Load cookies from browser using browser-cookie3.

        Args:
            browser: Browser name ('chrome', 'firefox', 'edge', 'safari')
            try_fallback: If True and on Windows, try Firefox if Chromium browser fails

        Returns:
            requests.Session with the CIS cookies, this manager's TLS setting and rate

        Raises:
            ValueError: If browser is not supported
            Exception: If cookie extraction fails
        """
        session = self._new_session()

        browser_loaders = {
            "chrome": browser_cookie3.chrome,
            "firefox": browser_cookie3.firefox,
            "edge": browser_cookie3.edge,
            "safari": browser_cookie3.safari,
        }

        try:
            logger.debug(f"Extracting cookies from {browser}...")

            loader = browser_loaders.get(browser.lower())
            if loader is None:
                raise ValueError(
                    f"Unsupported browser: {browser}. Use chrome, firefox, edge, or safari"
                )

            cj = loader(domain_name=CIS_ROOT_DOMAIN)
            for cookie in cj:
                if is_cis_domain(cookie.domain):
                    session.cookies.set_cookie(cookie)

            cookie_count = len(list(session.cookies))
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
                    return self.load_cookies_from_browser(fallback, try_fallback=False)

            # No fallback available or not on Windows - raise with helpful message
            raise Exception(f"Failed to extract cookies from {browser}: {e}") from e

    def load_cookies_from_file(self, cookies_file: str | Path) -> requests.Session:
        """Load cookies from Netscape format cookies.txt file.

        Args:
            cookies_file: Path to cookies.txt file

        Returns:
            requests.Session with the file's cookies, this manager's TLS setting and rate

        Raises:
            FileNotFoundError: If cookies file doesn't exist
            Exception: If cookie loading fails
        """
        session = self._new_session()

        try:
            logger.debug(f"Loading cookies from {cookies_file}...")
            cj = http.cookiejar.MozillaCookieJar(str(cookies_file))
            cj.load(ignore_discard=True, ignore_expires=True)
            for cookie in cj:
                session.cookies.set_cookie(cookie)

            cookie_count = len(list(session.cookies))
            logger.debug(f"Loaded {cookie_count} cookies from file")

            return session

        except FileNotFoundError as e:
            raise FileNotFoundError(f"Cookies file not found: {cookies_file}") from e
        except Exception as e:
            raise Exception(f"Failed to load cookies from file: {e}") from e

    def save_session(self, session: requests.Session) -> None:
        """Save session cookies to the session file.

        Args:
            session: requests.Session with cookies to save

        Raises:
            Exception: If saving fails
        """
        session_path = self.session_file

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

    def load_saved_session(self) -> requests.Session | None:
        """Load the previously saved session from the session file.

        Returns:
            requests.Session with loaded cookies, or None if no saved session or unreadable
        """
        session_path = self.session_file

        if not session_path.exists():
            logger.debug("No saved session found")
            return None

        try:
            logger.debug(f"Loading saved session from {session_path}")
            return self.load_cookies_from_file(session_path)

        except Exception as e:
            logger.warning(f"Failed to load saved session: {e}")
            # Return None instead of raising - let caller handle re-auth
            return None

    def clear_saved_session(self) -> bool:
        """Clear/delete saved session cookies.

        Returns:
            True if session was cleared, False if no session existed
        """
        session_path = self.session_file

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

    def validate_session(self, session: requests.Session | None) -> bool:
        """Validate that session cookies are still valid, completing trusted CIS Auth0 SSO redirects.

        Args:
            session: Session to validate

        Returns:
            True if WorkBench accepts the session on this manager's host; False if WorkBench
            rejected it (a login page or a redirect to login, 401 or 403)

        Raises:
            TLSVerificationError: If the server certificate cannot be verified. This is
                raised rather than returned as False so callers never report a trust
                failure as an expired session.
            FetchError: If WorkBench could not be asked (a timeout or connection failure
                after the retries, or an error status). Nothing is known about the session
                then, so this is never reported as False.
        """
        if not session or not session.cookies:
            return False

        workbench_host = self.workbench_host
        benchmarks_url = catalog_listing_url(base_url=self.workbench_url)
        trusted_hosts = TRUSTED_SSO_HOSTS | {workbench_host}

        requested = benchmarks_url
        try:
            current_url = benchmarks_url

            for _ in range(MAX_SSO_REDIRECTS + 1):
                requested = current_url
                response = session.get(
                    current_url,
                    timeout=self.timeout,
                    allow_redirects=False,
                    verify=self.verify_ssl,
                )

                if 300 <= response.status_code < 400:
                    location = response.headers.get("Location", "")
                    if not location:
                        logger.debug("Session invalid - redirect missing Location header")
                        return False

                    next_url = urljoin(current_url, location)
                    parsed = urlparse(next_url)

                    if parsed.scheme != "https" or parsed.netloc not in trusted_hosts:
                        logger.debug(f"Session invalid - untrusted redirect target: {next_url}")
                        return False

                    if parsed.path.startswith("/login") or parsed.path.startswith("/u/login"):
                        logger.debug(f"Session invalid - redirected to login: {next_url}")
                        return False

                    if next_url == current_url:
                        logger.debug(f"Session invalid - self-redirect loop at {next_url}")
                        return False

                    current_url = next_url
                    continue

                if 200 <= response.status_code < 300:
                    if urlparse(current_url).netloc != workbench_host:
                        logger.debug(
                            f"Session invalid - SSO stopped off WorkBench host at {current_url}"
                        )
                        return False

                    if is_workbench_login_page(response.text):
                        logger.debug("Session invalid - received login page")
                        return False

                    if current_url != benchmarks_url:
                        requested = benchmarks_url
                        bench_response = session.get(
                            benchmarks_url,
                            timeout=self.timeout,
                            allow_redirects=False,
                            verify=self.verify_ssl,
                        )
                        if not (200 <= bench_response.status_code < 300):
                            if not _is_a_rejection(bench_response.status_code):
                                raise _no_answer(session, benchmarks_url, bench_response)
                            logger.debug(
                                "Session invalid - /benchmarks inaccessible after SSO handshake"
                            )
                            return False
                        if is_workbench_login_page(bench_response.text):
                            logger.debug("Session invalid - /benchmarks returned login page")
                            return False

                    logger.debug("Session validated successfully")
                    return True

                if not _is_a_rejection(response.status_code):
                    raise _no_answer(session, current_url, response)
                logger.debug(f"Session invalid - WorkBench answered {response.status_code}")
                return False

            logger.debug("Session invalid - exceeded maximum SSO redirects")
            return False

        except requests.exceptions.SSLError as e:
            logger.error(f"TLS certificate verification failed for {workbench_host}: {e}")
            raise TLSVerificationError(
                f"TLS certificate verification failed for {workbench_host}: {e}. "
                "If a proxy re-signs HTTPS traffic, point REQUESTS_CA_BUNDLE at its CA "
                "bundle; to skip verification entirely set CIS_BENCH_VERIFY_SSL=false."
            ) from e
        except requests.exceptions.RequestException as e:
            # WorkBench could not be asked; that says nothing about the session.
            raise FetchError(requested, attempts_allowed(session, requested), str(e)) from e

    def get_or_create_session(
        self, browser: str | None = None, force_refresh: bool = False
    ) -> requests.Session:
        """Get an authenticated session, using the saved session if it is still valid.

        This is the main entry point for getting an authenticated session.
        It tries the saved session first, then falls back to browser extraction.

        Args:
            browser: Browser to extract cookies from if needed
            force_refresh: Force refresh from browser even if saved session exists

        Returns:
            Authenticated requests.Session

        Raises:
            NoSavedSessionError: If no saved session exists and no browser was given
            AuthenticationError: If freshly extracted browser cookies are not accepted by WorkBench
            TLSVerificationError: If the WorkBench certificate cannot be verified
            FetchError: If WorkBench could not be reached to check a session; the saved
                session is left as it is
        """
        # If force refresh, skip saved session
        if not force_refresh:
            saved_session = self.load_saved_session()

            if saved_session:
                if self.validate_session(saved_session):
                    logger.debug("Using saved session")
                    return saved_session
                logger.info("Saved session invalid, need to re-authenticate")
                self.clear_saved_session()

        # No valid saved session, need to authenticate
        if not browser:
            raise NoSavedSessionError(
                "No saved session found. Please run 'cis-bench auth login --browser <browser>' to authenticate"
            )

        # Extract fresh cookies from browser
        logger.debug(f"Authenticating via {browser}")
        session = self.load_cookies_from_browser(browser)

        if not self.validate_session(session):
            raise AuthenticationError(
                f"Failed to authenticate. Please ensure you are logged into {self.workbench_host} in {browser}"
            )

        # Save for future use
        self.save_session(session)

        return session
