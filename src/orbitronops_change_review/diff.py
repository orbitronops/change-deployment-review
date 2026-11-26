"""Diff checks: what changed vs the baseline manifest, and is it breaking?

Only the change itself is reviewed by checks.py; this module answers the
second question a reviewer asks — "what is different from what is running
now, and could that difference break it?"
"""
from __future__ import annotations

from .models import Finding, Manifest


def compare_manifests(baseline: Manifest, change: Manifest) -> list[Finding]:
    findings: list[Finding] = []
    if not baseline.containers or not change.containers:
        return findings
    base = baseline.containers[0]
    new = change.containers[0]

    # Replicas lowered: fewer pods serving the same traffic.
    if change.replicas < baseline.replicas:
        findings.append(Finding(
            id="replicas-lowered", severity="HIGH", category="diff",
            message=f"Replicas lowered from {baseline.replicas} to {change.replicas}.",
            recommendation="Confirm the lower replica count still meets the availability "
                           "target, or keep the baseline replica count.",
        ))

    # Env vars removed: the app may fail to start (the config error the
    # triage agent keeps finding in logs).
    for name in sorted(set(base.env) - set(new.env)):
        findings.append(Finding(
            id="env-var-removed", severity="HIGH", category="diff",
            message=f"Environment variable {name} was removed.",
            recommendation=f"Confirm the app no longer needs {name}, or restore it "
                           "before deploying.",
        ))
    for name in sorted(set(base.env) & set(new.env)):
        if base.env[name] != new.env[name]:
            findings.append(Finding(
                id="env-var-changed", severity="MEDIUM", category="diff",
                message=f"Environment variable {name} changed value.",
                recommendation=f"Confirm the new value of {name} is correct for "
                               "this environment before deploying.",
            ))

    # Ports changed: anything calling the old port breaks.
    if base.ports and new.ports and base.ports != new.ports:
        findings.append(Finding(
            id="port-changed", severity="MEDIUM", category="diff",
            message=f"Container port changed from {base.ports} to {new.ports}.",
            recommendation="Confirm services, ingress, and clients use the new port, "
                           "or keep the old one.",
        ))
    elif base.ports and not new.ports:
        findings.append(Finding(
            id="port-removed", severity="MEDIUM", category="diff",
            message=f"Container port {base.ports} was removed.",
            recommendation="Confirm nothing depends on the removed port.",
        ))

    # Image changed: not a failure on its own, but the reviewer should
    # verify the new image is the one that was tested.
    if base.image and new.image and base.image != new.image:
        findings.append(Finding(
            id="image-changed", severity="LOW", category="diff",
            message=f"Image changed from {base.image} to {new.image}.",
            recommendation="Confirm the new image is the tested build and its tag "
                           "is pinned, not :latest.",
        ))

    # Probes removed: the deployment loses its ability to detect a bad pod.
    if base.readiness_probe and not new.readiness_probe:
        findings.append(Finding(
            id="readiness-probe-removed", severity="HIGH", category="diff",
            message="Readiness probe was removed.",
            recommendation="Restore the readiness probe before deploying.",
        ))
    if base.liveness_probe and not new.liveness_probe:
        findings.append(Finding(
            id="liveness-probe-removed", severity="HIGH", category="diff",
            message="Liveness probe was removed.",
            recommendation="Restore the liveness probe before deploying.",
        ))

    # Limits removed: the guardrail against OOMKilled goes away.
    if (base.limits.get("cpu") or base.limits.get("memory")) and not (
        new.limits.get("cpu") or new.limits.get("memory")
    ):
        findings.append(Finding(
            id="limits-removed", severity="HIGH", category="diff",
            message="Resource limits were removed.",
            recommendation="Restore cpu and memory limits before deploying.",
        ))
    return findings
