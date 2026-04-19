"""Offline mode helpers."""

import click
from rich.console import Console

console = Console()


def check_offline_mode(ctx, command_name: str) -> None:
    """Check if offline mode is enabled and raise error if so.

    Call this at the start of any command that requires network access.

    Args:
        ctx: Click context (must have ctx.obj["offline"])
        command_name: Name of the command for error message

    Raises:
        click.ClickException: If offline mode is enabled
    """
    if ctx.obj and ctx.obj.get("offline"):
        raise click.ClickException(
            f"Cannot run '{command_name}' in offline mode.\n\n"
            f"This command requires network access to CIS WorkBench.\n"
            f"Remove --offline flag to allow network calls.\n\n"
            f"Tip: Run 'cis-bench cache status' to see what's available offline."
        )
