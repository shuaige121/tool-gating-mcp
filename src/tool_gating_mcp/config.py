"""Configuration management for Tool Gating MCP"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # API Keys
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-4-sonnet-latest"

    # File paths
    mcp_servers_path: str = "mcp-servers.json"
    api_keys_path: str = ".api-keys.json"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    @property
    def has_anthropic_key(self) -> bool:
        """Check if Anthropic API key is configured"""
        return bool(self.anthropic_api_key)

    def get_api_key(self, service: str) -> str | None:
        """Get API key for a service from environment or secure storage"""
        # First check environment variables
        env_key = f"{service.upper()}_API_KEY"
        if env_value := os.getenv(env_key):
            return env_value

        # Then check API keys file
        api_keys_file = Path(self.api_keys_path)
        if api_keys_file.exists():
            import json

            with open(api_keys_file) as f:
                keys = json.load(f)
                return keys.get(service)

        return None


# Global settings instance
settings = Settings()

# MCP Server Configurations - loaded from mcp-servers.json
def _load_mcp_servers() -> dict:
    import json
    servers_path = Path(settings.mcp_servers_path)
    if servers_path.exists():
        with open(servers_path) as f:
            return json.load(f)
    return {}

MCP_SERVERS = _load_mcp_servers()
