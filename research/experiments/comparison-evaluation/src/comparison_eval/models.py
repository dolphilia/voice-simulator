from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Estimate:
    value: float | None
    confidence: float = 1.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    sample_rate: int
    sample_count: int
    duration_sec: float
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "duration_sec": self.duration_sec,
            "issues": list(self.issues),
        }


@dataclass
class FeatureBundle:
    sample_id: str
    path: str
    sha256: str
    sample_rate: int
    profile: str
    scalar: dict[str, float | None] = field(default_factory=dict)
    estimates: dict[str, Estimate] = field(default_factory=dict)
    frame_series: dict[str, list[float | None]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "path": self.path,
            "sha256": self.sha256,
            "sample_rate": self.sample_rate,
            "profile": self.profile,
            "scalar": self.scalar,
            "estimates": {key: value.to_dict() for key, value in self.estimates.items()},
            "frame_series": self.frame_series,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class MetricResult:
    name: str
    value: float | None
    unit: str
    category: str
    direction: str
    confidence: float = 1.0
    available: bool = True
    reason: str = ""
    signed_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
