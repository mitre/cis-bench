"""Logging configuration for CIS Benchmark CLI.

Provides centralized logging setup with consistent formatting and levels.
"""

import logging
import sys


class LoggingConfig:
    """Configure logging for the application."""

    # Log format
    DEFAULT_FORMAT = "%(levelname)s: %(name)s: %(message)s"
    VERBOSE_FORMAT = (
        "%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s"
    )

    # Log levels
    QUIET = logging.WARNING
    NORMAL = logging.INFO
    VERBOSE = logging.DEBUG

    @classmethod
    def setup(cls, level: int = logging.INFO, verbose: bool = False) -> None:
        """Configure logging for the application.

        Args:
            level: Logging level (logging.INFO, logging.DEBUG, etc.)
            verbose: If True, use detailed format with timestamps and line numbers

        Example:
            >>> LoggingConfig.setup(level=logging.DEBUG, verbose=True)
            >>> logger = logging.getLogger(__name__)
            >>> logger.debug("Debug message")
        """
        # Choose format based on verbosity
        log_format = cls.VERBOSE_FORMAT if verbose else cls.DEFAULT_FORMAT

        # Configure root logger
        logging.basicConfig(
            level=level,
            format=log_format,
            stream=sys.stderr,  # Send logs to stderr (stdout for program output)
            force=True,  # Override any existing configuration
        )

        # Reduce noise from third-party libraries
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("xsdata").setLevel(logging.WARNING)

    @classmethod
    def setup_from_flags(cls, quiet: bool = False, verbose: bool = False) -> None:
        """Configure logging based on CLI flags.

        Args:
            quiet: If True, only show warnings and errors
            verbose: If True, show debug messages with detailed format

        Example:
            >>> LoggingConfig.setup_from_flags(quiet=False, verbose=True)
        """
        if quiet:
            level = cls.QUIET
        elif verbose:
            level = cls.VERBOSE
        else:
            level = cls.NORMAL

        cls.setup(level=level, verbose=verbose)

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get a logger instance for a module.

        Args:
            name: Module name (usually __name__)

        Returns:
            Logger instance

        Example:
            >>> logger = LoggingConfig.get_logger(__name__)
            >>> logger.info("Information message")
        """
        return logging.getLogger(name)
