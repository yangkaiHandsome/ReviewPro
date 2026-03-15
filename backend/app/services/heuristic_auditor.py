from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.models import Rule
from app.schemas import AuditResultPayload, PageTextBlock, ReviewPlan


def _extract_tokens(text: str) -> List[str]:
    raw_tokens = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", text.lower())
    stopwords = {
        "must",
        "should",
        "document",
        "rule",
        "format",
        "requirements",
        "review",
        "check",
        "page",
        "the",
        "and",
        "for",
    }
    return [token for token in raw_tokens if token not in stopwords]


def _first_bbox(blocks: List[PageTextBlock]) -> List[float]:
    if not blocks:
        return [20.0, 20.0, 220.0, 120.0]
    return list(blocks[0].bbox)


def run_heuristic_audit(
    rules: List[Rule],
    review_plan: ReviewPlan,
    page_blocks: Dict[int, List[PageTextBlock]],
) -> Tuple[List[AuditResultPayload], List[str]]:
    results: List[AuditResultPayload] = []
    logs: List[str] = ["Using local deterministic heuristic auditor."]
    all_pages_text: Dict[int, str] = {
        page: " ".join(block.text for block in blocks).lower() for page, blocks in page_blocks.items()
    }

    selected_pages = [item.page for item in review_plan.selected_pages]
    if not selected_pages:
        return [], logs

    for rule in rules:
        tokens = _extract_tokens("{} {}".format(rule.title, rule.description))
        found_page = None
        match_token = None
        for page in selected_pages:
            text = all_pages_text.get(page, "")
            for token in tokens:
                if token and token in text:
                    found_page = page
                    match_token = token
                    break
            if found_page is not None:
                break

        if found_page is not None:
            blocks = page_blocks.get(found_page, [])
            message = (
                "Rule '{}' has evidence on page {} (keyword: {}). "
                "Manual confirmation is still recommended.".format(rule.title, found_page, match_token)
            )
            results.append(
                AuditResultPayload(
                    rule_id=rule.id,
                    page=found_page,
                    bbox=_first_bbox(blocks),
                    content=message,
                    suggestion="Auto match found. Keep manual validation in the final review.",
                    status="pass",
                    severity=rule.severity,
                )
            )
            continue

        fallback_page = selected_pages[0]
        fallback_blocks = page_blocks.get(fallback_page, [])
        result_status = "fail" if rule.is_required else "pass"
        issue = (
            "No clear evidence found in sampled pages."
            if result_status == "fail"
            else "No evidence found, but rule is optional so it is tentatively passed."
        )
        results.append(
            AuditResultPayload(
                rule_id=rule.id,
                page=fallback_page,
                bbox=_first_bbox(fallback_blocks),
                content="Rule '{}': {}".format(rule.title, issue),
                suggestion="Increase sampled pages or run focused manual inspection.",
                status=result_status,
                severity=rule.severity,
            )
        )

    return results, logs


def normalize_model_results(raw_results: List[Dict[str, Any]]) -> List[AuditResultPayload]:
    normalized: List[AuditResultPayload] = []
    for item in raw_results:
        normalized.append(
            AuditResultPayload(
                rule_id=str(item["rule_id"]),
                page=int(item["page"]),
                bbox=[float(v) for v in item["bbox"]],
                content=str(item["content"]),
                suggestion=str(item["suggestion"]),
                status=str(item["status"]),
                severity=str(item.get("severity", "medium")),
            )
        )
    return normalized
