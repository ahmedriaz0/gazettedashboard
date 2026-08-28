#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Download and extract Linux Poppler binaries locally into the service
mkdir -p /opt/render/project/src/poppler
cd /tmp
curl -sL https://github.com/oschwartz10612/poppler-windows/releases/download/v24.08.0-0/Release-24.08.0-0.zip -o poppler.zip || true

# Alternatively, download pre-built Ubuntu x86_64 poppler utilities
if ! command -v pdftotext &> /dev/null; then
    echo "Installing Poppler utils via apt-get cache download..."
    apt-get update && apt-get install -y --download-only poppler-utils
    for deb in /var/cache/apt/archives/*.deb; do
        dpkg -x "$deb" /opt/render/project/src/poppler/
    done
fi