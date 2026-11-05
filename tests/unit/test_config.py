"""Tests for cis_bench.config: the Settings class, where its values come from, and the folders.

Settings come from, highest first: a value passed in (a CLI flag), the environment,
<config folder>/config.toml, then the default. The folders follow the XDG base directories
the way the GitHub CLI resolves them; CIS_BENCH_HOME puts everything in one folder.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cis_bench.config import Folders, load_settings, xdg_folders
from cis_bench.exceptions import ConfigurationError

HOME = Path("/home/u")
WIN_HOME = Path("C:/Users/u")


@pytest.fixture
def clean_env(monkeypatch):
    """No CIS_BENCH_* or XDG_* variable in the environment."""
    for name in list(os.environ):
        if name.startswith(("CIS_BENCH_", "XDG_")):
            monkeypatch.delenv(name)


@pytest.fixture
def data_dir(tmp_path, clean_env, monkeypatch):
    """An empty folder set as CIS_BENCH_HOME: config.toml, catalog.db and session.cookies all live in it."""
    monkeypatch.setenv("CIS_BENCH_HOME", str(tmp_path))
    return tmp_path


def _unix(environ):
    return xdg_folders(environ, home=HOME, windows=False)


class TestFoldersFollowTheXdgBaseDirectoriesLikeGh:
    """Config: CIS_BENCH_CONFIG_DIR > CIS_BENCH_HOME > XDG_CONFIG_HOME > AppData (Windows) > ~/.config.
    Data and state: CIS_BENCH_HOME > XDG_DATA_HOME / XDG_STATE_HOME > LocalAppData (Windows) > ~/.local."""

    def test_nothing_set_is_the_xdg_defaults_under_the_home_folder(self):
        assert _unix({}) == Folders(
            config=HOME / ".config" / "cis-bench",
            data=HOME / ".local" / "share" / "cis-bench",
            state=HOME / ".local" / "state" / "cis-bench",
        )

    def test_the_xdg_variables_each_move_their_own_folder(self):
        folders = _unix({"XDG_CONFIG_HOME": "/c", "XDG_DATA_HOME": "/d", "XDG_STATE_HOME": "/s"})
        assert folders == Folders(
            config=Path("/c/cis-bench"), data=Path("/d/cis-bench"), state=Path("/s/cis-bench")
        )

    @pytest.mark.parametrize("value", ["", "   ", "relative/dir"])
    def test_a_blank_or_relative_xdg_value_is_ignored_as_the_spec_says(self, value):
        folders = _unix({"XDG_CONFIG_HOME": value, "XDG_DATA_HOME": value, "XDG_STATE_HOME": value})
        assert folders == _unix({})

    def test_cis_bench_home_puts_all_three_in_one_flat_folder(self):
        folders = _unix({"CIS_BENCH_HOME": "/one", "XDG_CONFIG_HOME": "/c", "XDG_DATA_HOME": "/d"})
        assert folders == Folders(config=Path("/one"), data=Path("/one"), state=Path("/one"))

    def test_cis_bench_config_dir_beats_cis_bench_home_for_config_only(self):
        folders = _unix({"CIS_BENCH_HOME": "/one", "CIS_BENCH_CONFIG_DIR": "/cfg"})
        assert folders == Folders(config=Path("/cfg"), data=Path("/one"), state=Path("/one"))

    def test_cis_bench_config_dir_beats_xdg_config_home(self):
        folders = _unix({"CIS_BENCH_CONFIG_DIR": "/cfg", "XDG_CONFIG_HOME": "/c"})
        assert folders.config == Path("/cfg")
        assert folders.data == HOME / ".local" / "share" / "cis-bench"

    def test_a_tilde_in_a_cis_bench_variable_is_the_home_folder(self):
        folders = _unix({"CIS_BENCH_HOME": "~/cis"})
        assert folders == Folders(config=HOME / "cis", data=HOME / "cis", state=HOME / "cis")

    def test_a_relative_cis_bench_folder_is_taken_from_the_working_directory(self):
        # As CIS_BENCH_DATA_DIR was; a blank value is ignored.
        assert _unix({"CIS_BENCH_HOME": "data"}).data == Path("data")
        assert _unix({"CIS_BENCH_HOME": "  "}) == _unix({})

    def test_windows_uses_appdata_and_localappdata_when_set(self):
        folders = xdg_folders(
            {"AppData": "C:/Users/u/AppData/Roaming", "LocalAppData": "C:/Users/u/AppData/Local"},
            home=WIN_HOME,
            windows=True,
        )
        assert folders == Folders(
            config=Path("C:/Users/u/AppData/Roaming/cis-bench"),
            data=Path("C:/Users/u/AppData/Local/cis-bench"),
            state=Path("C:/Users/u/AppData/Local/cis-bench"),
        )

    def test_on_windows_an_xdg_variable_beats_appdata_as_in_gh(self):
        folders = xdg_folders(
            {"AppData": "C:/Users/u/AppData/Roaming", "XDG_CONFIG_HOME": "C:/xdg"},
            home=WIN_HOME,
            windows=True,
        )
        assert folders.config == Path("C:/xdg/cis-bench")

    def test_on_windows_without_appdata_the_unix_defaults_apply(self):
        assert xdg_folders({}, home=WIN_HOME, windows=True) == xdg_folders(
            {}, home=WIN_HOME, windows=False
        )

    def test_appdata_is_not_read_off_windows(self):
        folders = _unix({"AppData": "/roaming", "LocalAppData": "/local"})
        assert folders == _unix({})


class TestWhereTheFilesLive:
    def test_config_toml_catalog_db_and_session_cookies_each_live_in_their_xdg_folder(
        self, clean_env, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "s"))
        settings = load_settings()
        assert settings.config_file_path == tmp_path / "c" / "cis-bench" / "config.toml"
        assert settings.catalog_db_path == tmp_path / "d" / "cis-bench" / "catalog.db"
        assert settings.benchmarks_dir == tmp_path / "d" / "cis-bench" / "benchmarks"
        assert settings.session_file_path == tmp_path / "s" / "cis-bench" / "session.cookies"
        assert settings.data_dir == tmp_path / "d" / "cis-bench"

    def test_cis_bench_home_is_one_flat_folder(self, data_dir):
        settings = load_settings()
        assert settings.config_file_path == data_dir / "config.toml"
        assert settings.catalog_db_path == data_dir / "catalog.db"
        assert settings.benchmarks_dir == data_dir / "benchmarks"
        assert settings.session_file_path == data_dir / "session.cookies"

    def test_the_config_file_is_read_from_cis_bench_config_dir_over_cis_bench_home(
        self, data_dir, monkeypatch, tmp_path
    ):
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        (cfg / "config.toml").write_text("search_limit = 5\n")
        (data_dir / "config.toml").write_text("search_limit = 7\n")
        monkeypatch.setenv("CIS_BENCH_CONFIG_DIR", str(cfg))
        settings = load_settings()
        assert settings.search_limit == 5
        assert settings.catalog_db_path == data_dir / "catalog.db"

    def test_a_dot_env_file_is_not_read(self, data_dir):
        (data_dir / ".env").write_text("CIS_BENCH_SEARCH_LIMIT=7\n")
        assert load_settings().search_limit == 100

    def test_cis_bench_data_dir_is_refused_and_names_cis_bench_home(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_DATA_DIR", str(data_dir))
        with pytest.raises(ConfigurationError, match="CIS_BENCH_HOME") as caught:
            load_settings()
        assert "CIS_BENCH_DATA_DIR" in str(caught.value)

    def test_cis_bench_env_is_refused_and_names_cis_bench_home(self, data_dir, monkeypatch):
        # A leftover CIS_BENCH_ENV=dev must never silently pick a folder.
        monkeypatch.setenv("CIS_BENCH_ENV", "dev")
        with pytest.raises(ConfigurationError, match="CIS_BENCH_HOME") as caught:
            load_settings()
        assert "CIS_BENCH_ENV" in str(caught.value)

    @pytest.mark.parametrize("key", ["data_dir", "folders", "config_dir"])
    def test_the_folders_cannot_be_set_from_config_toml(self, data_dir, key):
        (data_dir / "config.toml").write_text(f'{key} = "/elsewhere"\n')
        with pytest.raises(ConfigurationError, match=key) as caught:
            load_settings()
        assert "config.toml" in str(caught.value)

    def test_surrounding_spaces_are_ignored_like_everywhere_else(self, data_dir, monkeypatch):
        # The folder the file is read from and the folder reported must be the same one.
        monkeypatch.setenv("CIS_BENCH_HOME", f"  {data_dir}  ")
        (data_dir / "config.toml").write_text("search_limit = 5\n")
        settings = load_settings()
        assert settings.data_dir == data_dir
        assert settings.search_limit == 5

    def test_a_cis_bench_folders_variable_is_not_a_setting_either(self, data_dir, monkeypatch):
        # The folders field is fed by resolve_folders only; a stray variable of that name is
        # neither parsed as the field nor an error.
        monkeypatch.setenv("CIS_BENCH_FOLDERS", "/elsewhere")
        assert load_settings().data_dir == data_dir

    def test_the_folders_are_not_settings(self, data_dir):
        # The "unknown setting" message lists settings; the folders are located, not set.
        (data_dir / "config.toml").write_text("serch_limit = 7\n")
        with pytest.raises(ConfigurationError) as caught:
            load_settings()
        assert "CIS_BENCH_FOLDERS" not in str(caught.value)
        assert "CIS_BENCH_SEARCH_LIMIT" in str(caught.value)


class TestAnEarlierInstallsFolderKeepsWorking:
    """~/.cis-bench from an earlier version is used, and reported, until it is migrated."""

    @pytest.fixture
    def home(self, clean_env, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
        return tmp_path

    def test_an_existing_dot_cis_bench_is_the_home_folder_and_is_reported(self, home):
        (home / ".cis-bench").mkdir()
        settings = load_settings()
        assert settings.folders == Folders(
            config=home / ".cis-bench",
            data=home / ".cis-bench",
            state=home / ".cis-bench",
            legacy=home / ".cis-bench",
        )

    def test_without_the_old_folder_the_xdg_folders_apply_and_nothing_is_reported(self, home):
        settings = load_settings()
        assert settings.folders.legacy is None
        assert settings.data_dir == home / "xdg-data" / "cis-bench"

    def test_an_override_wins_over_the_old_folder(self, home, monkeypatch):
        (home / ".cis-bench").mkdir()
        monkeypatch.setenv("CIS_BENCH_HOME", str(home / "one"))
        settings = load_settings()
        assert settings.folders.legacy is None
        assert settings.data_dir == home / "one"

    def test_a_migrated_install_is_not_pulled_back_to_the_old_folder(self, home):
        # Once catalog.db exists in the XDG data folder, a leftover ~/.cis-bench is ignored.
        (home / ".cis-bench").mkdir()
        (home / "xdg-data" / "cis-bench").mkdir(parents=True)
        (home / "xdg-data" / "cis-bench" / "catalog.db").touch()
        settings = load_settings()
        assert settings.folders.legacy is None
        assert settings.data_dir == home / "xdg-data" / "cis-bench"


class TestPrecedence:
    """One chain: passed-in value > environment > config.toml > default."""

    def test_config_toml_beats_the_default(self, data_dir):
        (data_dir / "config.toml").write_text("search_limit = 5\n")
        assert load_settings().search_limit == 5

    def test_the_environment_beats_config_toml(self, data_dir, monkeypatch):
        (data_dir / "config.toml").write_text("search_limit = 7\n")
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "9")
        assert load_settings().search_limit == 9

    def test_a_blank_environment_value_falls_through_to_config_toml(self, data_dir, monkeypatch):
        (data_dir / "config.toml").write_text("search_limit = 7\n")
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "  ")
        assert load_settings().search_limit == 7

    def test_a_passed_in_value_beats_the_environment(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "9")
        assert load_settings(search_limit=3).search_limit == 3

    def test_a_change_to_the_environment_is_seen_by_the_next_read(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "9")
        assert load_settings().search_limit == 9
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "11")
        assert load_settings().search_limit == 11

    def test_the_config_file_does_not_change_the_process_environment(self, data_dir):
        (data_dir / "config.toml").write_text("search_limit = 7\n")
        assert load_settings().search_limit == 7
        assert "CIS_BENCH_SEARCH_LIMIT" not in os.environ

    def test_an_unknown_cis_bench_name_in_the_config_file_is_refused(self, data_dir):
        # A typo must not be ignored silently.
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
        assert load_settings().table_title_width == 90

    def test_from_env(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_TABLE_TITLE_WIDTH", "120")
        assert load_settings().table_title_width == 120

    def test_blank_means_the_default(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_TABLE_TITLE_WIDTH", "")
        assert load_settings().table_title_width == 90

    @pytest.mark.parametrize("value", ["abc", "0", "-3", "1.5"])
    def test_a_value_that_is_not_a_positive_integer_is_refused(self, data_dir, monkeypatch, value):
        monkeypatch.setenv("CIS_BENCH_TABLE_TITLE_WIDTH", value)
        with pytest.raises(ConfigurationError, match="CIS_BENCH_TABLE_TITLE_WIDTH") as caught:
            load_settings()
        assert repr(value) in str(caught.value)


class TestConfigSearchLimit:
    """CIS_BENCH_SEARCH_LIMIT: an integer of 1 or more, default 100."""

    def test_default(self, data_dir):
        assert load_settings().search_limit == 100

    def test_from_env(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "500")
        assert load_settings().search_limit == 500

    def test_blank_means_the_default(self, data_dir, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", "")
        assert load_settings().search_limit == 100

    @pytest.mark.parametrize("value", ["abc", "many", "0", "-1", "2.5"])
    def test_a_value_that_is_not_a_positive_integer_is_refused(self, data_dir, monkeypatch, value):
        monkeypatch.setenv("CIS_BENCH_SEARCH_LIMIT", value)
        with pytest.raises(ConfigurationError, match="CIS_BENCH_SEARCH_LIMIT") as caught:
            load_settings()
        assert repr(value) in str(caught.value)


class TestConfigVerifySSL:
    """Tests for SSL verification configuration."""

    def test_verify_ssl_default_true(self):
        """Certificate verification is on when CIS_BENCH_VERIFY_SSL is unset or blank."""
        env = os.environ.copy()
        env.pop("CIS_BENCH_VERIFY_SSL", None)
        with patch.dict(os.environ, env, clear=True):
            assert load_settings().verify_ssl is True

        with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": "   "}):
            assert load_settings().verify_ssl is True

    def test_verify_ssl_true_values(self):
        """Should return True for 'true', '1', 'yes' values."""
        for value in ["true", "True", "TRUE", "1", "yes", "Yes", "YES", " true "]:
            with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": value}):
                assert load_settings().verify_ssl is True, f"Failed for value: {value}"

    def test_verify_ssl_false_values(self):
        """Should return False only for the explicit opt-out values 'false', '0', 'no'."""

        for value in ["false", "False", "FALSE", "0", "no", "No", "NO", " false "]:
            with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": value}):
                assert load_settings().verify_ssl is False, f"Failed for value: {value}"

    def test_verify_ssl_rejects_unrecognized_value(self):
        """A typo in a security setting is a configuration error, never a silent opt-out."""
        for value in ["anything", "off", "disable", "f"]:
            with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": value}):
                with pytest.raises(ValueError, match="CIS_BENCH_VERIFY_SSL") as exc_info:
                    load_settings()
                assert value in str(exc_info.value)


class TestConfigWorkbenchBaseUrl:
    """Tests for configurable CIS WorkBench base URL validation."""

    def test_workbench_url_defaults_to_production(self):
        """Should return https://workbench.cisecurity.org when CIS_BENCH_WORKBENCH_URL is unset or blank."""

        env = os.environ.copy()
        env.pop("CIS_BENCH_WORKBENCH_URL", None)
        with patch.dict(os.environ, env, clear=True):
            assert load_settings().workbench_url == "https://workbench.cisecurity.org"

        with patch.dict(os.environ, {"CIS_BENCH_WORKBENCH_URL": "   "}):
            assert load_settings().workbench_url == "https://workbench.cisecurity.org"

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
    def test_workbench_url_accepts_valid_cisecurity_origins(self, raw_url: str, expected: str):
        """Should normalize valid https://*.cisecurity.org origins."""

        with patch.dict(os.environ, {"CIS_BENCH_WORKBENCH_URL": raw_url}):
            assert load_settings().workbench_url == expected

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
    def test_workbench_url_rejects_untrusted_insecure_or_non_origin_urls(self, invalid_url: str):
        """Should raise ValueError for non-HTTPS, non-cisecurity.org, credentialed, or path/query URLs."""

        with patch.dict(os.environ, {"CIS_BENCH_WORKBENCH_URL": invalid_url}):
            with pytest.raises(ValueError, match="CIS_BENCH_WORKBENCH_URL"):
                load_settings()


