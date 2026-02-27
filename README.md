# langfuse-hook

Automatic [Langfuse](https://langfuse.com) tracing hook for CLI-based AI coding assistants. Every conversation turn, tool call, and model response is captured as structured traces in your Langfuse dashboard.

## Features

- **Turn-complete tracing** -- each user prompt + assistant response becomes a Langfuse trace
- **Tool call tracking** -- every tool use is captured with inputs and outputs
- **Reasoning blocks** -- model reasoning is captured as separate spans
- **Token usage** -- input/output/cache token counts are recorded on each generation
- **Cost estimation** -- optional USD cost estimation from env-configured prices
- **Session grouping** -- traces are grouped by session ID
- **Incremental processing** -- only new turns are sent (no duplicates)
- **Fail-open design** -- if anything goes wrong the hook exits silently; the host process is never blocked
- **Cross-platform** -- works on macOS, Linux, and Windows

## Prerequisites

- **Python 3.8+** -- with `pip` available
- **Langfuse account** -- [cloud.langfuse.com](https://cloud.langfuse.com) (free tier available) or a self-hosted instance

## Setup

### 1. Install the langfuse SDK

```bash
pip install langfuse
```

### 2. Configure environment variables

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_USER_ID=your-username
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY` | Yes | - | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | Yes | - | Langfuse secret key |
| `LANGFUSE_BASE_URL` | No | `https://cloud.langfuse.com` | Langfuse host URL |
| `LANGFUSE_USER_ID` | No | `user` | User ID for trace attribution |
| `LANGFUSE_DEBUG` | No | `false` | Set to `"true"` for verbose logging |
| `LANGFUSE_INCLUDE_AGENT_REASONING` | No | `false` | Include agent reasoning event stream |
| `LANGFUSE_MAX_REASONING_BLOCKS` | No | `200` | Max reasoning blocks per turn |
| `LANGFUSE_PRICE_MAP_JSON` | No | - | JSON map for per-model pricing |

### Cost Estimation

```bash
LANGFUSE_PRICE_INPUT_PER_1M=2.50
LANGFUSE_PRICE_OUTPUT_PER_1M=10.00
LANGFUSE_PRICE_CACHED_INPUT_PER_1M=0.50
```

Or use a per-model JSON map:

```bash
LANGFUSE_PRICE_MAP_JSON='{"gpt-4o":{"input_per_1m":2.50,"output_per_1m":10.00}}'
```

## Compatibility

| Component | Version |
|-----------|---------|
| Python | 3.8+ |
| langfuse SDK | 2.0+ |
| OS | macOS, Linux, Windows |

## License

[MIT](LICENSE)
