"""Stable company brand-mark assignment shared by BI projections."""

from __future__ import annotations

from hashlib import sha256
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BRAND_ICON_CATALOG_VERSION: Final = "simple-icons-v16-us-listed-1"
BRAND_COLOR_COUNT: Final = 12
BRAND_ROTATIONS: Final = (-12, -8, -4, 0, 4, 8, 12)

# Public-company and public-company-owned brands distributed with Simple Icons.
# The order is versioned because persisted snapshots reference icons by slug.
BRAND_ICON_SLUGS: Final = (
    "3m",
    "abbvie",
    "airbnb",
    "amd",
    "americanairlines",
    "apple",
    "arm",
    "atandt",
    "atlassian",
    "autodesk",
    "boeing",
    "bookingdotcom",
    "broadcom",
    "caterpillar",
    "cisco",
    "cloudflare",
    "cocacola",
    "coinbase",
    "datadog",
    "dell",
    "delta",
    "digitalocean",
    "doordash",
    "dropbox",
    "duolingo",
    "ebay",
    "elastic",
    "etsy",
    "expedia",
    "fastly",
    "fedex",
    "ferrari",
    "fiverr",
    "ford",
    "fortinet",
    "generalmotors",
    "gitlab",
    "google",
    "hilton",
    "honda",
    "hp",
    "hubspot",
    "instacart",
    "intel",
    "intuit",
    "jetblue",
    "johndeere",
    "kfc",
    "lucid",
    "lyft",
    "marriott",
    "mastercard",
    "mcdonalds",
    "merck",
    "meta",
    "mongodb",
    "motorola",
    "netflix",
    "nike",
    "nubank",
    "nvidia",
    "okta",
    "palantir",
    "paloaltonetworks",
    "paramountplus",
    "paypal",
    "pinterest",
    "qualcomm",
    "reddit",
    "robinhood",
    "roblox",
    "roku",
    "shopify",
    "snapchat",
    "snowflake",
    "southwestairlines",
    "spotify",
    "starbucks",
    "tacobell",
    "taketwointeractivesoftware",
    "target",
    "tesla",
    "tinder",
    "toyota",
    "tripadvisor",
    "twitch",
    "uber",
    "underarmour",
    "unitedairlines",
    "unity",
    "ups",
    "upwork",
    "verizon",
    "visa",
    "whatsapp",
    "wix",
    "yelp",
    "zillow",
    "zoom",
    "github",
)


class CompanyBrandMark(BaseModel):
    """Persisted instructions for rendering one augmented source logo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_version: Literal["simple-icons-v16-us-listed-1"] = (
        BRAND_ICON_CATALOG_VERSION
    )
    source_icon: str = Field(min_length=1, max_length=80)
    color_index: int = Field(ge=0, lt=BRAND_COLOR_COUNT)
    rotation_degrees: int = Field(ge=-12, le=12)
    flip_vertical: bool

    @field_validator("source_icon")
    @classmethod
    def require_catalog_icon(cls, value: str) -> str:
        if value not in BRAND_ICON_SLUGS:
            raise ValueError("source_icon must exist in the versioned brand catalog")
        return value


def assign_company_brand_mark(
    company_id: str,
    workbook_hash: str,
) -> CompanyBrandMark:
    """Assign a deterministic random-looking mark when a snapshot is built."""

    digest = sha256(f"{company_id.casefold()}\x1f{workbook_hash}".encode()).digest()
    return CompanyBrandMark(
        source_icon=BRAND_ICON_SLUGS[int.from_bytes(digest[:4]) % len(BRAND_ICON_SLUGS)],
        color_index=digest[4] % BRAND_COLOR_COUNT,
        rotation_degrees=BRAND_ROTATIONS[digest[5] % len(BRAND_ROTATIONS)],
        flip_vertical=bool(digest[6] & 1),
    )


__all__ = [
    "BRAND_COLOR_COUNT",
    "BRAND_ICON_CATALOG_VERSION",
    "BRAND_ICON_SLUGS",
    "CompanyBrandMark",
    "assign_company_brand_mark",
]
