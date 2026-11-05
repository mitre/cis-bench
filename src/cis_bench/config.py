"""cis-bench settings: one typed, validated Settings class, the folders, and the fixed request policy.

Every user setting is a field of ``Settings``. A value comes from, highest first:

1. a value passed in (``load_settings(search_limit=...)``, how a CLI flag overrides);
2. the environment (``CIS_BENCH_SEARCH_LIMIT``);
3. ``<config folder>/config.toml`` (the field names: ``search_limit = 100``);
4. the default.

The folders follow the XDG Base Directory specification the way the GitHub CLI resolves
it (``xdg_folders``): config.toml in the config folder, catalog.db and benchmarks/ in the
data folder, session.cookies in the state folder. ``CIS_BENCH_HOME`` puts all of them in
one flat folder, for containers, CI and tests; ``CIS_BENCH_CONFIG_DIR`` moves config.toml
alone. The folders are located, never set: they are not settings and no file can change them.

Nothing is copied into the process environment. Variables that belong to the HTTP stack,
such as HTTPS_PROXY, NO_PROXY, REQUESTS_CA_BUNDLE and SSL_CERT_FILE, stay with requests.
"""

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, ValidationError, field_validator
from pydantic_core import ErrorDetails
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from cis_bench import __version__
from cis_bench.exceptions import ConfigurationError

ENV_PREFIX = "CIS_BENCH_"
APP_FOLDER_NAME = "cis-bench"
HOME_VARIABLE = f"{ENV_PREFIX}HOME"
CONFIG_DIR_VARIABLE = f"{ENV_PREFIX}CONFIG_DIR"
CONFIG_FILE_NAME = "config.toml"
CATALOG_DB_FILE_NAME = "catalog.db"
SESSION_FILE_NAME = "session.cookies"
BENCHMARKS_FOLDER_NAME = "benchmarks"
# The one folder earlier versions used; still read, with a notice, until it is migrated.
LEGACY_FOLDER_NAME = ".cis-bench"
# Variables earlier versions read; a run that still sets one stops and names the replacement.
_RETIRED_VARIABLES = (f"{ENV_PREFIX}DATA_DIR", f"{ENV_PREFIX}ENV")
_FOLDERS_FIELD = "folders"

CIS_ROOT_DOMAIN = "cisecurity.org"
DEFAULT_WORKBENCH_URL = f"https://workbench.{CIS_ROOT_DOMAIN}"
# The connect timeout of every WorkBench request; never longer than the read timeout.
CONNECT_TIMEOUT_SECONDS = 10.0

# WorkBench request policy: fixed values, not settings. The code that sends requests
# (fetcher.http, the scrapers) imports these; none of them keeps a copy.
# Politeness: the most requests cis-bench sends to one WorkBench host per second.
WORKBENCH_REQUESTS_PER_SECOND = 3.0
# Concurrent requests, and how many items one batch of parallel work holds.
WORKBENCH_MAX_CONCURRENT_REQUESTS = 5
WORKBENCH_BATCH_SIZE = 10
# Retries after the first attempt, and the statuses worth retrying; every other status is
# final. urllib3's backoff: the first retry is immediate, then factor * 2 seconds plus up to
# the jitter. A server's Retry-After is honored up to the cap.
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


@dataclass(frozen=True)
class Folders:
    """Where cis-bench keeps its files.

    config holds config.toml; data holds catalog.db and benchmarks/; state holds
    session.cookies. legacy is the ~/.cis-bench of an earlier version when this run uses
    it (all three then point there), else None.
    """

    config: Path
    data: Path
    state: Path
    legacy: Path | None = None


def _given(environ: Mapping[str, str], name: str) -> str | None:
    """The variable's value without surrounding spaces, or None when unset or blank."""
    value = environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _own_folder(environ: Mapping[str, str], name: str, home: Path) -> Path | None:
    """A CIS_BENCH_* folder: ``~`` is the home folder; a relative path is from the working directory."""
    value = _given(environ, name)
    if value is None:
        return None
    if value == "~":
        return home
    if value[:2] in ("~/", "~\\"):
        return home / value[2:]
    return Path(value)


def xdg_folders(environ: Mapping[str, str], *, home: Path, windows: bool) -> Folders:
    """The folders for this environment, resolved as the GitHub CLI resolves its own.

    Config: CIS_BENCH_CONFIG_DIR > CIS_BENCH_HOME > XDG_CONFIG_HOME/cis-bench >
    %AppData%/cis-bench (Windows only) > ~/.config/cis-bench.
    Data: CIS_BENCH_HOME > XDG_DATA_HOME/cis-bench > %LocalAppData%/cis-bench (Windows only) >
    ~/.local/share/cis-bench. State: the same with XDG_STATE_HOME and ~/.local/state.
    A blank or relative XDG value is ignored, as the specification requires. macOS follows
    the Unix rows. Nothing here touches the file system.
    """
    pure = PureWindowsPath if windows else PurePosixPath

    def base(xdg_name: str, windows_name: str, default: Path) -> Path:
        xdg = _given(environ, xdg_name)
        if xdg is not None and pure(xdg).is_absolute():
            return Path(xdg) / APP_FOLDER_NAME
        if windows:
            app_data = _given(environ, windows_name)
            if app_data is not None:
                return Path(app_data) / APP_FOLDER_NAME
        return home / default / APP_FOLDER_NAME

    own_home = _own_folder(environ, HOME_VARIABLE, home)
    own_config = _own_folder(environ, CONFIG_DIR_VARIABLE, home)
    return Folders(
        config=own_config or own_home or base("XDG_CONFIG_HOME", "AppData", Path(".config")),
        data=own_home or base("XDG_DATA_HOME", "LocalAppData", Path(".local/share")),
        state=own_home or base("XDG_STATE_HOME", "LocalAppData", Path(".local/state")),
    )


