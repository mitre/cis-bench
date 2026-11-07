"""User-facing error reports shared by the CLI commands.

Each report prints a heading and the error's own message, escaped so Rich
shows it as written. The caller decides how the command exits.
"""

from rich.console import Console
from rich.markup import escape

from cis_bench.exceptions import (
    AuthenticationError,
    FetchError,
    NoSavedSessionError,
    TLSVerificationError,
)

# What logging in or downloading from WorkBench can raise; report_download_error reports each.
DOWNLOAD_ERRORS = (AuthenticationError, TLSVerificationError, FetchError)


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


def report_login_required(console: Console) -> None:
    """Tell the user there is no saved session, and how to make one."""
    console.print("\n[bold red]Authentication Required[/bold red]\n")
    console.print("[bold cyan]Please log in first:[/bold cyan]")
    console.print("  cis-bench auth login --browser chrome")
    console.print("\n[dim]This saves your session for future commands.[/dim]")
    console.print("\n[dim]Windows users: If Chrome fails, try Firefox or --cookies option.[/dim]")


def report_download_error(
    console: Console,
    error: AuthenticationError | TLSVerificationError | FetchError,
) -> None:
    """Report one of DOWNLOAD_ERRORS the way download, get and diff all report it."""
    if isinstance(error, NoSavedSessionError):
        report_login_required(console)
    elif isinstance(error, AuthenticationError):
        report_expired_session(console, error)
    elif isinstance(error, TLSVerificationError):
        # The server could not be trusted; the message carries the remediation.
        console.print(f"\n[red]✗ {escape(str(error))}[/red]")
    else:
        report_unreachable(console, error)


def cache_failure(benchmark_id: str, error: Exception) -> str:
    """The message for a failed cache write, naming its cause.

    SQLAlchemy's own message adds the SQL statement and its parameters (the whole benchmark
    JSON); the cause it wraps is what the user needs.
    """
    cause = getattr(error, "orig", None)
    return f"Could not cache {benchmark_id}: {cause if cause is not None else error}"
