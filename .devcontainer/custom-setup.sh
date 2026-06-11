#!/usr/bin/env bash
# .devcontainer/custom-setup.sh — project-specific hook, runs on every container attach
uv run pre-commit install --install-hooks
