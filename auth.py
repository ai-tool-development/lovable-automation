"""
Playwright-based authentication for Lovable.

Handles:
1. Automated login flow (email/password - two-step)
2. Bearer token extraction from network requests
3. Session persistence for reuse
"""
import json
import time
from pathlib import Path
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from rich.console import Console
from rich.panel import Panel

from config import LovableConfig, get_config

console = Console()


class LovableAuth:
    """Handles Lovable authentication via Playwright."""

    LOVABLE_URL = "https://lovable.dev"
    LOGIN_URL = "https://lovable.dev/login"
    API_BASE = "https://api.lovable.dev"

    def __init__(self, config: Optional[LovableConfig] = None):
        self.config = config or get_config()
        self.bearer_token: Optional[str] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def _extract_token_from_request(self, request) -> Optional[str]:
        """Extract bearer token from a request's authorization header."""
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return None

    def _setup_request_interceptor(self, page: Page) -> list:
        """Set up request interception to capture bearer tokens."""
        captured_tokens = []

        def handle_request(request):
            # Capture from any authenticated request
            token = self._extract_token_from_request(request)
            if token and token not in captured_tokens:
                captured_tokens.append(token)

        page.on("request", handle_request)
        return captured_tokens

    def login_with_email_password(self) -> Tuple[str, Optional[str]]:
        """
        Perform headless email+password login.

        Two-step flow:
        1. Enter email, click Continue
        2. Enter password, click Log In
        3. Capture token from network requests

        Returns:
            Tuple of (bearer_token, error_message)
        """
        if not self.config.has_credentials():
            return "", "No email/password credentials configured"

        with sync_playwright() as p:
            console.print("[blue]Launching browser...[/blue]")

            browser = p.chromium.launch(
                headless=self.config.headless,
                slow_mo=self.config.slow_mo,
            )

            context = browser.new_context()
            page = context.new_page()
            captured_tokens = self._setup_request_interceptor(page)

            try:
                # Step 1: Navigate to login page
                console.print("[blue]Navigating to login...[/blue]")
                page.goto(self.LOGIN_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                # Step 2: Enter email
                console.print("[blue]Entering email...[/blue]")
                email_input = page.locator('input[type="email"]').first
                email_input.wait_for(state="visible", timeout=10000)
                email_input.fill(self.config.email)

                # Step 3: Click Continue
                continue_btn = page.locator('button:has-text("Continue")').last
                continue_btn.click()
                page.wait_for_timeout(2000)

                # Step 4: Wait for and fill password
                console.print("[blue]Entering password...[/blue]")
                password_input = page.locator('input[type="password"]').first
                password_input.wait_for(state="visible", timeout=10000)
                password_input.fill(self.config.password)

                # Step 5: Click Log In
                login_btn = page.locator('button:has-text("Log in"), button:has-text("Log In"), button[type="submit"]').first
                login_btn.click()

                # Step 6: Wait for redirect (login complete)
                console.print("[blue]Waiting for login to complete...[/blue]")
                page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
                console.print("[green]✓ Login successful![/green]")

                # Step 7: Navigate to projects to ensure we have a token
                page.goto(f"{self.LOVABLE_URL}/projects", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Get the token
                if captured_tokens:
                    self.bearer_token = captured_tokens[0]

                    # Save session for reuse
                    console.print("[blue]Saving session...[/blue]")
                    session_file = self.config.get_session_file()
                    storage_state = context.storage_state()
                    session_file.write_text(json.dumps(storage_state, indent=2))

                    # Save token
                    token_file = self.config.session_dir / "bearer_token.txt"
                    token_file.write_text(self.bearer_token)

                    console.print("[green]✓ Session and token saved![/green]")
                    return self.bearer_token, None
                else:
                    return "", "Login succeeded but no bearer token captured"

            except Exception as e:
                return "", f"Login error: {str(e)}"
            finally:
                browser.close()

    def login_and_extract_token(self) -> Tuple[str, Optional[str]]:
        """
        Perform login and extract bearer token.

        Returns:
            Tuple of (bearer_token, error_message)
        """
        # Check for existing valid session first
        session_file = self.config.get_session_file()
        if session_file.exists():
            console.print("[yellow]Checking existing session...[/yellow]")
            is_valid, token = self._validate_session(session_file)
            if is_valid and token:
                console.print("[green]✓ Existing session is valid![/green]")
                return token, None

        # Need to login
        if self.config.has_credentials():
            return self.login_with_email_password()
        else:
            return "", "No credentials configured. Set LOVABLE_EMAIL and LOVABLE_PASSWORD in .env"

    def _validate_session(self, session_file: Path) -> Tuple[bool, Optional[str]]:
        """Check if saved session is still valid."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(storage_state=str(session_file))
                page = context.new_page()

                captured_tokens = self._setup_request_interceptor(page)

                # Try to access projects page
                page.goto(f"{self.LOVABLE_URL}/projects", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Check if we got redirected to login
                if "/login" in page.url:
                    browser.close()
                    return False, None

                # Check if we captured a token
                if captured_tokens:
                    # Update saved token
                    token_file = self.config.session_dir / "bearer_token.txt"
                    token_file.write_text(captured_tokens[0])
                    browser.close()
                    return True, captured_tokens[0]

                # Check for saved token
                token_file = self.config.session_dir / "bearer_token.txt"
                if token_file.exists():
                    browser.close()
                    return True, token_file.read_text().strip()

                browser.close()
                return False, None

        except Exception as e:
            console.print(f"[yellow]Session validation failed: {e}[/yellow]")
            return False, None

    def _is_logged_in(self, page: Page) -> bool:
        """Check if user is already logged in."""
        try:
            page.wait_for_selector(
                '[data-testid="projects-list"], [href="/projects"], '
                '[aria-label="Create new project"], button:has-text("New project")',
                timeout=3000
            )
            return True
        except:
            return False


def get_or_refresh_token(config: Optional[LovableConfig] = None) -> Tuple[str, Optional[str]]:
    """
    Get a valid bearer token, refreshing if necessary.

    Returns:
        Tuple of (bearer_token, error_message)
    """
    config = config or get_config()

    # Check for saved token
    token_file = config.session_dir / "bearer_token.txt"
    session_file = config.get_session_file()

    if token_file.exists() and session_file.exists():
        saved_token = token_file.read_text().strip()
        if saved_token:
            # Validate the session is still good
            auth = LovableAuth(config)
            is_valid, token = auth._validate_session(session_file)
            if is_valid and token:
                console.print("[green]✓ Using valid saved session[/green]")
                return token, None

    # Check if token provided in config/env
    if config.has_token():
        console.print("[green]Using token from environment[/green]")
        return config.bearer_token, None

    # Need to login
    auth = LovableAuth(config)
    return auth.login_and_extract_token()


if __name__ == "__main__":
    # Test authentication
    token, error = get_or_refresh_token()
    if error:
        console.print(f"[red]Error: {error}[/red]")
    else:
        console.print(f"[green]Token: {token[:20]}...{token[-10:]}[/green]")
