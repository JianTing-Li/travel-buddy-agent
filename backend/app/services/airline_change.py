"""Shape of an airline change shown to the traveler, shared by the mock and (later) Duffel sources. Owner: Jian.

Not part of contract/models.py. Duffel's airline-initiated changes are time shifts; the mock service can also
cancel. A change is tracked by change_id so the same one is never shown twice.
"""
from typing import Literal

from pydantic import BaseModel

from ..contract.models import DataSource


class AirlineChange(BaseModel):
    change_id: str
    booking_id: str
    kind: Literal["cancellation", "delay"]
    summary: str
    detected_at: str  # ISO timestamp in UTC
    data_source: DataSource
    simulated: bool = True
