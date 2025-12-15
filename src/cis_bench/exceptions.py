"""Custom exceptions for CIS Benchmark CLI."""


class CISBenchError(Exception):
    """Base exception for CIS Benchmark CLI."""

    pass


class AuthenticationError(CISBenchError):
    """Raised when authentication fails or session is invalid."""

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
