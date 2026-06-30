#!/usr/bin/env bash
set -euo pipefail

# Bump version (patch by default: 1.0.0 -> 1.0.1)
# Usage: ./bump-version.sh [major|minor|patch]
PART="${1:-patch}"

VERSION_FILE="backend/app/__init__.py"
CURRENT=$(sed -n "s/^__version__ = \"\(.*\)\"/\1/p" "$VERSION_FILE")
IFS='.' read -r MAJ MIN PATCH <<< "$CURRENT"

case "$PART" in
  major) MAJ=$((MAJ+1)); MIN=0; PATCH=0 ;;
  minor) MIN=$((MIN+1)); PATCH=0 ;;
  patch) PATCH=$((PATCH+1)) ;;
  *) echo "Usage: $0 [major|minor|patch]"; exit 1 ;;
esac

NEW="$MAJ.$MIN.$PATCH"
sed -i "s/^__version__ = \".*\"/__version__ = \"$NEW\"/" "$VERSION_FILE"

echo "$CURRENT -> $NEW"

# Build frontend
cd frontend && npm run build --silent

# Copy to backend
rm -rf ../backend/dist && cp -r dist ../backend/dist

# Restart service
sudo systemctl restart cookidoo-api

echo "v$NEW deployed"
