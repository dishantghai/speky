# speky — Installation Guide

speky is a CLI tool that turns your product ideas into structured specs, plans, and IDE-ready context — powered by Claude AI.

---

## Prerequisites

- **An AI API key** — speky supports three providers (pick one):
  - **Anthropic Claude** (recommended) — [console.anthropic.com](https://console.anthropic.com)
  - **OpenAI GPT** (1st fallback) — [platform.openai.com](https://platform.openai.com)
  - **Google Gemini** (2nd fallback) — [aistudio.google.com](https://aistudio.google.com)
- **macOS or Linux** (Windows: manual install below)

---

## Install (macOS / Linux — one-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/dishantghai/speky/main/scripts/install.sh | bash
```

This downloads the correct binary for your platform and installs it to `/usr/local/bin/speky`.

---

## Windows — Manual Install

1. Download `speky-windows-x86_64.exe` from [github.com/dishantghai/speky/releases/latest](https://github.com/dishantghai/speky/releases/latest)
2. Rename it to `speky.exe`
3. Move it to a folder on your PATH (e.g. `C:\Windows\System32\` or create `C:\speky\` and add it to PATH)

---

## Optional: Gemini Support

The speky binary includes Anthropic and OpenAI support out of the box. To use Google Gemini as a fallback, install the package once:

```bash
pip install google-generativeai
```

Then set your `GEMINI_API_KEY` as shown below.

---

## Set Your API Key

speky auto-detects which provider to use based on which key is set. Priority: **Anthropic → OpenAI → Gemini**.

Set the key for whichever provider you have:

### macOS / Linux — add to shell profile

```bash
# Anthropic (recommended)
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc

# OR OpenAI
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc

# OR Google Gemini
echo 'export GEMINI_API_KEY="AIza..."' >> ~/.zshrc

source ~/.zshrc   # reload
```

### Per-project — `.env` file

Create a `.env` file in your project root (speky auto-loads it):

```
# Use whichever you have — speky picks the first one set
ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AIza...
```

### Windows

```powershell
# Anthropic
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")

# OR OpenAI
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")

# OR Gemini
[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "AIza...", "User")
```

---

## Verify Install

```bash
speky --help
```

You should see the list of available commands.

---

## Update

Re-run the install script at any time to get the latest version:

```bash
curl -fsSL https://raw.githubusercontent.com/dishantghai/speky/main/scripts/install.sh | bash
```

---

## Uninstall

```bash
sudo rm /usr/local/bin/speky
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `command not found: speky` | Restart your terminal, or run `export PATH="$PATH:/usr/local/bin"` |
| `permission denied` | Run the install with `sudo bash` instead |
| `API key not set` | Check `echo $ANTHROPIC_API_KEY` (or OPENAI / GEMINI) returns your key |
| API errors / 401 | Key is invalid or expired — regenerate at your provider's console |
| macOS "unverified developer" | Run `xattr -d com.apple.quarantine /usr/local/bin/speky` |

---

> Next: see **GUIDE.md** for how to use speky.
