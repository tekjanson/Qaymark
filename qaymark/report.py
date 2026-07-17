"""Shared per-attempt report structure."""

from __future__ import annotations

from dataclasses import dataclass

from .hygiene import HygieneResult
from .idud_bridge import IdudResult
from .operations import OperationOutcome


@dataclass
class AttemptReport:
    attempt: int
    validation_ok: bool
    validation_output: str
    hygiene: HygieneResult
    idud: IdudResult
    operations: OperationOutcome

    def passed(self) -> bool:
        return self.validation_ok and self.hygiene.passed
