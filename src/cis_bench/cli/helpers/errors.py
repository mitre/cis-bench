"""User-facing error reports shared by the CLI commands.

Each report prints a heading and the error's own message, escaped so Rich
shows it as written. The caller decides how the command exits.
"""

from rich.console import Console
from rich.markup import escape


def report_configuration_error(console: Console, error: Exception) -> None:
    """Report a bad setting (for example CIS_BENCH_REQUEST_TIMEOUT) under one heading."""
    console.print(
        f"\n[bold red]Configuration Error[/bold red]\n[yellow]{escape(str(error))}[/yellow]"
    )


def report_expired_session(console: Console, error: Exception) -> None:
    """Tell the user WorkBench no longer accepts the saved session, and how to log in again."""
    console.print("\n[bold red]Authentication Failed[/bold red]\n")
    console.print(f"[yellow]Error: {escape(str(error))}[/yellow]\n")
    console.print("[bold cyan]Your session may have expired. To refresh:[/bold cyan]")
    console.print("  cis-bench auth login --browser chrome")


def report_unreachable(console: Console, error: Exception) -> None:
    """Tell the user WorkBench did not answer. That is not an expired session: nothing was
    learned about the session, and the saved one is left as it is."""
    console.print("\n[bold red]Could not reach WorkBench[/bold red]\n")
    console.print(f"[yellow]Error: {escape(str(error))}[/yellow]\n", soft_wrap=True)
    console.print(
        "Nothing was changed: any saved session was kept. "
        "Check the network connection and try again."
    )
