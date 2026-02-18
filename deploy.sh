#!/bin/bash
# deploy.sh — Build and copy plugin files to the Decky homebrew directory

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/homebrew/plugins/Reshadeck"
PLUGIN_NAME="Reshadeck"

# Ensure we are in the project root
cd "$SRC"

echo "Deploying from: $SRC"
echo "Deploying to:   $DEST"

# 1. Build the frontend
echo "Building frontend..."
if ! command -v pnpm &> /dev/null; then
    echo "Error: pnpm is not installed."
    exit 1
fi

pnpm install
pnpm run build

if [ $? -ne 0 ]; then
    echo "Error: Frontend build failed."
    exit 1
fi

# 2. Create a temporary staging directory
TEMP_DIR=$(mktemp -d)
STAGING_DIR="${TEMP_DIR}/${PLUGIN_NAME}"
mkdir -p "$STAGING_DIR"

echo "Staging files..."

# 3. Copy necessary files to the staging directory
# Using cp to copy files (symlinks removed)
cp -r \
    dist \
    shaders \
    textures \
    main.py \
    plugin.json \
    package.json \
    LICENSE \
    README.md \
    "$STAGING_DIR"

# Remove source maps if present
rm -f "$STAGING_DIR/dist/"*.map

# 4. Deploy using rsync
echo "Syncing files to $DEST..."
mkdir -p "$DEST"
rsync -rv --delete "$STAGING_DIR/" "$DEST/"

# 5. Cleanup
echo "Cleaning up..."
rm -rf "$TEMP_DIR"

echo ""
#echo "Deploy complete. Restarting Decky..."
#sudo systemctl restart plugin_loader.service
echo "Done!"
