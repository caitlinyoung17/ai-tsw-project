"""Plain-text cleanup report."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Optional, Sequence

from .detection import FailedItem


@dataclass(frozen=True)
class ItemOutcome:
    failed: FailedItem
    fixed: bool
    error: Optional[str] = None


def render_cleanup_report(outcomes: Sequence[ItemOutcome]) -> str:
    fixed = sum(1 for o in outcomes if o.fixed)
    lines = ["TSW STEP 1.5 - BATCH CLEANUP REPORT", "=" * 40, "",
             f"Failed items detected: {len(outcomes)}",
             f"Successfully reprocessed: {fixed}",
             f"Still failed: {len(outcomes) - fixed}", ""]
    if outcomes:
        lines.append("FAILURE TYPES:")
        for reason, n in Counter(o.failed.reason.value for o in outcomes).most_common():
            lines.append(f"  - {reason}: {n} items")
        lines += ["", "DETAILED ITEMS:", "-" * 25]
        for i, o in enumerate(outcomes, 1):
            name = o.failed.item.get("filename", "Unknown")
            lines.append(f"{i:3d}. Item {o.failed.index + 1}: {name}")
            lines.append(f"     Reason: {o.failed.reason.value}")
            status = "Reprocessed" if o.fixed else f"Failed to reprocess ({o.error})"
            lines.append(f"     Status: {status}")
    else:
        lines.append("No items needed reprocessing.")
    return "\n".join(lines) + "\n"
