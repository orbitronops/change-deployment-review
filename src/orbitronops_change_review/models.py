"""Data models for the change / deployment review agent.

Plain dataclasses, no dependencies. A review is advisory: it never applies
anything, and a real deployment always waits for a human approver.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
VERDICTS = ("APPROVE", "APPROVE WITH CONDITIONS", "BLOCK")


@dataclass
class Finding:
    """One review finding, ordered by severity in the report."""

    id: str
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    category: str  # image | resources | replicas | probes | security | pdb | diff | capacity
    message: str
    recommendation: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "recommendation": self.recommendation,
        }


@dataclass
class Container:
    name: str
    image: str = ""
    env: dict = field(default_factory=dict)
    ports: list[int] = field(default_factory=list)
    limits: dict = field(default_factory=dict)
    requests: dict = field(default_factory=dict)
    readiness_probe: bool = False
    liveness_probe: bool = False
    privileged: bool = False
    security_context_present: bool = False
    read_only_root_filesystem: bool | None = None


@dataclass
class Manifest:
    """A Deployment parsed from a manifest file, plus whether a PDB covers it."""

    name: str
    namespace: str = "prod"
    replicas: int = 1
    critical: bool = False
    containers: list[Container] = field(default_factory=list)
    has_pdb: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "replicas": self.replicas,
            "critical": self.critical,
            "has_pdb": self.has_pdb,
            "containers": [
                {
                    "name": c.name,
                    "image": c.image,
                    "env": c.env,
                    "ports": c.ports,
                    "limits": c.limits,
                    "requests": c.requests,
                    "readiness_probe": c.readiness_probe,
                    "liveness_probe": c.liveness_probe,
                    "privileged": c.privileged,
                    "read_only_root_filesystem": c.read_only_root_filesystem,
                }
                for c in self.containers
            ],
        }


@dataclass
class ReviewResult:
    """The review outcome. Advisory only — a human decides whether to deploy."""

    workload: str
    namespace: str
    verdict: str  # APPROVE | APPROVE WITH CONDITIONS | BLOCK
    findings: list[Finding] = field(default_factory=list)
    baseline_compared: bool = False
    requires_human_approval: bool = True
    action_executed: bool = False

    @property
    def counts(self) -> dict[str, int]:
        counts = {sev: 0 for sev in SEVERITY_RANK}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "workload": self.workload,
            "namespace": self.namespace,
            "verdict": self.verdict,
            "baseline_compared": self.baseline_compared,
            "findings": [f.to_dict() for f in self.findings],
            "counts": self.counts,
            "requires_human_approval": self.requires_human_approval,
            "action_executed": self.action_executed,
        }
