#!/usr/bin/env python3
"""
CLI interface for Lovable automation tools.

Commands:
- auth: Authenticate and get bearer token
- remix: Create a remix of a project
- probe: Discover available API endpoints
- projects: List projects (if endpoint exists)
- status: Show safety status and limits
- reset: Reset safety state (with confirmation)
"""
import sys
import json
import argparse
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import LovableConfig, get_config
from auth import get_or_refresh_token, LovableAuth
from api import LovableAPI
from safety import get_safety_manager

console = Console()


def cmd_auth(args):
    """Authenticate and display/save bearer token."""
    console.print(Panel(
        "[bold]Lovable Authentication[/bold]",
        border_style="blue",
    ))

    if args.force:
        # Clear existing session
        config = get_config()
        session_file = config.get_session_file()
        token_file = config.session_dir / "bearer_token.txt"

        if session_file.exists():
            session_file.unlink()
            console.print("[yellow]Cleared existing session[/yellow]")
        if token_file.exists():
            token_file.unlink()
            console.print("[yellow]Cleared existing token[/yellow]")

    token, error = get_or_refresh_token()

    if error:
        console.print(f"[red]Error: {error}[/red]")
        return 1

    if args.show:
        console.print(f"\n[bold]Bearer Token:[/bold]\n{token}")
    else:
        console.print(f"\n[bold]Bearer Token:[/bold] {token[:20]}...{token[-10:]}")
        console.print("[dim]Use --show to display full token[/dim]")

    return 0


def cmd_remix(args):
    """Create a remix of a project."""
    # Import here to avoid circular imports
    from remix import create_remix, interactive_remix

    # Show safety status first
    safety = get_safety_manager()
    safety.print_status()

    if args.interactive:
        result = interactive_remix()
    else:
        config = get_config()
        project_id = args.project_id or config.project_id

        if not project_id:
            console.print("[red]Error: No project ID provided.[/red]")
            console.print("Use: python cli.py remix <project_id>")
            console.print("Or set LOVABLE_PROJECT_ID environment variable")
            return 1

        # Note: create_remix handles safety checks internally
        result = create_remix(
            project_id,
            include_history=args.include_history,
            skip_confirmation=args.yes,  # --yes flag skips confirmation
        )

    if result is None:
        console.print("[red]Operation was blocked by safety checks[/red]")
        return 1

    if args.json:
        from dataclasses import asdict
        print(json.dumps(asdict(result), indent=2))

    return 0 if result.success else 1


