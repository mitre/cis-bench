"""Where the CLI turns the run's settings into the objects its commands use.

The root command builds and checks the settings once per run (cli/app.py) and keeps them on
the Click context. Library code never reads settings itself: each command takes them from
here and passes the specific values in, so this module is the one place that maps a setting
onto a constructor argument.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import click

from cis_bench.config import Settings, load_settings

if TYPE_CHECKING:
    import requests

    from cis_bench.catalog.database import CatalogDatabase
    from cis_bench.catalog.scraper import CatalogScraper
    from cis_bench.fetcher.auth import AuthManager
    from cis_bench.fetcher.workbench import WorkbenchScraper

_SETTINGS_KEY = "settings"


def settings_from(ctx: click.Context | None = None) -> Settings:
    """The settings the root command checked for this run.

    A command invoked without the root command (a test, or code embedding one command) has
    none on its context yet; they are loaded once then and kept on the root context.

    Raises:
        ConfigurationError: If a setting is invalid (only when loading here).
    """
    root = (ctx or click.get_current_context()).find_root()
    if root.obj is None:
        root.obj = {}
    settings = root.obj.get(_SETTINGS_KEY)
    if not isinstance(settings, Settings):
        settings = load_settings()
        root.obj[_SETTINGS_KEY] = settings
    return settings


def settings_with_flags(**flags: object) -> Settings:
    """The run's settings with the values of CLI flags on top; a flag beats every other source.

    A flag left unset (None) changes nothing, so a command passes each of its setting flags
    as given and gets the run's settings when none was used.

    Raises:
        ConfigurationError: If a flag's value is not accepted for its setting.
    """
    given = {name: value for name, value in flags.items() if value is not None}
    return load_settings(**given) if given else settings_from()


def auth_manager(settings: Settings, *, requests_per_second: float | None = None) -> AuthManager:
    """An AuthManager for the configured WorkBench, TLS setting, session file, request policy
    and request timeout.

    requests_per_second replaces the configured rate for every session it makes, from the
    session check on (a run's --rate-limit); None keeps the configured rate.
    """
    from cis_bench.fetcher.auth import AuthManager

    policy = settings.request_policy
    if requests_per_second is not None:
        policy = replace(policy, requests_per_second=requests_per_second)
    return AuthManager(
        workbench_url=settings.workbench_url,
        verify_ssl=settings.verify_ssl,
        session_file=settings.session_file_path,
        request_policy=policy,
        timeout=settings.request_timeouts,
    )


def workbench_scraper(settings: Settings, session: requests.Session) -> WorkbenchScraper:
    """A benchmark scraper on the configured origin, timeout, worker count and batch size."""
    from cis_bench.fetcher.workbench import WorkbenchScraper

    return WorkbenchScraper(
        session,
        base_url=settings.workbench_url,
        timeout=settings.request_timeouts,
        max_workers=settings.max_concurrent_requests,
        batch_size=settings.batch_size,
    )


def catalog_scraper(
    settings: Settings, database: CatalogDatabase, session: requests.Session
) -> CatalogScraper:
    """A catalog scraper on the configured origin, timeout, worker count and batch size."""
    from cis_bench.catalog.scraper import CatalogScraper

    return CatalogScraper(
        database,
        session,
        base_url=settings.workbench_url,
        timeout=settings.request_timeouts,
        max_workers=settings.max_concurrent_requests,
        batch_size=settings.batch_size,
    )
