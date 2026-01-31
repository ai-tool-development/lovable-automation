#!/usr/bin/env python3
"""
Main orchestration script for creating Lovable remixes.

This is the primary entry point for the end-to-end remix workflow:
1. Authenticate (login if needed, extract/reuse token)
2. Verify source project exists
3. Create remix (with safety checks)
4. Return new project details

Safety features integrated:
- Pre-operation safety checks via SafetyManager
- Rate limiting between API calls
- Idempotency checking (prevent duplicate remixes)
- User confirmation prompts
- Audit logging of all operations
"""
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import LovableConfig, get_config, set_config
from auth import get_or_refresh_token, LovableAuth
from api import LovableAPI, RemixResult
from safety import get_safety_manager

console = Console()


@dataclass
class RemixWorkflowResult:
    """Complete result of a remix workflow."""
    success: bool
    source_project_id: str
    new_project_id: Optional[str] = None
    new_project_url: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


def create_remix(
    source_project_id: str,
    include_history: bool = False,
    config: Optional[LovableConfig] = None,
    skip_confirmation: bool = False,
) -> Optional[RemixWorkflowResult]:
    """
    Create a remix of a Lovable project.

    This is the main entry point for programmatic remix creation.
    All operations go through safety checks before execution.

    Args:
        source_project_id: The ID of the project to remix
        include_history: Whether to include edit history
        config: Optional configuration override
        skip_confirmation: Skip the user confirmation prompt

    Returns:
        RemixWorkflowResult with success status and new project details,
        or None if blocked by safety checks
    """
    config = config or get_config()
    safety = get_safety_manager()

    console.print(Panel(
        f"[bold]Creating Remix[/bold]\n"
        f"Source: {source_project_id}\n"
        f"Include History: {include_history}\n"
        f"Skip Confirmation: {skip_confirmation}",
        title="Lovable Remix Workflow",
        border_style="blue",
    ))

    # Step 1: Get authentication token
    console.print("\n[bold]Step 1: Authentication[/bold]")
    token, auth_error = get_or_refresh_token(config)

    if auth_error:
        console.print(f"[red]Authentication failed: {auth_error}[/red]")
        return RemixWorkflowResult(
            success=False,
            source_project_id=source_project_id,
            error=f"Authentication failed: {auth_error}",
        )

    console.print("[green]✓ Authenticated successfully[/green]")

    # Step 2: Initialize API client (includes SafetyManager)
    console.print("\n[bold]Step 2: Initialize API Client[/bold]")
    api = LovableAPI(token, config, safety)
    console.print("[green]✓ API client ready with safety checks[/green]")

    # Step 3: Optionally verify source project (may not work if endpoint doesn't exist)
    console.print("\n[bold]Step 3: Verify Source Project[/bold]")
    source_project = api.get_project(source_project_id)
    if source_project:
        console.print(f"[green]✓ Source project found: {source_project.name}[/green]")
    else:
        console.print("[yellow]⚠ Could not verify source project (endpoint may not exist)[/yellow]")
        console.print("[yellow]  Proceeding with remix attempt...[/yellow]")

    # Step 4: Create remix (safety checks happen inside api.remix_project)
    console.print("\n[bold]Step 4: Create Remix[/bold]")
    console.print("[dim]Safety checks: rate limit, idempotency, daily limits, confirmation[/dim]")

    result = api.remix_project(
        source_project_id,
        include_history,
        skip_confirmation=skip_confirmation,
    )

    # Check if operation was blocked
    if result.error and "Operation blocked" in result.error:
        console.print(f"\n[yellow]Operation was blocked: {result.error}[/yellow]")
        return None

    if result.success:
        workflow_result = RemixWorkflowResult(
            success=True,
            source_project_id=source_project_id,
            new_project_id=result.project_id,
            new_project_url=result.project_url,
        )

        # Display success
        console.print("\n")
        console.print(Panel(
            f"[green bold]✓ Remix Created Successfully![/green bold]\n\n"
            f"[bold]New Project ID:[/bold] {result.project_id}\n"
            f"[bold]URL:[/bold] {result.project_url}",
            title="Success",
            border_style="green",
        ))

        # Save result
        _save_result(workflow_result)

        return workflow_result
    else:
        workflow_result = RemixWorkflowResult(
            success=False,
            source_project_id=source_project_id,
            error=result.error,
        )

        console.print("\n")
        console.print(Panel(
            f"[red bold]✗ Remix Failed[/red bold]\n\n"
            f"[bold]Error:[/bold] {result.error}",
            title="Error",
            border_style="red",
        ))

        _save_result(workflow_result)

        return workflow_result


def _save_result(result: RemixWorkflowResult) -> None:
    """Save workflow result to file for reference."""
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    filename = f"remix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    result_file = results_dir / filename

    result_file.write_text(json.dumps(asdict(result), indent=2))
    console.print(f"[dim]Result saved to: {result_file}[/dim]")


def interactive_remix() -> Optional[RemixWorkflowResult]:
    """
    Interactive remix workflow that prompts for missing configuration.
    """
    config = get_config()
    safety = get_safety_manager()

    console.print(Panel(
        "[bold]Interactive Lovable Remix[/bold]\n\n"
        "This wizard will help you create a remix of a Lovable project.\n"
        "All operations include safety checks and rate limiting.",
        title="Welcome",
        border_style="blue",
    ))

    # Show current safety status
    safety.print_status()

    # Check for credentials
    if not config.has_credentials() and not config.has_token():
        console.print("\n[yellow]No credentials found in environment.[/yellow]")
        console.print("OAuth flow will be used for authentication.")

    # Check for project ID
    if not config.project_id:
        console.print("\n[yellow]No project ID configured.[/yellow]")
        project_input = console.input(
            "[bold]Enter project ID or URL: [/bold]"
        )

        # Handle URL or ID
        if "lovable.dev/projects/" in project_input:
            parts = project_input.rstrip("/").split("/")
            if "projects" in parts:
                idx = parts.index("projects")
                if idx + 1 < len(parts):
                    config.project_id = parts[idx + 1]
        else:
            config.project_id = project_input.strip()

        set_config(config)

    # Confirm (this is in addition to the safety confirmation)
    console.print(f"\n[bold]Project to remix:[/bold] {config.project_id}")
    if not console.input("[bold]Proceed to safety checks? (y/n): [/bold]").lower().startswith("y"):
        console.print("[yellow]Cancelled.[/yellow]")
        return RemixWorkflowResult(
            success=False,
            source_project_id=config.project_id or "",
            error="Cancelled by user",
        )

    # Note: skip_confirmation=False means the safety check will also ask for confirmation
    return create_remix(config.project_id, skip_confirmation=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create a Lovable project remix")
    parser.add_argument(
        "project_id",
        nargs="?",
        help="Project ID to remix (or set LOVABLE_PROJECT_ID env var)",
    )
    parser.add_argument(
        "--include-history",
        action="store_true",
        help="Include edit history in remix",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompts",
    )

    args = parser.parse_args()

    if args.interactive:
        result = interactive_remix()
    else:
        config = get_config()
        project_id = args.project_id or config.project_id

        if not project_id:
            console.print("[red]Error: No project ID provided.[/red]")
            console.print("Use: python remix.py <project_id>")
            console.print("Or set LOVABLE_PROJECT_ID environment variable")
            sys.exit(1)

        result = create_remix(
            project_id,
            args.include_history,
            skip_confirmation=args.yes,
        )

    if result is None:
        console.print("[red]Operation was blocked[/red]")
        sys.exit(1)

    sys.exit(0 if result.success else 1)
