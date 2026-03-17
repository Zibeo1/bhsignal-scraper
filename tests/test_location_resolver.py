from pathlib import Path

from app.services.location_resolver import LocationResolver


def _resolver() -> LocationResolver:
    catalog = Path(__file__).parents[1] / "app" / "data" / "location_catalog.json"
    return LocationResolver(str(catalog))


def test_location_match_from_title() -> None:
    resolver = _resolver()
    resolved = resolver.resolve(
        title="Sastanak gradonacelnika odrzan u Sarajevu",
        summary="Razgovori o javnom prevozu.",
        category="BiH",
    )

    assert resolved.location_name == "Sarajevo"
    assert resolved.latitude is not None
    assert resolved.location_confidence >= 0.9


def test_category_fallback_when_no_city_match() -> None:
    resolver = _resolver()
    resolved = resolver.resolve(
        title="Usvojene nove mjere u parlamentu",
        summary="Diskusija je trajala vise sati.",
        category="BiH",
    )

    assert resolved.location_name == "Bosnia and Herzegovina"
    assert resolved.location_confidence > 0
