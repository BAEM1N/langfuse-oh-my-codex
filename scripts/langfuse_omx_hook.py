#!/usr/bin/env python3
"""
OMX hook-plugin -> Langfuse bridge (hook-only mode).

Deep observability in hook-only mode:
- turn reconstruction from Codex rollout JSONL
- tool call + output linkage
- token usage extraction from token_count events
- optional USD cost estimation from env-configured prices

Fail-open: any error returns exit code 0.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"


def _as_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            f = float(s)
            return int(f) if f.is_integer() else None
        except Exception:
            return None
    return None


def _compact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if v is None:
            continue
        if isinstance(v, str) and v == "":
            continue
        out[k] = v
    return out


def _truncate_text(text: str, max_chars: int = 20000) -> Tuple[str, Dict[str, Any]]:
    if text is None:
        return "", {"truncated": False, "orig_len": 0}
    orig_len = len(text)
    if orig_len <= max_chars:
        return text, {"truncated": False, "orig_len": orig_len}
    return (
        text[:max_chars],
        {
            "truncated": True,
            "orig_len": orig_len,
            "kept_len": max_chars,
        },
    )


def _json_dumps_safe(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return _as_str(value)


def _parse_iso_ts(value: Any) -> Optional[datetime]:
    s = _as_str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _include_agent_reasoning() -> bool:
    """Whether to include low-level agent_reasoning event stream as spans.

    Default is False because event stream can be very noisy and appear out-of-order
    compared to tool observations in the Langfuse UI.
    """
    raw = os.getenv("OMX_LANGFUSE_INCLUDE_AGENT_REASONING", "").strip().lower()
    if not raw:
        return False
    return raw in ("1", "true", "yes", "on")


def _max_reasoning_blocks() -> int:
    raw = os.getenv("OMX_LANGFUSE_MAX_REASONING_BLOCKS", "200").strip()
    try:
        n = int(raw)
    except Exception:
        return 200
    return max(1, min(n, 500))


def _reasoning_raw_passthrough() -> bool:
    """When true, keep reasoning blocks as-is (including duplicates/order)."""
    raw = os.getenv("OMX_LANGFUSE_REASONING_RAW_PASSTHROUGH", "").strip().lower()
    if not raw:
        return False
    return raw in ("1", "true", "yes", "on")


def _include_turn_context_spans() -> bool:
    """Whether to emit turn_context:* instruction spans."""
    raw = os.getenv("OMX_LANGFUSE_INCLUDE_TURN_CONTEXT_SPANS", "").strip().lower()
    if not raw:
        return True
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Input payload
# ---------------------------------------------------------------------------

def _read_payload() -> Dict[str, Any]:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    if not raw and len(sys.argv) > 1:
        raw = _as_str(sys.argv[1])

    if not raw.strip():
        return {}

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_event_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    input_messages_raw = payload.get("input_messages")
    input_messages: List[str] = []
    if isinstance(input_messages_raw, list):
        input_messages = [_as_str(x) for x in input_messages_raw if _as_str(x)]

    return {
        "timestamp": _as_str(payload.get("timestamp")) or datetime.now(timezone.utc).isoformat(),
        "source": _as_str(payload.get("source")) or "omx-hook-plugin",
        "event": _as_str(payload.get("event")) or "turn-complete",
        "type": _as_str(payload.get("type")) or _as_str(payload.get("event")) or "turn-complete",
        "cwd": _as_str(payload.get("cwd")),
        "session_id": _as_str(payload.get("session_id")),
        "thread_id": _as_str(payload.get("thread_id")),
        "turn_id": _as_str(payload.get("turn_id")),
        "mode": _as_str(payload.get("mode")),
        "input_messages": input_messages,
        "output_message": _as_str(payload.get("output_message")),
    }


# ---------------------------------------------------------------------------
# State (dedupe + rollout path cache)
# ---------------------------------------------------------------------------

@dataclass
class HookState:
    emitted_turns: Dict[str, str] = field(default_factory=dict)  # key -> iso timestamp
    session_rollout: Dict[str, Dict[str, str]] = field(default_factory=dict)  # session_id -> {path, cwd, updated}


def _state_path(cwd: str) -> Path:
    return Path(cwd) / ".omx" / "hooks" / "langfuse_state.json"


def _load_state(cwd: str) -> HookState:
    path = _state_path(cwd)
    if not path.exists():
        return HookState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return HookState(
            emitted_turns=raw.get("emitted_turns", {}) if isinstance(raw, dict) else {},
            session_rollout=raw.get("session_rollout", {}) if isinstance(raw, dict) else {},
        )
    except Exception:
        return HookState()


def _save_state(cwd: str, state: HookState) -> None:
    path = _state_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)

    # prune dedupe cache (keep only recent-ish and bounded size)
    now = datetime.now(timezone.utc)
    pruned: Dict[str, str] = {}
    items = sorted(state.emitted_turns.items(), key=lambda kv: kv[1], reverse=True)
    for key, ts in items:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if now - dt > timedelta(days=3):
                continue
        except Exception:
            pass
        pruned[key] = ts
        if len(pruned) >= 5000:
            break
    state.emitted_turns = pruned

    data = {
        "emitted_turns": state.emitted_turns,
        "session_rollout": state.session_rollout,
        "updated_at": now.isoformat(),
    }

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _dedupe_key(session_id: str, turn_id: str) -> str:
    return f"{session_id}:{turn_id}"


# ---------------------------------------------------------------------------
# Rollout discovery + parsing
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: Any
    timestamp: Optional[str] = None
    output: Optional[str] = None
    seq: Optional[int] = None


@dataclass
class TurnData:
    turn_id: str
    model: Optional[str] = None
    effort: Optional[str] = None
    user_messages: List[str] = field(default_factory=list)
    assistant_messages: List[str] = field(default_factory=list)
    developer_messages: List[str] = field(default_factory=list)
    reasoning: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_output_by_call_id: Dict[str, str] = field(default_factory=dict)
    response_items: List[Dict[str, Any]] = field(default_factory=list)
    token_events: List[Dict[str, Any]] = field(default_factory=list)
    rate_limits: Optional[Dict[str, Any]] = None
    turn_context: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


def _session_dirs(days_back: int = 7) -> List[Path]:
    """
    Return candidate Codex session directories with timezone drift tolerance.

    Rollout paths are date-partitioned by local clock in some environments.
    If we only look at UTC dates, turns near local midnight can be missed.
    """
    base = Path.home() / ".codex" / "sessions"
    dates = set()

    # Consider both UTC and local anchors, and include +1 day tolerance.
    anchors = [datetime.now(timezone.utc), datetime.now()]
    for anchor in anchors:
        for offset in range(-1, max(1, days_back)):
            day = (anchor - timedelta(days=offset)).date()
            dates.add((day.year, day.month, day.day))

    ordered = sorted(dates, reverse=True)
    return [base / f"{y:04d}" / f"{m:02d}" / f"{d:02d}" for (y, m, d) in ordered]


def _read_session_meta(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            first = f.readline().strip()
            if not first:
                return None
            obj = json.loads(first)
            if obj.get("type") != "session_meta":
                return None
            payload = obj.get("payload")
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _find_rollout_file(session_id: str, cwd: str, state: HookState) -> Optional[Path]:
    # 1) cached path
    cached = state.session_rollout.get(session_id)
    if isinstance(cached, dict):
        p = Path(_as_str(cached.get("path")))
        if p.exists():
            return p

    # 2) filename hint (rollout-*<session_id>*.jsonl)
    candidates: List[Path] = []
    for d in _session_dirs(7):
        if not d.exists():
            continue
        candidates.extend(d.glob(f"rollout-*{session_id}*.jsonl"))

    # 3) fallback: recent rollout files and session_meta match
    if not candidates:
        for d in _session_dirs(7):
            if not d.exists():
                continue
            candidates.extend(d.glob("rollout-*.jsonl"))

    # sort newest first
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)

    for path in candidates[:250]:
        meta = _read_session_meta(path)
        if not meta:
            continue
        meta_id = _as_str(meta.get("id"))
        meta_cwd = _as_str(meta.get("cwd"))
        if meta_id == session_id and (not cwd or not meta_cwd or meta_cwd == cwd):
            state.session_rollout[session_id] = {
                "path": str(path),
                "cwd": meta_cwd,
                "updated": datetime.now(timezone.utc).isoformat(),
            }
            return path

    return None


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    parts: List[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item)
                continue
            if not isinstance(item, dict):
                continue

            itype = _as_str(item.get("type")).lower()
            if itype in ("input_text", "output_text", "text"):
                txt = _as_str(item.get("text"))
                if txt.strip():
                    parts.append(txt)
            elif "text" in item:
                txt = _as_str(item.get("text"))
                if txt.strip():
                    parts.append(txt)
    return "\n".join(parts)


def _consume_response_item(turn: TurnData, payload: Dict[str, Any], timestamp: Optional[str], seq: Optional[int] = None) -> None:
    ptype = _as_str(payload.get("type"))
    turn.response_items.append({"type": ptype, "timestamp": timestamp, "seq": seq})

    if ptype == "message":
        role = _as_str(payload.get("role"))
        text = _extract_message_text(payload.get("content"))
        if not text:
            return
        if role == "user":
            turn.user_messages.append(text)
        elif role == "assistant":
            turn.assistant_messages.append(text)
        elif role == "developer":
            turn.developer_messages.append(text)
        return

    if ptype == "function_call":
        turn.tool_calls.append(
            ToolCall(
                call_id=_as_str(payload.get("call_id")),
                name=_as_str(payload.get("name")) or "unknown_tool",
                arguments=payload.get("arguments"),
                timestamp=timestamp,
                seq=seq,
            )
        )
        return

    if ptype == "function_call_output":
        call_id = _as_str(payload.get("call_id"))
        if call_id:
            out = payload.get("output")
            out_text = out if isinstance(out, str) else _json_dumps_safe(out)
            turn.tool_output_by_call_id[call_id] = out_text
        return

    if ptype == "reasoning":
        # Prefer summary text; encrypted blobs are not useful for observability.
        summary = payload.get("summary")
        if isinstance(summary, list):
            for item in summary:
                if isinstance(item, dict):
                    txt = _as_str(item.get("text"))
                    if txt.strip():
                        turn.reasoning.append(
                            {
                                "text": txt,
                                "timestamp": timestamp,
                                "kind": "reasoning_summary",
                                "seq": seq,
                            }
                        )
        return

    # Other call-like items (e.g. web_search_call) are logged as tool-like operations.
    if ptype.endswith("_call") and ptype not in ("function_call",):
        call_id = f"{ptype}:{len(turn.tool_calls) + 1}"
        tool_name = ptype.replace("_call", "")
        arguments = {k: v for k, v in payload.items() if k != "type"}
        output = None
        if "status" in payload:
            output = _as_str(payload.get("status"))
        turn.tool_calls.append(
            ToolCall(
                call_id=call_id,
                name=tool_name,
                arguments=arguments,
                timestamp=timestamp,
                output=output,
                seq=seq,
            )
        )
        return


def _parse_turn_from_rollout(path: Path, target_turn_id: str) -> Optional[TurnData]:
    turns: Dict[str, TurnData] = {}
    active_turn_id: Optional[str] = None
    pending_pre_turn_items: List[Tuple[Dict[str, Any], Optional[str], int]] = []
    pending_task_started = False
    line_seq = 0

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line_seq += 1
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                ts = _as_str(obj.get("timestamp")) or None
                typ = _as_str(obj.get("type"))
                payload = obj.get("payload")

                if typ == "event_msg" and isinstance(payload, dict):
                    ptype = _as_str(payload.get("type"))

                    if ptype == "task_started":
                        pending_task_started = True
                        pending_pre_turn_items = []
                        active_turn_id = None
                        continue

                    if ptype == "task_complete":
                        done_tid = _as_str(payload.get("turn_id"))
                        if done_tid:
                            td = turns.setdefault(done_tid, TurnData(turn_id=done_tid))
                            td.completed_at = ts
                        if active_turn_id == done_tid:
                            active_turn_id = None
                        pending_task_started = False
                        pending_pre_turn_items = []
                        continue

                    if ptype == "token_count" and active_turn_id:
                        td = turns.setdefault(active_turn_id, TurnData(turn_id=active_turn_id))
                        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
                        last_usage = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
                        total_usage = info.get("total_token_usage") if isinstance(info.get("total_token_usage"), dict) else {}
                        if last_usage or total_usage:
                            td.token_events.append(
                                {
                                    "timestamp": ts,
                                    "last_token_usage": last_usage,
                                    "total_token_usage": total_usage,
                                }
                            )
                        if isinstance(payload.get("rate_limits"), dict):
                            td.rate_limits = payload.get("rate_limits")
                        continue

                    if ptype == "agent_reasoning" and active_turn_id:
                        if _include_agent_reasoning():
                            text = _as_str(payload.get("text"))
                            if text:
                                td = turns.setdefault(active_turn_id, TurnData(turn_id=active_turn_id))
                                td.reasoning.append(
                                    {
                                        "text": text,
                                        "timestamp": ts,
                                        "kind": "agent_reasoning_raw",
                                        "seq": line_seq,
                                    }
                                )
                        continue

                if typ == "turn_context" and isinstance(payload, dict):
                    tid = _as_str(payload.get("turn_id"))
                    if tid:
                        td = turns.setdefault(tid, TurnData(turn_id=tid))
                        model = _as_str(payload.get("model"))
                        effort = _as_str(payload.get("effort"))
                        if model:
                            td.model = model
                        if effort:
                            td.effort = effort
                        td.turn_context = {
                            "approval_policy": payload.get("approval_policy"),
                            "collaboration_mode": payload.get("collaboration_mode"),
                            "cwd": payload.get("cwd"),
                            "developer_instructions": payload.get("developer_instructions"),
                            "user_instructions": payload.get("user_instructions"),
                            "personality": payload.get("personality"),
                            "sandbox_policy": payload.get("sandbox_policy"),
                            "summary": payload.get("summary"),
                            "truncation_policy": payload.get("truncation_policy"),
                        }
                        if not td.started_at:
                            td.started_at = ts

                        active_turn_id = tid

                        # attach buffered pre-turn response items (usually user message)
                        if pending_pre_turn_items:
                            for item_payload, item_ts, item_seq in pending_pre_turn_items:
                                _consume_response_item(td, item_payload, item_ts, seq=item_seq)
                            pending_pre_turn_items = []
                        pending_task_started = False
                    continue

                if typ == "response_item" and isinstance(payload, dict):
                    if active_turn_id:
                        td = turns.setdefault(active_turn_id, TurnData(turn_id=active_turn_id))
                        _consume_response_item(td, payload, ts, seq=line_seq)
                    elif pending_task_started:
                        pending_pre_turn_items.append((payload, ts, line_seq))
                    continue

    except Exception:
        return None

    turn = turns.get(target_turn_id)
    if not turn:
        return None

    # link tool outputs by call_id
    for tc in turn.tool_calls:
        if tc.call_id and tc.call_id in turn.tool_output_by_call_id:
            tc.output = turn.tool_output_by_call_id[tc.call_id]

    return turn


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

@dataclass
class PriceRates:
    input_per_1m: Optional[float] = None
    cached_input_per_1m: Optional[float] = None
    output_per_1m: Optional[float] = None
    reasoning_output_per_1m: Optional[float] = None


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None


def _resolve_price_rates(model: Optional[str]) -> PriceRates:
    # 1) model map JSON (preferred)
    raw_map = os.getenv("OMX_LANGFUSE_PRICE_MAP_JSON", "").strip()
    if raw_map and model:
        try:
            parsed = json.loads(raw_map)
            if isinstance(parsed, dict):
                row = parsed.get(model)
                if isinstance(row, dict):
                    return PriceRates(
                        input_per_1m=_as_float(row.get("input_per_1m")),
                        cached_input_per_1m=_as_float(row.get("cached_input_per_1m")),
                        output_per_1m=_as_float(row.get("output_per_1m")),
                        reasoning_output_per_1m=_as_float(row.get("reasoning_output_per_1m")),
                    )
        except Exception:
            pass

    # 2) global env fallback
    return PriceRates(
        input_per_1m=_as_float(os.getenv("OMX_LANGFUSE_PRICE_INPUT_PER_1M")),
        cached_input_per_1m=_as_float(os.getenv("OMX_LANGFUSE_PRICE_CACHED_INPUT_PER_1M")),
        output_per_1m=_as_float(os.getenv("OMX_LANGFUSE_PRICE_OUTPUT_PER_1M")),
        reasoning_output_per_1m=_as_float(os.getenv("OMX_LANGFUSE_PRICE_REASONING_OUTPUT_PER_1M")),
    )


def _latest_usage(turn: TurnData) -> Optional[Dict[str, int]]:
    if not turn.token_events:
        return None
    last = turn.token_events[-1]
    usage = last.get("last_token_usage") if isinstance(last.get("last_token_usage"), dict) else {}

    input_tokens = _as_int(usage.get("input_tokens"))
    cached_input_tokens = _as_int(usage.get("cached_input_tokens"))
    output_tokens = _as_int(usage.get("output_tokens"))
    reasoning_output_tokens = _as_int(usage.get("reasoning_output_tokens"))
    total_tokens = _as_int(usage.get("total_tokens"))

    data = _compact_dict(
        {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": reasoning_output_tokens,
            "total_tokens": total_tokens,
        }
    )
    return data if data else None


def _estimate_cost_usd(usage: Optional[Dict[str, int]], rates: PriceRates) -> Optional[Dict[str, Any]]:
    if not usage:
        return None

    in_tok = usage.get("input_tokens", 0)
    cached_tok = usage.get("cached_input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    reasoning_tok = usage.get("reasoning_output_tokens", 0)

    # If no price hints, return None
    if (
        rates.input_per_1m is None
        and rates.cached_input_per_1m is None
        and rates.output_per_1m is None
        and rates.reasoning_output_per_1m is None
    ):
        return None

    uncached_in = max(in_tok - cached_tok, 0)

    input_rate = rates.input_per_1m if rates.input_per_1m is not None else 0.0
    cached_rate = rates.cached_input_per_1m if rates.cached_input_per_1m is not None else input_rate
    output_rate = rates.output_per_1m if rates.output_per_1m is not None else 0.0
    reasoning_rate = rates.reasoning_output_per_1m

    input_cost = (uncached_in / 1_000_000.0) * input_rate
    cached_cost = (cached_tok / 1_000_000.0) * cached_rate
    output_cost = (out_tok / 1_000_000.0) * output_rate

    # reasoning_output_tokens may overlap with output_tokens depending on provider.
    # Only add separately when explicit reasoning rate is configured.
    reasoning_cost = 0.0
    if reasoning_rate is not None:
        reasoning_cost = (reasoning_tok / 1_000_000.0) * reasoning_rate

    total = input_cost + cached_cost + output_cost + reasoning_cost

    return {
        "currency": "USD",
        "total": total,
        "components": {
            "input_uncached": input_cost,
            "input_cached": cached_cost,
            "output": output_cost,
            "reasoning_output": reasoning_cost,
        },
        "rates_per_1m": _compact_dict(
            {
                "input": rates.input_per_1m,
                "cached_input": rates.cached_input_per_1m,
                "output": rates.output_per_1m,
                "reasoning_output": rates.reasoning_output_per_1m,
            }
        ),
        "token_basis": {
            "input_uncached_tokens": uncached_in,
            "cached_input_tokens": cached_tok,
            "output_tokens": out_tok,
            "reasoning_output_tokens": reasoning_tok,
        },
    }


# ---------------------------------------------------------------------------
# Langfuse emission
# ---------------------------------------------------------------------------

def _build_turn_payload(event_data: Dict[str, Any], turn: TurnData, rollout_path: Path) -> Dict[str, Any]:
    user_text = "\n\n".join(turn.user_messages).strip()
    assistant_text = "\n\n".join(turn.assistant_messages).strip()

    # Some turns in rollout are internal sub-turns without explicit user message blocks.
    # Fallback to turn_context.user_instructions so Langfuse Input is never empty.
    if not user_text:
        user_text = _as_str(turn.turn_context.get("user_instructions")).strip()

    user_text_trunc, user_text_meta = _truncate_text(user_text)
    assistant_text_trunc, assistant_text_meta = _truncate_text(assistant_text)

    usage = _latest_usage(turn)
    rates = _resolve_price_rates(turn.model)
    cost = _estimate_cost_usd(usage, rates)

    tools: List[Dict[str, Any]] = []
    for idx, tc in enumerate(turn.tool_calls, start=1):
        args_raw = tc.arguments
        args_text = args_raw if isinstance(args_raw, str) else _json_dumps_safe(args_raw)
        args_text, args_meta = _truncate_text(_as_str(args_text), max_chars=12000)

        out_text, out_meta = _truncate_text(_as_str(tc.output or ""), max_chars=12000)
        tools.append(
            {
                "index": idx,
                "call_id": tc.call_id,
                "name": tc.name,
                "arguments": args_text,
                "arguments_meta": args_meta,
                "output": out_text,
                "output_meta": out_meta,
                "timestamp": tc.timestamp,
                "seq": tc.seq,
            }
        )

    reasoning_blocks: List[Dict[str, Any]] = []
    max_reasoning = _max_reasoning_blocks()
    keep_raw_reasoning = _reasoning_raw_passthrough()

    if keep_raw_reasoning:
        source_reasoning = list(turn.reasoning)
    else:
        # compact mode: dedupe repeated reasoning text while preserving first-seen order
        source_reasoning: List[Dict[str, Any]] = []
        seen_reasoning = set()
        for item in turn.reasoning:
            text = item.get("text") if isinstance(item, dict) else item
            norm = _as_str(text).strip()
            if not norm or norm in seen_reasoning:
                continue
            seen_reasoning.add(norm)
            if isinstance(item, dict):
                source_reasoning.append(item)
            else:
                source_reasoning.append({"text": norm, "timestamp": None, "kind": "reasoning"})

    for item in source_reasoning:
        text = item.get("text") if isinstance(item, dict) else item
        norm = _as_str(text).strip()
        if not norm:
            continue
        t, m = _truncate_text(norm, max_chars=12000)
        reasoning_blocks.append(
            {
                "index": len(reasoning_blocks) + 1,
                "text": t,
                "meta": m,
                "timestamp": item.get("timestamp") if isinstance(item, dict) else None,
                "kind": item.get("kind") if isinstance(item, dict) else "reasoning",
                "seq": item.get("seq") if isinstance(item, dict) else None,
            }
        )
        if len(reasoning_blocks) >= max_reasoning:
            break

    turn_context = turn.turn_context if isinstance(turn.turn_context, dict) else {}
    developer_instr = _as_str(turn_context.get("developer_instructions"))
    user_instr = _as_str(turn_context.get("user_instructions"))
    dev_instr_trunc, dev_instr_meta = _truncate_text(developer_instr, max_chars=12000)
    user_instr_trunc, user_instr_meta = _truncate_text(user_instr, max_chars=12000)

    return {
        "event": event_data.get("event") or "turn-complete",
        "source": event_data.get("source") or "omx-hook-plugin",
        "timestamp": event_data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "cwd": event_data.get("cwd"),
        "session_id": event_data.get("session_id"),
        "thread_id": event_data.get("thread_id"),
        "turn_id": turn.turn_id,
        "mode": event_data.get("mode"),
        "model": turn.model,
        "effort": turn.effort,
        "turn_started_at": turn.started_at,
        "turn_completed_at": turn.completed_at,
        "user_messages": turn.user_messages,
        "assistant_messages": turn.assistant_messages,
        "developer_messages": turn.developer_messages,
        "response_item_types": [x.get("type") for x in turn.response_items if isinstance(x, dict)],
        "input_text": user_text_trunc,
        "input_text_meta": user_text_meta,
        "output_text": assistant_text_trunc,
        "output_text_meta": assistant_text_meta,
        "turn_context": turn_context,
        "developer_instructions": dev_instr_trunc,
        "developer_instructions_meta": dev_instr_meta,
        "user_instructions": user_instr_trunc,
        "user_instructions_meta": user_instr_meta,
        "tools": tools,
        "reasoning_blocks": reasoning_blocks,
        "usage": usage,
        "cost": cost,
        "rate_limits": turn.rate_limits,
        "rollout_path": str(rollout_path),
    }


def _emit_rich_with_span_api(client: Any, data: Dict[str, Any], user_id: str) -> bool:
    if not hasattr(client, "start_as_current_span"):
        return False

    trace_name = f"OMX turn {data.get('turn_id') or 'unknown'}"

    metadata = _compact_dict(
        {
            "source": data.get("source"),
            "event": data.get("event"),
            "type": data.get("event"),
            "thread_id": data.get("thread_id"),
            "turn_id": data.get("turn_id"),
            "mode": data.get("mode"),
            "cwd": data.get("cwd"),
            "model": data.get("model"),
            "effort": data.get("effort"),
            "hostname": socket.gethostname(),
            "usage": data.get("usage"),
            "cost": data.get("cost"),
            "rate_limits": data.get("rate_limits"),
            "rollout_path": data.get("rollout_path"),
            "tool_count": len(data.get("tools") or []),
            "reasoning_count": len(data.get("reasoning_blocks") or []),
            "response_item_types": data.get("response_item_types"),
            "turn_context_summary": _compact_dict(
                {
                    "approval_policy": (data.get("turn_context") or {}).get("approval_policy") if isinstance(data.get("turn_context"), dict) else None,
                    "sandbox_policy": (data.get("turn_context") or {}).get("sandbox_policy") if isinstance(data.get("turn_context"), dict) else None,
                    "collaboration_mode": (data.get("turn_context") or {}).get("collaboration_mode") if isinstance(data.get("turn_context"), dict) else None,
                    "truncation_policy": (data.get("turn_context") or {}).get("truncation_policy") if isinstance(data.get("turn_context"), dict) else None,
                }
            ),
            "developer_instructions_meta": data.get("developer_instructions_meta"),
            "user_instructions_meta": data.get("user_instructions_meta"),
            "reconstruction": "hook-only-rollout-parse",
            "product": "oh-my-codex",
            "session_id": data.get("session_id"),
            "user_id": user_id or None,
        }
    )

    with client.start_as_current_span(
        name=trace_name,
        input={"role": "user", "content": data.get("input_text") or "\n\n".join(data.get("user_messages", []) or [])},
        output={"role": "assistant", "content": data.get("output_text")},
        metadata=metadata,
    ) as trace_span:
        if hasattr(client, "update_current_trace"):
            try:
                client.update_current_trace(
                    **_compact_dict(
                        {
                            "name": trace_name,
                            "session_id": data.get("session_id"),
                            "user_id": user_id or None,
                            "tags": ["oh-my-codex", "omx", "hook-only", "deep-observability"],
                            "metadata": metadata,
                        }
                    )
                )
            except Exception:
                pass

        # LCC/LGC style ordering: explicitly control start_time with monotonic cursor.
        step = timedelta(milliseconds=1)
        t0 = _parse_iso_ts(data.get("turn_started_at")) or datetime.now(timezone.utc)
        t_cursor = t0 + step
        try:
            trace_span.update(start_time=t0)
        except Exception:
            pass

        developer_instr = _as_str(data.get("developer_instructions")).strip()
        include_turn_context_spans = _include_turn_context_spans()
        if include_turn_context_spans and developer_instr:
            try:
                with client.start_as_current_span(
                    name="turn_context:developer_instructions",
                    input={"role": "developer"},
                    output=developer_instr,
                    metadata=_compact_dict(
                        {
                            "kind": "turn_context",
                            "meta": data.get("developer_instructions_meta"),
                        }
                    ),
                ) as span:
                    span.update(start_time=t_cursor)
                t_cursor = t_cursor + step
            except Exception:
                pass

        user_instr = _as_str(data.get("user_instructions")).strip()
        if include_turn_context_spans and user_instr:
            try:
                with client.start_as_current_span(
                    name="turn_context:user_instructions",
                    input={"role": "user"},
                    output=user_instr,
                    metadata=_compact_dict(
                        {
                            "kind": "turn_context",
                            "meta": data.get("user_instructions_meta"),
                        }
                    ),
                ) as span:
                    span.update(start_time=t_cursor)
                t_cursor = t_cursor + step
            except Exception:
                pass

        # generation node
        if hasattr(client, "start_as_current_generation"):
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            usage_payload = _compact_dict(
                {
                    "input": _as_int(usage.get("input_tokens")),
                    "output": _as_int(usage.get("output_tokens")),
                    "total": _as_int(usage.get("total_tokens")),
                    "input_cache_read": _as_int(usage.get("cached_input_tokens")),
                    "reasoning": _as_int(usage.get("reasoning_output_tokens")),
                }
            )
            try:
                with client.start_as_current_generation(
                    **_compact_dict(
                        {
                            "name": "assistant_turn",
                            "model": data.get("model"),
                            "input": {"role": "user", "content": data.get("input_text") or "\n\n".join(data.get("user_messages", []) or [])},
                            "output": {"role": "assistant", "content": data.get("output_text")},
                            "metadata": _compact_dict(
                                {
                                    "event": data.get("event"),
                                    "cost": data.get("cost"),
                                    "product": "oh-my-codex",
                                    "turn_context": data.get("turn_context"),
                                    "developer_instructions": data.get("developer_instructions"),
                                    "user_instructions": data.get("user_instructions"),
                                }
                            ),
                        }
                    )
                ) as gen_obs:
                    try:
                        gen_obs.update(start_time=t_cursor)
                    except Exception:
                        pass
                    if usage_payload:
                        try:
                            gen_obs.update(usage=usage_payload)
                        except Exception:
                            pass
                        try:
                            gen_obs.update(usage_details=usage_payload)
                        except Exception:
                            pass
                    t_cursor = t_cursor + step
            except Exception:
                pass

        # Chronological turn details (reasoning + tools) to preserve sequence in UI timeline.
        timeline: List[Dict[str, Any]] = []
        for rb in data.get("reasoning_blocks", []):
            timeline.append(
                {
                    "kind": "reasoning",
                    "timestamp": rb.get("timestamp"),
                    "seq": rb.get("seq"),
                    "index": rb.get("index"),
                    "payload": rb,
                }
            )
        for tool in data.get("tools", []):
            timeline.append(
                {
                    "kind": "tool",
                    "timestamp": tool.get("timestamp"),
                    "seq": tool.get("seq"),
                    "index": tool.get("index"),
                    "payload": tool,
                }
            )

        timeline = sorted(
            timeline,
            key=lambda x: (
                _parse_iso_ts(x.get("timestamp")) or datetime.max.replace(tzinfo=timezone.utc),
                int(x.get("seq") or 0),
                int(x.get("index") or 0),
            ),
        )

        for item in timeline:
            event_ts = _parse_iso_ts(item.get("timestamp"))
            base_start = event_ts or t_cursor
            span_start = base_start if base_start > t_cursor else t_cursor + step
            if item.get("kind") == "reasoning":
                rb = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                txt = _as_str(rb.get("text"))
                if not txt:
                    continue
                try:
                    with client.start_as_current_span(
                        name=f"reasoning[{rb.get('index')}]",
                        output=txt,
                        metadata=_compact_dict(
                            {
                                "kind": rb.get("kind") or "reasoning",
                                "timestamp": rb.get("timestamp"),
                                "seq": rb.get("seq"),
                                "meta": rb.get("meta"),
                            }
                        ),
                    ) as span:
                        span.update(start_time=span_start)
                except Exception:
                    pass
                t_cursor = span_start + step
                continue

            tool = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            name = _as_str(tool.get("name")) or "tool"
            args_txt = _as_str(tool.get("arguments"))
            out_txt = _as_str(tool.get("output"))

            if hasattr(client, "start_as_current_observation"):
                try:
                    with client.start_as_current_observation(
                        name=f"tool:{name}",
                        as_type="tool",
                        input=args_txt,
                        output=out_txt,
                        metadata=_compact_dict(
                            {
                                "call_id": tool.get("call_id"),
                                "index": tool.get("index"),
                                "seq": tool.get("seq"),
                                "arguments_meta": tool.get("arguments_meta"),
                                "output_meta": tool.get("output_meta"),
                                "timestamp": tool.get("timestamp"),
                            }
                        ),
                    ) as tool_obs:
                        tool_obs.update(start_time=span_start)
                        t_cursor = span_start + step
                    continue
                except Exception:
                    pass

            try:
                with client.start_as_current_span(
                    name=f"tool:{name}",
                    input=args_txt,
                    output=out_txt,
                    metadata=_compact_dict(
                        {
                            "kind": "tool",
                            "call_id": tool.get("call_id"),
                            "index": tool.get("index"),
                            "seq": tool.get("seq"),
                            "timestamp": tool.get("timestamp"),
                        }
                    ),
                ) as span:
                    span.update(start_time=span_start)
                    t_cursor = span_start + step
            except Exception:
                pass

    return True


def _emit_basic_with_trace_api(client: Any, data: Dict[str, Any], user_id: str) -> bool:
    if not hasattr(client, "trace"):
        return False

    trace_name = f"OMX turn {data.get('turn_id') or 'unknown'}"
    metadata = _compact_dict(
        {
            "source": data.get("source"),
            "event": data.get("event"),
            "thread_id": data.get("thread_id"),
            "turn_id": data.get("turn_id"),
            "mode": data.get("mode"),
            "cwd": data.get("cwd"),
            "model": data.get("model"),
            "usage": data.get("usage"),
            "cost": data.get("cost"),
            "tool_count": len(data.get("tools") or []),
            "reasoning_count": len(data.get("reasoning_blocks") or []),
            "tools": data.get("tools"),
            "response_item_types": data.get("response_item_types"),
            "turn_context": data.get("turn_context"),
            "developer_instructions_meta": data.get("developer_instructions_meta"),
            "user_instructions_meta": data.get("user_instructions_meta"),
            "product": "oh-my-codex",
            "session_id": data.get("session_id"),
            "user_id": user_id or None,
            "reasoning_blocks": data.get("reasoning_blocks"),
        }
    )

    trace = client.trace(
        **_compact_dict(
            {
                "name": trace_name,
                "session_id": data.get("session_id"),
                "user_id": user_id or None,
                "input": {"role": "user", "content": data.get("input_text") or "\n\n".join(data.get("user_messages", []) or [])},
                "output": {"role": "assistant", "content": data.get("output_text")},
                "metadata": metadata,
                "tags": ["oh-my-codex", "omx", "hook-only", "deep-observability"],
            }
        )
    )

    if hasattr(trace, "generation"):
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        usage_payload = _compact_dict(
            {
                "input": _as_int(usage.get("input_tokens")),
                "output": _as_int(usage.get("output_tokens")),
                "total": _as_int(usage.get("total_tokens")),
                "input_cache_read": _as_int(usage.get("cached_input_tokens")),
                "reasoning": _as_int(usage.get("reasoning_output_tokens")),
            }
        )
        trace.generation(
            **_compact_dict(
                {
                    "name": "assistant_turn",
                    "model": data.get("model"),
                    "input": {"role": "user", "content": data.get("input_text") or "\n\n".join(data.get("user_messages", []) or [])},
                    "output": {"role": "assistant", "content": data.get("output_text")},
                    "metadata": _compact_dict(
                        {
                            "cost": data.get("cost"),
                            "turn_context": data.get("turn_context"),
                            "developer_instructions": data.get("developer_instructions"),
                            "user_instructions": data.get("user_instructions"),
                        }
                    ),
                    "usage": usage_payload if usage_payload else None,
                    "usage_details": usage_payload if usage_payload else None,
                }
            )
        )

    return True


def _emit_lifecycle_event(client: Any, event_data: Dict[str, Any], user_id: str) -> bool:
    name = f"OMX {event_data.get('event') or 'event'}"
    metadata = _compact_dict(
        {
            "source": event_data.get("source"),
            "event": event_data.get("event"),
            "type": event_data.get("type"),
            "thread_id": event_data.get("thread_id"),
            "turn_id": event_data.get("turn_id"),
            "mode": event_data.get("mode"),
            "cwd": event_data.get("cwd"),
            "hostname": socket.gethostname(),
            "timestamp": event_data.get("timestamp"),
            "product": "oh-my-codex",
            "session_id": event_data.get("session_id"),
            "user_id": user_id or None,
        }
    )

    if hasattr(client, "trace"):
        client.trace(
            **_compact_dict(
                {
                    "name": name,
                    "session_id": event_data.get("session_id"),
                    "user_id": user_id or None,
                    "input": "\n\n".join(event_data.get("input_messages", []) or []),
                    "output": event_data.get("output_message"),
                    "metadata": metadata,
                    "tags": ["oh-my-codex", "omx", "hook-only", "lifecycle"],
                }
            )
        )
        return True

    if hasattr(client, "start_as_current_span"):
        with client.start_as_current_span(
            name=name,
            input="\n\n".join(event_data.get("input_messages", []) or []),
            output=event_data.get("output_message"),
            metadata=metadata,
        ):
            if hasattr(client, "update_current_trace"):
                try:
                    client.update_current_trace(
                        **_compact_dict(
                            {
                                "name": name,
                                "session_id": event_data.get("session_id"),
                                "user_id": user_id or None,
                                "tags": ["oh-my-codex", "omx", "hook-only", "lifecycle"],
                                "metadata": metadata,
                            }
                        )
                    )
                except Exception:
                    pass
        return True

    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # safety gate
    if not _env_true("OMX_TRACE_TO_LANGFUSE"):
        return 0

    payload = _read_payload()
    if not payload:
        return 0

    event_data = _normalize_event_payload(payload)

    public_key = _as_str(os.getenv("LANGFUSE_PUBLIC_KEY")).strip()
    secret_key = _as_str(os.getenv("LANGFUSE_SECRET_KEY")).strip()
    base_url = _as_str(os.getenv("LANGFUSE_BASE_URL")).strip()
    user_id = _as_str(os.getenv("LANGFUSE_USER_ID")).strip()

    if not public_key or not secret_key:
        return 0

    try:
        from langfuse import Langfuse
    except Exception:
        return 0

    try:
        kwargs: Dict[str, Any] = {"public_key": public_key, "secret_key": secret_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = Langfuse(**kwargs)
    except TypeError:
        try:
            kwargs = {"public_key": public_key, "secret_key": secret_key}
            if base_url:
                kwargs["host"] = base_url
            client = Langfuse(**kwargs)
        except Exception:
            return 0
    except Exception:
        return 0

    cwd = event_data.get("cwd") or os.getcwd()
    # Native turn-complete payloads may omit session_id but include thread_id.
    # Codex rollout session_meta.id matches thread_id, so fallback preserves hook-only reconstruction.
    session_id = _as_str(event_data.get("session_id")) or _as_str(event_data.get("thread_id"))
    if session_id and not _as_str(event_data.get("session_id")):
        event_data["session_id"] = session_id

    turn_id = _as_str(event_data.get("turn_id"))
    event_name = _as_str(event_data.get("event"))

    try:
        emitted = False

        # Deep turn path for turn-complete only
        if event_name == "turn-complete" and session_id and turn_id:
            state = _load_state(cwd)
            key = _dedupe_key(session_id, turn_id)
            if key not in state.emitted_turns:
                rollout = _find_rollout_file(session_id, _as_str(event_data.get("cwd")), state)
                if rollout:
                    turn = _parse_turn_from_rollout(rollout, turn_id)
                    if turn:
                        rich_payload = _build_turn_payload(event_data, turn, rollout)
                        # preferred: rich span API; fallback: basic trace API
                        emitted = _emit_rich_with_span_api(client, rich_payload, user_id)
                        if not emitted:
                            emitted = _emit_basic_with_trace_api(client, rich_payload, user_id)

            # mark dedupe even when parse failed, to avoid noisy repeats on same turn
            state.emitted_turns[key] = datetime.now(timezone.utc).isoformat()
            _save_state(cwd, state)

        # lifecycle/basic fallback
        if not emitted:
            emitted = _emit_lifecycle_event(client, event_data, user_id)

        if hasattr(client, "flush"):
            try:
                client.flush()
            except Exception:
                pass

    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
