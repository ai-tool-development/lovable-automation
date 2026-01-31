#!/usr/bin/env python3
"""
UI-based remix using Playwright.

This uses the "Remix this project" menu item which is the simplest flow.

Flow:
1. Navigate to project
2. Click on project header button (opens menu)
3. Click "Remix this project" menu item
4. Handle confirmation dialog (configure history, click Remix)
5. Wait for redirect to new project URL
"""
import re
import time
from typing import Optional
from dataclasses import dataclass
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from rich.console import Console
from rich.panel import Panel

from config import LovableConfig, get_config
from safety import get_safety_manager, SafetyManager

console = Console()

# Timeouts
NAVIGATION_TIMEOUT = 30000  # 30 seconds
ACTION_TIMEOUT = 10000  # 10 seconds
REMIX_CREATION_TIMEOUT = 120000  # 2 minutes


@dataclass
class UIRemixResult:
    """Result of a UI-based remix operation."""
    success: bool
    new_project_id: Optional[str] = None
    new_project_url: Optional[str] = None
    error: Optional[str] = None


def extract_project_id(url: str) -> Optional[str]:
    """Extract project ID from a Lovable URL."""
    match = re.search(r'/projects/([a-f0-9-]+)', url)
    return match.group(1) if match else None


def ui_remix(
    project_id: str,
    include_history: bool = True,
    skip_confirmation: bool = False,
    config: Optional[LovableConfig] = None,
    safety: Optional[SafetyManager] = None,
    debug: bool = False,
) -> Optional[UIRemixResult]:
    """
    Create a remix of a Lovable project via browser UI automation.

    Args:
        project_id: The project to remix
        include_history: Whether to include edit history (default True)
        skip_confirmation: Skip the safety confirmation prompt
        config: Optional config override
        safety: Optional safety manager override
        debug: Enable debug output

    Returns:
        UIRemixResult with new project details, or None if blocked
    """
    config = config or get_config()
    safety = safety or get_safety_manager()

    # Safety check
    allowed, reason = safety.pre_operation_check(
        operation="remix",
        project_id=project_id,
        skip_confirmation=skip_confirmation,
    )

    if not allowed:
        console.print(f"[red]Blocked: {reason}[/red]")
        return None

    console.print(Panel(
        f"[bold]UI-Based Remix[/bold]\n\n"
        f"Project: {project_id}\n"
        f"Include History: {include_history}",
        title="Lovable UI Remix",
        border_style="blue",
    ))

    # Check for session
    session_file = config.get_session_file()
    if not session_file.exists():
        console.print("[red]No session found. Run 'python cli.py auth' first.[/red]")
        return UIRemixResult(success=False, error="No session. Authenticate first.")

    with sync_playwright() as p:
        console.print("[blue]Launching browser...[/blue]")

        browser = p.chromium.launch(
            headless=config.headless,
            slow_mo=config.slow_mo,
        )

        try:
            # Load saved session
            context = browser.new_context(storage_state=str(session_file))
            console.print("[green]✓ Loaded saved session[/green]")

            page = context.new_page()
            page.set_default_timeout(ACTION_TIMEOUT)

            # Step 1: Navigate to project
            console.print(f"[blue]Step 1: Navigating to project...[/blue]")
            page.goto(
                f"https://lovable.dev/projects/{project_id}",
                timeout=NAVIGATION_TIMEOUT,
                wait_until="domcontentloaded"
            )
            # Don't use networkidle - Lovable has continuous websocket connections
            page.wait_for_timeout(3000)
            console.print("[green]✓ Project page loaded[/green]")

            # Step 2: Open project menu
            console.print(f"[blue]Step 2: Opening project menu...[/blue]")
            menu_button = page.locator("button[aria-haspopup='menu']").first
            menu_button.click(timeout=ACTION_TIMEOUT)
            page.wait_for_timeout(500)
            console.print("[green]✓ Menu opened[/green]")

            # Step 3: Click "Remix this project"
            console.print(f"[blue]Step 3: Clicking 'Remix this project'...[/blue]")

            # Find the remix menu item
            menu_items = page.locator("[role='menuitem']").all()
            remix_item = None
            for item in menu_items:
                try:
                    text = item.inner_text(timeout=500).strip().lower()
                    if "remix" in text:
                        remix_item = item
                        break
                except:
                    pass

            if remix_item is None:
                raise PlaywrightTimeout("Could not find 'Remix this project' menu item")

            remix_item.click()
            page.wait_for_timeout(500)
            console.print("[green]✓ Remix menu item clicked[/green]")

            # Step 4: Handle confirmation dialog
            console.print(f"[blue]Step 4: Handling confirmation dialog...[/blue]")

            dialog = page.locator("[role='dialog']")
            if dialog.is_visible(timeout=3000):
                console.print("[green]✓ Dialog appeared[/green]")

                # Configure history toggle if needed
                try:
                    history_switch = page.get_by_role("switch", name="Include project history")
                    if history_switch.is_visible(timeout=1000):
                        current_state = history_switch.get_attribute("aria-checked") == "true"
                        if current_state != include_history:
                            history_switch.click()
                            console.print(f"[green]✓ Toggled history to: {include_history}[/green]")
                        else:
                            console.print(f"[green]✓ History already set to: {include_history}[/green]")
                except:
                    pass  # History toggle may not always be present

                # Click confirm button
                confirm_btn = page.locator("[role='dialog'] button:has-text('Remix')").first
                if confirm_btn.is_visible(timeout=2000):
                    confirm_btn.click()
                    console.print("[green]✓ Confirmed remix[/green]")
            else:
                console.print("[yellow]No dialog - remix may start directly[/yellow]")

            # Step 5: Wait for redirect to new project
            console.print(f"[blue]Step 5: Waiting for new project...[/blue]")

            new_project_id = None

            # Use wait_for_url - this is what worked before
            try:
                page.wait_for_url(
                    re.compile(rf"lovable\.dev/projects/(?!{project_id})([a-f0-9-]+)"),
                    timeout=REMIX_CREATION_TIMEOUT
                )
                new_project_id = extract_project_id(page.url)
                console.print(f"[green]✓ New project detected: {new_project_id}[/green]")
            except PlaywrightTimeout:
                # Check current URL as fallback
                current_url = page.url
                current_id = extract_project_id(current_url)
                if current_id and current_id != project_id:
                    new_project_id = current_id
                    console.print(f"[green]✓ Found new project: {new_project_id}[/green]")

            if new_project_id:
                new_project_url = f"https://lovable.dev/projects/{new_project_id}"

                # Record success
                safety.record_remix_success(project_id, new_project_id)
                safety.record_request("ui_remix", "/ui/remix", True)

                console.print(Panel(
                    f"[green bold]✓ Remix Created Successfully![/green bold]\n\n"
                    f"[bold]New Project ID:[/bold] {new_project_id}\n"
                    f"[bold]URL:[/bold] {new_project_url}",
                    title="Success",
                    border_style="green",
                ))

                return UIRemixResult(
                    success=True,
                    new_project_id=new_project_id,
                    new_project_url=new_project_url,
                )
            else:
                error = "Timeout waiting for remix to complete"
                safety.record_request("ui_remix", "/ui/remix", False, error=error)
                return UIRemixResult(success=False, error=error)

        except PlaywrightTimeout as e:
            error_msg = f"Timeout: {str(e)}"
            console.print(f"[red]✗ {error_msg}[/red]")
            safety.record_request("ui_remix", "/ui/remix", False, error=error_msg)
            return UIRemixResult(success=False, error=error_msg)

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            console.print(f"[red]✗ {error_msg}[/red]")
            safety.record_request("ui_remix", "/ui/remix", False, error=error_msg)
            return UIRemixResult(success=False, error=error_msg)

        finally:
            page.wait_for_timeout(2000)  # Brief pause before closing
            context.close()
            browser.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Remix a Lovable project via UI automation")
    parser.add_argument("project_id", nargs="?", help="Project ID to remix")
    parser.add_argument("--no-history", action="store_true", help="Don't include edit history")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    config = get_config()
    project_id = args.project_id or config.project_id

    if not project_id:
        console.print("[red]Error: No project ID provided[/red]")
        console.print("Usage: python ui_remix.py <project_id>")
        exit(1)

    result = ui_remix(
        project_id,
        include_history=not args.no_history,
        skip_confirmation=args.yes,
        debug=args.debug,
    )

    exit(0 if result and result.success else 1)
