# Langfuse 통합 작업 진행 문서 (2026-02-25)

이 문서는 `langfuse-claude-code`, `langfuse-gemini-cli`, `langfuse-oh-my-codex`의 턴 내부 로깅/메타데이터 정합 작업을 이어서 진행할 수 있도록 현재 상태를 정리한 문서입니다.

## 1) 목표
- 3개 프로젝트 모두에서 턴 내부 데이터(assistant/tool/reasoning/usage) 로깅 강화
- 메타데이터 스키마 정렬(`product`, `reconstruction`, session/user/turn 식별자)
- OMX hook-only 모드에서도 deep observability 최대한 확보
- 타임라인 순서 안정화(특히 reasoning/tool 순서 문제)

---

## 2) 완료된 변경사항

## A. langfuse-claude-code
대상 파일:
- `/Users/baem1n/Dev/side/langfuse-claude-code/langfuse_hook.py`

핵심 반영:
- usage 집계 강화
  - 정수 변환 안전화
  - reasoning 토큰 필드(`reasoning_tokens`/`reasoning_output_tokens`) 반영
- 이벤트 분류 강화
  - `hook_event_name`/`event` 기반으로 `Stop`, `Notification`, `PreToolUse`, `PostToolUse` 판별
- Pre/Post Tool 이벤트 활용 개선
  - 버퍼된 tool 이벤트를 turn별로 best-effort 매핑
  - turn trace 메타데이터에 `hook_tool_events` 수치 반영
  - Hook Tool observation 추가(`Hook Tool [n]: ...`)
- Notification 독립 span 추가
  - `Claude Code - Notification`
- 메타데이터 강화
  - `product=claude-code`, `reconstruction=hook-transcript-plus-tool-buffer`, `hook_event`

검증:
- `python3 -m py_compile .../langfuse_hook.py` 통과

---

## B. langfuse-gemini-cli
대상 파일:
- `/Users/baem1n/Dev/side/langfuse-gemini-cli/langfuse_hook.py`

핵심 반영:
- 버퍼 이벤트에 순번(`seq`) + raw 이벤트 보존
  - `TraceData.raw_events` 추가
- model/tool selection/tool call에 seq 연결
- `mcp_context` 실제 tool 메타데이터 반영
- usage 확장
  - `thoughtsTokenCount`/`reasoningTokenCount` -> `reasoning`
  - `extract_gemini_usage_details()` 추가 (usageMetadata 원본 정규화)
  - generation에 `usage` + `usage_details` 업데이트
- 기타 buffered 이벤트를 별도 span으로 기록
  - `Hook Event [n]: ...`
- 메타데이터 강화
  - `product=gemini-cli`, `reconstruction=hook-buffer-assembly`
  - `raw_event_count`, `event_sequence`, `hook_event`, `event_timestamp`

검증:
- `python3 -m py_compile .../langfuse_hook.py` 통과

---

## C. langfuse-oh-my-codex (hook-only)
대상 파일:
- `/Users/baem1n/langfuse-oh-my-codex/scripts/langfuse_omx_hook.py`

핵심 반영:
- turn_context 확장 수집
  - `developer_instructions`, `user_instructions`, policy/sandbox/collaboration 필드
- input fallback
  - user message가 비어있는 turn은 `turn_context.user_instructions`를 input으로 사용
- reasoning 구조화
  - `reasoning_summary`, `agent_reasoning_raw` 구분
  - `timestamp`, `kind`, `seq` 보존
- 도구 수집 확장
  - `function_call`/`function_call_output`뿐 아니라 `*_call`(예: web_search_call)도 tool-like로 수집
  - tool에 `seq` 추가
- 타임라인 순서 안정화 (LCC/LGC 방식 차용)
  - trace/generation 및 하위 span에 `start_time` 명시
  - 정렬 키: `timestamp -> seq -> index`
  - span 시작시간을 monotonic cursor로 보정
- turn_context를 metadata뿐 아니라 별도 span으로 추가
  - `turn_context:developer_instructions`
  - `turn_context:user_instructions`
- 메타데이터 강화
  - `response_item_types`, `turn_context_summary`, instruction meta, `product=oh-my-codex`, `reconstruction=hook-only-rollout-parse`

검증:
- `python3 -m py_compile .../scripts/langfuse_omx_hook.py` 통과
- 샘플 파싱 테스트:
  - reasoning/tool에 `seq` 존재 확인
  - developer/user instructions 길이 확인

---

## 3) 로컬 런타임 반영 상태
스크립트 동기화 완료:
- `~/.claude/hooks/langfuse_hook.py` <- langfuse-claude-code 최신본
- `~/.gemini/hooks/langfuse_hook.py` <- langfuse-gemini-cli 최신본
- `~/.omx/hooks/langfuse_omx_hook.py` <- langfuse-oh-my-codex 최신본
- `~/langfuse-oh-my-codex/.omx/hooks/langfuse_omx_hook.py` 동기화
- `~/oh-my-codex/.omx/hooks/langfuse_omx_hook.py` 동기화

검증:
- `omx hooks test` => `langfuse: ok`

---

## 4) 현재 확인 포인트 (남은 점검)
1. Langfuse UI 타임라인에서 reasoning/tool 순서가 기대대로 정렬되는지 실턴 확인
2. turn_context instruction span 표시가 과도한지(노이즈) 여부 판단
3. 필요 시 env 토글 추가 검토
   - 예: `OMX_LANGFUSE_INCLUDE_TURN_CONTEXT_SPANS=true/false`

---

## 5) 이어서 작업할 때 추천 절차
1. OMX/Claude/Gemini 각각 1턴 실행
2. Langfuse Trace에서 아래 항목 점검
   - Input/Output 표시
   - tool observation input/output
   - reasoning span 순서
   - usage/usage_details/cost
   - metadata tags (`oh-my-codex`, `omx`, `hook-only` 등)
3. 순서 이슈가 남으면
   - 해당 trace의 rollout_path/turn_id 기준 raw 이벤트 시퀀스 비교
   - 필요한 경우 start_time 보정 로직(마이크로초 step) 추가 조정

---

## 6) 참고 명령어
```bash
# 컴파일 체크
python3 -m py_compile /Users/baem1n/Dev/side/langfuse-claude-code/langfuse_hook.py
python3 -m py_compile /Users/baem1n/Dev/side/langfuse-gemini-cli/langfuse_hook.py
python3 -m py_compile /Users/baem1n/langfuse-oh-my-codex/scripts/langfuse_omx_hook.py

# OMX hook 테스트
omx hooks test

# 런타임 hook 동기화 (OMX)
cp /Users/baem1n/langfuse-oh-my-codex/scripts/langfuse_omx_hook.py /Users/baem1n/.omx/hooks/langfuse_omx_hook.py
```

---

## 7) Git 상태 메모
- `langfuse-claude-code`: `langfuse_hook.py` 수정됨
- `langfuse-gemini-cli`: `langfuse_hook.py` 수정됨 (`docs/` untracked 존재)
- `langfuse-oh-my-codex`: `scripts/langfuse_omx_hook.py` untracked(신규) + docs untracked 존재

