"""Deterministic review checks for a Deployment manifest.

Every check is a pure function of the parsed manifest. Nothing here talks
to a cluster, and nothing here deploys anything — the result is a verdict
and a list of findings for a human to act on.
"""
from __future__ import annotations

from .diff import compare_manifests
from .models import SEVERITY_RANK, Container, Finding, Manifest, ReviewResult
from .yaml_lite import parse_documents

# Sample cluster capacity used for the requests-vs-capacity check. These are
# demo constants, not a live cluster: 3 nodes x 4 CPU / 8 Gi.
CLUSTER_CPU = 12.0
CLUSTER_MEMORY_MI = 24576


def parse_cpu(value) -> float | None:
    """Parse a Kubernetes CPU quantity to cores. '500m' -> 0.5, '2' -> 2.0."""
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith("m"):
        try:
            return float(text[:-1]) / 1000.0
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_memory_mi(value) -> int | None:
    """Parse a Kubernetes memory quantity to Mi. '512Mi' -> 512, '1Gi' -> 1024."""
    if value is None:
        return None
    text = str(value).strip()
    for suffix, factor in (("Gi", 1024), ("Mi", 1), ("G", 1000), ("M", 1), ("Ki", 1 / 1024)):
        if text.endswith(suffix):
            try:
                return int(float(text[: -len(suffix)]) * factor)
            except ValueError:
                return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _container_from_dict(data: dict) -> Container:
    env: dict[str, str] = {}
    for entry in data.get("env") or []:
        if isinstance(entry, dict) and "name" in entry:
            env[str(entry["name"])] = str(entry.get("value", ""))
    ports = []
    for entry in data.get("ports") or []:
        if isinstance(entry, dict) and "containerPort" in entry:
            ports.append(int(entry["containerPort"]))
    resources = data.get("resources") or {}
    security = data.get("securityContext") or {}
    return Container(
        name=str(data.get("name", "unnamed")),
        image=str(data.get("image", "")),
        env=env,
        ports=ports,
        limits=dict(resources.get("limits") or {}),
        requests=dict(resources.get("requests") or {}),
        readiness_probe="readinessProbe" in data,
        liveness_probe="livenessProbe" in data,
        privileged=bool(security.get("privileged", False)),
        security_context_present=bool(security),
        read_only_root_filesystem=security.get("readOnlyRootFilesystem"),
    )


def manifest_from_documents(documents: list[dict]) -> Manifest | None:
    """Extract the Deployment (and PDB coverage) from parsed YAML documents."""
    deployment = None
    has_pdb = False
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") == "PodDisruptionBudget":
            has_pdb = True
        if doc.get("kind") == "Deployment":
            deployment = doc
    if deployment is None:
        return None
    metadata = deployment.get("metadata") or {}
    labels = metadata.get("labels") or {}
    spec = deployment.get("spec") or {}
    template = spec.get("template") or {}
    pod_spec = template.get("spec") or {}
    containers = [_container_from_dict(c) for c in (pod_spec.get("containers") or [])]
    return Manifest(
        name=str(metadata.get("name", "unknown")),
        namespace=str(metadata.get("namespace", "prod")),
        replicas=int(spec.get("replicas", 1) or 1),
        critical=str(labels.get("critical", "false")).lower() == "true",
        containers=containers,
        has_pdb=has_pdb,
    )


def _check_container(container: Container, manifest: Manifest) -> list[Finding]:
    findings: list[Finding] = []
    name = container.name

    # Image: :latest (or untagged) is a blocking finding — you cannot roll
    # back to, or reproduce, "latest".
    if not container.image:
        findings.append(Finding(
            id="image-missing", severity="CRITICAL", category="image",
            message=f"Container {name} has no image set.",
            recommendation="Set an explicit image with a pinned tag or digest.",
        ))
    elif ":" not in container.image or container.image.endswith(":latest"):
        findings.append(Finding(
            id="image-latest", severity="CRITICAL", category="image",
            message=f"Container {name} uses image {container.image} "
                    "(untagged or :latest).",
            recommendation="Pin the image to an explicit version tag or digest, "
                           "e.g. checkout-api:2.4.2.",
        ))

    # Resources: limits are the guardrail that stops one container taking a
    # node down (the OOMKilled the triage agent keeps finding).
    if not container.limits.get("cpu") or not container.limits.get("memory"):
        findings.append(Finding(
            id="limits-missing", severity="HIGH", category="resources",
            message=f"Container {name} has no resource limits set.",
            recommendation="Set cpu and memory limits, e.g. cpu 500m / memory 512Mi, "
                           "and validate them under load.",
        ))
    if not container.requests.get("cpu") or not container.requests.get("memory"):
        findings.append(Finding(
            id="requests-missing", severity="MEDIUM", category="resources",
            message=f"Container {name} has no resource requests set.",
            recommendation="Set cpu and memory requests so the scheduler places "
                           "the pod on a node that can actually run it.",
        ))
    req_cpu = parse_cpu(container.requests.get("cpu"))
    lim_cpu = parse_cpu(container.limits.get("cpu"))
    if req_cpu is not None and lim_cpu is not None and req_cpu > lim_cpu:
        findings.append(Finding(
            id="requests-exceed-limits", severity="HIGH", category="resources",
            message=f"Container {name} requests more CPU ({container.requests.get('cpu')}) "
                    f"than its limit ({container.limits.get('cpu')}).",
            recommendation="Raise the CPU limit above the request, or lower the request.",
        ))

    # Probes: without them Kubernetes cannot tell a live pod from a stuck one.
    if not container.readiness_probe:
        findings.append(Finding(
            id="readiness-probe-missing", severity="MEDIUM", category="probes",
            message=f"Container {name} has no readiness probe.",
            recommendation="Add a readiness probe (e.g. HTTP GET /health) so traffic "
                           "only reaches pods that are ready to serve it.",
        ))
    if not container.liveness_probe:
        findings.append(Finding(
            id="liveness-probe-missing", severity="MEDIUM", category="probes",
            message=f"Container {name} has no liveness probe.",
            recommendation="Add a liveness probe (e.g. HTTP GET /health) so a stuck "
                           "container is restarted instead of serving errors.",
        ))

    # Security: privileged is never acceptable in this review; a missing
    # securityContext is a medium finding, not a blocker.
    if container.privileged:
        findings.append(Finding(
            id="privileged-container", severity="CRITICAL", category="security",
            message=f"Container {name} runs privileged.",
            recommendation="Remove privileged: true. If the workload truly needs "
                           "elevated access, document why and get it approved separately.",
        ))
    elif not container.security_context_present:
        findings.append(Finding(
            id="security-context-missing", severity="MEDIUM", category="security",
            message=f"Container {name} has no securityContext.",
            recommendation="Add a securityContext: runAsNonRoot, readOnlyRootFilesystem, "
                           "and drop unnecessary capabilities.",
        ))
    elif container.read_only_root_filesystem is False:
        findings.append(Finding(
            id="writable-root-filesystem", severity="LOW", category="security",
            message=f"Container {name} has a writable root filesystem.",
            recommendation="Set readOnlyRootFilesystem: true and mount a writable "
                           "volume only where the app needs one.",
        ))
    return findings


