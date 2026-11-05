"""Tests for `cis-bench config migrate`: moving an earlier version's ~/.cis-bench into the XDG folders."""

import os
import stat

import pytest

from cis_bench.cli.app import cli


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home folder with ~/.cis-bench from an earlier version; the XDG folders point under it too."""
    for name in list(os.environ):
        if name.startswith(("CIS_BENCH_", "XDG_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    legacy = tmp_path / ".cis-bench"
    legacy.mkdir()
    (legacy / "config.toml").write_text("search_limit = 5\n")
    (legacy / "catalog.db").write_bytes(b"catalog")
    (legacy / "benchmarks").mkdir()
    (legacy / "benchmarks" / "one.json").write_text("{}")
    (legacy / "session.cookies").write_bytes(b"cookies")
    return tmp_path


def _targets(home):
    return (
        home / "xdg-config" / "cis-bench",
        home / "xdg-data" / "cis-bench",
        home / "xdg-state" / "cis-bench",
    )


class TestConfigMigrate:
    def test_moves_each_file_to_its_folder_and_says_so(self, cli_runner, home):
        config, data, state = _targets(home)

        result = cli_runner.invoke(cli, ["config", "migrate"])

        assert result.exit_code == 0, result.output
        assert (config / "config.toml").read_text() == "search_limit = 5\n"
        assert (data / "catalog.db").read_bytes() == b"catalog"
        assert (data / "benchmarks" / "one.json").read_text() == "{}"
        assert (state / "session.cookies").read_bytes() == b"cookies"
        for name in ("config.toml", "catalog.db", "benchmarks", "session.cookies"):
            assert name in result.output
        assert str(data / "catalog.db") in result.output

    def test_the_new_folders_are_private_to_the_user(self, cli_runner, home):
        result = cli_runner.invoke(cli, ["config", "migrate"])

        assert result.exit_code == 0, result.output
        for folder in _targets(home):
            assert stat.S_IMODE(folder.stat().st_mode) == 0o700

    def test_removes_the_old_folder_once_it_is_empty(self, cli_runner, home):
        result = cli_runner.invoke(cli, ["config", "migrate"])

        assert result.exit_code == 0, result.output
        assert not (home / ".cis-bench").exists()
        assert str(home / ".cis-bench") in result.output

    def test_leaves_other_files_in_place_and_names_them(self, cli_runner, home):
        (home / ".cis-bench" / ".env").write_text("CIS_BENCH_SEARCH_LIMIT=7\n")
        (home / ".cis-bench" / "catalog.db.backup-1").write_bytes(b"old")

        result = cli_runner.invoke(cli, ["config", "migrate"])

        assert result.exit_code == 0, result.output
        assert sorted(p.name for p in (home / ".cis-bench").iterdir()) == [
            ".env",
            "catalog.db.backup-1",
        ]
        assert ".env" in result.output
        assert "catalog.db.backup-1" in result.output

    def test_refuses_to_overwrite_and_moves_nothing(self, cli_runner, home):
        config, data, _ = _targets(home)
        config.mkdir(parents=True)
        (config / "config.toml").write_text("search_limit = 9\n")

        result = cli_runner.invoke(cli, ["config", "migrate"])

        assert result.exit_code == 1
        assert str(config / "config.toml") in result.output
        assert (config / "config.toml").read_text() == "search_limit = 9\n"
        assert (home / ".cis-bench" / "catalog.db").read_bytes() == b"catalog"
        assert not (data / "catalog.db").exists()

    def test_a_second_run_has_nothing_to_do_and_no_notice(self, cli_runner, home):
        first = cli_runner.invoke(cli, ["config", "migrate"])
        assert first.exit_code == 0, first.output

        second = cli_runner.invoke(cli, ["config", "migrate"])

        assert second.exit_code == 0, second.output
        assert "Nothing to migrate" in second.stdout
        assert "config migrate" not in second.stderr  # the notice is gone once migrated

    def test_nothing_to_migrate_when_one_folder_is_chosen(self, cli_runner, home, monkeypatch):
        monkeypatch.setenv("CIS_BENCH_HOME", str(home / "one"))

        result = cli_runner.invoke(cli, ["config", "migrate"])

        assert result.exit_code == 0, result.output
        assert "Nothing to migrate" in result.stdout
        assert (home / ".cis-bench" / "catalog.db").exists()
