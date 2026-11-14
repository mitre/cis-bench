"""Offline mode: cis-bench never contacts CIS WorkBench.

Offline mode is the ``offline`` setting (CIS_BENCH_OFFLINE, ``offline = true`` in config.toml),
and ``cis-bench --offline`` turns it on for one run. It means what it means for cargo and uv:
use the catalog and the downloaded benchmarks, and fail only what needs WorkBench. Every
WorkBench session is opened through services.workbench_session, which refuses there.
"""

import click

from cis_bench.config import Settings


class OfflineError(click.ClickException):
    """A command needed CIS WorkBench while offline mode is on (stderr, exit code 1)."""


def require_online(settings: Settings, needs: str) -> None:
    """Refuse when offline mode is on: the current command needs WorkBench to do ``needs``.

    Raises:
        OfflineError: Offline mode is on. Nothing has been sent to WorkBench.
    """
    if settings.offline:
        raise OfflineError(
            f"{_command_name(click.get_current_context())} needs CIS WorkBench to {needs}, "
            "and offline mode is on (--offline, CIS_BENCH_OFFLINE, or offline = true in "
            "config.toml). Nothing was sent to WorkBench. Run 'cis-bench cache status' to "
            "see what is available offline."
        )


def _command_name(ctx: click.Context) -> str:
    """The command as a user types it ("cis-bench catalog download"), whatever the program
    was started as (python -m cis_bench, a test runner)."""
    names: list[str] = []
    while ctx.parent is not None:
        names.append(ctx.info_name or ctx.command.name or "")
        ctx = ctx.parent
    return " ".join(["cis-bench", *reversed(names)])
