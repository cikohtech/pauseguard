"""Cloud Trace for the agents (the agent trace in the deck and video).

ADK already opens an OpenTelemetry span for every agent run, model call and tool call
(`invoke_agent`, `call_llm`, `execute_tool`). On Cloud Run we export them to Cloud Trace through
telemetry.googleapis.com (OTLP over HTTP; `roles/cloudtrace.agent` includes
`telemetry.traces.write`). The API adds one parent span per check-in answer (`pauseguard.check`,
analysis.py), so one check is one trace: evidence ∥ watchlist → fusion → explainer → case file ∥
Scam-Intel search.

Message content stays out of the spans (`ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`, as
`adk deploy` sets it): the evidence is customer data (SECURITY_PRIVACY §2). Spans carry IDs,
model names, token counts and timings only. Off locally unless CLOUD_TRACE=true.
"""

from __future__ import annotations

import os

from opentelemetry import trace

from app.config import Settings
from app.log import get_logger

log = get_logger(__name__)
tracer = trace.get_tracer("pauseguard")

_enabled = False


def setup_tracing(settings: Settings) -> bool:
    """Once per process. Never raises: tracing must not stop the API from starting."""
    global _enabled
    if _enabled or not settings.cloud_trace_enabled:
        return _enabled
    os.environ.setdefault("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "false")
    try:
        from google.adk.telemetry.google_cloud import get_gcp_exporters, get_gcp_resource
        from google.adk.telemetry.setup import maybe_set_otel_providers

        hooks = get_gcp_exporters(enable_cloud_tracing=True)
        resource = get_gcp_resource(settings.google_cloud_project)
        maybe_set_otel_providers([hooks], otel_resource=resource)
    except Exception:
        log.exception("cloud_trace_setup_failed")
        return False
    _enabled = True
    log.info("cloud_trace_enabled", project=settings.google_cloud_project)
    return True
