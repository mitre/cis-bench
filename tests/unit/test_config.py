"""Tests for cis_bench.config: the Settings class, where its values come from, and the paths.

Settings come from, highest first: a value passed in (a CLI flag), the environment,
<data dir>/.env, <data dir>/config.toml, then the default. CIS_BENCH_DATA_DIR, read from
the environment only, locates the data folder and both files.
"""

import os
from unittest.mock import patch

import pytest

from cis_bench.config import Config, load_settings
from cis_bench.exceptions import ConfigurationError


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """An empty data folder, set as CIS_BENCH_DATA_DIR, with no CIS_BENCH_* setting in the environment."""
    for name in list(os.environ):
        if name.startswith("CIS_BENCH_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(tmp_path))
    return tmp_path


class TestDataDir:
    """CIS_BENCH_DATA_DIR places catalog.db, session.cookies, benchmarks/, .env and config.toml."""

    def test_every_path_is_in_the_data_dir(self, data_dir):
        assert Config.get_data_dir() == data_dir
        assert Config.get_catalog_db_path() == data_dir / "catalog.db"
        assert Config.get_session_file_path() == data_dir / "session.cookies"
        assert Config.get_benchmarks_dir() == data_dir / "benchmarks"

    def test_the_default_is_dot_cis_bench_in_the_home_folder(self, data_dir, monkeypatch, tmp_path):
        monkeypatch.delenv("CIS_BENCH_DATA_DIR")
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        assert Config.get_data_dir() == tmp_path / "home" / ".cis-bench"

    def test_a_tilde_is_expanded(self, data_dir, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("CIS_BENCH_DATA_DIR", "~/cis-data")
        assert Config.get_data_dir() == tmp_path / "home" / "cis-data"

    def test_cis_bench_env_is_refused_and_names_the_replacement(self, data_dir, monkeypatch):
        # A leftover CIS_BENCH_ENV=dev must never silently write to ~/.cis-bench.
        monkeypatch.setenv("CIS_BENCH_ENV", "dev")
        with pytest.raises(ConfigurationError, match="CIS_BENCH_DATA_DIR") as caught:
            load_settings()
        assert "CIS_BENCH_ENV" in str(caught.value)

    @pytest.mark.parametrize(
        "file_name,line",
        [(".env", "CIS_BENCH_DATA_DIR=/elsewhere\n"), ("config.toml", 'data_dir = "/elsewhere"\n')],
    )
    def test_the_data_dir_cannot_be_set_from_a_file_in_it(self, data_dir, file_name, line):
        (data_dir / file_name).write_text(line)
        with pytest.raises(ConfigurationError, match="CIS_BENCH_DATA_DIR") as caught:
            load_settings()
        assert file_name in str(caught.value)

    def test_surrounding_spaces_are_ignored_like_everywhere_else(self, data_dir, monkeypatch):
        # The folder the files are read from and the folder reported must be the same one.
        monkeypatch.setenv("CIS_BENCH_DATA_DIR", f"  {data_dir}  ")
        (data_dir / "config.toml").write_text("search_limit = 5\n")
        settings = load_settings()
        assert settings.data_dir == data_dir
        assert settings.search_limit == 5

    def test_ensure_directories_creates_the_data_and_benchmarks_dirs(self, data_dir):
        target = data_dir / "new"
        with patch.dict(os.environ, {"CIS_BENCH_DATA_DIR": str(target)}):
            Config.ensure_directories()
            Config.ensure_directories()  # a second call is harmless
        assert (target / "benchmarks").is_dir()


class TestPrecedence:
    """One chain: passed-in value > environment > .env > config.toml > default."""

    def test_config_toml_beats_the_default(self, data_dir):
        (data_dir / "config.toml").write_text("search_limit = 5\n")
        assert load_settings().search_limit == 5

    def test_dotenv_beats_config_toml(self, data_dir):
        (data_dir / "config.toml").write_text("search_limit = 5\n")
        (data_dir / ".env").write_text("CIS_BENCH_SEARCH_LIMIT=7\n")
        assert load_settings().search_limit == 7

    def test_the_environment_beats_dotenv(self, data_dir, monkeypatch):
        (data_dir / ".env").write_text("CIS_BENCH_SEARCH_LIMIT=7\n")
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "9")
        assert load_settings().search_limit == 9

    def test_a_blank_environment_value_falls_through_to_dotenv(self, data_dir, monkeypatch):
        (data_dir / ".env").write_text("CIS_BENCH_SEARCH_LIMIT=7\n")
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "  ")
        assert load_settings().search_limit == 7

    def test_a_passed_in_value_beats_the_environment(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "9")
        assert load_settings(search_limit=3).search_limit == 3

    def test_a_change_to_the_environment_is_seen_by_the_next_read(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "9")
        assert Config.get_search_default_limit() == 9
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "11")
        assert Config.get_search_default_limit() == 11

    def test_files_do_not_change_the_process_environment(self, data_dir):
        (data_dir / ".env").write_text("CIS_BENCH_SEARCH_LIMIT=7\nREQUESTS_CA_BUNDLE=/x.pem\n")
        assert load_settings().search_limit == 7
        assert "CIS_BENCH_SEARCH_LIMIT" not in os.environ
        assert "REQUESTS_CA_BUNDLE" not in os.environ

    def test_an_unknown_cis_bench_name_in_a_file_is_refused(self, data_dir):
        # A typo must not be ignored silently; other tools' variables in .env are left alone.
        (data_dir / ".env").write_text("CIS_BENCH_SERCH_LIMIT=7\nHTTPS_PROXY=http://p:3128\n")
        with pytest.raises(ConfigurationError, match="serch_limit"):
            load_settings()
        (data_dir / ".env").unlink()
        (data_dir / "config.toml").write_text("serch_limit = 7\n")
        with pytest.raises(ConfigurationError, match="serch_limit"):
            load_settings()

    def test_a_config_toml_that_is_not_valid_toml_is_a_configuration_error(self, data_dir):
        (data_dir / "config.toml").write_text("search_limit = \n")
        with pytest.raises(ConfigurationError, match="config.toml") as caught:
            load_settings()
        assert "TOML" in str(caught.value)

    @pytest.mark.parametrize("value", ["0", "1", "2", '"maybe"'])
    def test_verify_ssl_in_config_toml_takes_only_the_documented_values(self, data_dir, value):
        (data_dir / "config.toml").write_text(f"verify_ssl = {value}\n")
        with pytest.raises(ConfigurationError, match="CIS_BENCH_VERIFY_SSL") as caught:
            load_settings()
        assert "true/1/yes" in str(caught.value)

    def test_verify_ssl_in_config_toml_accepts_booleans(self, data_dir):
        (data_dir / "config.toml").write_text("verify_ssl = false\n")
        assert load_settings().verify_ssl is False

    @pytest.mark.parametrize(
        "variable,value,accepted",
        [
            ("CIS_BENCH_SEARCH_LIMIT", "abc", "an integer of 1 or more"),
            ("CIS_BENCH_TABLE_TITLE_WIDTH", "abc", "an integer of 1 or more"),
            ("CIS_BENCH_REQUEST_TIMEOUT", "abc", "a finite number of seconds greater than 0"),
        ],
    )
    def test_a_refusal_says_what_is_accepted(
        self, data_dir, monkeypatch, variable, value, accepted
    ):
        monkeypatch.setenv(variable, value)
        with pytest.raises(ConfigurationError, match=variable) as caught:
            load_settings()
        assert accepted in str(caught.value)

    def test_a_bad_value_in_config_toml_names_the_file_key(self, data_dir):
        (data_dir / "config.toml").write_text("search_limit = 0\n")
        with pytest.raises(ConfigurationError, match="CIS_BENCH_SEARCH_LIMIT") as caught:
            load_settings()
        assert "search_limit" in str(caught.value)


