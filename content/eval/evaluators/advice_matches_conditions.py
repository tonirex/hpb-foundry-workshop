"""Custom evaluator: does the coach's advice fit the resident's known conditions?

A deterministic code evaluator (no model calls, no tokens), used by content/assets/lab2_evaluate.py next to the
built-in LLM-judged evaluators. Each condition in `conditions` has:

* `address`: evidence that the reply took the condition into account (for example, indoor options on a
  hazy day, or balance and strength for someone over 60);
* `avoid`: advice that contradicts the condition (for example, recommending swimming to someone who dislikes
  it). A sentence that also says "avoid", "don't", "instead of" and similar counts as a warning, not a
  recommendation, so "avoid bubble tea" is fine.

Score 1-5: start at 5, minus 2 per contradicting sentence, minus 1 per condition the reply ignores, floor 1.
Pass at >= 3. Rows without conditions (or a blocked reply) score 5 and say so in the reason.

    from advice_matches_conditions import AdviceMatchesConditionsEvaluator
    AdviceMatchesConditionsEvaluator()(response="...", conditions=["pre_diabetes", "hazy_day"])
"""
from __future__ import annotations

import json
import re

RULES: dict[str, dict[str, str]] = {
    "pre_diabetes": {
        "address": r"blood (sugar|glucose)|pre-?diabet|wholegrain|whole grain|fibre|fiber|brown rice|sugar|carbohydrate",
        "avoid": r"\b(bubble tea|soft drinks?|sweetened drinks?|kaya toast|extra sugar|condensed milk)\b",
    },
    "high_blood_pressure": {
        "address": r"salt|sodium|blood pressure|gravy|sauce|soup",
        "avoid": r"\b(add|extra|more) (salt|soy sauce|sauce|gravy)\b|\bhold(ing)? your breath\b",
    },
    "high_cholesterol": {
        "address": r"cholesterol|fried|saturated|aerobic|brisk|oats|fibre|fiber",
        "avoid": r"\b(deep-fried|fried chicken|goreng|lard|pork lard)\b",
    },
    "age_60_plus": {
        "address": r"balance|strength|pace|gradual|warm[- ]?up|fall|older|after 60|tai ?chi",
        "avoid": r"\b(sprint(s|ing)?|hiit|high-intensity interval|heavy lifting|max(imum)? effort)\b",
    },
    "hazy_day": {
        "address": r"indoor|psi|haze|hazy|air quality|mall|community cent(re|er)|at home",
        "avoid": r"\b(outdoor|outside) (run|jog|workout|cycling|exercise)\b|\b(run|jog|cycle) (outdoors|outside)\b",
    },
    "dislikes_swimming": {
        "address": r"walk|tai ?chi|danc|cycl|strength|brisk|zumba|qigong|class",
        "avoid": r"\b(swim|swimming|aqua|water aerobics|pool)\b",
    },
    "prefers_mornings": {
        "address": r"morning|\bam\b|early|before work|breakfast",
        "avoid": r"\b(evening|night|after dinner|late)\b",
    },
    "low_steps": {
        "address": r"steps|start (small|slow)|gradual|build up|short walk|10[- ]minute|a little more",
        "avoid": r"\b10,?000 steps (right away|immediately|from (day one|the start))\b",
    },
}

_NEGATION = re.compile(r"\b(avoid|don't|do not|not|no|never|skip|instead of|rather than|limit|cut|reduce|less|swap|"
                       r"unless|if you (dislike|don't)|since you (dislike|don't)|stay away|postpone|move .* indoors)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?;\n])\s+|\n+|\s+[-*]\s+")


def _text(response) -> str:
    """Accept a plain reply, a JSON reply (answer / advice / rationale) or a list of messages."""
    if isinstance(response, list):
        response = " ".join(str(m.get("content", m)) if isinstance(m, dict) else str(m) for m in response)
    s = str(response or "")
    try:
        data = json.loads(s)
        if isinstance(data, dict):
            s = " ".join(str(data.get(k, "")) for k in ("answer", "advice", "rationale")) or s
    except (ValueError, TypeError):
        pass
    return s


def _conditions(conditions) -> list[str]:
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except ValueError:
            conditions = [c.strip() for c in conditions.split(",")]
    return [c for c in (conditions or []) if c in RULES]


class AdviceMatchesConditionsEvaluator:
    """Callable evaluator for azure.ai.evaluation.evaluate(): keys advice_matches_conditions(_result/_reason)."""

    id = "livewell.advice_matches_conditions"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def __call__(self, *, response, conditions=None, **kwargs) -> dict:
        conds, text = _conditions(conditions), _text(response)
        if not conds or not text.strip():
            reason = "no known conditions in this row" if not conds else "no advice given (blocked or empty reply)"
            return self._result(5, reason)
        sentences = [s for s in _SENTENCE.split(text) if s.strip()]
        violations, ignored = [], []
        for c in conds:
            rule = RULES[c]
            if not re.search(rule["address"], text, re.I):
                ignored.append(c)
            for s in sentences:
                if re.search(rule["avoid"], s, re.I) and not _NEGATION.search(s):
                    violations.append(f"{c}: '{s.strip()[:80]}'")
        score = max(1, 5 - 2 * len(violations) - len(ignored))
        parts = []
        if violations:
            parts.append("contradicts " + "; ".join(violations))
        if ignored:
            parts.append("ignores " + ", ".join(ignored))
        return self._result(score, "; ".join(parts) or f"fits {', '.join(conds)}")

    def _result(self, score: int, reason: str) -> dict:
        return {"advice_matches_conditions": float(score),
                "advice_matches_conditions_result": "pass" if score >= self.threshold else "fail",
                "advice_matches_conditions_threshold": self.threshold,
                "advice_matches_conditions_reason": reason}


if __name__ == "__main__":
    ev = AdviceMatchesConditionsEvaluator()
    cases = [
        ("Try brisk walking in the morning at the mall; avoid swimming if you dislike it.", ["dislikes_swimming", "prefers_mornings", "hazy_day"]),
        ("Go for a swim in the evening and jog outside.", ["dislikes_swimming", "prefers_mornings", "hazy_day"]),
        ('{"answer": "Choose brown rice and water instead of bubble tea."}', ["pre_diabetes"]),
        ("Any reply", []),
    ]
    for response, conds in cases:
        print(ev(response=response, conditions=conds))
