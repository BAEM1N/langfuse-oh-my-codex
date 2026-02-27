# langfuse-oh-my-codex

[English](README.md) | [한국어](README.ko.md)

Automatic [Langfuse](https://langfuse.com) tracing for [oh-my-codex (OMX)](https://github.com/Yeachan-Heo/oh-my-codex). Every conversation turn, tool call, and model response is captured as structured traces in your Langfuse dashboard -- zero code changes required.

## Status (February 25, 2026)

- Hook pipeline verified on real OMX runs
- Turn traces, tool spans, and token usage confirmed in Langfuse
- Repository cleanup completed (no unnecessary tracked files found)
- `v0.0.1` release/tag refreshed with final docs sync
- Aligned with companion repos:
  - `langfuse-claude-code`
  - `langfuse-gemini-cli`
  - `langfuse-opencode`
- Progress docs: [English](./PROGRESS.md) | [한국어](./PROGRESS.ko.md)

## Features

- **Turn-complete tracing** -- each user prompt + assistant response becomes a Langfuse trace
- **Tool call tracking** -- every tool use is captured with inputs and outputs
- **Reasoning blocks** -- model reasoning is captured as separate spans
- **Token usage** -- input/output/cache token counts are recorded on each generation
- **Cost estimation** -- optional USD cost estimation from env-configured prices
- **Session grouping** -- traces are grouped by OMX session ID
- **Incremental processing** -- only new turns are sent (no duplicates)
- **Fail-open design** -- if anything goes wrong the hook exits silently; OMX is never blocked
- **Cross-platform** -- works on macOS, Linux, and Windows

## Prerequisites

- **oh-my-codex** -- installed and working ([install guide](https://github.com/Yeachan-Heo/oh-my-codex))
- **Python 3.8+** -- with `pip` available (`python3 -m pip --version` or `python -m pip --version` to verify)
- **Langfuse account** -- [cloud.langfuse.com](https://cloud.langfuse.com) (free tier available) or a self-hosted instance

## Quick Start

```bash
# Clone and run the installer
git clone https://github.com/BAEM1N/langfuse-oh-my-codex.git
cd langfuse-oh-my-codex
bash install.sh
```

On Windows (PowerShell):

```powershell
git clone https://github.com/BAEM1N/langfuse-oh-my-codex.git
cd langfuse-oh-my-codex
.\install.ps1
```

The installer will:
1. Check Python 3.8+ is available
2. Install the `langfuse` Python package
3. Copy the hook script to `~/.omx/hooks/`
4. Prompt you for your Langfuse credentials:
   - Public Key (`pk-lf-...`)
   - Secret Key (`sk-lf-...`, masked input)
   - Base URL (defaults to `https://cloud.langfuse.com`)
   - User ID (defaults to `omx-user`)
5. Write credentials to `~/.omx/.env`
6. Verify the installation

## Manual Setup

### 1. Install the langfuse SDK

```bash
pip install langfuse
```

### 2. Copy the hook script

```bash
mkdir -p ~/.omx/hooks
cp langfuse_hook.py ~/.omx/hooks/
chmod +x ~/.omx/hooks/langfuse_hook.py
```

### 3. Configure `~/.omx/.env`

```bash
TRACE_TO_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_USER_ID=your-username
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TRACE_TO_LANGFUSE` | Yes | - | Set to `"true"` to enable tracing |
| `LANGFUSE_PUBLIC_KEY` | Yes | - | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | Yes | - | Langfuse secret key |
| `LANGFUSE_BASE_URL` | No | `https://cloud.langfuse.com` | Langfuse host URL |
| `LANGFUSE_USER_ID` | No | `omx-user` | User ID for trace attribution |
| `LANGFUSE_INCLUDE_AGENT_REASONING` | No | `false` | Include agent reasoning event stream |
| `LANGFUSE_MAX_REASONING_BLOCKS` | No | `200` | Max reasoning blocks per turn |
| `LANGFUSE_PRICE_MAP_JSON` | No | - | JSON map for per-model pricing |

### Cost Estimation

Configure pricing with environment variables:

```bash
LANGFUSE_PRICE_INPUT_PER_1M=2.50
LANGFUSE_PRICE_OUTPUT_PER_1M=10.00
LANGFUSE_PRICE_CACHED_INPUT_PER_1M=0.50
```

Or use a per-model JSON map:

```bash
LANGFUSE_PRICE_MAP_JSON='{"gpt-4o":{"input_per_1m":2.50,"output_per_1m":10.00}}'
```

### Self-hosted Langfuse

Set `LANGFUSE_BASE_URL` to your instance URL:

```
LANGFUSE_BASE_URL=https://langfuse.your-company.com
```

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                   oh-my-codex (OMX)                      │
│                                                          │
│  User prompt ──► Model response ──► Tool calls ──► ...   │
│       │                                                  │
│       ▼                                                  │
│  Codex rollout file (.jsonl)                             │
│       │                                                  │
│       │  ┌── turn-complete ──┐                           │
│       └─►│ langfuse_hook.py  │                           │
│          │                   │                           │
│          │ 1. Read rollout   │                           │
│          │ 2. Build turns    │                           │
│          │ 3. Emit traces    │                           │
│          └───────┬───────────┘                           │
│                  │                                       │
└──────────────────┼───────────────────────────────────────┘
                   │
                   ▼
          ┌─────────────────────┐
          │      Langfuse        │
          │                      │
          │  Trace (Turn 1)      │
          │  ├─ Generation       │
          │  │   ├─ model        │
          │  │   ├─ usage tokens │
          │  │   └─ cost         │
          │  ├─ Reasoning [1]    │
          │  ├─ Tool: search     │
          │  ├─ Tool: read       │
          │  └─ Tool: write      │
          │                      │
          │  Session: abc123     │
          └─────────────────────┘
```

**Flow:**

1. OMX writes conversation data to Codex rollout JSONL files
2. On every **turn-complete** event, the hook reads the rollout
3. The hook reconstructs complete turns from JSONL entries
4. Each turn is emitted as a Langfuse **trace** with:
   - A **generation** observation (with model, token usage, cost)
   - **Reasoning** spans for model thinking blocks
   - **Tool** spans for each tool call (with input/output linkage)
5. Only **new** turns are sent (deduplication via state cache)
6. All traces share the same `session_id` for grouping

## Compatibility

| Component | Version |
|-----------|---------|
| Python | 3.8+ |
| langfuse SDK | 2.0+ |
| oh-my-codex | Any version with hook support |
| OS | macOS, Linux, Windows |

## Troubleshooting

### Traces not appearing

1. Verify `TRACE_TO_LANGFUSE` is set to `"true"`
2. Check that your API keys are correct
3. Check the log file: `~/.omx/hooks/langfuse_hook.log`

### Hook not firing

1. Verify the hook script exists at `~/.omx/hooks/langfuse_hook.py`
2. Check that the OMX hook plugin is configured to call the script
3. Test manually: `echo '{}' | python3 ~/.omx/hooks/langfuse_hook.py` (use `python` instead of `python3` on Windows)

### Duplicate traces

The hook tracks processed turns in `~/.omx/hooks/langfuse_state.json`. If this file is deleted, previously-sent turns will be re-sent on the next invocation. Delete the state file only if you want a fresh start.

## Uninstall

1. Delete the hook script: `rm ~/.omx/hooks/langfuse_hook.py`
2. Remove credentials: `rm ~/.omx/.env`
3. Optionally remove state: `rm ~/.omx/hooks/langfuse_state.json`

## License

[MIT](LICENSE)
