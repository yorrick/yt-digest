# yt_digest/config.py
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel


class SummarizerConfig(BaseModel):
    primary: str = "notebooklm"
    fallback: str = "claude"


class SlackConfig(BaseModel):
    webhook_url: str


class ClaudeConfig(BaseModel):
    model: str = "claude-sonnet-4-20250514"


class AppConfig(BaseModel):
    summarizer: SummarizerConfig = SummarizerConfig()
    slack: SlackConfig
    claude: ClaudeConfig = ClaudeConfig()
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