def cmd_probe(args):
    """Probe API endpoints to discover functionality."""
    console.print(Panel(
        "[bold]API Endpoint Discovery[/bold]\n"
        "Probing various endpoints to discover available functionality.\n"
        "[dim]Limited to prevent excessive requests.[/dim]",
        border_style="blue",
    ))

    token, error = get_or_refresh_token()
    if error:
        console.print(f"[red]Auth error: {error}[/red]")
        return 1

    api = LovableAPI(token)

    # Limited probe
    results = api.probe_endpoints(limit=args.limit)

    # Display results
    table = Table(title="API Endpoints")
    table.add_column("Endpoint", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Result", style="green")

    for endpoint, result in results.items():
        status = str(result.get("status", "error"))
        success = "✓" if result.get("success") else "✗"
        table.add_row(endpoint, status, success)

    console.print(table)

    if args.json:
        print(json.dumps(results, indent=2))

    return 0


def cmd_projects(args):
    """List available projects."""
    console.print(Panel(
        "[bold]Project List[/bold]",
        border_style="blue",
    ))

    token, error = get_or_refresh_token()
    if error:
        console.print(f"[red]Auth error: {error}[/red]")
        return 1

    api = LovableAPI(token)
    projects = api.list_projects()

    if not projects:
        console.print("[yellow]No projects found (or endpoint not available)[/yellow]")
        return 1

    table = Table(title="Your Projects")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("URL", style="blue")

    for project in projects:
        table.add_row(project.id, project.name, project.url)

    console.print(table)

    if args.json:
        from dataclasses import asdict
        print(json.dumps([asdict(p) for p in projects], indent=2))

    return 0


def cmd_status(args):
    """Show safety status and limits."""
    safety = get_safety_manager()
    safety.print_status()

    if args.verbose:
        console.print("\n[bold]Recent Request Log:[/bold]")
        for entry in safety.state.request_log[-10:]:
            status = "✓" if entry.get("success") else "✗"
            console.print(f"  {status} {entry.get('timestamp', '')[:19]} - {entry.get('operation')}")

        if safety.state.remix_history:
            console.print("\n[bold]Remix History (this session):[/bold]")
            for source, remix in safety.state.remix_history.items():
                console.print(f"  {source[:8]}... → {remix[:8]}...")

    return 0


def cmd_reset(args):
    """Reset safety state."""
    if not args.confirm:
        console.print(Panel(
            "[yellow bold]Warning: This will reset all safety counters.[/yellow bold]\n\n"
            "This includes:\n"
            "- Daily request counts\n"
            "- Remix history (idempotency)\n"
            "- Circuit breaker state\n\n"
            "Use --confirm to proceed.",
            title="Confirm Reset",
            border_style="yellow",
        ))
        return 1

    safety = get_safety_manager()
    state_file = safety.state_file

    if state_file.exists():
        state_file.unlink()
        console.print("[green]✓ Safety state reset[/green]")
    else:
        console.print("[yellow]No safety state to reset[/yellow]")

    return 0


def cmd_ui_remix(args):
    """Create a remix via UI automation (recommended)."""
    from ui_remix import ui_remix
    from dataclasses import asdict

    # Show safety status first
    safety = get_safety_manager()
    safety.print_status()

    config = get_config()
    project_id = args.project_id or config.project_id

    if not project_id:
        console.print("[red]Error: No project ID provided.[/red]")
        console.print("Use: python cli.py ui-remix <project_id>")
        console.print("Or set LOVABLE_PROJECT_ID environment variable")
        return 1

    result = ui_remix(
        project_id,
        include_history=not args.no_history,
        skip_confirmation=args.yes,
        debug=args.debug,
    )

    if result is None:
        console.print("[red]Operation was blocked by safety checks[/red]")
        return 1

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        if result.success:
            console.print(Panel(
                f"[green bold]✓ Remix Created![/green bold]\n\n"
                f"New Project ID: {result.new_project_id}\n"
                f"URL: {result.new_project_url}",
                title="Success",
                border_style="green",
            ))
        else:
            console.print(Panel(
                f"[red bold]✗ Remix Failed[/red bold]\n\n"
                f"Error: {result.error}",
                title="Error",
                border_style="red",
            ))

    return 0 if result.success else 1


def main():
    parser = argparse.ArgumentParser(
        description="Lovable Automation CLI - Safe, rate-limited automation for Lovable",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py auth              # Authenticate (OAuth flow)
  python cli.py auth --force      # Force re-authentication
  python cli.py status            # Show safety limits and usage
  python cli.py remix <id>        # Create remix (with confirmation)
  python cli.py remix <id> --yes  # Skip confirmation prompt
  python cli.py probe --limit 3   # Probe 3 API endpoints
  python cli.py projects          # List your projects

Safety Features:
  - Rate limiting: 2s between requests, 10/minute, 60/hour
  - Circuit breaker: Stops after 3 consecutive failures
  - Idempotency: Prevents duplicate remixes
  - Daily limits: Max 20 remixes per day
  - Confirmation: Required for remix operations
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Auth command
    auth_parser = subparsers.add_parser("auth", help="Authenticate and get bearer token")
    auth_parser.add_argument("--force", "-f", action="store_true", help="Force re-authentication")
    auth_parser.add_argument("--show", "-s", action="store_true", help="Show full token")

    # Remix command (API - may not work)
    remix_parser = subparsers.add_parser("remix", help="Create a project remix via API (may not work)")
    remix_parser.add_argument("project_id", nargs="?", help="Project ID to remix")
    remix_parser.add_argument("--include-history", action="store_true", help="Include edit history")
    remix_parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    remix_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    remix_parser.add_argument("--json", action="store_true", help="Output JSON result")

    # UI Remix command (browser automation - more reliable)
    ui_remix_parser = subparsers.add_parser("ui-remix", help="Create a project remix via browser UI (recommended)")
    ui_remix_parser.add_argument("project_id", nargs="?", help="Project ID to remix")
    ui_remix_parser.add_argument("--no-history", action="store_true", help="Don't include edit history")
    ui_remix_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    ui_remix_parser.add_argument("--json", action="store_true", help="Output JSON result")
    ui_remix_parser.add_argument("--debug", "-d", action="store_true", help="Debug mode - show all elements")

    # Probe command
    probe_parser = subparsers.add_parser("probe", help="Probe API endpoints")
    probe_parser.add_argument("--limit", type=int, default=3, help="Max endpoints to probe (default: 3)")
    probe_parser.add_argument("--json", action="store_true", help="Output JSON result")

    # Projects command
    projects_parser = subparsers.add_parser("projects", help="List projects")
    projects_parser.add_argument("--json", action="store_true", help="Output JSON result")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show safety status")
    status_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed logs")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset safety state")
    reset_parser.add_argument("--confirm", action="store_true", help="Confirm reset")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "auth": cmd_auth,
        "remix": cmd_remix,
        "ui-remix": cmd_ui_remix,
        "probe": cmd_probe,
        "projects": cmd_projects,
        "status": cmd_status,
        "reset": cmd_reset,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
