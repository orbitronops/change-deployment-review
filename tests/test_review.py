"""Tests for the change / deployment review engine. Run: python -m pytest -q"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbitronops_change_review.checks import review_change  # noqa: E402
from orbitronops_change_review.report import render_markdown, render_text  # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _manifest(image="registry.example.com/checkout-api:2.4.2", replicas=3,
              limits=True, requests=True, probes=True, security=True,
              critical=True, env=("DATABASE_URL", "REDIS_URL"), port=8080,
              pdb=True, privileged=False):
    env_lines = "\n".join(
        f"            - name: {name}\n              value: x" for name in env
    )
    resources = ""
    if limits or requests:
        resources = "          resources:\n"
        if limits:
            resources += '            limits:\n              cpu: "500m"\n              memory: 512Mi\n'
        if requests:
            resources += '            requests:\n              cpu: "250m"\n              memory: 256Mi\n'
    probes = ""
    if probes:
        probes = ("          readinessProbe:\n            httpGet:\n"
                  "              path: /health\n              port: 8080\n"
                  "          livenessProbe:\n            httpGet:\n"
                  "              path: /health\n              port: 8080\n")
    sec = ""
    if security:
        sec = ("          securityContext:\n"
               f"            privileged: {'true' if privileged else 'false'}\n"
               "            readOnlyRootFilesystem: true\n")
    pdb_doc = ""
    if pdb:
        pdb_doc = ("\n---\napiVersion: policy/v1\nkind: PodDisruptionBudget\n"
                   "metadata:\n  name: checkout-api\n  namespace: prod\n"
                   "spec:\n  minAvailable: 2\n")
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
  namespace: prod
  labels:
    app: checkout-api
    critical: "{'true' if critical else 'false'}"
spec:
  replicas: {replicas}
  template:
    spec:
      containers:
        - name: checkout-api
          image: {image}
          ports:
            - containerPort: {port}
          env:
{env_lines}
{resources}{probes}{sec}{pdb_doc}"""


def _finding_ids(result):
    return {f.id for f in result.findings}


def test_safe_change_approves():
    result = review_change((EXAMPLES / "safe-change.yaml").read_text())
    assert result.verdict == "APPROVE"
    assert result.findings == []
    assert result.requires_human_approval is True
    assert result.action_executed is False


def test_safe_change_vs_baseline_stays_approve():
    baseline = (EXAMPLES / "baseline.yaml").read_text()
    result = review_change((EXAMPLES / "safe-change.yaml").read_text(), baseline)
    assert result.verdict == "APPROVE"
    assert result.baseline_compared is True
    # The only diff is the image bump — a LOW finding, not a blocker.
    assert _finding_ids(result) == {"image-changed"}


def test_risky_change_blocks():
    result = review_change((EXAMPLES / "risky-change.yaml").read_text())
    assert result.verdict == "BLOCK"
    ids = _finding_ids(result)
    assert "image-latest" in ids
    assert "limits-missing" in ids
    assert "single-replica-critical" in ids
    assert "readiness-probe-missing" in ids
    assert "pdb-missing" in ids
    assert result.counts["CRITICAL"] >= 1


def test_risky_change_vs_baseline_flags_breaking_diffs():
    baseline = (EXAMPLES / "baseline.yaml").read_text()
    result = review_change((EXAMPLES / "risky-change.yaml").read_text(), baseline)
    assert result.verdict == "BLOCK"
    ids = _finding_ids(result)
    assert "env-var-removed" in ids
    assert "replicas-lowered" in ids
    assert "port-changed" in ids
    assert "limits-removed" in ids


def test_latest_image_flagged():
    result = review_change(_manifest(image="registry.example.com/checkout-api:latest"))
    assert result.verdict == "BLOCK"
    assert "image-latest" in _finding_ids(result)


def test_missing_limits_flagged():
    result = review_change(_manifest(limits=False))
    assert "limits-missing" in _finding_ids(result)
    assert result.verdict == "APPROVE WITH CONDITIONS"


def test_single_replica_flagged_for_critical_workload():
    result = review_change(_manifest(replicas=1))
    assert "single-replica-critical" in _finding_ids(result)


def test_single_replica_not_flagged_for_non_critical_workload():
    result = review_change(_manifest(replicas=1, critical=False, pdb=False))
    assert "single-replica-critical" not in _finding_ids(result)
    assert "pdb-missing" not in _finding_ids(result)


def test_removed_env_var_flagged_vs_baseline():
    baseline = _manifest()
    change = _manifest(env=("REDIS_URL",))
    result = review_change(change, baseline)
    assert "env-var-removed" in _finding_ids(result)
    assert result.verdict == "APPROVE WITH CONDITIONS"


def test_requests_exceeding_limits_flagged():
    text = _manifest().replace('cpu: "250m"', 'cpu: "1000m"', 1)
    result = review_change(text)
    assert "requests-exceed-limits" in _finding_ids(result)


def test_privileged_container_blocks():
    result = review_change(_manifest(privileged=True))
    assert "privileged-container" in _finding_ids(result)
    assert result.verdict == "BLOCK"


def test_capacity_check_flags_huge_requests():
    text = _manifest().replace('cpu: "250m"', 'cpu: "5000m"', 1)
    text = text.replace("memory: 256Mi", "memory: 10000Mi", 1)
    result = review_change(text)
    assert "capacity-cpu" in _finding_ids(result) or "capacity-memory" in _finding_ids(result)


def test_empty_manifest_is_blocked_not_a_crash():
    result = review_change("")
    assert result.verdict == "BLOCK"
    assert "no-deployment" in _finding_ids(result)


def test_json_output_is_valid():
    result = review_change((EXAMPLES / "risky-change.yaml").read_text())
    data = json.loads(json.dumps(result.to_dict()))
    assert data["verdict"] == "BLOCK"
    assert data["action_executed"] is False
    assert data["requires_human_approval"] is True
    assert data["counts"]["CRITICAL"] >= 1
    assert all("recommendation" in f for f in data["findings"])


def test_text_and_markdown_render_the_verdict():
    result = review_change((EXAMPLES / "risky-change.yaml").read_text())
    assert "Verdict: BLOCK" in render_text(result)
    assert "Human approval: REQUIRED" in render_text(result)
    assert "Verdict:** BLOCK" in render_markdown(result)


def test_no_mutating_commands_anywhere():
    banned = ("kubectl apply", "kubectl delete", "kubectl scale",
              "kubectl drain", "kubectl cordon", "kubectl rollout restart")
    src = Path(__file__).resolve().parents[1] / "src"
    for path in src.rglob("*.py"):
        assert "subprocess" not in path.read_text(), path
    result = review_change((EXAMPLES / "risky-change.yaml").read_text())
    rendered = render_text(result) + render_markdown(result)
    for cmd in banned:
        assert cmd not in rendered, cmd
    for finding in result.findings:
        for cmd in banned:
            assert cmd not in finding.recommendation, finding.recommendation
