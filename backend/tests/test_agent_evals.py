"""ADK eval sets (tests/agent_evals/): valid ADK EvalSets with 3 golden cases per agent, in sync
with the agents' input builders; the custom metric; and (live) the evals themselves through
ADK's AgentEvaluator: `uv --directory backend run pytest -m live -k agent_evals`."""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest
from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.evaluator import EvalStatus
from google.genai import types

from tests.agent_evals import build_evalsets as build
from tests.agent_evals.metrics import check, expectations


@pytest.mark.parametrize("agent", build.AGENTS)
def test_eval_set_is_valid_current_and_has_three_cases(agent: str) -> None:
    folder = build.HERE / agent
    for name, content in build.render(agent).items():
        on_disk = (folder / name).read_text(encoding="utf-8")
        assert on_disk == content, f"run `python -m tests.agent_evals.build_evalsets` ({name})"
    eval_set = EvalSet.model_validate_json((folder / f"{agent}.test.json").read_text())
    assert len(eval_set.eval_cases) == 3
    for case in eval_set.eval_cases:
        [turn] = case.conversation or []
        assert turn.final_response and turn.final_response.parts
        assert isinstance(json.loads(turn.final_response.parts[0].text or ""), dict)


@pytest.mark.parametrize("agent", ["evidence", "explainer", "casefile"])
def test_agent_modules_expose_root_agent(agent: str) -> None:
    module = importlib.import_module(f"tests.agent_evals.{agent}")
    assert module.agent.root_agent.name == f"{agent}_agent"


async def test_intel_module_builds_the_agent_with_its_tools() -> None:
    module = importlib.import_module("tests.agent_evals.intel")
    agent, stack = await module.agent.get_agent_async()
    with stack:
        assert agent.name == "intel_agent"
        assert {t.name for t in agent.tools} == {"watchlist_lookup", "search_agent"}


# --- the metric --------------------------------------------------------------------------

OUT = {
    "typology_guess": "JOB_TASK",
    "typology_confidence": 0.9,
    "injection_attempt_detected": False,
    "red_flags": [{"code": "PAY_TO_EARN", "severity": "HIGH"}, {"code": "URGENCY"}],
    "headline": "Please pause and check",
    "body": "This looks like a known job scam.",
    "recommended_action": "HOLD",
    "web_findings": [],
}


@pytest.mark.parametrize(
    ("rules", "tools", "failed"),
    [
        ({"typology_guess": "JOB_TASK", "typology_confidence": 0.75}, [], 0),
        ({"typology_guess": "NONE"}, [], 1),
        ({"typology_confidence": 0.95}, [], 1),  # numbers are minimums
        ({"injection_attempt_detected": False}, [], 0),
        ({"red_flags": [{"code": "PAY_TO_EARN", "severity": "HIGH"}]}, [], 0),
        ({"red_flags": [{"code": "SAFE_ACCOUNT"}]}, [], 1),
        ({"$one_of": {"recommended_action": ["HOLD", "REPORT_SCAM"]}}, [], 0),
        ({"$one_of": {"recommended_action": ["RELEASE"]}}, [], 1),
        ({"$language": "en", "$max_len": {"headline": 4}}, [], 0),
        ({"$language": "zh"}, [], 2),  # headline and body are English
        ({"$max_len": {"body": 3}}, [], 1),
        ({"$contains": {"body": ["JOB SCAM"]}, "$not_contains": {"*": ["http"]}}, [], 0),
        ({"$not_contains": {"*": ["known job scam"]}}, [], 1),
        ({"$max_items": {"web_findings": 0}}, [], 0),
        ({"$tools_called": ["search_agent"]}, ["search_agent"], 0),
        ({"$tools_called": ["search_agent"]}, [], 1),
        ({"$tools_not_called": ["search_agent"]}, ["search_agent"], 1),
    ],
)
def test_check(rules: dict[str, Any], tools: list[str], failed: int) -> None:
    assert len(check(rules, OUT, tools)) == failed


def test_check_language_and_invalid_json() -> None:
    zh = {"headline": "为保护您，转账已暂停", "body": "真正的官员绝不会要求您转账。"}
    assert check({"$language": "zh", "$max_len": {"headline": 16, "body": 120}}, zh, []) == []
    assert check({"$max_len": {"headline": 5}, "$language": "zh"}, zh, []) != []
    assert check({}, None, []) == ["the answer is not valid JSON"]


def _invocation(text: str, *, tools: tuple[str, ...] = ()) -> Invocation:
    return Invocation(
        invocation_id="i",
        user_content=types.Content(role="user", parts=[types.Part.from_text(text="in")]),
        final_response=types.Content(role="model", parts=[types.Part.from_text(text=text)]),
        intermediate_data=IntermediateData(
            tool_uses=[types.FunctionCall(name=t, args={}) for t in tools]
        ),
    )


def test_expectations_metric_scores_each_invocation() -> None:
    metric = EvalMetric(metric_name=build.METRIC, threshold=1.0)
    rules = json.dumps({"typology_guess": "JOB_TASK", "$tools_called": ["search_agent"]})
    good = _invocation("```json\n" + json.dumps(OUT) + "\n```", tools=("search_agent",))
    bad = _invocation("not json")
    passed = expectations(metric, [good], [_invocation(rules)])
    assert passed.overall_score == 1.0 and passed.overall_eval_status == EvalStatus.PASSED
    mixed = expectations(metric, [good, bad], [_invocation(rules), _invocation(rules)])
    assert mixed.overall_score == 0.5 and mixed.overall_eval_status == EvalStatus.FAILED
    assert [r.eval_status for r in mixed.per_invocation_results] == [
        EvalStatus.PASSED,
        EvalStatus.FAILED,
    ]
    assert expectations(metric, [], []).overall_eval_status == EvalStatus.FAILED


# --- live: the golden cases through ADK's AgentEvaluator ----------------------------------


@pytest.mark.live
@pytest.mark.parametrize("agent", build.AGENTS)
async def test_agent_evals_live(agent: str) -> None:
    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    await AgentEvaluator.evaluate(
        agent_module=f"tests.agent_evals.{agent}",
        eval_dataset_file_path_or_dir=str(build.HERE / agent),
        num_runs=1,
    )
