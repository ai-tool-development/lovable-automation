#!/bin/bash
# Setup script for Lovable Remix Automation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================="
echo "Lovable Remix Automation Setup"
echo "=================================="

# Check Python version
echo ""
echo "Checking Python version..."
python3 --version

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ -d ".venv" ]; then
    echo "Virtual environment already exists, skipping..."
else
    python3 -m venv .venv
    echo "Virtual environment created."
fi

# Activate and install dependencies
echo ""
echo "Installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright browsers
echo ""
echo "Installing Playwright browsers..."
playwright install chromium

# Create .env from example if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your Lovable credentials."
fi

# Create directories
mkdir -p session_state
mkdir -p results

echo ""
echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Edit .env with your Lovable credentials"
echo "2. Run: source .venv/bin/activate"
echo "3. Run: python cli.py auth"
echo "4. Run: python cli.py remix <project_id>"
echo ""
