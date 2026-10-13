"""Pure builders for the authority JSON, statistics, and text report."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from processors.entity_authority.entities import Entity


def _record(e: Entity) -> dict:
    return {
        "appearances": list(e.sources),
        "contexts": list(e.contexts),
        "entity_type": e.type,
        "original_forms": list(e.original_forms),
        "clustered_variants": list(e.variants),
        "frequency": len(e.sources),
    }


def generate_statistics(entities: list[Entity]) -> dict:
    by_type: dict = defaultdict(int)
    by_freq: dict = defaultdict(int)
    examples: dict = defaultdict(list)
    with_variants = merged = 0
    for e in entities:
        by_type[e.type] += 1
        if len(examples[e.type]) < 3:
            examples[e.type].append(e.name)
        if len(e.variants) > 1:
            with_variants += 1
            merged += len(e.variants) - 1
        f = len(e.sources)
        if f == 1:
            by_freq["single_mention"] += 1
        elif 2 <= f <= 3:
            by_freq["low_frequency"] += 1
        elif 4 <= f <= 10:
            by_freq["medium_frequency"] += 1
        elif f > 10:
            by_freq["high_frequency"] += 1
    return {"by_type": dict(by_type), "by_frequency": dict(by_freq),
            "type_examples": dict(examples),
            "clustering_stats": {"entities_with_variants": with_variants,
                                 "total_variants_merged": merged}}


def build_authority_file(entities: list[Entity], *, created: str,
                         library: Optional[str] = None,
                         threshold: float = 85) -> dict:
    return {
        "metadata": {
            "created": created,
            "source": "Texas ScholarWorks dissertations",
            "total_entities": len(entities),
            "extraction_method": "Named Entities from Step 1 metadata (with type classification)",
            "fuzzy_matching": {"enabled": library is not None, "library": library,
                               "similarity_threshold": threshold},
            "entity_types": list({e.type for e in entities}),
        },
        "entities": {e.name: _record(e) for e in entities},
        "statistics": generate_statistics(entities),
    }


def render_report(stats: dict, entities: list[Entity], *, generated: str,
                  library: Optional[str] = None, threshold: float = 85) -> str:
    out = ["DISSERTATION ENTITY AUTHORITY REPORT", "=" * 50, "",
           f"Generated: {generated}", f"Total Entities: {len(entities)}"]
    fuzzy = f"Fuzzy Matching: {'Enabled' if library else 'Disabled'}"
    if library:
        fuzzy += f" ({library}, threshold: {threshold}%)"
    out += [fuzzy, ""]
    cs = stats["clustering_stats"]
    if library and cs["entities_with_variants"] > 0:
        out += ["FUZZY MATCHING RESULTS:", "-" * 25,
                f"  Entities with variants: {cs['entities_with_variants']}",
                f"  Total variants merged: {cs['total_variants_merged']}", ""]
    out += ["ENTITY TYPE BREAKDOWN:", "-" * 25]
    for t, c in sorted(stats["by_type"].items(), key=lambda x: x[1], reverse=True):
        out.append(f"  {t.upper().replace('_', ' ')}: {c} entities")
    out.append("")
    grouped: dict[str, list[Entity]] = defaultdict(list)
    for e in entities:
        grouped[e.type].append(e)
    for t in sorted(grouped):
        group = sorted(grouped[t], key=lambda e: len(e.sources), reverse=True)
        out += [f"{t.upper().replace('_', ' ')} ({len(group)} entities):", "-" * 40]
        for e in group:
            out += [f"  {e.name}", f"    Frequency: {len(e.sources)} appearances"]
            others = [v for v in e.variants if v != e.name]
            if len(e.variants) > 1 and others:
                out.append(f"    Variants: {', '.join(others)}")
            if len(e.original_forms) > 1:
                out.append(f"    Forms: {', '.join(e.original_forms)}")
            if e.sources:
                line = f"    Appearances: {', '.join(e.sources[:5])}"
                if len(e.sources) > 5:
                    line += f" ... (+{len(e.sources) - 5} more)"
                out.append(line)
            out.append("")
    return "\n".join(out) + "\n"
