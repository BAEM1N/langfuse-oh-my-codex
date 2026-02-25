# 진행 현황 (2026-02-25)

## 완료
- Langfuse OMX 훅 구현 및 런타임 훅 경로 동기화 완료.
- 스팬 ms 단위 순서 보정 로직 적용.
- turn-context 노이즈 제어용 `OMX_LANGFUSE_INCLUDE_TURN_CONTEXT_SPANS` 토글 추가.

## 검증
- 훅 문법 검사(`py_compile`) 통과.
- Langfuse API로 최근 트레이스 조회 검증 완료.
- 실제 트레이스로 순서/노이즈 점검 완료.

## 다음
- 필요 시 장기 세션 기준 Langfuse UI 최종 점검.