def _refuse_retired_variables() -> None:
    for name in _RETIRED_VARIABLES:
        if any(variable.upper() == name for variable in os.environ):
            raise ConfigurationError(
                f"{name} is no longer used; set {HOME_VARIABLE} to one folder for config.toml, "
                "catalog.db, benchmarks/ and session.cookies, or unset it to use the XDG folders "
                "(~/.config, ~/.local/share and ~/.local/state)"
            )


def resolve_folders(*, use_legacy: bool = True) -> Folders:
    """The folders of this run, from the environment; an earlier version's ~/.cis-bench while it lasts.

    ~/.cis-bench is used, and reported through ``Folders.legacy``, only when neither
    CIS_BENCH_HOME nor CIS_BENCH_CONFIG_DIR is set and the data folder has no catalog.db yet
    (a migrated install is never pulled back). ``use_legacy=False`` gives the folders this
    environment resolves to on its own: where ``config migrate`` moves the files.

    Raises:
        ConfigurationError: If a retired variable (CIS_BENCH_DATA_DIR, CIS_BENCH_ENV) is set.
    """
    _refuse_retired_variables()
    home = Path.home()
    folders = xdg_folders(os.environ, home=home, windows=os.name == "nt")
    if not use_legacy:
        return folders
    legacy = home / LEGACY_FOLDER_NAME
    overridden = (
        _given(os.environ, HOME_VARIABLE) is not None
        or _given(os.environ, CONFIG_DIR_VARIABLE) is not None
    )
    if not overridden and legacy.is_dir() and not (folders.data / CATALOG_DB_FILE_NAME).exists():
        return Folders(config=legacy, data=legacy, state=legacy, legacy=legacy)
    return folders


class _EnvSource(EnvSettingsSource):
    """The environment, without the folders: those are located by resolve_folders, not set."""

    def get_field_value(self, field, field_name):
        if field_name == _FOLDERS_FIELD:
            return None, field_name, False
        return super().get_field_value(field, field_name)


class _Source(PydanticBaseSettingsSource):
    """The environment or config.toml, with blank values left to the next source.

    A file may not set the folders: the folders locate the file.
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
        if self._file_name is not None and _FOLDERS_FIELD in values:
            raise ConfigurationError(
                f"{_FOLDERS_FIELD} cannot be set in {self._file_name}: the folders locate that "
                f"file; set {HOME_VARIABLE}, {CONFIG_DIR_VARIABLE} or the XDG variables instead"
            )
        return values


class Settings(BaseSettings):
    """Every cis-bench setting, with its type, default and accepted values, and the folders."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        extra="forbid",  # an unknown name in config.toml is a typo
    )

    folders: Folders = Field(
        description="Where config.toml, catalog.db, benchmarks/ and session.cookies live",
        exclude=True,  # located from the environment by resolve_folders, never a setting
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
    def data_dir(self) -> Path:
        """The data folder: catalog.db and benchmarks/."""
        return self.folders.data

    @property
    def config_file_path(self) -> Path:
        return self.folders.config / CONFIG_FILE_NAME

    @property
    def catalog_db_path(self) -> Path:
        return self.folders.data / CATALOG_DB_FILE_NAME

    @property
    def session_file_path(self) -> Path:
        return self.folders.state / SESSION_FILE_NAME

    @property
    def benchmarks_dir(self) -> Path:
        """Where download writes benchmark files and export, list and info look for them."""
        return self.folders.data / BENCHMARKS_FOLDER_NAME

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
            dict(init_settings.init_kwargs) if isinstance(init_settings, InitSettingsSource) else {}
        )
        folders = init_kwargs.get(_FOLDERS_FIELD)
        if not isinstance(folders, Folders):
            folders = resolve_folders()
            init_kwargs[_FOLDERS_FIELD] = folders
        config_file = folders.config / CONFIG_FILE_NAME
        try:
            toml = TomlConfigSettingsSource(settings_cls, toml_file=config_file)
        except tomllib.TOMLDecodeError as error:
            raise ConfigurationError(f"{config_file} is not valid TOML: {error}") from None
        return (
            InitSettingsSource(settings_cls, init_kwargs=init_kwargs),
            _Source(_EnvSource(settings_cls)),
            _Source(toml, CONFIG_FILE_NAME),
        )


def setting_names() -> list[str]:
    """The settings' field names, in declaration order; the folders are not one."""
    return [name for name in Settings.model_fields if name != _FOLDERS_FIELD]


def _describe(error: ErrorDetails) -> str:
    """One line per invalid value: the variable, its config.toml key, the value and what is accepted."""
    field = str(error["loc"][0]) if error["loc"] else "?"
    message = str(error["msg"]).removeprefix("Value error, ")
    if error["type"] == "extra_forbidden":
        return (
            f"unknown setting {field!r} in {CONFIG_FILE_NAME} "
            f"(cis-bench settings are {', '.join(ENV_PREFIX + n.upper() for n in setting_names())})"
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
