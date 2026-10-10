"""Custom ADK eval metric for the golden cases: `expectations`.

Our agents answer in JSON, so instead of ROUGE against a reference answer, each eval case's
`final_response` holds an *expectations* object that the agent's actual JSON must satisfy:

    {"typology_guess": "JOB_TASK",                    plain key: equal (numbers: actual >= value)
     "red_flags": [{"code": "PAY_TO_EARN"}],          list: every item matches some actual item
     "$one_of": {"recommended_action": ["HOLD", "REPORT_SCAM"]},
     "$language": "zh",                                every string field is in that language
     "$max_len": {"headline": 16},                     words (en) or characters (zh)
     "$contains": {"*": ["mas-gov-verify"]},           case-insensitive; "*" = the whole answer
     "$not_contains": {"body": ["you are being scammed"]},
     "$max_items": {"web_findings": 0},
     "$tools_called": ["search_agent"], "$tools_not_called": ["search_agent"]}

A case passes when every expectation holds (score 1.0); test_config.json requires 1.0.
"""

from __future__ import annotations

import json
import re
from typing import Any

from google.adk.evaluation.conversation_scenarios import ConversationScenario
from google.adk.evaluation.eval_case import Invocation, get_all_tool_calls
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.evaluator import EvalStatus, EvaluationResult, PerInvocationResult
from google.genai import types

_CJK = re.compile(r"[一-鿿]")


def _text(content: types.Content | None) -> str:
    if content is None:
        return ""
    return "".join(p.text or "" for p in content.parts or [] if not p.thought)


def _json(text: str) -> Any:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and _matches(v, actual[k]) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and all(
            any(_matches(e, a) for a in actual) for e in expected
        )
    if isinstance(expected, bool) or expected is None:
        return expected is actual
    if isinstance(expected, int | float):
        return isinstance(actual, int | float) and actual >= expected
    return expected == actual


def _field(output: Any, name: str) -> Any:
    return output if name == "*" else (output or {}).get(name)


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _size(text: str, language: str) -> int:
    return len(re.sub(r"\s", "", text)) if language == "zh" else len(text.split())


def check(expectations: dict[str, Any], output: Any, tools: list[str]) -> list[str]:
    """Every expectation that does not hold, as a readable string (empty list = pass)."""
    if output is None:
        return ["the answer is not valid JSON"]
    failures = []
    language = expectations.get("$language", "en")
    for key, want in expectations.items():
        if key == "$one_of":
            failures += [
                f"{f}={_field(output, f)!r} not in {opts}"
                for f, opts in want.items()
                if _field(output, f) not in opts
            ]
        elif key == "$language":
            for s in _strings(output):
                has_cjk = bool(_CJK.search(s))
                if (want == "zh") != has_cjk and len(s.split()) > 1:
                    failures.append(f"not in {want}: {s[:40]!r}")
        elif key == "$max_len":
            for f, n in want.items():
                size = _size(_as_text(_field(output, f)), language)
                if size > n:
                    failures.append(f"{f} is {size} long (max {n})")
        elif key in ("$contains", "$not_contains"):
            for f, subs in want.items():
                text = _as_text(_field(output, f)).casefold()
                for sub in subs:
                    if (sub.casefold() in text) != (key == "$contains"):
                        failures.append(f"{f} {key[1:]} {sub!r} failed")
        elif key == "$max_items":
            failures += [
                f"{f} has more than {n} items"
                for f, n in want.items()
                if len(_field(output, f) or []) > n
            ]
        elif key == "$tools_called":
            failures += [f"tool {t} was not called" for t in want if t not in tools]
        elif key == "$tools_not_called":
            failures += [f"tool {t} was called" for t in want if t in tools]
        elif not _matches(want, _field(output, key)):
            failures.append(f"{key}: expected {want!r}, got {_field(output, key)!r}")
    return failures


def expectations(
    eval_metric: EvalMetric,
    actual_invocations: list[Invocation],
    expected_invocations: list[Invocation] | None = None,
    conversation_scenario: ConversationScenario | None = None,
) -> EvaluationResult:
    """The ADK custom-metric entry point (see test_config.json)."""
    results = []
    for actual, expected in zip(actual_invocations, expected_invocations or [], strict=False):
        rules = _json(_text(expected.final_response)) or {}
        tools = [c.name or "" for c in get_all_tool_calls(actual.intermediate_data)]
        failures = check(rules, _json(_text(actual.final_response)), tools)
        if failures:
            print(f"[{eval_metric.metric_name}] {actual.invocation_id}: {failures}")
        results.append(
            PerInvocationResult(
                actual_invocation=actual,
                expected_invocation=expected,
                score=0.0 if failures else 1.0,
                eval_status=EvalStatus.FAILED if failures else EvalStatus.PASSED,
            )
        )
    scores = [r.score or 0.0 for r in results]
    overall = sum(scores) / len(scores) if scores else 0.0
    return EvaluationResult(
        overall_score=overall,
        overall_eval_status=EvalStatus.PASSED if scores and overall == 1.0 else EvalStatus.FAILED,
        per_invocation_results=results,
    )
