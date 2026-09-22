# yt_digest/config.py
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class SlackConfig(BaseModel):
    webhook_url: str


class OpenRouterConfig(BaseModel):
    model: str = "deepseek/deepseek-v4.1-flash"
    provider: str = "deepinfra"
    timeout: float = Field(default=90, gt=0)


class ApifyConfig(BaseModel):
    timeout: int = Field(default=120, ge=1, le=300)
    max_charge_usd: float = Field(default=0.05, gt=0)


class AppConfig(BaseModel):
    slack: SlackConfig
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    apify: ApifyConfig = Field(default_factory=ApifyConfig)
    db_path: str = "~/.yt-digest/data.db"


def _substitute_env_vars(text: str) -> str:
    """Replace ${VAR_NAME} with environment variable values."""

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            raise ValueError(f"Environment variable {var_name} is not set")
        return value

    return re.sub(r"\$\{(\w+)\}", replacer, text)


def load_config(config_path: str = "config.yaml") -> AppConfig:
    load_dotenv()
    raw = Path(config_path).read_text()
    substituted = _substitute_env_vars(raw)
    data = yaml.safe_load(substituted)
    config = AppConfig(**data)
    config.db_path = str(Path(config.db_path).expanduser())
    return config
