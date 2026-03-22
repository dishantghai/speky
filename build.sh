#!/usr/bin/env bash
# =============================================================================
# SPEKY Build Script
# Compiles speky.py into a standalone native binary using Nuitka
# Usage: ./build.sh [--version 1.0.0]
# =============================================================================

set -e

VERSION="${1:-$(python3 -c "import re; print(re.search(r'version=\"([^\"]+)\"', open('setup.py').read()).group(1))" 2>/dev/null || echo "0.0.0")}"
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
OUTPUT_NAME="speky"
DIST_DIR="dist"

echo "============================================="
echo " SPEKY Build Pipeline"
echo " Version : $VERSION"
echo " Platform: $PLATFORM-$ARCH"
echo "============================================="

# ── 1. Check dependencies ────────────────────────────────────────────────────
echo ""
echo "[1/4] Checking build dependencies..."

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Please install Python 3.8+."
  exit 1
fi

if ! python3 -c "import nuitka" &>/dev/null; then
  echo "  → Nuitka not found. Installing..."
  pip install nuitka
fi

if ! python3 -c "import ordered_set" &>/dev/null; then
  pip install ordered-set
fi

echo "  ✓ Dependencies OK"

# ── 2. Install runtime deps into a requirements file Nuitka can follow ───────
echo ""
echo "[2/4] Ensuring runtime dependencies are installed..."
pip install -r requirements.txt --quiet
echo "  ✓ Runtime dependencies installed"

# ── 3. Compile with Nuitka ───────────────────────────────────────────────────
echo ""
echo "[3/4] Compiling with Nuitka (this may take a minute)..."

mkdir -p "$DIST_DIR"

python3 -m nuitka \
  --onefile \
  --output-dir="$DIST_DIR" \
  --output-filename="$OUTPUT_NAME" \
  --include-package=anthropic \
  --include-package=dotenv \
  --include-package=requests \
  --follow-imports \
  --assume-yes-for-downloads \
  --remove-output \
  speky.py

echo "  ✓ Compilation complete"

# ── 4. Verify binary ─────────────────────────────────────────────────────────
echo ""
echo "[4/4] Verifying binary..."

BINARY="$DIST_DIR/$OUTPUT_NAME"

if [ ! -f "$BINARY" ]; then
  echo "ERROR: Binary not found at $BINARY"
  exit 1
fi

chmod +x "$BINARY"
"$BINARY" --version 2>/dev/null || "$BINARY" status 2>/dev/null || true

BINARY_SIZE=$(du -sh "$BINARY" | cut -f1)
echo "  ✓ Binary: $BINARY ($BINARY_SIZE)"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "============================================="
echo " Build successful!"
echo " Binary  : $DIST_DIR/$OUTPUT_NAME"
echo " Platform: $PLATFORM-$ARCH"
echo "============================================="
echo ""
echo "To install locally:"
echo "  sudo cp $DIST_DIR/$OUTPUT_NAME /usr/local/bin/speky"
echo ""
echo "To test:"
echo "  ./$DIST_DIR/$OUTPUT_NAME status"