def _check_manifest(manifest: Manifest) -> list[Finding]:
    findings: list[Finding] = []
    for container in manifest.containers:
        findings.extend(_check_container(container, manifest))

    # Replicas: a critical workload on one replica is one node failure away
    # from an outage.
    if manifest.critical and manifest.replicas < 2:
        findings.append(Finding(
            id="single-replica-critical", severity="HIGH", category="replicas",
            message=f"Critical workload {manifest.name} runs a single replica.",
            recommendation="Run at least 2 replicas for a critical workload, spread "
                           "across availability zones.",
        ))
    if not manifest.has_pdb and manifest.critical:
        findings.append(Finding(
            id="pdb-missing", severity="MEDIUM", category="pdb",
            message=f"Critical workload {manifest.name} has no PodDisruptionBudget.",
            recommendation="Add a PodDisruptionBudget (e.g. minAvailable: 1) so voluntary "
                           "disruptions cannot take the workload down.",
        ))

    # Capacity: total requests across replicas vs the demo cluster capacity.
    total_cpu = 0.0
    total_mem = 0
    for container in manifest.containers:
        cpu = parse_cpu(container.requests.get("cpu"))
        mem = parse_memory_mi(container.requests.get("memory"))
        if cpu is not None:
            total_cpu += cpu * manifest.replicas
        if mem is not None:
            total_mem += mem * manifest.replicas
    if total_cpu > CLUSTER_CPU:
        findings.append(Finding(
            id="capacity-cpu", severity="HIGH", category="capacity",
            message=f"Total CPU requests ({total_cpu:.2f} cores) exceed the cluster "
                    f"capacity ({CLUSTER_CPU:.0f} cores).",
            recommendation="Lower requests, raise the replica budget, or add node capacity "
                           "before deploying.",
        ))
    if total_mem > CLUSTER_MEMORY_MI:
        findings.append(Finding(
            id="capacity-memory", severity="HIGH", category="capacity",
            message=f"Total memory requests ({total_mem}Mi) exceed the cluster "
                    f"capacity ({CLUSTER_MEMORY_MI}Mi).",
            recommendation="Lower requests, or add node capacity before deploying.",
        ))
    return findings


def review_change(change_text: str, baseline_text: str | None = None) -> ReviewResult:
    """Review a manifest change. ``baseline_text`` enables diff checks."""
    documents = parse_documents(change_text)
    manifest = manifest_from_documents(documents)
    if manifest is None:
        return ReviewResult(
            workload="unknown", namespace="prod", verdict="BLOCK",
            findings=[Finding(
                id="no-deployment", severity="CRITICAL", category="diff",
                message="No Deployment manifest found in the change.",
                recommendation="Provide a Deployment manifest to review.",
            )],
        )
    findings = _check_manifest(manifest)
    baseline_compared = False
    if baseline_text:
        baseline = manifest_from_documents(parse_documents(baseline_text))
        if baseline is not None:
            findings.extend(compare_manifests(baseline, manifest))
            baseline_compared = True
    findings.sort(key=lambda f: SEVERITY_RANK[f.severity])
    severities = {f.severity for f in findings}
    if "CRITICAL" in severities:
        verdict = "BLOCK"
    elif "HIGH" in severities:
        verdict = "APPROVE WITH CONDITIONS"
    else:
        verdict = "APPROVE"
    return ReviewResult(
        workload=manifest.name,
        namespace=manifest.namespace,
        verdict=verdict,
        findings=findings,
        baseline_compared=baseline_compared,
    )
