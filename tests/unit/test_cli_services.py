"""The CLI's one place where settings become the values library objects are built with."""

from unittest.mock import Mock

import click
import pytest
import requests

from cis_bench.catalog.scraper import CatalogScraper
from cis_bench.cli.helpers.services import (
    auth_manager,
    catalog_scraper,
    settings_from,
    settings_with_flags,
    workbench_scraper,
)
from cis_bench.config import Folders, Settings, load_settings
from cis_bench.exceptions import ConfigurationError
from cis_bench.fetcher.auth import AuthManager
from cis_bench.fetcher.workbench import WorkbenchScraper

STAGING = "https://workbench-staging.cisecurity.org"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return load_settings(
        folders=Folders(config=tmp_path, data=tmp_path, state=tmp_path),
        workbench_url=STAGING,
        verify_ssl=False,
        request_timeout=45,
    )


class TestSettingsFrom:
    def test_returns_the_settings_the_root_command_checked(self, settings):
        ctx = click.Context(click.Command("cis-bench"), obj={"settings": settings})
        with ctx:
            assert settings_from() is settings

    def test_a_command_run_without_the_root_loads_them_once(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "7")
        ctx = click.Context(click.Command("search"))
        with ctx:
            first = settings_from()
            assert first.search_limit == 7
            assert settings_from() is first

    def test_a_bad_value_is_a_configuration_error(self, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "abc")
        with click.Context(click.Command("search")):
            with pytest.raises(ConfigurationError, match="CIS_BENCH_SEARCH_LIMIT"):
                settings_from()


class TestSettingsWithFlags:
    def test_no_flag_given_is_the_runs_settings(self, settings):
        with click.Context(click.Command("cis-bench"), obj={"settings": settings}):
            assert settings_with_flags(verify_ssl=None) is settings

    def test_a_flag_beats_the_environment(self, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_VERIFY_SSL", "true")
        with click.Context(click.Command("cis-bench")):
            assert settings_with_flags(verify_ssl=False).verify_ssl is False


class TestFactories:
    def test_auth_manager_is_built_from_the_settings(self, settings, tmp_path):
        auth = auth_manager(settings)
        assert isinstance(auth, AuthManager)
        assert auth.workbench_url == STAGING
        assert auth.verify_ssl is False
        assert auth.session_file == tmp_path / "session.cookies"
        assert auth.requests_per_second is None

    def test_auth_manager_takes_a_run_specific_rate(self, settings):
        assert auth_manager(settings, requests_per_second=0.5).requests_per_second == 0.5

    def test_workbench_scraper_gets_the_origin_and_timeouts(self, settings):
        scraper = workbench_scraper(settings, requests.Session())
        assert isinstance(scraper, WorkbenchScraper)
        assert scraper.base_url == STAGING
        assert scraper.timeout == (10.0, 45.0)

    def test_catalog_scraper_gets_the_origin_and_timeouts(self, settings):
        db = Mock()
        scraper = catalog_scraper(settings, db, requests.Session())
        assert isinstance(scraper, CatalogScraper)
        assert scraper.db is db
        assert scraper.base_url == STAGING
        assert scraper.timeout == (10.0, 45.0)
