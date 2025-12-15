"""Authentication commands for CIS Benchmark CLI."""

import logging
import shutil
import subprocess
import sys
import webbrowser
from urllib.parse import urlparse

import click
from rich.console import Console

from cis_bench.cli.helpers.output import output_data
from cis_bench.config import Config
from cis_bench.fetcher.auth import AuthManager

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def auth():
    """Manage authentication for CIS WorkBench.

    These commands help you log in, check your session status, and log out.

    \b
    Example workflow:
        cis-bench auth login --browser chrome   # First time login
        cis-bench auth status                   # Check if logged in
        cis-bench auth logout                   # Clear saved session
    """
    pass


@auth.command()
@click.option(
    "--browser",
    "-b",
    type=click.Choice(["chrome", "firefox", "edge", "safari"]),
    required=True,
    help="Browser to use for authentication",
)
@click.option(
    "--open",
    "-o",
    is_flag=True,
    help="Open CIS WorkBench login page in browser",
)
@click.option(
    "--no-verify-ssl",
    is_flag=True,
    help="Disable SSL certificate verification (use if encountering SSL errors)",
)
def login(browser, open, no_verify_ssl):
    """Log in to CIS WorkBench and save session.

    This command will:
    1. Optionally open the CIS WorkBench login page in your browser
    2. Wait for you to log in manually
    3. Extract session cookies from your browser
    4. Save them for future use

    After running this once, other commands won't need --browser flag.

    \b
    Examples:
        cis-bench auth login --browser chrome --open
        cis-bench auth login --browser firefox
    """
    try:
        # Open browser if requested
        if open:
            console.print("[cyan]Opening CIS WorkBench login page...[/cyan]")
            login_url = "https://workbench.cisecurity.org/"

            # Security: Validate URL is CIS WorkBench domain
            parsed = urlparse(login_url)
            if parsed.netloc != "workbench.cisecurity.org" or parsed.scheme != "https":
                raise ValueError("Invalid login URL - must be https://workbench.cisecurity.org/")

            try:
                import platform

                system = platform.system()

                if system == "Darwin":  # macOS
                    # Use macOS 'open' command with full path and specific browser
                    open_cmd = shutil.which("open")
                    if not open_cmd:
                        raise FileNotFoundError("'open' command not found")

                    browser_apps = {
                        "chrome": "Google Chrome",
                        "firefox": "Firefox",
                        "edge": "Microsoft Edge",
                        "safari": "Safari",
                    }
                    app_name = browser_apps.get(browser.lower(), "Google Chrome")
                    subprocess.run(
                        [open_cmd, "-a", app_name, login_url],
                        check=True,
                        capture_output=True,
                    )
                elif system == "Linux":
                    # Use xdg-open with full path
                    xdg_open = shutil.which("xdg-open")
                    if not xdg_open:
                        raise FileNotFoundError("'xdg-open' command not found")
                    subprocess.run([xdg_open, login_url], check=True, capture_output=True)
                elif system == "Windows":
                    # Use webbrowser module instead of shell command
                    webbrowser.open(login_url)
                else:
                    # Fallback to webbrowser module
                    webbrowser.open(login_url)

                console.print(f"[green]✓[/green] Opened {login_url} in {browser}\n")

            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Could not open browser: {e}")
                console.print(f"[dim]Please open manually: {login_url}[/dim]\n")

            console.print("[yellow]Please log in to CIS WorkBench in your browser...[/yellow]")
            console.print("[dim]Press Enter when you've completed login...[/dim]")
            input()

        # Extract cookies from browser
        console.print(f"[cyan]Extracting session cookies from {browser}...[/cyan]")

        # Determine SSL verification setting
        verify_ssl = not no_verify_ssl if no_verify_ssl else Config.get_verify_ssl()

        session = AuthManager.load_cookies_from_browser(browser, verify_ssl=verify_ssl)

        if not session or not session.cookies:
            console.print(f"[red]✗ No cookies found in {browser}[/red]")
            console.print(
                "\n[yellow]Make sure you are logged into workbench.cisecurity.org in your browser[/yellow]"
            )
            sys.exit(1)

        cookie_count = len(list(session.cookies))
        console.print(f"[green]✓[/green] Extracted {cookie_count} cookies from {browser}")

        # Validate session
        console.print("[cyan]Validating session...[/cyan]")

        # Determine SSL verification: flag overrides config/env
        verify_ssl = not no_verify_ssl if no_verify_ssl else Config.get_verify_ssl()

        if not AuthManager.validate_session(session, verify_ssl=verify_ssl):
            console.print("[red]✗ Session validation failed[/red]")
            console.print(
                "\n[yellow]Please ensure you are logged into workbench.cisecurity.org in your browser[/yellow]"
            )
            if verify_ssl:
                console.print(
                    "[dim]Tip: Try adding --no-verify-ssl if you're encountering SSL errors[/dim]"
                )
                console.print("[dim]Or set: export CIS_BENCH_VERIFY_SSL=false[/dim]")
            sys.exit(1)

        console.print("[green]✓[/green] Session is valid")

        # Save session
        console.print("[cyan]Saving session...[/cyan]")
        AuthManager.save_session(session)

        session_path = AuthManager.get_session_file_path()
        console.print(f"[green]✓[/green] Session saved to {session_path}\n")

        console.print("[bold green]Login successful![/bold green]")
        console.print("[dim]You can now run commands without --browser flag[/dim]")

    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Login failed: {e}", exc_info=True)
        console.print(f"[red]✗ Login failed: {e}[/red]")
        sys.exit(1)


