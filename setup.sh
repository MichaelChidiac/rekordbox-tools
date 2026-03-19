#!/bin/bash
# Install dependencies for rekordbox-tools
set -e

echo "==> Installing Node.js dependencies..."
cd "$(dirname "$0")"
npm install

echo "==> Installing Python dependencies..."
python3.11 -m pip install pyrekordbox --quiet

echo "==> All done."
