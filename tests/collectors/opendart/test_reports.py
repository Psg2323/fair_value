from datetime import date

from fair_value.collectors.opendart.disclosures import fetch_periodic_disclosures
from fair_value.collectors.opendart.financial_statements import (
    fetch_financial_statement,
)
from fair_value.collectors.opendart.periodic_reports import (
    fetch_periodic_report,
)


class StubOpenDartClient:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, object]:
        assert params is not None
        self.calls.append((path, params))
        return self.payloads.pop(0)


def test_fetch_financial_statement_uses_quarterly_report_code() -> None:
    client = StubOpenDartClient([{"status": "000", "list": []}])

    payload = fetch_financial_statement(
        client=client,  # type: ignore[arg-type]
        corp_code="00126380",
        business_year=2026,
        report_code="11012",
    )

    assert payload is not None
    path, params = client.calls[0]
    assert path == "/api/fnlttSinglAcntAll.json"
    assert params["reprt_code"] == "11012"
    assert params["fs_div"] == "CFS"


def test_fetch_periodic_report_uses_share_count_endpoint() -> None:
    client = StubOpenDartClient([{"status": "000", "list": []}])

    payload = fetch_periodic_report(
        client=client,  # type: ignore[arg-type]
        endpoint="share_counts",
        corp_code="00126380",
        business_year=2025,
        report_code="11011",
    )

    assert payload is not None
    path, params = client.calls[0]
    assert path == "/api/stockTotqySttus.json"
    assert params["bsns_year"] == "2025"


def test_fetch_periodic_disclosures_paginates() -> None:
    client = StubOpenDartClient(
        [
            {
                "status": "000",
                "total_page": 2,
                "list": [{"rcept_no": "20250101000001"}],
            },
            {
                "status": "000",
                "total_page": 2,
                "list": [{"rcept_no": "20260101000001"}],
            },
        ]
    )

    records = fetch_periodic_disclosures(
        client=client,  # type: ignore[arg-type]
        corp_code="00126380",
        begin_date=date(2025, 1, 1),
        end_date=date(2026, 8, 24),
        page_count=1,
    )

    assert [record["rcept_no"] for record in records] == [
        "20250101000001",
        "20260101000001",
    ]
    assert [call[1]["page_no"] for call in client.calls] == ["1", "2"]
