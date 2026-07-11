from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.cli.seed_content import (
    _should_bootstrap_staff,
    deterministic_id,
    load_content_package,
    should_activate_seed_version,
)
from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "filename,expected_documents",
    [("template.knowledge.json", 5), ("tuotu.knowledge.json", 12)],
)
def test_content_packages_validate(filename: str, expected_documents: int) -> None:
    package = load_content_package(ROOT / "packages" / "tenant-content" / filename)

    assert package.card.slug == package.company.slug
    assert len(package.documents) == expected_documents
    assert all(document.content for document in package.documents)
    assert package.forbidden_topics


def test_tuotu_package_bootstraps_the_public_business_catalog() -> None:
    package = load_content_package(
        ROOT / "packages" / "tenant-content" / "tuotu.knowledge.json"
    )

    assert len(package.products) == 4
    assert len(package.case_studies) == 3
    assert [field.field_type for field in package.contact_fields] == ["website"]
    assert {rule.action for rule in package.forbidden_topics} == {
        "refuse",
        "handoff",
        "safe_template",
    }


def test_seed_identifiers_are_stable_and_tenant_specific() -> None:
    assert deterministic_id("tuotu", "company") == deterministic_id("tuotu", "company")
    assert deterministic_id("tuotu", "company") != deterministic_id("template", "company")


def test_admin_bootstrap_is_limited_to_the_explicit_tenant_slug() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        admin_bootstrap_tenant_slug="tuotu",
        admin_bootstrap_account="admin@example.test",
        admin_bootstrap_password="a-strong-bootstrap-password",  # noqa: S106
    )

    assert _should_bootstrap_staff(settings, "tuotu")
    assert not _should_bootstrap_staff(settings, "template")


def test_startup_seed_never_replaces_an_admin_published_version() -> None:
    seed_version_id = uuid.uuid4()

    assert should_activate_seed_version(None, seed_version_id)
    assert should_activate_seed_version(seed_version_id, seed_version_id)
    assert not should_activate_seed_version(uuid.uuid4(), seed_version_id)
