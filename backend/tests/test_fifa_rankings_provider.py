from app.providers.fifa_rankings import _extract_results, _parse_row


def test_parse_row_from_parse_bot_shape() -> None:
    row = _parse_row(
        {
            "Rank": 1,
            "IdCountry": "FRA",
            "ConfederationName": "UEFA",
            "PubDate": "2026-04-01T13:00:00+00:00",
            "TeamName": [{"Locale": "en-GB", "Description": "France"}],
        }
    )
    assert row is not None
    assert row.rank == 1
    assert row.team_name == "France"
    assert row.country_code == "FRA"
    assert row.confederation == "UEFA"
    assert row.as_of is not None


def test_extract_results_nested_data() -> None:
    payload = {"data": {"Results": [{"Rank": 2, "name": "Spain", "IdCountry": "ESP"}]}}
    results = _extract_results(payload)
    assert len(results) == 1
    row = _parse_row(results[0])
    assert row is not None
    assert row.team_name == "Spain"
