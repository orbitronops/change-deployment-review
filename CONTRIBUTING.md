# Contributing

Thanks for looking at this OrbitronOps demo.

## Ground rules

1. **Read-only stays read-only.** No PR may add a step that applies, deletes, restarts, or scales anything. The review only ever produces a verdict and findings. The test `test_no_mutating_commands_anywhere` enforces this.
2. **No fake client claims.** Do not add a case study, logo, or testimonial for work that did not happen. This is a demo prototype.
3. **Every new check needs a test.** Add the manifest to `examples/` if it is a good demo, and a test in `tests/test_review.py`.

## Running it locally

```bash
python -m orbitronops_change_review review examples/risky-change.yaml --baseline examples/baseline.yaml
python -m orbitronops_change_review review examples/safe-change.yaml --baseline examples/baseline.yaml
python -m pytest -q
```
