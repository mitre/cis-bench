"""Configuration management for CIS Benchmark CLI.

Provides environment-aware configuration for database paths, directories,
and application settings. Supports test isolation.

Loads configuration from .env file if present.
"""

import os
from pathlib import Path

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
        """Get SSL verification setting.

        Checks environment variable.

        Priority:
        1. CIS_BENCH_VERIFY_SSL environment variable
        2. Default: False (don't verify - CIS WorkBench has cert issues)

        Returns:
            True to verify SSL certificates, False to disable verification
        """
        # Check environment variable first
        env_value = os.getenv("CIS_BENCH_VERIFY_SSL")

        if env_value is not None:
            # Parse as boolean (handles "true", "false", "1", "0", "yes", "no")
            return env_value.lower() in ("true", "1", "yes")

        # Default: DON'T verify SSL (CIS WorkBench has certificate issues)
        return False


# Convenience functions
def get_catalog_db_path() -> Path:
    """Get catalog database path (environment-aware)."""
    return Config.get_catalog_db_path()


def is_test_mode() -> bool:
    """Check if running in test mode."""
    return Config.is_test_environment()
