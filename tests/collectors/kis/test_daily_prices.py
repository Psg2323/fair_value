from datetime import date

import pytest

from fair_value.collectors.kis.daily_prices import fetch_daily_prices_page


class StubKISClient:
    def __init__(self) -> None:
        self.params: dict[str, str] | None = None

    def get(
        self,
        path: str,
        tr_id: str,
        params: dict[str, str],
    ) -> dict[str, object]:
        self.params = params
        return {"output2": []}


@pytest.mark.parametrize(
    ("adjusted", "expected_code"),
    [(True, "0"), (False, "1")],
)
def test_fetch_daily_prices_page_maps_adjusted_price_flag(
    adjusted: bool,
    expected_code: str,
) -> None:
    client = StubKISClient()

    fetch_daily_prices_page(
        client=client,  # type: ignore[arg-type]
        ticker="005930",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 20),
        adjusted=adjusted,
    )

    assert client.params is not None
    assert client.params["FID_ORG_ADJ_PRC"] == expected_code
