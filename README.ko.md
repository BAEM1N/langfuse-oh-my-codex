# langfuse-oh-my-codex

[English](README.md) | [한국어](README.ko.md)

[oh-my-codex (OMX)](https://github.com/Yeachan-Heo/oh-my-codex)를 위한 자동 [Langfuse](https://langfuse.com) 트레이싱. 대화 턴, 도구 호출, 모델 응답이 Langfuse 대시보드에 구조화된 트레이스로 자동 기록됩니다. 코드 변경 없이 사용할 수 있습니다.

## 상태 (2026년 2월 25일)

- 실제 OMX 실행 기준 훅 파이프라인 검증 완료
- 턴 트레이스, 도구 스팬, 토큰 사용량이 Langfuse에 정상 기록됨
- 저장소 정리 완료 (불필요 추적 파일 없음 확인)
- 최종 문서 동기화 기준 `v0.0.1` 릴리즈/태그 정리 완료
- 다음 연동 저장소와 정렬 완료:
  - `langfuse-claude-code`
  - `langfuse-gemini-cli`
  - `langfuse-opencode`
- 진행 문서: [English](./PROGRESS.md) | [한국어](./PROGRESS.ko.md)

## 주요 기능

- **턴 완료 트레이싱** -- 사용자 프롬프트 + 어시스턴트 응답이 하나의 Langfuse 트레이스로 기록
- **도구 호출 추적** -- 모든 도구 사용이 입출력과 함께 캡처됨
- **추론 블록** -- 모델 추론이 별도 스팬으로 캡처됨
- **토큰 사용량** -- 입출력/캐시 토큰 수가 generation에 기록
- **비용 추정** -- 환경 변수로 설정된 가격 기반 USD 비용 추정 (선택)
- **세션 그룹핑** -- OMX 세션 ID 기준으로 트레이스 그룹화
- **증분 처리** -- 새로운 턴만 전송됨 (중복 없음)
- **Fail-open 설계** -- 오류 발생 시 훅이 조용히 종료; OMX 작업에 영향 없음
- **크로스 플랫폼** -- macOS, Linux, Windows 모두 지원

## 사전 요구 사항

- **oh-my-codex** -- 설치 및 실행 가능 상태 ([설치 가이드](https://github.com/Yeachan-Heo/oh-my-codex))
- **Python 3.8+** -- `pip` 사용 가능 (`python3 -m pip --version` 또는 `python -m pip --version`으로 확인)
- **Langfuse 계정** -- [cloud.langfuse.com](https://cloud.langfuse.com) (무료 플랜 가능) 또는 셀프 호스팅 인스턴스

## 빠른 시작

```bash
# 클론 후 설치 스크립트 실행
git clone https://github.com/BAEM1N/langfuse-oh-my-codex.git
cd langfuse-oh-my-codex
bash install.sh
```

Windows (PowerShell):

```powershell
git clone https://github.com/BAEM1N/langfuse-oh-my-codex.git
cd langfuse-oh-my-codex
.\install.ps1
```

설치 스크립트가 수행하는 작업:
1. Python 3.8+ 설치 확인
2. `langfuse` Python 패키지 설치
3. 훅 스크립트를 `~/.omx/hooks/`에 복사
4. Langfuse 인증 정보 입력 프롬프트:
   - Public Key (`pk-lf-...`)
   - Secret Key (`sk-lf-...`, 마스킹 입력)
   - Base URL (기본값: `https://cloud.langfuse.com`)
   - User ID (기본값: `omx-user`)
5. 인증 정보를 `~/.omx/.env`에 저장
6. 설치 검증

## 수동 설치

### 1. langfuse SDK 설치

```bash
pip install langfuse
```

### 2. 훅 스크립트 복사

```bash
mkdir -p ~/.omx/hooks
cp langfuse_hook.py ~/.omx/hooks/
chmod +x ~/.omx/hooks/langfuse_hook.py
```

### 3. `~/.omx/.env` 설정

```bash
TRACE_TO_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_USER_ID=your-username
```

## 설정

### 환경변수

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `TRACE_TO_LANGFUSE` | 예 | - | `"true"`로 설정하여 트레이싱 활성화 |
| `LANGFUSE_PUBLIC_KEY` | 예 | - | Langfuse 퍼블릭 키 |
| `LANGFUSE_SECRET_KEY` | 예 | - | Langfuse 시크릿 키 |
| `LANGFUSE_BASE_URL` | 아니오 | `https://cloud.langfuse.com` | Langfuse 호스트 URL |
| `LANGFUSE_USER_ID` | 아니오 | `omx-user` | 트레이스 귀속 사용자 ID |
| `LANGFUSE_INCLUDE_AGENT_REASONING` | 아니오 | `false` | 에이전트 추론 이벤트 스트림 포함 |
| `LANGFUSE_MAX_REASONING_BLOCKS` | 아니오 | `200` | 턴당 최대 추론 블록 수 |
| `LANGFUSE_PRICE_MAP_JSON` | 아니오 | - | 모델별 가격 JSON 맵 |

### 비용 추정

환경 변수로 가격을 설정하세요:

```bash
LANGFUSE_PRICE_INPUT_PER_1M=2.50
LANGFUSE_PRICE_OUTPUT_PER_1M=10.00
LANGFUSE_PRICE_CACHED_INPUT_PER_1M=0.50
```

또는 모델별 JSON 맵 사용:

```bash
LANGFUSE_PRICE_MAP_JSON='{"gpt-4o":{"input_per_1m":2.50,"output_per_1m":10.00}}'
```

### 셀프 호스팅 Langfuse

`LANGFUSE_BASE_URL`에 자체 인스턴스 URL을 설정하세요:

```
LANGFUSE_BASE_URL=https://langfuse.your-company.com
```

## 작동 원리

```
┌─────────────────────────────────────────────────────────┐
│                   oh-my-codex (OMX)                      │
│                                                          │
│  사용자 프롬프트 ──► 모델 응답 ──► 도구 호출 ──► ...      │
│       │                                                  │
│       ▼                                                  │
│  Codex 롤아웃 파일 (.jsonl)                               │
│       │                                                  │
│       │  ┌── turn-complete ──┐                           │
│       └─►│ langfuse_hook.py  │                           │
│          │                   │                           │
│          │ 1. 롤아웃 읽기    │                           │
│          │ 2. 턴 구성        │                           │
│          │ 3. 트레이스 전송  │                           │
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

**흐름:**

1. OMX가 대화 데이터를 Codex 롤아웃 JSONL 파일에 기록
2. **turn-complete** 이벤트마다 훅이 롤아웃 읽기
3. JSONL 항목에서 완전한 턴을 재구성
4. 각 턴을 Langfuse **트레이스**로 전송:
   - **generation** 관찰 (모델명, 토큰 사용량, 비용 포함)
   - **추론** 스팬: 모델 thinking 블록
   - **도구** 스팬: 각 도구 호출 (입출력 연결 포함)
5. **새로운** 턴만 전송 (상태 캐시로 중복 제거)
6. 동일 `session_id`로 모든 트레이스 그룹화

## 호환성

| 구성 요소 | 버전 |
|-----------|------|
| Python | 3.8+ |
| langfuse SDK | 2.0+ |
| oh-my-codex | 훅 지원하는 모든 버전 |
| OS | macOS, Linux, Windows |

## 문제 해결

### 트레이스가 나타나지 않는 경우

1. `TRACE_TO_LANGFUSE`가 `"true"`인지 확인
2. API 키가 올바른지 확인
3. 로그 파일 확인: `~/.omx/hooks/langfuse_hook.log`

### 훅이 실행되지 않는 경우

1. `~/.omx/hooks/langfuse_hook.py`에 훅 스크립트가 존재하는지 확인
2. OMX 훅 플러그인이 스크립트를 호출하도록 설정되었는지 확인
3. 수동 테스트: `echo '{}' | python3 ~/.omx/hooks/langfuse_hook.py` (Windows에서는 `python3` 대신 `python` 사용)

### 중복 트레이스

훅이 `~/.omx/hooks/langfuse_state.json`에 처리된 턴을 추적합니다. 이 파일을 삭제하면 이전에 전송된 턴이 다시 전송됩니다. 새로 시작하려는 경우에만 상태 파일을 삭제하세요.

## 제거

1. 훅 스크립트 삭제: `rm ~/.omx/hooks/langfuse_hook.py`
2. 인증 정보 제거: `rm ~/.omx/.env`
3. 선택적으로 상태 파일 제거: `rm ~/.omx/hooks/langfuse_state.json`

## 라이선스

[MIT](LICENSE)
