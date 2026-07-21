from __future__ import annotations

from typing import Protocol

from .contracts import ReviewBrief, ReviewInput


class ReviewAnalyzer(Protocol):
    def analyze(self, review: ReviewInput) -> ReviewBrief: ...


class DeterministicAnalyzer:
    """Produces a review brief without network or model dependencies."""

    def analyze(self, review: ReviewInput) -> ReviewBrief:
        return ReviewBrief(review=review)
