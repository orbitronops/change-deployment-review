# OrbitronOps Change / Deployment Review

> **A read-only change / deployment review agent for Kubernetes / platform teams.**
> It reviews a deployment change before it ships — image, resources, replicas,
> probes, security, and what changed vs the baseline — and returns a verdict:
> APPROVE, APPROVE WITH CONDITIONS, or BLOCK. It never deploys anything.

[![CI](https://github.com/orbitronops/change-deployment-review/actions/workflows/ci.yml/badge.svg)](https://github.com/orbitronops/change-deployment-review/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Demo](https://img.shields.io/badge/status-demo%20%E2%80%94%20not%20client%20work-lightgrey.svg)](#status)

**By [OrbitronOps](https://www.orbitronops.com)** — Production AI Infrastructure on Kubernetes.
North Vancouver, BC · Canada Remote / BC Hybrid

---

## What this proves

A buyer doesn't have to take our word for it. They can run this in 2 minutes:

```bash
git clone https://github.com/orbitronops/change-deployment-review.git
cd change-deployment-review
python -m orbitronops_change_review review examples/risky-change.yaml --baseline examples/baseline.yaml
```

And get a review like this (the risky change is blocked):

```
Change review: checkout-api (namespace: prod)
Verdict: BLOCK
Findings: 15  (CRITICAL 1, HIGH 7, MEDIUM 6, LOW 1)
Baseline: compared against the baseline manifest.

Findings (most severe first):
  [CRITICAL] Container checkout-api uses image registry.example.com/checkout-api:latest (untagged or :latest).
    -> Pin the image to an explicit version tag or digest, e.g. checkout-api:2.4.2.
  [HIGH] Container checkout-api has no resource limits set.
    -> Set cpu and memory limits, e.g. cpu 500m / memory 512Mi, and validate them under load.
  [HIGH] Critical workload checkout-api runs a single replica.
    -> Run at least 2 replicas for a critical workload, spread across availability zones.
  [HIGH] Environment variable DATABASE_URL was removed.
    -> Confirm the app no longer needs DATABASE_URL, or restore it before deploying.
  [HIGH] Replicas lowered from 3 to 1.
    -> Confirm the lower replica count still meets the availability target, or keep the baseline replica count.

Human approval: REQUIRED — nothing was deployed by this review.
This tool only reviews. A real deployment waits for a named approver.
```

The full output is in [`examples/sample-output.txt`](examples/sample-output.txt).

The same tool approves the safe change — a pinned image bump to `2.4.2` with a raised memory limit — with one LOW finding (the image changed vs the baseline, so verify it is the tested build):

```bash
python -m orbitronops_change_review review examples/safe-change.yaml --baseline examples/baseline.yaml
# Verdict: APPROVE — Findings: 1 (LOW 1)
```

No API key needed for the demo. No cluster needed. No cloud bill.

## Why review before shipping?

Most of the incidents the triage agent sees start as a change: an unpinned image, a removed env var, a dropped limit, a single replica. This reviewer catches those at the pull-request stage, when fixing them costs minutes instead of an incident.

1. **Read-only** — it reads manifest files. It has no deploy path at all.
2. **Deterministic** — same change in, same verdict out.
3. **Human-in-the-loop** — every result carries `requires_human_approval: true` and `action_executed: false`. A BLOCK exits with code 1, so a CI pipeline can gate on it, but a human still decides.

## Quickstart

**Requirements:** Python 3.10+ only. No dependencies for the demo.

```bash
# 1. Clone
git clone https://github.com/orbitronops/change-deployment-review.git
cd change-deployment-review

# 2. Review the risky change (BLOCK, exit code 1)
python -m orbitronops_change_review review examples/risky-change.yaml --baseline examples/baseline.yaml

# 3. Review the safe change (APPROVE)
python -m orbitronops_change_review review examples/safe-change.yaml --baseline examples/baseline.yaml

# 4. Or JSON / Markdown, for tooling
python -m orbitronops_change_review review examples/risky-change.yaml --baseline examples/baseline.yaml --format json
python -m orbitronops_change_review review examples/safe-change.yaml --format markdown

# 5. Run the tests
python -m pytest -q
# or, with no pytest installed:
python -m unittest discover -s tests -v
```

### Try your own change

Copy an example and edit it:

```bash
cp examples/baseline.yaml my-change.yaml
# edit my-change.yaml, then:
python -m orbitronops_change_review review my-change.yaml --baseline examples/baseline.yaml
```

See [`examples/`](examples/) for the manifest shape, and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the checks and verdict work.

## How it works

```
Change manifest (YAML) → Checks → Verdict + findings
                              → Diff vs baseline (if --baseline given)
                              → Report (text / Markdown / JSON)
```

| Check category | Examples |
| --- | --- |
| Image | `:latest` or untagged image (CRITICAL), image changed vs baseline (LOW) |
| Resources | Missing limits (HIGH), missing requests (MEDIUM), requests above limits (HIGH) |
| Replicas | Single replica on a critical workload (HIGH), replicas lowered (HIGH) |
| Probes | Missing or removed readiness / liveness probe (MEDIUM / HIGH) |
| Security | Privileged container (CRITICAL), missing securityContext (MEDIUM) |
| PDB | No PodDisruptionBudget on a critical workload (MEDIUM) |
| Capacity | Total requests exceed the demo cluster capacity (HIGH) |
| Diff | Env var removed (HIGH), env value changed (MEDIUM), port changed (MEDIUM), limits removed (HIGH) |

Verdict: any CRITICAL → **BLOCK**; any HIGH → **APPROVE WITH CONDITIONS**; otherwise **APPROVE**.

## Project layout

```
.
├── src/orbitronops_change_review/  # the reviewer: models, checks, diff, report, CLI
│   ├── models.py                   # Finding / Manifest / ReviewResult dataclasses
│   ├── yaml_lite.py                # no-dependency YAML-subset parser for the examples
│   ├── checks.py                   # deterministic review checks + verdict
│   ├── diff.py                     # baseline comparison (breaking changes)
│   ├── report.py                   # text / Markdown / JSON rendering
│   └── cli.py                      # `python -m orbitronops_change_review review <file>`
├── examples/                       # baseline + safe + risky changes, sample output
│   ├── baseline.yaml               # checkout-api as it runs today (3 replicas, pinned image)
│   ├── safe-change.yaml            # image bump to 2.4.2, raised memory limit — APPROVE
│   └── risky-change.yaml           # :latest, no limits, 1 replica, env removed — BLOCK
├── tests/                          # 16 tests for every check, diff rule, and verdict
├── docs/
│   ├── ARCHITECTURE.md             # design, verdict logic, extension points
│   └── SECURITY.md                 # what the reviewer can / cannot do
├── .github/workflows/ci.yml        # lint + tests on every push
├── Dockerfile                      # run the demo in a container, no local Python needed
└── pyproject.toml
```

## Status

**Demo — not client work.**

OrbitronOps has not yet delivered a client deployment review using this tool. This repository is a working prototype built to show how we review: the checks, the diff rules, and the verdict a client would actually get. No client names, no client results, and no client data appear anywhere in it.

If you want this wired to *your* pull requests, manifests, and clusters, talk to us: [orbitronops.com](https://www.orbitronops.com) · [LinkedIn](https://www.linkedin.com/company/orbitronops/)

## Roadmap

- Deterministic checks + baseline diff + verdicts + Markdown/JSON reports
- Live cluster reads (fetch the running Deployment as the baseline)
- GitHub / GitLab PR review comments (still read-only, still no deploy)
- Admission-controller mode (webhook that blocks bad changes at the API server)
- Policy packs per team (stricter rules for regulated workloads)
- Optional LLM explainer (pluggable, off by default)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — please keep the read-only rule intact.

## License

MIT — see [LICENSE](LICENSE).
