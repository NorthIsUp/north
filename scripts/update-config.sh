#!/bin/bash
# Simple wrapper to update north configuration

cd "$(dirname "$0")/.."
echo "🔄 Updating north package configuration..."
uv run python scripts/update_north_config.py
echo "✨ Done! Run 'uv sync' to apply changes."
