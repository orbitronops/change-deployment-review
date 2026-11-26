# Architecture

## Design goals

1. **A stranger can run it in 2 minutes** — no API key, no cluster, no cloud bill.
2. **Deterministic** — same change in, same verdict out. No hidden randomness in the demo path.
3. **Safe by construction** — the reviewer cannot deploy anything. There is no code path that calls `kubectl apply` or any other mutating command, and the tests enforce that.

## Flow

```
Change manifest (YAML)
  → yaml_lite.parse_documents()   # no-dependency YAML-subset parser
  → checks.manifest_from_documents()  # Deployment + PodDisruptionBudget
  → checks._check_manifest()      # image, resources, replicas, probes, security, PDB, capacity
  → diff.compare_manifests()      # only when --baseline is given
  → report.render_text() / render_markdown() / JSON
  → CLI prints the verdict; exit code 1 only when the verdict is BLOCK
```

## Verdict logic

| Findings present | Verdict |
| --- | --- |
| Any CRITICAL | BLOCK |
| Any HIGH, no CRITICAL | APPROVE WITH CONDITIONS |
| Only MEDIUM / LOW, or none | APPROVE |

Severity is a property of the finding, not of the workload: `:latest` is always CRITICAL because an unpinned image cannot be rolled back to or reproduced, while a missing liveness probe is MEDIUM because the workload still runs — it just cannot detect a stuck pod.

## The YAML parser

The demo has no dependencies, so it ships `yaml_lite.py`, a parser for the YAML subset used in `examples/`: multi-document files, nested mappings, lists of scalars or mappings, and plain/quoted scalars. It deliberately raises `ValueError` on anything outside that subset (tabs, anchors, flow collections) instead of silently mis-parsing a manifest. A production version would use PyYAML; the checks themselves only see plain Python dicts, so swapping the parser is a one-file change.

## Extension points

| Want to add… | Where |
|---|---|
| A new check | A new block in `checks._check_container()` or `checks._check_manifest()` + a test in `tests/test_review.py` |
| A new diff rule | A new block in `diff.compare_manifests()` + a test |
| A real YAML parser | Replace `yaml_lite.parse_documents()` with PyYAML; the rest of the code is unchanged |
| Live cluster reads | A new `connectors/kubernetes.py` that fetches the live Deployment and feeds it to `review_change()` as the baseline |
| GitHub / GitLab PR review | A new `connectors/pr.py` that posts the rendered Markdown as a review comment — still read-only, still no deploy |
| LLM explainer | A new `llm.py` with a `summarise(result) -> str` interface. It must only reword the findings — it must not change the verdict, severities, or execute anything. Off by default, bring your own key. |

## What this is not (yet)

- Not a live admission controller — the demo reads manifest files, not a real API server.
- Not a deploy tool — there is intentionally no apply path.
- Not a client delivery — see README Status. It is a prototype that shows how OrbitronOps builds.
