"""
Configuration management for Lovable automation.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv


class LovableConfig(BaseModel):
    """Configuration for Lovable automation."""

    # Authentication
    email: Optional[str] = Field(default=None, description="Lovable account email")
    password: Optional[str] = Field(default=None, description="Lovable account password")
    bearer_token: Optional[str] = Field(default=None, description="Pre-existing bearer token")

    # Project
    project_id: Optional[str] = Field(default=None, description="Lovable project ID to remix")
    project_url: Optional[str] = Field(default=None, description="Full Lovable project URL")

    # Browser settings
    headless: bool = Field(default=False, description="Run browser in headless mode")
    slow_mo: int = Field(default=100, description="Slow down operations by this many ms")

    # Paths
    session_dir: Path = Field(default=Path("session_state"), description="Directory for session storage")

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "LovableConfig":
        """Load configuration from environment variables."""
        if env_file and env_file.exists():
            load_dotenv(env_file)
        else:
            load_dotenv()

        project_url = os.getenv("LOVABLE_PROJECT_URL")
        project_id = os.getenv("LOVABLE_PROJECT_ID")

        # Extract project ID from URL if not provided directly
        if project_url and not project_id:
            # URL format: https://lovable.dev/projects/{project_id}
            parts = project_url.rstrip("/").split("/")
            if "projects" in parts:
                idx = parts.index("projects")
                if idx + 1 < len(parts):
                    project_id = parts[idx + 1]

        return cls(
            email=os.getenv("LOVABLE_EMAIL"),
            password=os.getenv("LOVABLE_PASSWORD"),
            bearer_token=os.getenv("LOVABLE_BEARER_TOKEN"),
            project_id=project_id,
            project_url=project_url,
            headless=os.getenv("HEADLESS", "false").lower() == "true",
            slow_mo=int(os.getenv("SLOW_MO", "100")),
        )

    def has_credentials(self) -> bool:
        """Check if login credentials are available."""
        return bool(self.email and self.password)

    def has_token(self) -> bool:
        """Check if a bearer token is already available."""
        return bool(self.bearer_token)

    def get_session_file(self) -> Path:
        """Get the path to the session state file."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        return self.session_dir / "lovable_session.json"


# Global config instance
_config: Optional[LovableConfig] = None


def get_config() -> LovableConfig:
    """Get or create the global configuration."""
    global _config
    if _config is None:
        _config = LovableConfig.from_env()
    return _config


def set_config(config: LovableConfig) -> None:
    """Set the global configuration."""
    global _config
    _config = config
