from __future__ import annotations

import math
import re
from collections import defaultdict

from app.models import Rule
from app.schemas import PageMeta, ReviewPlan, ReviewPlanPage


def _keyword_tokens(rules: list[Rule]) -> list[str]:
    tokens: set[str] = set()
    for rule in rules:
        text = f"{rule.title} {rule.description}".lower()
        parts = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", text)
        tokens.update(parts)
    return sorted(tokens)


def _coverage_pages(page_count: int) -> list[int]:
    if page_count <= 0:
        return []
    if page_count <= 4:
        return list(range(1, page_count + 1))

    # Evenly sample pages to guarantee minimal document-wide coverage.
    anchors = {1, page_count}
    segment_count = min(6, max(3, math.ceil(page_count / 5)))
    for idx in range(segment_count):
        pos = round(1 + idx * (page_count - 1) / max(segment_count - 1, 1))
        anchors.add(pos)
    return sorted(anchors)


def build_review_plan(
    rules: list[Rule],
    pages: list[PageMeta],
    doc_type: str,
    max_page_budget: int,
    budget_ratio: float,
    min_review_pages: int,
) -> ReviewPlan:
    page_count = len(pages)
    if page_count == 0:
        return ReviewPlan(page_budget=0, selected_pages=[], notes=["Document has no pages."])

    if doc_type == "text" and page_count <= max_page_budget:
        budget = page_count
    else:
        ratio_budget = max(1, math.ceil(page_count * budget_ratio))
        budget = min(page_count, max(min_review_pages, ratio_budget))
        budget = min(budget, max_page_budget)

    page_map = {p.page_number: p for p in pages}
    reasons: dict[int, str] = {}
    selected: set[int] = set()

    for page in _coverage_pages(page_count):
        selected.add(page)
        reasons[page] = "minimum_coverage"

    toc_pages = [p.page_number for p in pages if p.is_toc_like]
    for page in toc_pages[:2]:
        selected.add(page)
        reasons[page] = "toc_priority"

    keyword_tokens = _keyword_tokens(rules)
    scores: defaultdict[int, int] = defaultdict(int)
    for page in pages:
        preview = page.text_preview.lower()
        for token in keyword_tokens:
            if token in preview:
                scores[page.page_number] += 1

    ranked_pages = sorted(
        pages,
        key=lambda p: (
            scores[p.page_number],
            int(not p.likely_drawing),
            -p.page_number,
        ),
        reverse=True,
    )

    for page in ranked_pages:
        if len(selected) >= budget:
            break
        if page.page_number in selected:
            continue
        selected.add(page.page_number)
        reasons[page.page_number] = "rule_keyword_match"

    # Fill remaining budget with evenly distributed pages.
    if len(selected) < budget:
        for page in _coverage_pages(page_count):
            if len(selected) >= budget:
                break
            if page not in selected:
                selected.add(page)
                reasons[page] = "coverage_fill"

    # Final padding for short docs where evenly sampled anchors collide.
    for page_num in range(1, page_count + 1):
        if len(selected) >= budget:
            break
        if page_num in selected:
            continue
        selected.add(page_num)
        reasons[page_num] = "budget_fill"

    # Respect budget even when minimum coverage anchors exceed it.
    if len(selected) > budget:
        reason_weight = {
            "toc_priority": 0,
            "rule_keyword_match": 1,
            "minimum_coverage": 2,
            "coverage_fill": 3,
            "budget_fill": 4,
        }
        ordered = sorted(
            selected,
            key=lambda page_num: (
                reason_weight.get(reasons.get(page_num, ""), 9),
                -scores.get(page_num, 0),
                page_num,
            ),
        )
        selected = set(ordered[:budget])

    selected_pages: list[ReviewPlanPage] = []
    for page_num in sorted(selected):
        page = page_map[page_num]
        if doc_type == "image":
            depth = "image"
        elif page.likely_drawing:
            depth = "both"
        else:
            depth = "text_blocks"
        selected_pages.append(
            ReviewPlanPage(
                page=page_num,
                depth=depth,
                reason=reasons.get(page_num, "model_choice"),
            )
        )

    warnings: list[str] = []
    if page_count > budget:
        warnings.append(
            f"Page budget limited to {budget}/{page_count}. Consider manual spot checks for skipped pages."
        )

    notes = []
    if doc_type == "image":
        notes.append("Image-heavy document: page review defaults to image mode.")
    elif budget == page_count:
        notes.append("Text document fits within budget, so all pages are reviewed.")
    else:
        notes.append("Text document: text blocks are prioritized for high-precision annotations.")

    return ReviewPlan(
        page_budget=budget,
        selected_pages=selected_pages,
        coverage_warnings=warnings,
        notes=notes,
    )


