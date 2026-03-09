#!/usr/bin/env bash
# One-shot provisioning script for fresh Ubuntu 22.04 ARM64 (Oracle Always Free)
# Run as: bash setup_oracle.sh
set -euo pipefail

BOT_DIR="/home/ubuntu/discchatbot"
VENV_DIR="/home/ubuntu/venv"

echo "=== Updating system packages ==="
sudo apt-get update -y
sudo apt-get upgrade -y

echo "=== Installing system dependencies ==="
sudo apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    libmagic1 \
    git \
    curl

echo "=== Creating Python virtual environment ==="
python3.11 -m venv "$VENV_DIR"
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
sudo cp "$BOT_DIR/systemd/discchatbot.service" /etc/systemd/system/
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
