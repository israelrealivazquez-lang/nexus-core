#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip

if [ -f requirements_cloud.txt ]; then
  python -m pip install -r requirements_cloud.txt
fi

if [ -f package.json ]; then
  npm install
fi

gh --version || true
python --version
node --version

echo "NEXUS remote Codespace is ready. Keep heavy parsing here, not on the Lenovo."
