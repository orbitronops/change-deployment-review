"""Render a ReviewResult as text, Markdown, or JSON (via to_dict)."""
from __future__ import annotations

from .models import ReviewResult


def render_text(result: ReviewResult) -> str:
    lines = [
        f"Change review: {result.workload} (namespace: {result.namespace})",
        f"Verdict: {result.verdict}",
        f"Findings: {len(result.findings)}  "
        f"(CRITICAL {result.counts['CRITICAL']}, HIGH {result.counts['HIGH']}, "
        f"MEDIUM {result.counts['MEDIUM']}, LOW {result.counts['LOW']})",
    ]
    if result.baseline_compared:
        lines.append("Baseline: compared against the baseline manifest.")
    lines.append("")
    if result.findings:
        lines.append("Findings (most severe first):")
        for finding in result.findings:
            lines.append(f"  [{finding.severity}] {finding.message}")
            lines.append(f"    -> {finding.recommendation}")
    else:
        lines.append("No findings. The change passes every check in this review.")
    lines += [
        "",
        "Human approval: REQUIRED — nothing was deployed by this review.",
        "This tool only reviews. A real deployment waits for a named approver.",
    ]
    return "\n".join(lines)


def render_markdown(result: ReviewResult) -> str:
    lines = [
        f"# Change review: {result.workload}",
        "",
        f"- **Namespace:** {result.namespace}",
        f"- **Verdict:** {result.verdict}",
        f"- **Findings:** {len(result.findings)} "
        f"(CRITICAL {result.counts['CRITICAL']}, HIGH {result.counts['HIGH']}, "
        f"MEDIUM {result.counts['MEDIUM']}, LOW {result.counts['LOW']})",
        f"- **Baseline compared:** {'yes' if result.baseline_compared else 'no'}",
        "",
    ]
    if result.findings:
        lines.append("## Findings")
        lines.append("")
        for finding in result.findings:
            lines.append(f"### [{finding.severity}] {finding.message}")
            lines.append("")
            lines.append(f"Recommendation: {finding.recommendation}")
            lines.append("")
    else:
        lines.append("No findings. The change passes every check in this review.")
        lines.append("")
    lines += [
        "## Human approval",
        "",
        "REQUIRED — nothing was deployed by this review. "
        "A real deployment waits for a named approver.",
        "",
    ]
    return "\n".join(lines)
