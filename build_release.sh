#!/bin/bash

# Ensure we are in the project root first
cd "$(dirname "$0")"

# Configuration — PLUGIN_NAME matches the install directory (must stay "reshadeck_plus")
PLUGIN_NAME="ReshadeckPlus"
# Read version from package.json using node or jq. 
# Using node as it's guaranteed to be present for a node project.
if command -v jq &> /dev/null; then
    VERSION=$(jq -r .version package.json)
else
    # Fallback to node if jq is not available
    VERSION=$(node -p "require('./package.json').version")
fi

if [ -z "$VERSION" ]; then
    echo "Error: Could not determine version from package.json"
    exit 1
fi

AUTHOR="jeanbottein"
ZIP_NAME="${PLUGIN_NAME,,}-${VERSION}.zip"

echo "Starting build process for ${ZIP_NAME}..."

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
# Using cp to copy files (symlinks resolved)
cp -R -L \
    dist \
    shaders \
    textures \
    main.py \
    utils \
    plugin.json \
    package.json \
    LICENSE \
    README.md \
    "$STAGING_DIR"

# Remove source maps and python caches if present
rm -f "$STAGING_DIR/dist/"*.map
find "$STAGING_DIR" -type d -name "__pycache__" -exec rm -rf {} +

# 4. Create the zip file
echo "Creating zip archive..."
current_dir=$(pwd)
cd "$TEMP_DIR"
zip -r "$current_dir/$ZIP_NAME" "$PLUGIN_NAME"
cd "$current_dir"

# 5. Cleanup
echo "Cleaning up..."
rm -rf "$TEMP_DIR"

echo "Build complete! Release file created: ${ZIP_NAME}"
