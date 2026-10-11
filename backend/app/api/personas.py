"""GET /personas: the demo customers for the persona picker (Firestore `personas/`).

Public: it is what the picker shows before anyone signs in, and the personas are synthetic.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ServicesDep
from app.models.schemas import Persona

router = APIRouter(tags=["customer"])


@router.get("/personas", response_model=list[Persona], summary="Demo personas")
async def list_personas(services: ServicesDep) -> list[Persona]:
    """Mrs Tan (cust_001, zh), Raj (cust_002) and Aisyah (cust_003), with their stories."""
    return await services.state.list_personas()
