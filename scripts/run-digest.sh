#!/usr/bin/env bash
set -euo pipefail

# systemd does not inherit an interactive shell's API credentials.
source "${HOME}/.ssh/apify.sh"
source "${HOME}/.ssh/openrouter-aura.sh"

cd "$(dirname "$0")/.."
exec "${HOME}/.local/bin/uv" run --frozen python -m yt_digest "$@"
