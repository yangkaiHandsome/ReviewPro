from __future__ import annotations

from app.models import Rule
from app.schemas import PageMeta
from app.services.planning_service import build_review_plan


def test_review_plan_respects_budget_and_coverage():
    rules = [
        Rule(id="R001", strategy_id="S1", title="Glossary", description="Check glossary section", severity="high"),
        Rule(id="R002", strategy_id="S1", title="Version History", description="Check version history", severity="high"),
    ]
    pages = [
        PageMeta(page_number=1, has_text=True, text_preview="Cover", image_density=0.0),
        PageMeta(page_number=2, has_text=True, text_preview="Contents", image_density=0.0, is_toc_like=True),
        PageMeta(page_number=3, has_text=True, text_preview="Glossary", image_density=0.0),
        PageMeta(page_number=4, has_text=True, text_preview="Architecture", image_density=0.0),
        PageMeta(page_number=5, has_text=True, text_preview="Version History", image_density=0.0),
        PageMeta(page_number=6, has_text=True, text_preview="Conclusion", image_density=0.0),
    ]
    plan = build_review_plan(
        rules=rules,
        pages=pages,
        doc_type="text",
        max_page_budget=4,
        budget_ratio=0.5,
        min_review_pages=3,
    )

    assert plan.page_budget == 3
    assert len(plan.selected_pages) == 3
    selected = [item.page for item in plan.selected_pages]
    assert 1 in selected
    assert 2 in selected


def test_text_document_within_budget_reviews_all_pages():
    rules = [
        Rule(id="R001", strategy_id="S1", title="错别字检查", description="检查每一页是否存在错别字", severity="medium"),
    ]
    pages = [
        PageMeta(page_number=1, has_text=True, text_preview="第一页", image_density=0.0),
        PageMeta(page_number=2, has_text=True, text_preview="第二页", image_density=0.0),
        PageMeta(page_number=3, has_text=True, text_preview="第三页", image_density=0.0),
        PageMeta(page_number=4, has_text=True, text_preview="第四页", image_density=0.0),
        PageMeta(page_number=5, has_text=True, text_preview="第五页", image_density=0.0),
    ]

    plan = build_review_plan(
        rules=rules,
        pages=pages,
        doc_type="text",
        max_page_budget=20,
        budget_ratio=0.3,
        min_review_pages=4,
    )

    assert plan.page_budget == 5
    assert [item.page for item in plan.selected_pages] == [1, 2, 3, 4, 5]
