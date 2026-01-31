"""
Lovable API client for remix and other operations.

Safety-aware implementation with:
- Request timeouts
- Rate limiting integration
- Detailed error handling
- Audit logging
"""
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from rich.console import Console

from config import LovableConfig, get_config
from safety import get_safety_manager, SafetyManager

console = Console()

# Request timeout (seconds) - prevents hanging
REQUEST_TIMEOUT = 30


@dataclass
class RemixResult:
    """Result of a remix operation."""
    success: bool
    project_id: Optional[str] = None
    project_url: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    response_code: Optional[int] = None


@dataclass
class Project:
    """Lovable project information."""
    id: str
    name: str
    url: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LovableAPI:
    """
    Client for Lovable API operations.

    All operations are safety-checked before execution.
    """

    BASE_URL = "https://api.lovable.dev"

    def __init__(
        self,
        bearer_token: str,
        config: Optional[LovableConfig] = None,
        safety: Optional[SafetyManager] = None,
    ):
        self.bearer_token = bearer_token
        self.config = config or get_config()
        self.safety = safety or get_safety_manager()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Add user-agent to be transparent about automation
            "User-Agent": "LovableAutomation/1.0 (https://github.com/regassist-lovable)",
        })

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        operation_name: str = "api_request",
    ) -> requests.Response:
        """
        Make an authenticated request to the Lovable API.

        Includes safety checks and rate limiting.
        """
        url = f"{self.BASE_URL}{endpoint}"

        # Wait for rate limit before request
        self.safety.wait_for_rate_limit()

        console.print(f"[dim]→ {method} {url}[/dim]")

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            console.print(f"[dim]← {response.status_code}[/dim]")

            # Record the request
            self.safety.record_request(
                operation=operation_name,
                endpoint=endpoint,
                success=response.status_code in (200, 201),
                response_code=response.status_code,
            )

            return response

        except requests.Timeout:
            error_msg = f"Request timeout after {REQUEST_TIMEOUT}s"
            console.print(f"[red]✗ {error_msg}[/red]")
            self.safety.record_request(
                operation=operation_name,
                endpoint=endpoint,
                success=False,
                error=error_msg,
            )
            raise

        except requests.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            console.print(f"[red]✗ {error_msg}[/red]")
            self.safety.record_request(
                operation=operation_name,
                endpoint=endpoint,
                success=False,
                error=error_msg,
            )
            raise

    def remix_project(
        self,
        project_id: str,
        include_history: bool = False,
        skip_confirmation: bool = False,
    ) -> RemixResult:
        """
        Create a remix of an existing project.

        This operation:
        1. Checks safety limits (rate, daily, circuit breaker)
        2. Checks idempotency (was this already remixed?)
        3. Requests user confirmation (unless skipped)
        4. Executes the remix
        5. Records the result

        Args:
            project_id: The ID of the project to remix
            include_history: Whether to include edit history in the remix
            skip_confirmation: Skip the confirmation prompt

        Returns:
            RemixResult with the new project details or error
        """
        # Pre-operation safety check
        allowed, reason = self.safety.pre_operation_check(
            operation="remix",
            project_id=project_id,
            skip_confirmation=skip_confirmation,
        )

        if not allowed:
            return RemixResult(
                success=False,
                error=f"Operation blocked: {reason}",
            )

        console.print(f"[blue]Creating remix of project: {project_id}[/blue]")

        try:
            response = self._request(
                method="POST",
                endpoint=f"/projects/{project_id}/remix",
                data={"include_history": str(include_history).lower()},
                operation_name="remix",
            )

            if response.status_code in (200, 201):
                data = response.json()
                console.print(f"[green]✓ Remix created successfully![/green]")
                console.print(f"[dim]Response: {data}[/dim]")

                # Extract project info from response
                # Note: Response structure may vary
                new_project_id = data.get("id") or data.get("project_id") or data.get("projectId")

                # Record successful remix for idempotency
                if new_project_id:
                    self.safety.record_remix_success(project_id, new_project_id)

                return RemixResult(
                    success=True,
                    project_id=new_project_id,
                    project_url=f"https://lovable.dev/projects/{new_project_id}" if new_project_id else None,
                    raw_response=data,
                    response_code=response.status_code,
                )
            else:
                error_msg = f"Remix failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = f"{error_msg}: {error_data}"
                except:
                    error_msg = f"{error_msg}: {response.text}"

                console.print(f"[red]✗ {error_msg}[/red]")
                return RemixResult(
                    success=False,
                    error=error_msg,
                    raw_response={"status": response.status_code, "text": response.text},
                    response_code=response.status_code,
                )

        except Exception as e:
            error_msg = f"Remix request failed: {str(e)}"
            console.print(f"[red]✗ {error_msg}[/red]")
            return RemixResult(success=False, error=error_msg)

    def list_projects(self) -> List[Project]:
        """
        List all projects for the authenticated user.

        Note: This endpoint is undocumented and may not exist.
        """
        # Simple rate limit check (not a critical operation)
        self.safety.wait_for_rate_limit()

        console.print("[blue]Listing projects...[/blue]")

        try:
            response = self._request(
                method="GET",
                endpoint="/projects",
                operation_name="list_projects",
            )

            if response.status_code == 200:
                data = response.json()
                projects = []

                # Handle different response structures
                items = data if isinstance(data, list) else data.get("projects", data.get("items", []))

                for item in items:
                    projects.append(Project(
                        id=item.get("id", ""),
                        name=item.get("name", "Unnamed"),
                        url=f"https://lovable.dev/projects/{item.get('id', '')}",
                        created_at=item.get("created_at") or item.get("createdAt"),
                        updated_at=item.get("updated_at") or item.get("updatedAt"),
                    ))

                console.print(f"[green]✓ Found {len(projects)} projects[/green]")
                return projects
            else:
                console.print(f"[red]✗ Failed to list projects: {response.status_code}[/red]")
                return []

        except Exception as e:
            console.print(f"[red]✗ Error listing projects: {e}[/red]")
            return []

    def get_project(self, project_id: str) -> Optional[Project]:
        """
        Get details for a specific project.

        Note: This endpoint is undocumented and may not exist.
        """
        self.safety.wait_for_rate_limit()

        console.print(f"[blue]Getting project: {project_id}[/blue]")

        try:
            response = self._request(
                method="GET",
                endpoint=f"/projects/{project_id}",
                operation_name="get_project",
            )

            if response.status_code == 200:
                data = response.json()
                return Project(
                    id=data.get("id", project_id),
                    name=data.get("name", "Unnamed"),
                    url=f"https://lovable.dev/projects/{project_id}",
                    created_at=data.get("created_at") or data.get("createdAt"),
                    updated_at=data.get("updated_at") or data.get("updatedAt"),
                )
            else:
                console.print(f"[yellow]Could not get project details: {response.status_code}[/yellow]")
                return None

        except Exception as e:
            console.print(f"[red]✗ Error getting project: {e}[/red]")
            return None

    def probe_endpoints(self, limit: int = 6) -> Dict[str, Any]:
        """
        Probe various potential API endpoints to discover available functionality.

        This is for research/experimentation purposes.
        Limited to prevent excessive requests.
        """
        console.print("[blue]Probing API endpoints...[/blue]")
        console.print(f"[dim]Limited to {limit} endpoints for safety[/dim]")

        endpoints_to_try = [
            ("GET", "/me"),
            ("GET", "/user"),
            ("GET", "/profile"),
            ("GET", "/projects"),
            ("GET", "/workspaces"),
            ("GET", "/account"),
        ][:limit]  # Limit number of probes

        results = {}

        for method, endpoint in endpoints_to_try:
            # Rate limit between probes
            self.safety.wait_for_rate_limit()

            try:
                response = self._request(
                    method,
                    endpoint,
                    operation_name="probe",
                )
                results[endpoint] = {
                    "status": response.status_code,
                    "success": response.status_code == 200,
                    "data": response.json() if response.status_code == 200 else None,
                }
            except Exception as e:
                results[endpoint] = {
                    "status": "error",
                    "error": str(e),
                }

        return results


if __name__ == "__main__":
    # Test API client
    from auth import get_or_refresh_token

    token, error = get_or_refresh_token()
    if error:
        console.print(f"[red]Auth error: {error}[/red]")
    else:
        api = LovableAPI(token)

        # Show safety status
        api.safety.print_status()

        # Probe endpoints (limited)
        results = api.probe_endpoints(limit=3)
        for endpoint, result in results.items():
            status = "✓" if result.get("success") else "✗"
            console.print(f"{status} {endpoint}: {result.get('status')}")
