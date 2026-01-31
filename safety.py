"""
Safety mechanisms for Lovable automation.

Implements:
1. Rate limiting - prevents request spam
2. Request counting - tracks and warns on excessive usage
3. Circuit breaker - stops after repeated failures
4. Idempotency - prevents duplicate operations
5. Confirmation prompts - requires explicit user consent
6. Audit logging - records all operations for review
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from functools import wraps
from rich.console import Console
from rich.panel import Panel

console = Console()


# =============================================================================
# Configuration Constants - Tuned for safety
# =============================================================================

# Rate limiting
MIN_REQUEST_INTERVAL_SECONDS = 2.0  # Minimum time between API requests
MAX_REQUESTS_PER_MINUTE = 10  # Hard limit on requests per minute
MAX_REQUESTS_PER_HOUR = 60  # Hard limit on requests per hour

# Circuit breaker
MAX_CONSECUTIVE_FAILURES = 3  # Stop after this many failures
CIRCUIT_BREAKER_RESET_MINUTES = 15  # Wait this long before retrying after circuit break

# Retry settings
MAX_RETRIES = 2  # Maximum retry attempts
RETRY_BACKOFF_BASE = 2.0  # Exponential backoff base (seconds)
RETRY_BACKOFF_MAX = 30.0  # Maximum backoff delay

# Session limits
MAX_OPERATIONS_PER_SESSION = 10  # Warn after this many operations
MAX_REMIXES_PER_DAY = 20  # Hard limit on daily remixes


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RequestLog:
    """Log entry for a single request."""
    timestamp: str
    operation: str
    endpoint: str
    success: bool
    error: Optional[str] = None
    response_code: Optional[int] = None


@dataclass
class SafetyState:
    """Persistent safety state across sessions."""
    requests_today: int = 0
    remixes_today: int = 0
    last_request_time: Optional[str] = None
    consecutive_failures: int = 0
    circuit_breaker_until: Optional[str] = None
    last_reset_date: str = ""
    request_log: list = field(default_factory=list)
    remix_history: Dict[str, str] = field(default_factory=dict)  # project_id -> remix_id

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SafetyState":
        return cls(**data)


# =============================================================================
# Safety Manager
# =============================================================================

class SafetyManager:
    """
    Manages all safety mechanisms for the automation.

    This class is the gatekeeper for all operations - it must approve
    every action before it's executed.
    """

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or Path("session_state/safety_state.json")
        self.state = self._load_state()
        self._check_daily_reset()

    def _load_state(self) -> SafetyState:
        """Load safety state from file."""
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                return SafetyState.from_dict(data)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load safety state: {e}[/yellow]")
        return SafetyState()

    def _save_state(self) -> None:
        """Persist safety state to file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state.to_dict(), indent=2))

    def _check_daily_reset(self) -> None:
        """Reset daily counters if it's a new day."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.state.last_reset_date != today:
            console.print(f"[dim]New day detected, resetting daily counters[/dim]")
            self.state.requests_today = 0
            self.state.remixes_today = 0
            self.state.last_reset_date = today
            self.state.request_log = []  # Clear old logs
            self._save_state()

    def _log_request(self, operation: str, endpoint: str, success: bool,
                     error: Optional[str] = None, response_code: Optional[int] = None) -> None:
        """Log a request for audit purposes."""
        log_entry = RequestLog(
            timestamp=datetime.now().isoformat(),
            operation=operation,
            endpoint=endpoint,
            success=success,
            error=error,
            response_code=response_code,
        )
        self.state.request_log.append(asdict(log_entry))

        # Keep only last 100 log entries
        if len(self.state.request_log) > 100:
            self.state.request_log = self.state.request_log[-100:]

        self._save_state()

    # =========================================================================
    # Safety Checks
    # =========================================================================

    def check_rate_limit(self) -> tuple[bool, str]:
        """
        Check if we're within rate limits.

        Returns:
            Tuple of (allowed, reason)
        """
        now = datetime.now()

        # Check minimum interval
        if self.state.last_request_time:
            last_time = datetime.fromisoformat(self.state.last_request_time)
            elapsed = (now - last_time).total_seconds()
            if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
                wait_time = MIN_REQUEST_INTERVAL_SECONDS - elapsed
                return False, f"Rate limit: wait {wait_time:.1f}s before next request"

        # Check hourly limit
        if self.state.requests_today >= MAX_REQUESTS_PER_HOUR:
            return False, f"Hourly limit reached ({MAX_REQUESTS_PER_HOUR} requests)"

        return True, ""

    def check_circuit_breaker(self) -> tuple[bool, str]:
        """
        Check if circuit breaker is tripped.

        Returns:
            Tuple of (allowed, reason)
        """
        if self.state.circuit_breaker_until:
            reset_time = datetime.fromisoformat(self.state.circuit_breaker_until)
            if datetime.now() < reset_time:
                remaining = (reset_time - datetime.now()).total_seconds() / 60
                return False, f"Circuit breaker active: {remaining:.1f} minutes until reset"
            else:
                # Reset circuit breaker
                self.state.circuit_breaker_until = None
                self.state.consecutive_failures = 0
                self._save_state()

        return True, ""

    def check_daily_limits(self, operation: str) -> tuple[bool, str]:
        """
        Check daily operation limits.

        Returns:
            Tuple of (allowed, reason)
        """
        if operation == "remix" and self.state.remixes_today >= MAX_REMIXES_PER_DAY:
            return False, f"Daily remix limit reached ({MAX_REMIXES_PER_DAY})"

        return True, ""

    def check_idempotency(self, operation: str, project_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if operation was already performed.

        Returns:
            Tuple of (is_new, existing_result_id)
        """
        if operation == "remix":
            existing = self.state.remix_history.get(project_id)
            if existing:
                return False, existing

        return True, None

    # =========================================================================
    # Pre-Operation Gate
    # =========================================================================

    def pre_operation_check(self, operation: str, project_id: Optional[str] = None,
                            skip_confirmation: bool = False) -> tuple[bool, str]:
        """
        Comprehensive pre-operation safety check.

        This is the main gate that must be passed before any operation.

        Returns:
            Tuple of (allowed, reason_or_warning)
        """
        # Check circuit breaker first
        allowed, reason = self.check_circuit_breaker()
        if not allowed:
            return False, reason

        # Wait for rate limit (instead of blocking, we wait)
        # This provides smoother UX while still enforcing the limit
        self.wait_for_rate_limit()

        # Check daily limits
        allowed, reason = self.check_daily_limits(operation)
        if not allowed:
            return False, reason

        # Check idempotency for remix operations
        if operation == "remix" and project_id:
            is_new, existing_id = self.check_idempotency(operation, project_id)
            if not is_new:
                console.print(Panel(
                    f"[yellow]This project was already remixed in this session.[/yellow]\n\n"
                    f"Existing remix ID: {existing_id}\n\n"
                    "To create another remix, use --force flag.",
                    title="Idempotency Check",
                    border_style="yellow",
                ))
                return False, f"Already remixed: {existing_id}"

        # Warn if approaching limits
        if self.state.requests_today >= MAX_OPERATIONS_PER_SESSION:
            console.print(f"[yellow]Warning: {self.state.requests_today} operations this session[/yellow]")

        # Request confirmation for remix operations
        if operation == "remix" and not skip_confirmation:
            console.print(Panel(
                f"[bold]Confirm Remix Operation[/bold]\n\n"
                f"Project ID: {project_id}\n"
                f"Remixes today: {self.state.remixes_today}/{MAX_REMIXES_PER_DAY}\n"
                f"Requests today: {self.state.requests_today}",
                title="Confirmation Required",
                border_style="blue",
            ))
            response = console.input("[bold]Proceed with remix? (yes/no): [/bold]")
            if response.lower() not in ("yes", "y"):
                return False, "User declined"

        return True, ""

    # =========================================================================
    # Post-Operation Handlers
    # =========================================================================

    def record_request(self, operation: str, endpoint: str, success: bool,
                       error: Optional[str] = None, response_code: Optional[int] = None) -> None:
        """Record a completed request."""
        self.state.requests_today += 1
        self.state.last_request_time = datetime.now().isoformat()

        if success:
            self.state.consecutive_failures = 0
        else:
            self.state.consecutive_failures += 1

            # Trip circuit breaker if too many failures
            if self.state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                reset_time = datetime.now() + timedelta(minutes=CIRCUIT_BREAKER_RESET_MINUTES)
                self.state.circuit_breaker_until = reset_time.isoformat()
                console.print(Panel(
                    f"[red bold]Circuit Breaker Tripped[/red bold]\n\n"
                    f"{MAX_CONSECUTIVE_FAILURES} consecutive failures detected.\n"
                    f"Operations paused until: {reset_time.strftime('%H:%M:%S')}\n\n"
                    "This prevents potential issues with the Lovable service.",
                    title="Safety Stop",
                    border_style="red",
                ))

        self._log_request(operation, endpoint, success, error, response_code)
        self._save_state()

    def record_remix_success(self, source_project_id: str, new_project_id: str) -> None:
        """Record a successful remix for idempotency."""
        self.state.remixes_today += 1
        self.state.remix_history[source_project_id] = new_project_id
        self._save_state()

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def wait_for_rate_limit(self) -> None:
        """Wait until rate limit allows next request."""
        if self.state.last_request_time:
            last_time = datetime.fromisoformat(self.state.last_request_time)
            elapsed = (datetime.now() - last_time).total_seconds()
            if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
                wait_time = MIN_REQUEST_INTERVAL_SECONDS - elapsed
                console.print(f"[dim]Rate limiting: waiting {wait_time:.1f}s...[/dim]")
                time.sleep(wait_time)

    def get_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay for retries."""
        delay = min(RETRY_BACKOFF_BASE ** attempt, RETRY_BACKOFF_MAX)
        return delay

    def should_retry(self, attempt: int, error: Optional[str] = None) -> bool:
        """Determine if operation should be retried."""
        if attempt >= MAX_RETRIES:
            return False

        # Don't retry on certain errors
        if error:
            no_retry_errors = ["403", "401", "404", "already remixed", "supabase"]
            if any(e in error.lower() for e in no_retry_errors):
                return False

        return True

    def print_status(self) -> None:
        """Print current safety status."""
        console.print(Panel(
            f"[bold]Safety Status[/bold]\n\n"
            f"Requests today: {self.state.requests_today}/{MAX_REQUESTS_PER_HOUR}\n"
            f"Remixes today: {self.state.remixes_today}/{MAX_REMIXES_PER_DAY}\n"
            f"Consecutive failures: {self.state.consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}\n"
            f"Circuit breaker: {'ACTIVE' if self.state.circuit_breaker_until else 'OK'}",
            title="Safety Dashboard",
            border_style="green" if self.state.consecutive_failures == 0 else "yellow",
        ))


# =============================================================================
# Decorator for Safe Operations
# =============================================================================

def safe_operation(operation_name: str):
    """
    Decorator that wraps operations with safety checks.

    Usage:
        @safe_operation("remix")
        def create_remix(project_id: str) -> Result:
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            safety = SafetyManager()

            # Extract project_id from args/kwargs if present
            project_id = kwargs.get("project_id") or (args[0] if args else None)
            skip_confirm = kwargs.get("skip_confirmation", False)

            # Pre-operation check
            allowed, reason = safety.pre_operation_check(
                operation_name,
                project_id=project_id,
                skip_confirmation=skip_confirm,
            )

            if not allowed:
                console.print(f"[red]Operation blocked: {reason}[/red]")
                return None

            # Wait for rate limit
            safety.wait_for_rate_limit()

            # Execute operation with retry logic
            last_error = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    result = func(*args, **kwargs)

                    # Determine success from result
                    success = result is not None and getattr(result, "success", True)
                    error = getattr(result, "error", None) if result else "No result"

                    safety.record_request(
                        operation_name,
                        f"/{operation_name}",
                        success,
                        error=error,
                    )

                    if success and operation_name == "remix" and result:
                        safety.record_remix_success(
                            project_id,
                            getattr(result, "project_id", "unknown"),
                        )

                    return result

                except Exception as e:
                    last_error = str(e)
                    safety.record_request(operation_name, f"/{operation_name}", False, error=last_error)

                    if safety.should_retry(attempt, last_error):
                        delay = safety.get_retry_delay(attempt)
                        console.print(f"[yellow]Retry {attempt + 1}/{MAX_RETRIES} after {delay:.1f}s...[/yellow]")
                        time.sleep(delay)
                    else:
                        break

            console.print(f"[red]Operation failed after {MAX_RETRIES + 1} attempts: {last_error}[/red]")
            return None

        return wrapper
    return decorator


# =============================================================================
# Global Safety Instance
# =============================================================================

_safety_manager: Optional[SafetyManager] = None


def get_safety_manager() -> SafetyManager:
    """Get or create the global safety manager."""
    global _safety_manager
    if _safety_manager is None:
        _safety_manager = SafetyManager()
    return _safety_manager
