# SPEKY Deployment Guide

speky is compiled into a **standalone native binary** using [Nuitka](https://nuitka.net/). Users get a single executable with no Python required. Source code is not shipped.

---

## How It Works

```
speky.py  →  Nuitka  →  C code  →  native binary (speky / speky.exe)
```

The binary includes the Python runtime and all dependencies baked in. It runs from any directory, operates on the current working directory — exactly like `git` or `npm`.

---

## Local Development Setup

There are two modes for running speky locally — pick based on what you need.

---

### Mode 1 — Quick Iteration (live source, no build)

Best for active development. Changes to `speky.py` are reflected instantly.

Add the alias to your shell config (one-time):

```bash
echo 'alias speky-dev="python3 /Users/Shared/ALL_WORKSPACE/projects/speky/speky.py"' >> ~/.zshrc
source ~/.zshrc
```

Then from any folder:

```bash
speky-dev status
speky-dev init "My product idea"
```

---

### Mode 2 — Local Binary Install (test the compiled experience)

Best for testing exactly what end users will get.

#### Prerequisites

- Python 3.8+
- A C compiler (`clang` on macOS — already installed via Xcode CLT, `gcc` on Linux)
- pip

#### One-time setup

```bash
pip install nuitka ordered-set
pip install -r requirements.txt
```

#### Build + Install (one command)

```bash
chmod +x build_and_install.sh
./build_and_install.sh
```

This runs `build.sh` internally, then installs the binary to `/usr/local/bin/speky`.

Output: `dist/speky` (or `dist/speky.exe` on Windows)

Then from any project folder:

```bash
speky status
speky init "My product idea"
```

#### Build only (without installing)

```bash
./build.sh
# binary is at dist/speky
```

---

### Choosing between the two modes

| | `speky-dev` (alias) | `speky` (binary) |
|---|---|---|
| Code used | Live `speky.py` | Snapshot at compile time |
| Picks up code changes | Instantly | Only after rebuilding |
| Matches user experience | No | Yes |
| When to use | Daily development | Pre-release testing |

---

## Releasing a New Version

### Step 1 — Bump the version

Update the version string in `setup.py`:

```python
version="1.0.0",
```

### Step 2 — Commit and tag

```bash
git add setup.py
git commit -m "chore: bump version to v1.0.0"
git tag v1.0.0
git push origin main --tags
```

### Step 3 — GitHub Actions does the rest

Pushing a tag matching `v*.*.*` triggers the **Build & Release** workflow (`.github/workflows/release.yml`), which:

1. Builds the binary on 4 runners in parallel:
   - `ubuntu-latest` → `speky-linux-x86_64`
   - `macos-13` (Intel) → `speky-macos-x86_64`
   - `macos-latest` (Apple Silicon) → `speky-macos-arm64`
   - `windows-latest` → `speky-windows-x86_64.exe`
2. Creates a GitHub Release with all 4 binaries attached
3. Generates install instructions in the release notes

You can monitor the build at: `https://github.com/dishantghai/speky/actions`

---

## User Installation

### One-liner (macOS / Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/dishantghai/speky/main/scripts/install.sh | bash
```

The script:
- Detects the OS and architecture automatically
- Downloads the correct binary from the latest GitHub Release
- Installs it to `/usr/local/bin/speky`

### Manual install

1. Go to `https://github.com/dishantghai/speky/releases/latest`
2. Download the binary for your platform:

| Platform | File |
|---|---|
| macOS Apple Silicon (M1/M2/M3) | `speky-macos-arm64` |
| macOS Intel | `speky-macos-x86_64` |
| Linux x86_64 | `speky-linux-x86_64` |
| Windows | `speky-windows-x86_64.exe` |

3. Make it executable and move to PATH:

```bash
# macOS / Linux
chmod +x speky-macos-arm64
sudo mv speky-macos-arm64 /usr/local/bin/speky

# Windows — rename to speky.exe and place in a folder on your PATH
```

### Verify installation

```bash
speky status
```

---

## CI/CD Workflows

| File | Trigger | Purpose |
|---|---|---|
| `.github/workflows/release.yml` | Push tag `v*.*.*` | Build all platform binaries + create GitHub Release |
| `.github/workflows/build-check.yml` | PR / push to `main` | Verify the binary compiles (catch breakage early) |

---

## Versioning Convention

Follow [Semantic Versioning](https://semver.org/):

| Change | Version bump | Example |
|---|---|---|
| Bug fix | Patch | `1.0.0` → `1.0.1` |
| New feature (backward compatible) | Minor | `1.0.0` → `1.1.0` |
| Breaking change | Major | `1.0.0` → `2.0.0` |

---

## Troubleshooting Builds

**Build fails with `cc not found`**
```bash
# macOS
xcode-select --install

# Ubuntu/Debian
sudo apt-get install gcc
```

**`ModuleNotFoundError` at runtime**
A dependency wasn't bundled. Add it to the `--include-package` flags in `build.sh` and `.github/workflows/release.yml`.

**Binary too large**
Normal — the Python runtime is embedded. Typical size is 15–40 MB. Use `--lto=yes` in the Nuitka flags for smaller output (slower compile).

**First build is slow**
Expected. Nuitka compiles to C first. Subsequent builds use the cache and are faster. On CI each build starts fresh (~3–5 min per platform).