@auth.command()
@click.option(
    "--output-format",
    "-o",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format (default: table)",
)
def status(output_format):
    """Check authentication status.

    Shows whether you have a saved session and if it's still valid.

    \b
    Example:
        cis-bench auth status
    """
    try:
        session_path = AuthManager.get_session_file_path()

        # Check if session file exists
        if not session_path.exists():
            console.print("[yellow]Not logged in[/yellow]")
            console.print(f"\n[dim]No saved session found at {session_path}[/dim]")
            console.print("\n[cyan]To log in:[/cyan]")
            console.print("  cis-bench auth login --browser chrome --open")
            sys.exit(1)

        # Load session
        console.print("[cyan]Checking saved session...[/cyan]")
        session = AuthManager.load_saved_session()

        if not session:
            console.print("[red]✗ Could not load saved session[/red]")
            console.print("\n[cyan]Try logging in again:[/cyan]")
            console.print("  cis-bench auth login --browser chrome --open")
            sys.exit(1)

        cookie_count = len(list(session.cookies))
        console.print(f"[green]✓[/green] Found saved session with {cookie_count} cookies")

        # Validate session
        console.print("[cyan]Validating session...[/cyan]")

        verify_ssl = Config.get_verify_ssl()

        is_valid = AuthManager.validate_session(session, verify_ssl=verify_ssl)

        # Create structured data
        status_data = {
            "logged_in": is_valid,
            "session_file": str(session_path),
            "cookie_count": cookie_count,
            "ssl_verify": verify_ssl,
        }

        # Output in requested format
        if output_format != "table":
            output_data(status_data, output_format)

        # Display for humans
        if is_valid:
            console.print("[bold green]✓ Logged in[/bold green]")
            console.print(f"\n[dim]Session file: {session_path}[/dim]")
            console.print("[dim]Session is valid and ready to use[/dim]")
        else:
            console.print("[red]✗ Session expired[/red]")
            console.print("\n[yellow]Your saved session is no longer valid[/yellow]")
            console.print("\n[cyan]To refresh your session:[/cyan]")
            console.print("  cis-bench auth login --browser chrome")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Status check failed: {e}", exc_info=True)
        console.print(f"[red]✗ Status check failed: {e}[/red]")
        sys.exit(1)


@auth.command()
def logout():
    """Log out and clear saved session.

    This removes your saved session cookies. You'll need to log in again
    to use commands that require authentication.

    \b
    Example:
        cis-bench auth logout
    """
    try:
        session_path = AuthManager.get_session_file_path()

        if not session_path.exists():
            console.print("[yellow]No saved session to clear[/yellow]")
            console.print(f"\n[dim]No session file at {session_path}[/dim]")
            return

        # Clear session
        console.print("[cyan]Clearing saved session...[/cyan]")
        cleared = AuthManager.clear_saved_session()

        if cleared:
            console.print("[green]✓ Logged out successfully[/green]")
            console.print(f"\n[dim]Removed session file: {session_path}[/dim]")
            console.print("\n[cyan]To log in again:[/cyan]")
            console.print("  cis-bench auth login --browser chrome --open")
        else:
            console.print("[yellow]No session to clear[/yellow]")

    except Exception as e:
        logger.error(f"Logout failed: {e}", exc_info=True)
        console.print(f"[red]✗ Logout failed: {e}[/red]")
        sys.exit(1)
