"""Custom exceptions for CIS Benchmark CLI."""


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


class ParserError(CISBenchError):
    """Raised when parsing HTML fails."""

    pass


class ExportError(CISBenchError):
    """Raised when export fails."""

    pass
