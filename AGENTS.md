# Agent Setup Guide

This file helps AI coding agents (Claude Code, Gemini CLI, Cursor, etc.) automatically set up langfuse-oh-my-codex for the user.

## Project Overview

**langfuse-oh-my-codex** traces oh-my-codex (OMX) conversations to Langfuse. It hooks into OMX turn-complete events and sends structured traces including turns, tool calls, reasoning blocks, and token usage.

## Automated Setup Procedure

When a user asks to set up this project, follow these steps:

### Step 1: Check Prerequisites

```bash
# Python 3.8+
python3 --version

# pip available
python3 -m pip --version

# langfuse SDK
python3 -c "import langfuse; print(langfuse.__version__)" 2>/dev/null || echo "Not installed"
```

If langfuse is not installed:
```bash
python3 -m pip install --upgrade langfuse
```

### Step 2: Interview User for Langfuse Credentials

Ask the user for these values. Do NOT guess or use placeholder values.

| Key | Question to Ask | Example Format |
|-----|-----------------|----------------|
| `LANGFUSE_PUBLIC_KEY` | "Langfuse Public Key를 알려주세요" | `pk-lf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `LANGFUSE_SECRET_KEY` | "Langfuse Secret Key를 알려주세요" | `sk-lf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `LANGFUSE_BASE_URL` | "Langfuse URL을 알려주세요 (기본값: https://cloud.langfuse.com)" | `https://cloud.langfuse.com` or self-hosted URL |
| `LANGFUSE_USER_ID` | "트레이스에 표시할 사용자 ID를 알려주세요 (기본값: omx-user)" | Any string |

Get keys from: https://cloud.langfuse.com → Project Settings → API Keys

### Step 3: Install Hook Script

```bash
mkdir -p ~/.omx/hooks
cp langfuse_hook.py ~/.omx/hooks/langfuse_hook.py
chmod +x ~/.omx/hooks/langfuse_hook.py
```

### Step 4: Write Credentials to .env

Write the credentials to `~/.omx/.env`:

```bash
cat > ~/.omx/.env <<EOF
# Langfuse credentials for langfuse-oh-my-codex
# Environment variables take priority over .env values.

TRACE_TO_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=<from interview>
LANGFUSE_SECRET_KEY=<from interview>
LANGFUSE_BASE_URL=<from interview>
LANGFUSE_USER_ID=<from interview>
EOF
```

### Step 5: Verify

```bash
# Check hook file exists
ls -la ~/.omx/hooks/langfuse_hook.py

# Check .env file exists
ls -la ~/.omx/.env

# Check langfuse import works
python3 -c "import langfuse; print('OK')"

# Dry-run test (should exit silently)
echo '{}' | python3 ~/.omx/hooks/langfuse_hook.py
```

### Step 6: Inform User

Tell the user:
- Restart OMX to activate the hook
- Dashboard: the LANGFUSE_BASE_URL they provided
- Credentials: `~/.omx/.env`
- Logs: `~/.omx/hooks/langfuse_hook.log`
- Disable: set `TRACE_TO_LANGFUSE` to `"false"` in .env

## Configuration Hierarchy

Priority (highest first):
1. **Environment variables** (system-level)
2. **~/.omx/.env** (user-level credentials)

## File Paths

| File | Path | Purpose |
|------|------|---------|
| Hook script (source) | `./langfuse_hook.py` | Main hook implementation |
| Hook script (installed) | `~/.omx/hooks/langfuse_hook.py` | Active hook |
| Credentials | `~/.omx/.env` | Langfuse API keys |
| State | `~/.omx/hooks/langfuse_state.json` | Incremental processing offsets |
| Log | `~/.omx/hooks/langfuse_hook.log` | Hook execution log |

## Troubleshooting

- **No traces**: Check `TRACE_TO_LANGFUSE=true` and API keys in `~/.omx/.env`
- **Hook not firing**: Verify the hook script exists at `~/.omx/hooks/langfuse_hook.py`
- **Import error**: Run `python3 -m pip install langfuse`
- **Duplicate traces**: Delete `~/.omx/hooks/langfuse_state.json` for fresh start
