#!/usr/bin/env bash
# Provisioning script for Oracle Always Free ARM64 (Ubuntu 22.04 or 24.04)
# Run as: bash scripts/setup_oracle.sh
set -euo pipefail

BOT_DIR="/home/ubuntu/discchatbot"
VENV_DIR="/home/ubuntu/venv"

echo "=== Updating system packages ==="
sudo apt-get update -y

echo "=== Detecting Python version ==="
# Ubuntu 22.04 ships Python 3.10, 24.04 ships Python 3.12
# Find the best available python3 binary
if command -v python3.12 &>/dev/null; then
    PYTHON=python3.12
    PYTHON_VENV_PKG=python3.12-venv
elif command -v python3.11 &>/dev/null; then
    PYTHON=python3.11
    PYTHON_VENV_PKG=python3.11-venv
elif command -v python3.10 &>/dev/null; then
    PYTHON=python3.10
    PYTHON_VENV_PKG=python3.10-venv
else
    PYTHON=python3
    PYTHON_VENV_PKG=python3-venv
fi
echo "Using: $PYTHON"

echo "=== Installing system dependencies ==="
# libmagic1 was renamed to libmagic1t64 on Ubuntu 24.04 - install whichever exists
LIBMAGIC_PKG=libmagic1
if apt-cache show libmagic1t64 &>/dev/null 2>&1; then
    LIBMAGIC_PKG=libmagic1t64
fi

sudo apt-get install -y \
    "$PYTHON_VENV_PKG" \
    python3-pip \
    "$LIBMAGIC_PKG" \
    git \
    curl

echo "=== Creating Python virtual environment ==="
"$PYTHON" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "=== Installing Python dependencies ==="
pip install --upgrade pip
pip install -r "$BOT_DIR/requirements.txt"

echo "=== Creating data directory ==="
mkdir -p "$BOT_DIR/data"
mkdir -p /tmp/discchatbot

echo "=== Setting up .env (copy from example if not present) ==="
if [ ! -f "$BOT_DIR/.env" ]; then
    cp "$BOT_DIR/.env.example" "$BOT_DIR/.env"
    echo ""
    echo "!!! IMPORTANT: Edit $BOT_DIR/.env and add your API keys before starting! !!!"
    echo ""
fi

echo "=== Installing systemd service ==="
# Update the service file to point to the detected venv python
sed "s|/home/ubuntu/venv/bin/python|$VENV_DIR/bin/python|g" \
    "$BOT_DIR/systemd/discchatbot.service" | sudo tee /etc/systemd/system/discchatbot.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable discchatbot

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $BOT_DIR/.env with your API keys"
echo "  2. Start the bot: sudo systemctl start discchatbot"
echo "  3. View logs:     sudo journalctl -u discchatbot -f"
echo ""
