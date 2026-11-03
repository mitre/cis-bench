"""Configuration management for CIS Benchmark CLI.

Provides environment-aware configuration for database paths, directories,
and application settings. Supports test isolation.

Loads configuration from .env file if present.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from cis_bench.exceptions import ConfigurationError

# Load .env file if it exists (production/dev use)
# Tests don't need this - they set env vars directly
try:
    from dotenv import load_dotenv

    # Try to load from ~/.cis-bench/.env
    env_file = Path.home() / ".cis-bench" / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    # python-dotenv not installed - use environment variables only
    pass


class Config:
    """Application configuration (environment-aware)."""

    CIS_ROOT_DOMAIN = "cisecurity.org"
    _VERIFY_SSL_TRUE_VALUES = frozenset({"true", "1", "yes"})
    _VERIFY_SSL_FALSE_VALUES = frozenset({"false", "0", "no"})
    DEFAULT_WORKBENCH_URL = f"https://workbench.{CIS_ROOT_DOMAIN}"

    @staticmethod
    def is_cis_domain(host: str) -> bool:
        """Return True when host belongs to cisecurity.org or one of its subdomains."""
        normalized = host.lstrip(".").lower()
        return normalized == Config.CIS_ROOT_DOMAIN or normalized.endswith(
            f".{Config.CIS_ROOT_DOMAIN}"
        )

    @staticmethod
    def get_workbench_base_url() -> str:
        """Get validated CIS WorkBench base URL.

        Reads CIS_BENCH_WORKBENCH_URL when set, defaulting to
        https://workbench.cisecurity.org. Only https:// origins on
        cisecurity.org or *.cisecurity.org without path, query, fragment,
        or embedded credentials are accepted.
        """
        raw = os.getenv("CIS_BENCH_WORKBENCH_URL", "").strip()
        if not raw:
            return Config.DEFAULT_WORKBENCH_URL

        candidate = raw.rstrip("/")
        parsed = urlparse(candidate)
        hostname = parsed.hostname

        if (
            parsed.scheme.lower() != "https"
            or not hostname
            or not Config.is_cis_domain(hostname)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != ""
            or bool(parsed.params)
            or bool(parsed.query)
            or bool(parsed.fragment)
        ):
            raise ConfigurationError(
                f"Invalid CIS_BENCH_WORKBENCH_URL '{raw}': must be an https://*.cisecurity.org origin without path, query, fragment, or credentials"
            )

        return f"https://{parsed.netloc.lower()}"

    @staticmethod
    def get_environment() -> str:
        """Get current environment.

        Returns:
            'test', 'dev', or 'production'
        """
        env = os.getenv("CIS_BENCH_ENV", "production")
        return env.lower()

    @staticmethod
    def is_test_environment() -> bool:
        """Check if running in test environment.

        Returns:
            True if CIS_BENCH_ENV=test
        """
        return Config.get_environment() == "test"

    @staticmethod
    def is_dev_environment() -> bool:
        """Check if running in development environment.

        Returns:
            True if CIS_BENCH_ENV=dev
        """
        return Config.get_environment() == "dev"

    @staticmethod
    def get_data_dir() -> Path:
        """Get data directory path.

        Returns:
            /tmp/cis-bench-test/ for tests
            ~/.cis-bench-dev/ for development
            ~/.cis-bench/ for production
        """
        env = Config.get_environment()

        if env == "test":
            # Test mode: use system temp directory (ephemeral)
            import tempfile

            return Path(tempfile.gettempdir()) / "cis-bench-test"
        elif env == "dev":
            # Dev mode: separate from production
            return Path.home() / ".cis-bench-dev"
        else:
            # Production mode
            return Path.home() / ".cis-bench"

    @staticmethod
    def get_catalog_db_path() -> Path:
        """Get catalog database path.

        Returns:
            Path to catalog.db (environment-aware)
        """
        return Config.get_data_dir() / "catalog.db"

    @staticmethod
    def get_benchmarks_dir() -> Path:
        """Get benchmarks storage directory.

        Returns:
            Path to benchmarks directory
        """
        return Config.get_data_dir() / "benchmarks"

    @staticmethod
    def ensure_directories():
        """Create necessary directories if they don't exist."""
        Config.get_data_dir().mkdir(parents=True, exist_ok=True)
        Config.get_benchmarks_dir().mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_config_path() -> Path:
        """Get config file path.

        Returns:
            Path to config.yaml
        """
        return Config.get_data_dir() / "config.yaml"

    @staticmethod
    def get_table_title_width() -> int:
        """Get table title column width.

        Returns:
            Column width for title (default: 90 for 120+ char terminals)
        """
        width = os.getenv("CIS_BENCH_TABLE_TITLE_WIDTH")
        if width and width.isdigit():
            return int(width)
        return 90

    @staticmethod
    def get_search_default_limit() -> int:
        """Get default search result limit.

        Returns:
            Default limit for search results (default: 1000)
        """
        limit = os.getenv("CIS_BENCH_SEARCH_LIMIT")
        if limit and limit.isdigit():
            return int(limit)
        return 1000

    @staticmethod
    def get_verify_ssl() -> bool:
        """Get the TLS certificate verification setting for WorkBench requests.

        Verification is on unless ``CIS_BENCH_VERIFY_SSL`` explicitly opts out.

        Accepted values (case-insensitive, surrounding whitespace ignored):
        ``true``/``1``/``yes`` keep verification on, ``false``/``0``/``no`` turn it
        off. Unset or blank means on.

        Returns:
            True to verify certificates, False to skip verification.

        Raises:
            ConfigurationError: If the variable holds any other value. A typo in a
                security setting must never silently disable verification.
        """
        env_value = os.getenv("CIS_BENCH_VERIFY_SSL")
        if env_value is None or not env_value.strip():
            return True

        normalized = env_value.strip().lower()
        if normalized in Config._VERIFY_SSL_TRUE_VALUES:
            return True
        if normalized in Config._VERIFY_SSL_FALSE_VALUES:
            return False
        raise ConfigurationError(
            f"CIS_BENCH_VERIFY_SSL has unrecognized value {env_value!r}; "
            "use true/1/yes to verify certificates or false/0/no to disable verification"
        )


# Convenience functions
def get_catalog_db_path() -> Path:
    """Get catalog database path (environment-aware)."""
    return Config.get_catalog_db_path()


def is_test_mode() -> bool:
    """Check if running in test mode."""
    return Config.is_test_environment()


def get_workbench_base_url() -> str:
    """Get validated CIS WorkBench base URL (environment-aware)."""
    return Config.get_workbench_base_url()
