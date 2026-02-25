# oh-my-codex (OMX) 한국어 README

> 전체 원문 문서는 [English README](./README.md)를 참고하세요.

OMX는 OpenAI Codex CLI를 위한 멀티 에이전트 오케스트레이션 레이어입니다.

## Langfuse 연동 저장소 상태 (2026년 2월 25일)

- ✅ [`langfuse-oh-my-codex`](https://github.com/BAEM1N/langfuse-oh-my-codex)
- ✅ [`langfuse-claude-code`](https://github.com/BAEM1N/langfuse-claude-code)
- ✅ [`langfuse-gemini-cli`](https://github.com/BAEM1N/langfuse-gemini-cli)
- ✅ [`langfuse-opencode`](https://github.com/BAEM1N/langfuse-opencode)
- ✅ 저장소 최종 정리 완료 (불필요 추적 파일 없음)
- ✅ Langfuse companion 패키징 기준 `v0.0.1` 릴리즈/태그 정리 완료
- 진행 문서: [English](./PROGRESS.md) | [한국어](./PROGRESS.ko.md)

## 빠른 시작

```bash
npm install -g oh-my-codex
omx setup
omx doctor
```

## 핵심 기능

- 역할 프롬프트(`/prompts:name`) 기반 전문 에이전트 실행
- 워크플로우 스킬(`$name`) 기반 반복 작업 자동화
- tmux 팀 오케스트레이션(`omx team`, `$team`)
- MCP 서버를 통한 상태/메모리 지속성

## 주요 명령어

```bash
omx
omx setup
omx doctor
omx team <args>
omx status
omx cancel
```

## 더 알아보기

- 메인 문서: [README.md](./README.md)
- 웹사이트: https://yeachan-heo.github.io/oh-my-codex-website/
