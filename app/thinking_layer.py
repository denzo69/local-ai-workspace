from __future__ import annotations

"""Safe deliberation and creativity scaffolding for Local AI Workspace.

This layer does not make the system conscious and it must not expose hidden
chain-of-thought. It gives the response pipeline a compact instruction block
for better conversation: choose the right stance, consider alternatives when
useful, check the final answer against the user's actual question, and keep
tool/source boundaries intact.
"""

from dataclasses import asdict, dataclass
from typing import Any
import unicodedata


CREATIVE_TERMS = (
    "ideoi",
    "keksi",
    "luova",
    "luovasti",
    "suunnittele",
    "brainstorm",
    "nimi",
    "tarina",
    "vaihtoehto",
    "konsepti",
    "visio",
)

DELIBERATIVE_TERMS = (
    "kumpi",
    "vertaa",
    "arvioi",
    "punnitse",
    "kannattaako",
    "paras",
    "hyödyt",
    "haitat",
    "riskit",
    "priorisoi",
)

CONVERSATIONAL_TERMS = (
    "entä",
    "enta",
    "jatka",
    "miten se",
    "miksi se",
    "siihen",
    "siitä",
    "siita",
    "tuohon",
    "niistä",
    "niista",
)


@dataclass(frozen=True)
class ThinkingDirective:
    mode: str
    creativity: str
    use_alternatives: bool
    use_sources: bool
    use_conversation_context: bool
    self_check: list[str]
    public_style: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = _ascii(text)
    return any(term in lower for term in terms)


def _decision_attr(decision: Any, name: str, default: Any = None) -> Any:
    if isinstance(decision, dict):
        return decision.get(name, default)
    return getattr(decision, name, default)


def build_thinking_directive(message: str, decision: Any) -> ThinkingDirective:
    intent = str(_decision_attr(decision, "intent", "") or "")
    needs_web = bool(_decision_attr(decision, "needs_web", False))
    use_rag = bool(_decision_attr(decision, "use_rag", False))
    use_chat_context = bool(_decision_attr(decision, "use_chat_context", False))

    creative = _contains_any(message, CREATIVE_TERMS)
    deliberative = _contains_any(message, DELIBERATIVE_TERMS)
    conversational = use_chat_context or _contains_any(message, CONVERSATIONAL_TERMS)

    if intent in {"safety_secret_request", "destructive_action_request"}:
        mode = "safety_boundary"
    elif needs_web or use_rag or intent in {"current_external_information", "current_external_weather"}:
        mode = "source_grounded"
    elif creative:
        mode = "creative_exploration"
    elif deliberative:
        mode = "deliberative_comparison"
    elif conversational:
        mode = "contextual_conversation"
    elif intent.startswith("project") or intent in {"self_state_request", "version_or_model_status"}:
        mode = "project_aware"
    else:
        mode = "natural_conversation"

    self_check = [
        "Answer the user's current question, not an unrelated remembered topic.",
        "Use only context domains allowed by the planner.",
        "Do not expose hidden chain-of-thought; show only the final answer.",
    ]
    if mode == "source_grounded":
        self_check.append("Separate source-supported facts from cautious interpretation.")
    if mode == "creative_exploration":
        self_check.append("Offer several useful options, then recommend one if appropriate.")
    if mode == "deliberative_comparison":
        self_check.append("Compare options by practical criteria before giving a recommendation.")
    if mode == "contextual_conversation":
        self_check.append("Resolve pronouns and follow-ups from the latest visible chat topic.")
    if mode == "safety_boundary":
        self_check.append("Refuse unsafe or secret-revealing requests briefly and helpfully.")

    return ThinkingDirective(
        mode=mode,
        creativity="high" if creative else "normal",
        use_alternatives=creative or deliberative,
        use_sources=needs_web or use_rag,
        use_conversation_context=use_chat_context,
        self_check=self_check,
        public_style=(
            "warm, natural, and concise; ask a short follow-up question only when it materially helps"
        ),
    )


def build_thinking_context(message: str, decision: Any) -> str:
    directive = build_thinking_directive(message, decision)
    checks = "\n".join(f"- {item}" for item in directive.self_check)
    return f"""
Response thinking layer:
- Mode: {directive.mode}
- Creativity: {directive.creativity}
- Use alternatives: {directive.use_alternatives}
- Use source grounding: {directive.use_sources}
- Use conversation context: {directive.use_conversation_context}
- Public style: {directive.public_style}

Internal final-answer check:
{checks}

Important boundary:
Do not show hidden chain-of-thought or private scratchpad reasoning. Use this layer only to improve the visible final answer.
""".strip()
