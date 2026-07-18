"""Shared per-attempt report structure."""

from __future__ import annotations

from dataclasses import dataclass

from .hygiene import HygieneResult
from .reference_bridge import ReferenceResult
from .operations import OperationOutcome


@dataclass
class AttemptReport:
    attempt: int
    validation_ok: bool
    validation_output: str
    hygiene: HygieneResult
    reference: ReferenceResult
    operations: OperationOutcome

    def passed(self) -> bool:
        return self.validation_ok and self.hygiene.passed
