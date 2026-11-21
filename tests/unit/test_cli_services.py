"""The CLI's one place where settings become the values library objects are built with."""

from dataclasses import replace
from unittest.mock import Mock

import click
import pytest
import requests

from cis_bench.catalog.scraper import CatalogScraper
from cis_bench.cli.helpers.offline import OfflineError
from cis_bench.cli.helpers.services import (
    auth_manager,
    catalog_scraper,
    settings_from,
    settings_with_flags,
    workbench_scraper,
    workbench_session,
)
from cis_bench.config import Folders, RequestPolicy, Settings, load_settings
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
        max_concurrent_requests=2,
        batch_size=4,
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


class TestSettingsWithFlagsKeepsTheRootFlags:
    def test_a_command_flag_keeps_the_root_offline_flag(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CIS_BENCH_OFFLINE", raising=False)
        root_settings = load_settings(offline=True)
        obj = {"settings": root_settings, "setting_flags": {"offline": True}}
        with click.Context(click.Command("cis-bench"), obj=obj):
            settings = settings_with_flags(verify_ssl=False)
        assert settings.verify_ssl is False
        assert settings.offline is True


class TestWorkbenchSession:
    def test_offline_refuses_before_any_auth_manager_is_built(self, settings, auth_manager_class):
        offline = load_settings(folders=settings.folders, offline=True)
        with click.Context(click.Command("download"), parent=click.Context(click.Group("cli"))):
            with pytest.raises(OfflineError) as caught:
                workbench_session(offline, needs="download benchmark 23598")
        auth_manager_class.assert_not_called()
        message = caught.value.format_message()
        assert message.startswith(
            "cis-bench download needs CIS WorkBench to download benchmark 23598"
        )
        assert "offline mode is on" in message
        assert "--offline" in message and "CIS_BENCH_OFFLINE" in message
        assert caught.value.exit_code == 1

    def test_online_opens_the_session_with_the_browser_and_rate(self, settings, auth_manager_class):
        session = Mock(spec=requests.Session)
        auth_manager_class.return_value.get_or_create_session.return_value = session
        with click.Context(click.Command("refresh")):
            got = workbench_session(
                settings, needs="refresh the catalog", browser="firefox", requests_per_second=0.5
            )
        assert got is session
        auth_manager_class.return_value.get_or_create_session.assert_called_once_with(
            browser="firefox"
        )
        policy = auth_manager_class.call_args.kwargs["request_policy"]
        assert policy.requests_per_second == 0.5


class TestFactories:
    def test_auth_manager_is_built_from_the_settings(self, settings, tmp_path):
        auth = auth_manager(settings)
        assert isinstance(auth, AuthManager)
        assert auth.workbench_url == STAGING
        assert auth.verify_ssl is False
        assert auth.session_file == tmp_path / "session.cookies"
        assert auth.request_policy == settings.request_policy
        assert auth.request_policy == RequestPolicy(
            requests_per_second=3.0, retries=2, backoff_factor=1.0, jitter_seconds=0.5
        )

    def test_auth_manager_checks_the_session_with_the_request_timeout(self, monkeypatch):
        from cis_bench.config import load_settings

        monkeypatch.setenv("CIS_BENCH_REQUEST_TIMEOUT", "90")
        assert auth_manager(load_settings()).timeout == (10.0, 90.0)

    def test_auth_manager_takes_a_run_specific_rate(self, settings):
        policy = auth_manager(settings, requests_per_second=0.5).request_policy
        assert policy == replace(settings.request_policy, requests_per_second=0.5)

    def test_workbench_scraper_gets_the_origin_and_timeouts(self, settings):
        scraper = workbench_scraper(settings, requests.Session())
        assert isinstance(scraper, WorkbenchScraper)
        assert scraper.base_url == STAGING
        assert scraper.timeout == (10.0, 45.0)
        assert (scraper.max_workers, scraper.batch_size) == (2, 4)

    def test_catalog_scraper_gets_the_origin_and_timeouts(self, settings):
        db = Mock()
        scraper = catalog_scraper(settings, db, requests.Session())
        assert isinstance(scraper, CatalogScraper)
        assert scraper.db is db
        assert scraper.base_url == STAGING
        assert scraper.timeout == (10.0, 45.0)
        assert (scraper.max_workers, scraper.batch_size) == (2, 4)
