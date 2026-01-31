#!/usr/bin/env python3
"""
Record a remix action to capture the exact UI flow.

This script:
1. Opens a browser with your saved Lovable session
2. Records all your interactions (clicks, inputs, etc.)
3. Generates Python code that can replay those actions
4. Saves the recording for use in automated remixes

Usage:
    python record_remix.py <project_id>

Then manually perform the remix in the browser.
The script will output the recorded actions.
"""
import json
import subprocess
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from config import get_config

console = Console()


def record_remix(project_id: str):
    """
    Open browser for recording a remix action.
    """
    config = get_config()
    session_file = config.get_session_file()

    if not session_file.exists():
        console.print("[red]No session found. Run 'python cli.py auth' first.[/red]")
        return 1

    project_url = f"https://lovable.dev/projects/{project_id}"
    output_file = Path("recorded_remix.py")

    console.print(Panel(
        f"[bold yellow]Recording Mode[/bold yellow]\n\n"
        f"A browser will open at:\n{project_url}\n\n"
        f"[bold]Instructions:[/bold]\n"
        f"1. Perform the remix manually (click Settings → Remix → Confirm)\n"
        f"2. Wait for the new project to load\n"
        f"3. Close the browser when done\n\n"
        f"Your actions will be recorded to: {output_file}\n\n"
        f"[dim]Press Ctrl+C to cancel[/dim]",
        title="Playwright Codegen",
        border_style="yellow",
    ))

    input("\nPress Enter to start recording...")

    # Use Playwright codegen with saved session
    cmd = [
        sys.executable, "-m", "playwright", "codegen",
        "--target", "python",
        "--output", str(output_file),
        "--load-storage", str(session_file),
        project_url,
    ]

    console.print(f"\n[blue]Starting Playwright codegen...[/blue]")
    console.print(f"[dim]Command: {' '.join(cmd)}[/dim]\n")

    try:
        result = subprocess.run(cmd)

        if output_file.exists():
            console.print(Panel(
                f"[green bold]Recording saved![/green bold]\n\n"
                f"File: {output_file}\n\n"
                f"Review the generated code and we can use it\n"
                f"to create reliable automation.",
                title="Success",
                border_style="green",
            ))

            # Show the generated code
            console.print("\n[bold]Generated code:[/bold]")
            console.print(output_file.read_text())
        else:
            console.print("[yellow]No recording saved (browser closed without actions?)[/yellow]")

        return result.returncode

    except KeyboardInterrupt:
        console.print("\n[yellow]Recording cancelled[/yellow]")
        return 1
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        config = get_config()
        project_id = config.project_id
        if not project_id:
            console.print("Usage: python record_remix.py <project_id>")
            console.print("Or set LOVABLE_PROJECT_ID in .env")
            sys.exit(1)
    else:
        project_id = sys.argv[1]

    sys.exit(record_remix(project_id))
