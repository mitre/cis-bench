"""cis-bench settings: one typed, validated Settings class and the fixed request policy.

Every user setting is a field of ``Settings``. A value comes from, highest first:

1. a value passed in (``load_settings(search_limit=...)``, how a CLI flag overrides);
2. the environment (``CIS_BENCH_SEARCH_LIMIT``);
3. ``<data dir>/.env`` (the same ``CIS_BENCH_*`` names);
4. ``<data dir>/config.toml`` (the field names: ``search_limit = 100``);
5. the default.

``CIS_BENCH_DATA_DIR`` (default ``~/.cis-bench``) locates the data folder, and with it both
files, so it is read from the environment (or a passed-in value) only.

Nothing is copied into the process environment. Variables that belong to the HTTP stack,
such as HTTPS_PROXY, NO_PROXY, REQUESTS_CA_BUNDLE and SSL_CERT_FILE, stay with requests.
"""

import os
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, ValidationError, field_validator
from pydantic_core import ErrorDetails
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from cis_bench import __version__
from cis_bench.exceptions import ConfigurationError

ENV_PREFIX = "CIS_BENCH_"
DATA_DIR_VARIABLE = f"{ENV_PREFIX}DATA_DIR"
DOTENV_FILE_NAME = ".env"
CONFIG_FILE_NAME = "config.toml"
CIS_ROOT_DOMAIN = "cisecurity.org"
DEFAULT_WORKBENCH_URL = f"https://workbench.{CIS_ROOT_DOMAIN}"
# The connect timeout of every WorkBench request; never longer than the read timeout.
CONNECT_TIMEOUT_SECONDS = 10.0

_VERIFY_SSL_TRUE_VALUES = frozenset({"true", "1", "yes"})
_VERIFY_SSL_FALSE_VALUES = frozenset({"false", "0", "no"})
_VERIFY_SSL_ACCEPTED = (
    "true/1/yes to verify certificates or false/0/no to disable verification "
    "(in config.toml also true or false)"
)
_WORKBENCH_URL_ACCEPTED = (
    "an https://*.cisecurity.org origin without path, query, fragment, or credentials"
)


def is_cis_domain(host: str) -> bool:
    """Return True when host belongs to cisecurity.org or one of its subdomains."""
    normalized = host.lstrip(".").lower()
    return normalized == CIS_ROOT_DOMAIN or normalized.endswith(f".{CIS_ROOT_DOMAIN}")


def _default_data_dir() -> Path:
    return Path.home() / ".cis-bench"


def _normalize_data_dir(value: Any) -> Path:
    """One reading of a data folder value: surrounding spaces dropped, ~ expanded."""
    return Path(str(value).strip()).expanduser()


def _data_dir_for(init_kwargs: dict[str, Any], env_values: dict[str, Any]) -> Path:
    """The data folder a load reads its files from: passed in, else the environment, else the default.

    env_values comes from pydantic-settings' own environment source, so the variable is found
    exactly as the Settings field finds it.
    """
    if any(name.upper() == "CIS_BENCH_ENV" for name in os.environ):
        raise ConfigurationError(
            "CIS_BENCH_ENV is no longer used; set CIS_BENCH_DATA_DIR to the folder that holds "
            "catalog.db, session.cookies, .env and config.toml (default ~/.cis-bench)"
        )
    for value in (init_kwargs.get("data_dir"), env_values.get("data_dir")):
        if value is not None and str(value).strip():
            return _normalize_data_dir(value)
    return _default_data_dir()


class _Source(PydanticBaseSettingsSource):
    """The environment, .env or config.toml, with blank values left to the next source.

    A file source may not set the data folder: the data folder locates the file.
    """

    def __init__(self, source: PydanticBaseSettingsSource, file_name: str | None = None):
        super().__init__(source.settings_cls)
        self._source = source
        self._file_name = file_name

    def get_field_value(self, field, field_name):
        # Never called: __call__ below returns the wrapped source's values whole.
        raise NotImplementedError

    def __call__(self) -> dict[str, Any]:
        values = {
            name: value
            for name, value in self._source().items()
            if not (isinstance(value, str) and not value.strip())
        }
        if self._file_name is not None and "data_dir" in values:
            raise ConfigurationError(
                f"{DATA_DIR_VARIABLE} cannot be set in {self._file_name}: it locates that file; "
                "set it in the environment"
            )
        return values


