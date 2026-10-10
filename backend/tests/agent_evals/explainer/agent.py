"""The Customer Explainer agent exactly as the orchestrator builds it (ADK eval entry point)."""

from app.agents.explainer_agent import build_agent
from app.config import get_settings

get_settings().export_sdk_env()
root_agent = build_agent()
