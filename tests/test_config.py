# tests/test_config.py
from yt_digest.config import load_config


def test_load_config_from_yaml(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
slack:
  webhook_url: ${SLACK_WEBHOOK_URL}

claude:
  model: claude-sonnet-4-20250514

db_path: ~/.yt-digest/data.db
""")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    config = load_config(str(config_file))
    assert config.slack.webhook_url == "https://hooks.slack.com/test"
    assert config.claude.model == "claude-sonnet-4-20250514"


def test_config_env_var_substitution(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
slack:
  webhook_url: ${SLACK_WEBHOOK_URL}

claude:
  model: claude-sonnet-4-20250514

db_path: /tmp/test.db
""")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/replaced")
    config = load_config(str(config_file))
    assert config.slack.webhook_url == "https://hooks.slack.com/replaced"
