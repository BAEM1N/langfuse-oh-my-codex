# Progress (2026-02-25)

## Completed
- Langfuse OMX hook implemented and synced to runtime hook path.
- Millisecond ordering guard for spans added.
- `OMX_LANGFUSE_INCLUDE_TURN_CONTEXT_SPANS` toggle added for turn-context noise control.
- Repository cleanup checked (no unnecessary tracked/untracked artifacts).

## Verified
- Hook syntax checks passed (`py_compile`).
- Recent traces inspected from Langfuse API.
- Ordering/noise checks completed with real traces.
- `v0.0.1` release/tag updated to latest finalization commit.

## Next
- Optional: UI-level final check in Langfuse for long sessions.
