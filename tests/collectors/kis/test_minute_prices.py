from datetime import date

from fair_value.collectors.kis.minute_prices import (
    fetch_minute_prices,
    fetch_minute_prices_page,
)


class StubKISClient:
    def __init__(self, pages: list[list[dict[str, object]]]) -> None:
        self.pages = iter(pages)
        self.calls: list[dict[str, str]] = []

    def get(
        self,
        path: str,
        tr_id: str,
        params: dict[str, str],
    ) -> dict[str, object]:
        self.calls.append(params)
        return {"output2": next(self.pages)}


def minute_row(day: str, clock: str, price: str = "70000") -> dict[str, object]:
    return {
        "stck_bsop_date": day,
        "stck_cntg_hour": clock,
        "stck_prpr": price,
        "cntg_vol": "10",
    }


def test_fetch_minute_page_maps_official_kis_parameters() -> None:
    client = StubKISClient([[]])

    fetch_minute_prices_page(
        client=client,  # type: ignore[arg-type]
        ticker="005930",
        trading_date=date(2026, 8, 31),
        end_time="153000",
    )

    assert client.calls == [
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": "005930",
            "FID_INPUT_HOUR_1": "153000",
            "FID_INPUT_DATE_1": "20260831",
            "FID_PW_DATA_INCU_YN": "Y",
            "FID_FAKE_TICK_INCU_YN": "",
        }
    ]


def test_fetch_minute_prices_pages_backward_and_deduplicates() -> None:
    first_page = [minute_row("20260831", f"13{minute:02d}00") for minute in range(60)] + [
        minute_row("20260831", f"12{minute:02d}00") for minute in range(60)
    ]
    second_page = [
        minute_row("20260831", "125900"),
        minute_row("20260831", "090000"),
    ]
    client = StubKISClient([first_page, second_page])

    rows = fetch_minute_prices(
        client=client,  # type: ignore[arg-type]
        ticker="005930",
        trading_date=date(2026, 8, 31),
        request_delay=0,
    )

    assert client.calls[1]["FID_INPUT_HOUR_1"] == "115959"
    assert rows[0]["stck_cntg_hour"] == "090000"
    assert rows[-1]["stck_cntg_hour"] == "135900"
    assert len(rows) == 121
