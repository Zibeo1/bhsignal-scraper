from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""

    no_diacritics = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"\s+", " ", no_diacritics).strip()


def _contains_alias(text: str, alias: str) -> bool:
    if len(alias) < 2:
        return False
    # Aliases of 4+ chars are treated as word stems so Bosnian inflections match
    # (e.g. "mostar" -> "mostara", "mostaru"). Short aliases/abbreviations (ks, tk,
    # bih, hnk) must match as standalone words to avoid false hits.
    if len(alias) >= 4:
        pattern = rf"(^|[^a-z0-9]){re.escape(alias)}[a-z]*([^a-z0-9]|$)"
    else:
        pattern = rf"(^|[^a-z0-9]){re.escape(alias)}([^a-z0-9]|$)"
    return re.search(pattern, text) is not None


@dataclass(frozen=True)
class CatalogLocation:
    name: str
    latitude: float
    longitude: float
    precision: str
    aliases: list[str]
    bosnia: bool = False


@dataclass(frozen=True)
class ResolvedLocation:
    location_tag_raw: Optional[str]
    location_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    location_confidence: float
    precision: str
    is_bosnia: bool = False


class LocationResolver:
    def __init__(self, catalog_path: str) -> None:
        self.catalog = self._load_catalog(catalog_path)
        self._category_fallbacks = {
            "bih": "Bosnia and Herzegovina",
            "regija": "Balkans",
            "svijet": "World",
        }

    @staticmethod
    def _load_catalog(catalog_path: str) -> list[CatalogLocation]:
        candidate = Path(catalog_path)
        if not candidate.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            candidate = (project_root / catalog_path).resolve()

        raw_data = json.loads(candidate.read_text(encoding="utf-8"))
        loaded: list[CatalogLocation] = []
        for item in raw_data:
            loaded.append(
                CatalogLocation(
                    name=item["name"],
                    latitude=float(item["latitude"]),
                    longitude=float(item["longitude"]),
                    precision=item["precision"],
                    aliases=item["aliases"],
                    bosnia=bool(item.get("bosnia", False)),
                )
            )
        return loaded

    @staticmethod
    def is_bosnia(resolved: "ResolvedLocation") -> bool:
        return resolved.is_bosnia

    def resolve(self, title: str, summary: str, category: Optional[str]) -> ResolvedLocation:
        normalized_title = _normalize(title)
        normalized_summary = _normalize(summary)
        normalized_category = _normalize(category)

        best_location: Optional[CatalogLocation] = None
        best_alias: Optional[str] = None
        best_score = 0.0

        for location in self.catalog:
            for alias in location.aliases:
                alias_norm = _normalize(alias)
                title_hit = _contains_alias(normalized_title, alias_norm)
                summary_hit = _contains_alias(normalized_summary, alias_norm)
                category_hit = _contains_alias(normalized_category, alias_norm)

                if not any([title_hit, summary_hit, category_hit]):
                    continue

                score = 0.0
                if title_hit:
                    score += 0.65
                if summary_hit:
                    score += 0.25
                if category_hit:
                    score += 0.10

                if score > best_score:
                    best_score = score
                    best_location = location
                    best_alias = alias

        if best_location is not None:
            confidence = min(0.98, 0.30 + best_score)
            return ResolvedLocation(
                location_tag_raw=best_alias,
                location_name=best_location.name,
                latitude=best_location.latitude,
                longitude=best_location.longitude,
                location_confidence=round(confidence, 2),
                precision=best_location.precision,
                is_bosnia=best_location.bosnia,
            )

        fallback_target_name = self._category_fallbacks.get(normalized_category)
        if fallback_target_name:
            fallback_location = next(
                (location for location in self.catalog if location.name == fallback_target_name),
                None,
            )
            if fallback_location is not None:
                return ResolvedLocation(
                    location_tag_raw=category,
                    location_name=fallback_location.name,
                    latitude=fallback_location.latitude,
                    longitude=fallback_location.longitude,
                    location_confidence=0.42,
                    precision=fallback_location.precision,
                    is_bosnia=fallback_location.bosnia,
                )

        return ResolvedLocation(
            location_tag_raw=None,
            location_name=None,
            latitude=None,
            longitude=None,
            location_confidence=0.0,
            precision="unknown",
        )
