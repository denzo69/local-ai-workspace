# Response Planning Layer

Local AI Workspace uses a Response Planning Layer to choose the response path before tools, memory, RAG, Self-State or web search are used.

The goal is to avoid endless single-prompt patching. Regression prompts are examples of behavior categories, not hard-coded answer scripts.

## Why this layer exists

Earlier behavior showed that simple prompts could route to the wrong subsystem:

- date questions could trigger web search;
- permission questions could trigger unrelated human-rights style sources;
- Finnish language capability questions could trigger Self-State output;
- lifestyle questions could receive unrelated business, tax or freelance suggestions;
- Self-State and business-support templates could leak into unrelated answers.

These are planning failures, not isolated prompt failures. The assistant needs to classify the user message first, choose the response path second, generate the answer third, and validate the visible output before returning it.

## Target flow

```text
User message
  -> Intent Planner
  -> Context Gate
  -> Tool / memory / web / self-state decision
  -> Response Contract
  -> Assistant answer
  -> Output Validator
  -> Final answer
```

## Intent categories

Initial supported intents:

- `safety_secret_request`
- `destructive_action_request`
- `assistant_permissions`
- `self_state_request`
- `project_status_request`
- `date_time`
- `version_or_model_status`
- `finnish_language_capability`
- `general_knowledge`
- `health_lifestyle_general`
- `business_support`
- `current_external_weather`
- `current_external_information`
- `source_or_rag_question`
- `normal_chat`
- `unknown`

The planner is deterministic and does not call the LLM.

## Routing priority

Priority order:

1. Safety, secrets and destructive actions
2. Assistant permissions and tool boundaries
3. Self-State and project status
4. Local deterministic facts such as date, time, version and model status
5. Finnish language capability
6. General knowledge
7. Health and lifestyle general advice
8. Business and freelance support
9. Current external or source-dependent information
10. Web search
11. Normal chat fallback

Web search is not the first reflex. It is allowed when the planner marks the prompt as current, external or source-dependent, or when the user explicitly asks for web search.

## Context gating rules

The planner controls broad context domains:

- business/tax/freelance suggestions are blocked unless the prompt is business-related;
- Self-State is blocked unless the user asks for Self-State, project status or technical status;
- web search is blocked for simple date, general knowledge and lifestyle questions;
- memory and RAG should not be used blindly for unrelated prompts.

Example:

```text
Onko kaksi kuppia kahvia liikaa aamulla?
```

Expected planning:

```json
{
  "intent": "health_lifestyle_general",
  "needs_web": false,
  "use_self_state": false,
  "allow_business_suggestions": false,
  "blocked_context_domains": ["business", "tax", "contracts", "accounting", "freelance", "project_status", "self_state", "debug", "web_search"]
}
```

## Response contracts

Each intent defines allowed and forbidden behavior.

Examples:

| Intent | Response mode | Web | Forbidden |
|---|---|---:|---|
| `date_time` | `direct_answer` | no | web search, source list, business suggestions |
| `assistant_permissions` | `capability_boundary` | no | human-rights source drift, business suggestions, Self-State dump |
| `general_knowledge` | `general_answer` | no | unnecessary web search, source list |
| `current_external_weather` | `source_bounded_answer` | yes | unsourced factual weather values |
| `health_lifestyle_general` | `general_cautious_advice` | no | business suggestions, Self-State dump |

## Output validation

The output validator checks the visible draft answer for obvious mismatches:

- health/lifestyle answers must not contain tax, invoicing or freelance suggestions;
- date/time answers must not contain web-search boilerplate;
- assistant permission answers must not drift into unrelated human-rights sources;
- Finnish language capability answers must not dump Self-State;
- Self-State must not appear unless the planner allows it.

The validator does not expose hidden reasoning. It only inspects the final visible text.

## Correct routing examples

| Prompt | Intent | Expected route |
|---|---|---|
| `Mikä päivä nyt on?` | `date_time` | local/server time, no web |
| `onko talvella lunta?` | `general_knowledge` | general answer, no web |
| `Onko sinulle annettu mitä oikeuksia?` | `assistant_permissions` | tool/capability boundary, no web |
| `Entä suomenkielen taito sinulla?` | `finnish_language_capability` | natural Finnish capability answer |
| `Onko kaksi kuppia kahvia liikaa aamulla?` | `health_lifestyle_general` | cautious lifestyle answer, no business suggestions |
| `Onko Lieksassa nyt lunta?` | `current_external_weather` | web/source-bounded route |
| `Voinko saada apua laskutusmallin kanssa freelancer-työhön?` | `business_support` | business support allowed |

## Blocked leakage examples

Blocked in normal mode:

- `DTA`, `verokortti`, `laskutusmalli` in coffee or health answers;
- `Verkkohaku`, `DuckDuckGo`, `Tarkista lähteet` in date/time answers;
- `Oikeusministeriö`, `perusoikeudet`, `ihmisoikeudet` in assistant permission answers;
- `Self-State`, `Omatila`, document registry dumps in Finnish language capability answers.

## Portfolio value

This layer demonstrates AI engineering reliability:

- deterministic intent routing before tool use;
- safer tool and context selection;
- fewer one-off prompt patches;
- clearer safety boundaries;
- testable behavior regressions;
- maintainable architecture as the assistant grows.

