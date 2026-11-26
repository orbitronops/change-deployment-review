# Security

## What the reviewer can do

- Read a manifest file you give it (and an optional baseline file).
- Print a review report (text, Markdown, or JSON).
- Exit with code 1 when the verdict is BLOCK, so a CI pipeline can gate on it.

## What the reviewer cannot do

- It has no network access in the demo path.
- It cannot run `kubectl`, shell commands, or any mutating Kubernetes action.
- It cannot apply, delete, restart, scale, drain, cordon, or edit any workload.
- It stores no credentials. There is no place to put a token or API key in the demo.

## Human-in-the-loop

Every `ReviewResult` has:

- `requires_human_approval: true`
- `action_executed: false`

That is not a flag you can flip in config — there is no execution path at all in v0.1.0. A future live connector must keep that gate: review, log, wait for a named approver, then (and only then) let a separate, explicitly approved deploy step run, and log that too.

## Reporting a problem

Open an issue in this repo. Do not include real cluster credentials, real customer data, or real manifests with secrets in any issue or example.
