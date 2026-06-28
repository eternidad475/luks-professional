#!/usr/bin/env bash
# CaseFlow GPU Worker — One-shot deploy script
# Usage: bash deploy.sh
set -e

echo "=== CaseFlow Morph GPU Worker Deploy ==="

# 1. Install Modal CLI
pip install modal --quiet

# 2. Authenticate (opens browser on first run)
modal token new

# 3. Create secrets from .env file (first time only)
if [ -f ".env" ]; then
  echo "Creating Modal secret from .env..."
  # Parse key=value pairs and pass them to modal secret create
  modal secret create caseflow-secrets \
    $(grep -v '^#' .env | grep -v '^$' | sed 's/=/ /' | awk '{print "--"$1"="$2}') \
    --force
else
  echo "ERROR: .env file not found. Copy .env.example → .env and fill in values."
  exit 1
fi

# 4. Deploy the Modal app
echo "Deploying to Modal..."
modal deploy modal_morph_app.py

echo ""
echo "✓ Deploy complete!"
echo ""
echo "Your endpoint URL will look like:"
echo "  https://<YOUR_MODAL_USERNAME>--caseflow-morph-web.modal.run"
echo ""
echo "Set this in the CaseFlow HTML:"
echo "  localStorage.setItem('cfGpuEndpoint', 'https://YOUR_URL_HERE')"
echo "  (run this in the browser console at caseflow-studio.vercel.app)"