class TestConfigurationErrorType:
    """Configuration problems raise ConfigurationError so callers can classify them by type."""

    def test_invalid_workbench_url_raises_configuration_error(self):
        from cis_bench.exceptions import ConfigurationError

        with patch.dict(os.environ, {"CIS_BENCH_WORKBENCH_URL": "http://evil.example"}):
            with pytest.raises(ConfigurationError, match="CIS_BENCH_WORKBENCH_URL") as exc_info:
                load_settings()
        assert isinstance(exc_info.value, ValueError)

    def test_invalid_verify_ssl_raises_configuration_error(self):
        from cis_bench.exceptions import ConfigurationError

        with patch.dict(os.environ, {"CIS_BENCH_VERIFY_SSL": "bogus"}):
            with pytest.raises(ConfigurationError, match="CIS_BENCH_VERIFY_SSL") as exc_info:
                load_settings()
        assert isinstance(exc_info.value, ValueError)


class TestConfigRequestTimeout:
    """CIS_BENCH_REQUEST_TIMEOUT bounds every scraper request so a stalled connection cannot hang a download."""

    def test_default_is_thirty_second_read_with_ten_second_connect(self):
        env = os.environ.copy()
        env.pop("CIS_BENCH_REQUEST_TIMEOUT", None)
        with patch.dict(os.environ, env, clear=True):
            assert load_settings().request_timeouts == (10.0, 30.0)
        with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": "  "}):
            assert load_settings().request_timeouts == (10.0, 30.0)

    def test_value_sets_the_read_timeout(self):
        with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": "60"}):
            assert load_settings().request_timeouts == (10.0, 60.0)
        with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": " 45.5 "}):
            assert load_settings().request_timeouts == (10.0, 45.5)

    def test_connect_timeout_never_exceeds_read_timeout(self):
        with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": "5"}):
            assert load_settings().request_timeouts == (5.0, 5.0)

    def test_rejects_non_positive_or_non_numeric_values(self):
        from cis_bench.exceptions import ConfigurationError

        # inf would turn the timeout off again and nan is accepted by float() but
        # rejected by sockets; both must be configuration errors.
        for value in ["abc", "0", "-5", "30s", "nan", "inf", "-inf", "infinity"]:
            with patch.dict(os.environ, {"CIS_BENCH_REQUEST_TIMEOUT": value}):
                with pytest.raises(
                    ConfigurationError, match="CIS_BENCH_REQUEST_TIMEOUT"
                ) as exc_info:
                    load_settings()
                assert value in str(exc_info.value)