class TestConfigTableTitleWidth:
    """CIS_BENCH_TABLE_TITLE_WIDTH: an integer of 1 or more, default 90."""

    def test_default(self, data_dir):
        assert Config.get_table_title_width() == 90

    def test_from_env(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_TABLE_TITLE_WIDTH", "120")
        assert Config.get_table_title_width() == 120

    def test_blank_means_the_default(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_TABLE_TITLE_WIDTH", "")
        assert Config.get_table_title_width() == 90

    @pytest.mark.parametrize("value", ["abc", "0", "-3", "1.5"])
    def test_a_value_that_is_not_a_positive_integer_is_refused(self, data_dir, monkeypatch, value):
        monkeypatch.setenv("CIS_BENCH_TABLE_TITLE_WIDTH", value)
        with pytest.raises(ConfigurationError, match="CIS_BENCH_TABLE_TITLE_WIDTH") as caught:
            Config.get_table_title_width()
        assert repr(value) in str(caught.value)


class TestConfigSearchLimit:
    """CIS_BENCH_SEARCH_LIMIT: an integer of 1 or more, default 100."""

    def test_default(self, data_dir):
        assert Config.get_search_default_limit() == 100

    def test_from_env(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "500")
        assert Config.get_search_default_limit() == 500

    def test_blank_means_the_default(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "")
        assert Config.get_search_default_limit() == 100

    @pytest.mark.parametrize("value", ["abc", "many", "0", "-1", "2.5"])
    def test_a_value_that_is_not_a_positive_integer_is_refused(self, data_dir, monkeypatch, value):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", value)
        with pytest.raises(ConfigurationError, match="CIS_BENCH_SEARCH_LIMIT") as caught:
            Config.get_search_default_limit()
        assert repr(value) in str(caught.value)


class TestConfigVerifySSL:
    """Tests for SSL verification configuration."""

    def test_get_verify_ssl_default_true(self):
        """Certificate verification is on when CIS_BENCH_VERIFY_SSL is unset or blank."""
        env = os.environ.copy()
        env.pop("CIS_BENCH_VERIFY_SSL", None)
        with patch.dict(os.environ, env, clear=True):
            from cis_bench.config import Config

            assert Config.get_verify_ssl() is True

        with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": "   "}):
            assert Config.get_verify_ssl() is True

    def test_get_verify_ssl_true_values(self):
        """Should return True for 'true', '1', 'yes' values."""
        from cis_bench.config import Config

        for value in ["true", "True", "TRUE", "1", "yes", "Yes", "YES", " true "]:
            with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": value}):
                assert Config.get_verify_ssl() is True, f"Failed for value: {value}"

    def test_get_verify_ssl_false_values(self):
        """Should return False only for the explicit opt-out values 'false', '0', 'no'."""
        from cis_bench.config import Config

        for value in ["false", "False", "FALSE", "0", "no", "No", "NO", " false "]:
            with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": value}):
                assert Config.get_verify_ssl() is False, f"Failed for value: {value}"

    def test_get_verify_ssl_rejects_unrecognized_value(self):
        """A typo in a security setting is a configuration error, never a silent opt-out."""
        from cis_bench.config import Config

        for value in ["anything", "off", "disable", "f"]:
            with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": value}):
                with pytest.raises(ValueError, match="CIS_BENCH_VERIFY_SSL") as exc_info:
                    Config.get_verify_ssl()
                assert value in str(exc_info.value)


class TestConfigWorkbenchBaseUrl:
    """Tests for configurable CIS WorkBench base URL validation."""

    def test_get_workbench_base_url_defaults_to_production(self):
        """Should return https://workbench.cisecurity.org when CIS_BENCH_WORKBENCH_URL is unset or blank."""
        from cis_bench import config

        env = os.environ.copy()
        env.pop("CIS_BENCH_WORKBENCH_URL", None)
        with patch.dict(os.environ, env, clear=True):
            assert config.Config.get_workbench_base_url() == "https://workbench.cisecurity.org"
            assert config.get_workbench_base_url() == "https://workbench.cisecurity.org"

        with patch.dict(os.environ, {"CIS_BENCH_WORKBENCH_URL": "   "}):
            assert config.Config.get_workbench_base_url() == "https://workbench.cisecurity.org"

    @pytest.mark.parametrize(
        "raw_url,expected",
        [
            (
                "https://workbench-staging.cisecurity.org",
                "https://workbench-staging.cisecurity.org",
            ),
            (
                "https://workbench-staging.cisecurity.org/",
                "https://workbench-staging.cisecurity.org",
            ),
            (
                "https://WORKBENCH-STAGING.CISECURITY.ORG///",
                "https://workbench-staging.cisecurity.org",
            ),
        ],
    )
    def test_get_workbench_base_url_accepts_valid_cisecurity_origins(
        self, raw_url: str, expected: str
    ):
        """Should normalize valid https://*.cisecurity.org origins."""
        from cis_bench.config import Config

        with patch.dict(os.environ, {"CIS_BENCH_WORKBENCH_URL": raw_url}):
            assert Config.get_workbench_base_url() == expected

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "/",
            "///",
            "http://workbench.cisecurity.org",
            "https://evil-cisecurity.org",
            "https://cisecurity.org.attacker.example",
            "https://user:pass@workbench.cisecurity.org",
            "https://workbench.cisecurity.org/benchmarks",
            "https://workbench.cisecurity.org?next=1",
            "https://workbench.cisecurity.org#frag",
        ],
    )
    def test_get_workbench_base_url_rejects_untrusted_insecure_or_non_origin_urls(
        self, invalid_url: str
    ):
        """Should raise ValueError for non-HTTPS, non-cisecurity.org, credentialed, or path/query URLs."""
        from cis_bench.config import Config

        with patch.dict(os.environ, {"CIS_BENCH_WORKBENCH_URL": invalid_url}):
            with pytest.raises(ValueError, match="CIS_BENCH_WORKBENCH_URL"):
                Config.get_workbench_base_url()