class Settings(BaseSettings):
    """Every cis-bench setting, with its type, default and accepted values."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        extra="forbid",  # an unknown CIS_BENCH_* name in .env or config.toml is a typo
    )

    data_dir: Path = Field(
        default_factory=_default_data_dir,
        description="Folder for catalog.db, session.cookies, benchmarks/, .env and config.toml",
        json_schema_extra={"accepted": "a folder path, set in the environment only"},
    )
    workbench_url: str = Field(
        default=DEFAULT_WORKBENCH_URL,
        description="CIS WorkBench origin",
        json_schema_extra={"accepted": _WORKBENCH_URL_ACCEPTED},
    )
    request_timeout: float = Field(
        default=30.0,
        gt=0,
        allow_inf_nan=False,
        description="Read timeout of every WorkBench request, in seconds",
        json_schema_extra={"accepted": "a finite number of seconds greater than 0"},
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verify WorkBench TLS certificates",
        json_schema_extra={"accepted": _VERIFY_SSL_ACCEPTED},
    )
    search_limit: int = Field(
        default=100,
        ge=1,
        description="Default number of results for search, catalog search, catalog list and get",
        json_schema_extra={"accepted": "an integer of 1 or more"},
    )
    table_title_width: int = Field(
        default=90,
        ge=1,
        description="Widest the Title column of the search and get tables may grow, in characters",
        json_schema_extra={"accepted": "an integer of 1 or more"},
    )

    @field_validator("data_dir", mode="before")
    @classmethod
    def _read_data_dir(cls, value: Any) -> Path:
        return _normalize_data_dir(value)

    @field_validator("workbench_url")
    @classmethod
    def _check_workbench_url(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return DEFAULT_WORKBENCH_URL
        parsed = urlparse(stripped.rstrip("/"))
        hostname = parsed.hostname
        if (
            parsed.scheme.lower() != "https"
            or not hostname
            or not is_cis_domain(hostname)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != ""
            or bool(parsed.params)
            or bool(parsed.query)
            or bool(parsed.fragment)
        ):
            raise ValueError(f"must be {_WORKBENCH_URL_ACCEPTED}")
        return f"https://{parsed.netloc.lower()}"

    @field_validator("verify_ssl", mode="before")
    @classmethod
    def _parse_verify_ssl(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        normalized = value.strip().lower() if isinstance(value, str) else None
        if normalized in _VERIFY_SSL_TRUE_VALUES:
            return True
        if normalized in _VERIFY_SSL_FALSE_VALUES:
            return False
        # A typo in a security setting must never silently turn verification off; a TOML
        # number is not one of the documented values either.
        raise ValueError(f"use {_VERIFY_SSL_ACCEPTED}")

    @property
    def request_timeouts(self) -> tuple[float, float]:
        """(connect, read) seconds for requests; the connect timeout is capped at the read timeout."""
        return (min(CONNECT_TIMEOUT_SECONDS, self.request_timeout), self.request_timeout)

    @property
    def catalog_db_path(self) -> Path:
        return self.data_dir / "catalog.db"

    @property
    def session_file_path(self) -> Path:
        return self.data_dir / "session.cookies"

    @property
    def benchmarks_dir(self) -> Path:
        return self.data_dir / "benchmarks"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        init_kwargs = (
            init_settings.init_kwargs if isinstance(init_settings, InitSettingsSource) else {}
        )
        data_dir = _data_dir_for(init_kwargs, env_settings())
        dotenv = DotEnvSettingsSource(
            settings_cls,
            env_file=data_dir / DOTENV_FILE_NAME,
            # Only CIS_BENCH_* lines are cis-bench's; other tools' variables are left alone.
            dotenv_filtering="match_prefix",
        )
        config_file = data_dir / CONFIG_FILE_NAME
        try:
            toml = TomlConfigSettingsSource(settings_cls, toml_file=config_file)
        except tomllib.TOMLDecodeError as error:
            raise ConfigurationError(f"{config_file} is not valid TOML: {error}") from None
        return (
            init_settings,
            _Source(env_settings),
            _Source(dotenv, DOTENV_FILE_NAME),
            _Source(toml, CONFIG_FILE_NAME),
        )


def _describe(error: ErrorDetails) -> str:
    """One line per invalid value: the variable, its config.toml key, the value and what is accepted."""
    field = str(error["loc"][0]) if error["loc"] else "?"
    message = str(error["msg"]).removeprefix("Value error, ")
    if error["type"] == "extra_forbidden":
        return (
            f"unknown setting {field!r} in {DOTENV_FILE_NAME} or {CONFIG_FILE_NAME} "
            f"(cis-bench settings are {', '.join(ENV_PREFIX + n.upper() for n in Settings.model_fields)})"
        )
    variable = f"{ENV_PREFIX}{field.upper()}"
    if error["type"] != "value_error":
        # pydantic's own type and bound messages; ours already say what is accepted.
        model_field = Settings.model_fields.get(field)
        extra = model_field.json_schema_extra if model_field is not None else None
        if isinstance(extra, dict) and extra.get("accepted"):
            message = f"{message}; accepted: {extra['accepted']}"
    return (
        f"{variable} (config.toml key {field}) has invalid value {error.get('input')!r}: {message}"
    )


def load_settings(**overrides: Any) -> Settings:
    """Build the settings from every source; a passed-in value (a CLI flag) wins over all of them.

    Raises:
        ConfigurationError: naming each invalid setting, its value and the accepted values.
    """
    try:
        return Settings(**overrides)
    except ValidationError as error:
        raise ConfigurationError(
            "; ".join(_describe(detail) for detail in error.errors(include_url=False))
        ) from None


class Config:
    """The fixed request policy, and read access to the settings for code not yet given them."""

    CIS_ROOT_DOMAIN = CIS_ROOT_DOMAIN
    DEFAULT_WORKBENCH_URL = DEFAULT_WORKBENCH_URL

    # WorkBench request policy. The code that sends requests (fetcher.http, the scrapers)
    # reads these; none of them keeps a copy.
    # Politeness: the most requests cis-bench sends to one WorkBench host per second.
    WORKBENCH_REQUESTS_PER_SECOND = 3.0
    # Concurrent requests, and how many items one batch of parallel work holds.
    WORKBENCH_MAX_CONCURRENT_REQUESTS = 5
    WORKBENCH_BATCH_SIZE = 10
    # Retries after the first attempt, and the statuses worth retrying; every other status
    # is final. urllib3's backoff: the first retry is immediate, then factor * 2 seconds plus
    # up to the jitter. A server's Retry-After is honored up to the cap.
    REQUEST_RETRIES = 2
    RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
    RETRY_BACKOFF_FACTOR = 1.0
    RETRY_JITTER_SECONDS = 0.5
    RETRY_AFTER_MAX_SECONDS = 60
    # Sent on every WorkBench request so CIS can tell who is calling.
    USER_AGENT = f"cis-bench-cli/{__version__} (github.com/mitre/cis-bench)"
    # CIS's single sign-on hosts a login may pass through, and how many hops are followed.
    TRUSTED_SSO_HOSTS = frozenset({"auth.portal.cisecurity.org", "auth.portal.qa.cisecurity.org"})
    MAX_SSO_REDIRECTS = 8

    @staticmethod
    def is_cis_domain(host: str) -> bool:
        """Return True when host belongs to cisecurity.org or one of its subdomains."""
        return is_cis_domain(host)

    @staticmethod
    def get_workbench_base_url() -> str:
        """The validated CIS WorkBench origin (CIS_BENCH_WORKBENCH_URL)."""
        return load_settings().workbench_url

    @staticmethod
    def get_data_dir() -> Path:
        """The data folder (CIS_BENCH_DATA_DIR, default ~/.cis-bench)."""
        return load_settings().data_dir

    @staticmethod
    def get_catalog_db_path() -> Path:
        return load_settings().catalog_db_path

    @staticmethod
    def get_session_file_path() -> Path:
        """The saved WorkBench session's cookie file."""
        return load_settings().session_file_path

    @staticmethod
    def get_benchmarks_dir() -> Path:
        return load_settings().benchmarks_dir

    @staticmethod
    def ensure_directories() -> None:
        """Create the data folder and its benchmarks/ folder if they do not exist."""
        settings = load_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.benchmarks_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_table_title_width() -> int:
        """The widest the Title column of the search and get tables may grow (default 90)."""
        return load_settings().table_title_width

    @staticmethod
    def get_search_default_limit() -> int:
        """Default limit for search, catalog search, catalog list and get (default 100)."""
        return load_settings().search_limit

    @staticmethod
    def get_request_timeout() -> tuple[float, float]:
        """The (connect, read) timeout of every WorkBench request (CIS_BENCH_REQUEST_TIMEOUT)."""
        return load_settings().request_timeouts

    @staticmethod
    def get_verify_ssl() -> bool:
        """Whether WorkBench TLS certificates are verified (CIS_BENCH_VERIFY_SSL, default on)."""
        return load_settings().verify_ssl


# Convenience functions
def get_catalog_db_path() -> Path:
    """Get catalog database path."""
    return Config.get_catalog_db_path()


def get_workbench_base_url() -> str:
    """Get validated CIS WorkBench base URL."""
    return Config.get_workbench_base_url()
