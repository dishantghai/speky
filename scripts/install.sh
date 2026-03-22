#!/usr/bin/env bash
# =============================================================================
# SPEKY Installer
# Downloads and installs the latest speky binary to /usr/local/bin
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/yourusername/speky/main/scripts/install.sh | bash
# =============================================================================

set -e

REPO="dishantghai/speky"
INSTALL_DIR="/usr/local/bin"
BINARY_NAME="speky"

# ── Detect platform ───────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux)
    case "$ARCH" in
      x86_64)  PLATFORM="linux-x86_64" ;;
      aarch64) PLATFORM="linux-arm64" ;;
      *)       echo "Unsupported Linux architecture: $ARCH"; exit 1 ;;
    esac
    ;;
  Darwin)
    case "$ARCH" in
      x86_64)  PLATFORM="macos-x86_64" ;;
      arm64)   PLATFORM="macos-arm64" ;;
      *)       echo "Unsupported macOS architecture: $ARCH"; exit 1 ;;
    esac
    ;;
  *)
    echo "Unsupported OS: $OS"
    echo "Windows users: download speky.exe from https://github.com/$REPO/releases"
    exit 1
    ;;
esac

# ── Get latest release tag ────────────────────────────────────────────────────
echo "Fetching latest speky release..."
LATEST_TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z "$LATEST_TAG" ]; then
  echo "ERROR: Could not fetch latest release. Check your internet connection."
  exit 1
fi

echo "Latest version: $LATEST_TAG"

# ── Download binary ───────────────────────────────────────────────────────────
DOWNLOAD_URL="https://github.com/$REPO/releases/download/$LATEST_TAG/speky-$PLATFORM"
TMP_FILE="$(mktemp)"

echo "Downloading speky for $PLATFORM..."
curl -fsSL "$DOWNLOAD_URL" -o "$TMP_FILE"
chmod +x "$TMP_FILE"

# ── Install ───────────────────────────────────────────────────────────────────
if [ -w "$INSTALL_DIR" ]; then
  mv "$TMP_FILE" "$INSTALL_DIR/$BINARY_NAME"
else
  echo "Installing to $INSTALL_DIR (requires sudo)..."
  sudo mv "$TMP_FILE" "$INSTALL_DIR/$BINARY_NAME"
fi

# ── Verify ────────────────────────────────────────────────────────────────────
echo ""
echo "✓ speky installed to $INSTALL_DIR/$BINARY_NAME"
echo ""
speky status 2>/dev/null || echo "Run 'speky init' to get started."
