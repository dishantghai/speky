#!/usr/bin/env bash
# =============================================================================
# SPEKY Build & Install (Local)
# Builds the native binary and installs it to /usr/local/bin
# Use this for local user-level testing of the compiled binary.
#
# Usage: ./build_and_install.sh
# =============================================================================

set -e

# ── Build ─────────────────────────────────────────────────────────────────────
echo "Building speky binary..."
./build.sh

# ── Install ───────────────────────────────────────────────────────────────────
echo ""
echo "Installing to /usr/local/bin/speky (requires sudo)..."
sudo cp dist/speky /usr/local/bin/speky

# ── Verify ────────────────────────────────────────────────────────────────────
echo ""
echo "✓ Installed: $(which speky)"
echo ""
speky status || true
