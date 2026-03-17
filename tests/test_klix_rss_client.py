from pathlib import Path

from app.clients.klix_rss_client import parse_feed


def test_parse_feed_extracts_required_fields() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "klix_rss_sample.xml"
    xml_data = fixture_path.read_text(encoding="utf-8")

    entries = parse_feed(xml_data)

    assert len(entries) == 2
    first = entries[0]

    assert first.source_article_id == "260317001"
    assert first.title == "Sjednica odrzana u Sarajevu o javnom prevozu"
    assert first.category == "BiH"
    assert first.image_url is not None
