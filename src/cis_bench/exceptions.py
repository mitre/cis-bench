"""Custom exceptions for CIS Benchmark CLI."""

from gettext import ngettext


class CISBenchError(Exception):
    """Base exception for CIS Benchmark CLI."""

    pass


class ConfigurationError(CISBenchError, ValueError):
    """Raised when an environment setting is invalid.

    Subclasses ValueError so existing ``except ValueError`` callers keep working,
    while the CLI can tell configuration problems apart from bad user input.
    """

    pass


class AuthenticationError(CISBenchError):
    """Raised when authentication fails or session is invalid."""

    pass


class NoSavedSessionError(AuthenticationError):
    """Raised when a command needs a saved session and none exists.

    The remedy is always the same: run ``cis-bench auth login``.
    """

    pass


class TLSVerificationError(CISBenchError):
    """Raised when a WorkBench TLS handshake fails certificate verification.

    Distinct from AuthenticationError: the server could not be trusted, so no
    conclusion about the session is possible.
    """

    pass


class ScraperError(CISBenchError):
    """Raised when scraping fails."""

    pass


class FetchError(ScraperError):
    """Raised when a WorkBench request still fails after every retry.

    Carries the url so callers can report or skip the item that failed. The
    underlying requests exception is chained as ``__cause__``.
    """

    def __init__(self, url: str, attempts: int, message: str) -> None:
        super().__init__(
            ngettext(
                "{url}: {message} after {attempts} attempt",
                "{url}: {message} after {attempts} attempts",
                attempts,
            ).format(url=url, message=message, attempts=attempts)
        )
        self.url = url
        self.attempts = attempts


class IncompleteDownloadError(ScraperError):
    """Raised when pages of a benchmark could not be fetched or read: the benchmark is not
    downloaded, since a copy without them would be incomplete.

    Carries each failed page's url and what went wrong, in the order the pages were listed.
    """

    def __init__(self, benchmark_url: str, failures: list[tuple[str, str]]) -> None:
        lines = "\n".join(
            # Some errors already name the url (FetchError, requests.HTTPError): say it once.
            f"  {detail}" if url in detail else f"  {url}: {detail}"
            for url, detail in failures
        )
        super().__init__(
            ngettext(
                "{benchmark_url} was not downloaded: {count} page could not be fetched\n{lines}",
                "{benchmark_url} was not downloaded: {count} pages could not be fetched\n{lines}",
                len(failures),
            ).format(benchmark_url=benchmark_url, count=len(failures), lines=lines)
        )
        self.benchmark_url = benchmark_url
        self.failures = failures


class ParserError(CISBenchError):
    """Raised when parsing HTML fails."""

    pass


class ExportError(CISBenchError):
    """Raised when export fails."""

    pass
