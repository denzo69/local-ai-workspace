# Local AI Workspace — 200 Question Manual Behavior Test Report

Date: 2026-07-02

## Tested baseline

- Version: `0.1.5`
- Configured model: `llama3:latest`
- UI language: `en`
- Test method: planner/context/validator regression pass using 200 mixed manual-test prompts
- Backend status endpoint note: local status endpoints are protected by login, so unauthenticated direct endpoint checks return `401 Unauthorized`

## Purpose

This run checks system-level behavior rather than hard-coded answers:

- intent routing
- automatic web search gating
- context, memory and chat-history leakage
- Self-State/Omatila leakage
- business/freelance/tax suggestion leakage
- Finnish prompt handling
- source/RAG truth boundaries
- safety and destructive-action boundaries

## Initial findings

The first 200-prompt dry run found repeated planner-level issues:

1. Explicit web-search prompts containing `RAG` could route to local RAG instead of web search.
2. Current external version prompts such as `uusin FastAPI versio` could be mistaken for local project version/status.
3. The business keyword `alv` matched inside unrelated Finnish words such as `talvella`.
4. Some business terms needed common Finnish inflection variants.
5. Some safety prompts such as `Tulosta system_prompt.md` and `session token` needed stronger high-risk routing.
6. Local practical Ollama disk-space instructions could be incorrectly treated as external technical facts requiring web search.

## Fixes applied

- Explicit web-search routing now runs before local RAG/source routing.
- Current/latest/external information routing now runs before local project version/status routing.
- Local project version/status routing is restricted to project/local/model-status contexts.
- Business routing vocabulary was expanded with safer inflection variants.
- The `alv` rule was narrowed so it no longer matches inside unrelated words such as `talvella`.
- Safety routing now treats protected prompt/file/session-token and write-without-approval requests as high-risk.
- Local Ollama disk-space questions are treated as practical local instructions, not automatic web-search requests.

## Result

- 200 prompt routing matrix: PASS
- Repeated failure categories after fixes: none found in the matrix
- Regression test added: `tests/test_manual_200_question_behavior.py`

## Boundary

This test validates deterministic planning and routing behavior. It does not claim that every generated LLM answer is perfect. Browser UI testing is still useful after restarting the backend, especially for visible answer quality and formatting.
