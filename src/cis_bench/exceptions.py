"""Custom exceptions for CIS Benchmark CLI."""


class CISBenchError(Exception):
    """Base exception for CIS Benchmark CLI."""

    pass


class AuthenticationError(CISBenchError):
    """Raised when authentication fails or session is invalid."""

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
