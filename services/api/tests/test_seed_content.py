from __future__ import annotations

from pathlib import Path

import pytest

from app.cli.seed_content import deterministic_id, load_content_package

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "filename,expected_documents",
    [("template.knowledge.json", 5), ("tuotu.knowledge.json", 10)],
)
def test_content_packages_validate(filename: str, expected_documents: int) -> None:
    package = load_content_package(ROOT / "packages" / "tenant-content" / filename)

    assert package.card.slug == package.company.slug
    assert len(package.documents) == expected_documents
    assert all(document.content for document in package.documents)


def test_seed_identifiers_are_stable_and_tenant_specific() -> None:
    assert deterministic_id("tuotu", "company") == deterministic_id("tuotu", "company")
    assert deterministic_id("tuotu", "company") != deterministic_id("template", "company")
