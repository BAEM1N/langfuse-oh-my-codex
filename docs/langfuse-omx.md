# Langfuse for OMX (Hook-Only, Deep Observability)

## 결론
가능합니다. `hook-only`를 유지하면서도 아래까지 추적 가능합니다.
- 세션/유저/턴 단위 트레이싱
- 툴 호출/출력 재구성(call_id 기준)
- 토큰 usage 수집(input/cached/output/reasoning/total)
- 비용 추정(USD, env로 가격표 주입)

구현 방식은 **OMX 소스 변경 없이** `.omx/hooks/` 플러그인 + Python 브리지로 처리합니다.

## 파일
- `.omx/hooks/langfuse.mjs`
- `.omx/hooks/langfuse_omx_hook.py`
- `scripts/langfuse_omx_hook.py` (참고/복사용)

## 원리
1. hook 이벤트(`turn-complete`) 수신
2. Python 브리지가 `~/.codex/sessions/.../rollout-*.jsonl`를 파싱
3. `turn_id` 기준으로 메시지/툴/usage/reasoning 재구성
4. Langfuse trace/span/generation/tool observation 전송

## 환경변수

### 권장: `~/.omx/.env`
```bash
mkdir -p ~/.omx
cat > ~/.omx/.env <<'EOF'
OMX_HOOK_PLUGINS=1
OMX_TRACE_TO_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_USER_ID=baem1n
EOF
chmod 600 ~/.omx/.env
```

`langfuse_omx_hook.py`는 실행 시 아래 순서로 `.env`를 자동 로드합니다.
1. 이미 설정된 프로세스 환경변수(최우선)
2. `OMX_LANGFUSE_ENV_FILE` (명시 경로)
3. `~/.omx/.env`
4. `<cwd>/.omx/.env`

### 또는 shell export 방식
```bash
export OMX_HOOK_PLUGINS=1
export OMX_TRACE_TO_LANGFUSE=true

export LANGFUSE_PUBLIC_KEY='pk-lf-...'
export LANGFUSE_SECRET_KEY='sk-lf-...'
export LANGFUSE_BASE_URL='https://cloud.langfuse.com'   # optional
export LANGFUSE_USER_ID='baem1n'                         # optional

# optional tuning
export OMX_LANGFUSE_TIMEOUT_MS=2500
export OMX_LANGFUSE_DEBUG=true
```

## 비용 추적
기본적으로 usage만 전송됩니다.
비용까지 자동 추정하려면 단가를 넣어주세요.

```bash
# 전역 단가(USD / 1M tokens)
export OMX_LANGFUSE_PRICE_INPUT_PER_1M=3
export OMX_LANGFUSE_PRICE_CACHED_INPUT_PER_1M=0.3
export OMX_LANGFUSE_PRICE_OUTPUT_PER_1M=15
export OMX_LANGFUSE_PRICE_REASONING_OUTPUT_PER_1M=15

# 또는 모델별 맵(JSON)
export OMX_LANGFUSE_PRICE_MAP_JSON='{"gpt-5":{"input_per_1m":3,"cached_input_per_1m":0.3,"output_per_1m":15}}'
```

## 한계 (hook-only)
`langfuse-claude-code`급으로 100% 동일한 정밀도를 내려면 추가 개발이 필요할 수 있습니다.
- rollout 포맷 변경에 대한 호환 레이어
- 더 정교한 툴 상태/에러 분류
- 비용 계산의 공급자별 billing rule 반영

즉, **hook-only로 deep 관측은 실용 수준으로 가능**하고,
**완전 동일 수준(제품급 안정성/정밀도)은 점진적 고도화가 필요**합니다.
