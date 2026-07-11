from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from app.api.catalog_schemas import (
    PublicCaseStudyEnvelope,
    PublicCaseStudyListEnvelope,
    PublicProductEnvelope,
    PublicProductListEnvelope,
)
from app.services.catalog_store import CatalogStore

router = APIRouter(prefix="/public/cards/{slug}", tags=["Public Catalog"])
CardSlug = Annotated[
    str,
    Path(min_length=3, max_length=96, pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$"),
]
ContentSlug = Annotated[
    str,
    Path(min_length=3, max_length=96, pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$"),
]


def _store(request: Request) -> CatalogStore:
    override = getattr(request.app.state, "catalog_store", None)
    if override is not None:
        return override
    return CatalogStore(request.app.state.session_factory)


@router.get(
    "/products",
    response_model=PublicProductListEnvelope,
    operation_id="listPublicCardProducts",
)
async def list_public_products(
    slug: CardSlug,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PublicProductListEnvelope:
    records, total = await _store(request).list_public_products(
        card_slug=slug,
        limit=limit,
        offset=offset,
    )
    return PublicProductListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.get(
    "/products/{id}",
    response_model=PublicProductEnvelope,
    operation_id="getPublicCardProduct",
)
async def get_public_product(
    slug: CardSlug,
    id: ContentSlug,
    request: Request,
) -> PublicProductEnvelope:
    record = await _store(request).get_public_product(
        card_slug=slug,
        product_slug=id,
    )
    return PublicProductEnvelope(data=record)


@router.get(
    "/case-studies",
    response_model=PublicCaseStudyListEnvelope,
    operation_id="listPublicCardCaseStudies",
)
@router.get(
    "/cases",
    response_model=PublicCaseStudyListEnvelope,
    operation_id="listPublicCardCases",
)
async def list_public_case_studies(
    slug: CardSlug,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PublicCaseStudyListEnvelope:
    records, total = await _store(request).list_public_case_studies(
        card_slug=slug,
        limit=limit,
        offset=offset,
    )
    return PublicCaseStudyListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.get(
    "/case-studies/{id}",
    response_model=PublicCaseStudyEnvelope,
    operation_id="getPublicCardCaseStudy",
)
@router.get(
    "/cases/{id}",
    response_model=PublicCaseStudyEnvelope,
    operation_id="getPublicCardCase",
)
async def get_public_case_study(
    slug: CardSlug,
    id: ContentSlug,
    request: Request,
) -> PublicCaseStudyEnvelope:
    record = await _store(request).get_public_case_study(
        card_slug=slug,
        case_study_slug=id,
    )
    return PublicCaseStudyEnvelope(data=record)


__all__ = ["router"]
