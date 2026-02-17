#!/bin/bash
# deploy.sh — Copy plugin files to the Decky homebrew directory and restart Decky

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/homebrew/plugins/Reshadeck"

echo "Deploying from: $SRC"
echo "Deploying to:   $DEST"

mkdir -p "$DEST"

rsync -avL --delete \
    --exclude='.git/' \
    --exclude='.github/' \
    --exclude='.vscode/' \
    --exclude='.agent/' \
    --exclude='node_modules/' \
    --exclude='.pnpm-store/' \
    --exclude='src/' \
    --exclude='*.log' \
    --exclude='.gitignore' \
    --exclude='.env' \
    --exclude='Makefile' \
    --exclude='build_release.sh' \
    --exclude='deploy.sh' \
    "$SRC/" "$DEST/"

echo ""
#echo "Deploy complete. Restarting Decky..."
#sudo systemctl restart plugin_loader.service
echo "Done!"