class TestConvenienceFunctions:
    """Module-level shortcuts that callers use until they read the settings object."""

    def test_get_catalog_db_path_function(self, data_dir):
        from cis_bench.config import get_catalog_db_path

        assert get_catalog_db_path() == data_dir / "catalog.db"


class TestConfigurationErrorType:
    """Configuration problems raise ConfigurationError so callers can classify them by type."""

    def test_invalid_workbench_url_raises_configuration_error(self):
        from cis_bench.exceptions import ConfigurationError

        with patch.dict(os.environ, {"CIS_BENCH_WORKBENCH_URL": "http://evil.example"}):
            from cis_bench.config import Config

            with pytest.raises(ConfigurationError, match="CIS_BENCH_WORKBENCH_URL") as exc_info:
                Config.get_workbench_base_url()
        assert isinstance(exc_info.value, ValueError)

    def test_invalid_verify_ssl_raises_configuration_error(self):
        from cis_bench.exceptions import ConfigurationError

        with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": "bogus"}):
            from cis_bench.config import Config

            with pytest.raises(ConfigurationError, match="CIS_BENCH_VERIFY_SSL") as exc_info:
                Config.get_verify_ssl()
        assert isinstance(exc_info.value, ValueError)


class TestConfigRequestTimeout:
    """CIS_BENCH_REQUEST_TIMEOUT bounds every scraper request so a stalled connection cannot hang a download."""

    def test_default_is_thirty_second_read_with_ten_second_connect(self):
        env = os.environ.copy()
        env.pop("CIS_BENCH_REQUEST_TIMEOUT", None)
        with patch.dict(os.environ, env, clear=True):
            from cis_bench.config import Config

            assert Config.get_request_timeout() == (10.0, 30.0)
        with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": "  "}):
            assert Config.get_request_timeout() == (10.0, 30.0)

    def test_value_sets_the_read_timeout(self):
        from cis_bench.config import Config

        with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": "60"}):
            assert Config.get_request_timeout() == (10.0, 60.0)
        with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": " 45.5 "}):
            assert Config.get_request_timeout() == (10.0, 45.5)

    def test_connect_timeout_never_exceeds_read_timeout(self):
        from cis_bench.config import Config

        with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": "5"}):
            assert Config.get_request_timeout() == (5.0, 5.0)

    def test_rejects_non_positive_or_non_numeric_values(self):
        from cis_bench.config import Config
        from cis_bench.exceptions import ConfigurationError

        # inf would turn the timeout off again and nan is accepted by float() but
        # rejected by sockets; both must be configuration errors.
        for value in ["abc", "0", "-5", "30s", "nan", "inf", "-inf", "infinity"]:
            with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": value}):
                with pytest.raises(
                    ConfigurationError, match="CIS_BENCH_REQUEST_TIMEOUT"
                ) as exc_info:
                    Config.get_request_timeout()
                assert value in str(exc_info.value)
