from unittest.mock import patch

import httpx
from pydantic import SecretStr

from fair_value.collectors.comtrade.client import ComtradeClient
from fair_value.settings import Settings


def test_comtrade_client_maps_authenticated_monthly_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Ocp-Apim-Subscription-Key"] == "fake-comtrade-key"
        assert request.url.params["reporterCode"] == "410"
        assert request.url.params["cmdCode"] == "8541,8542,8486"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "period": "202607",
                        "reporterCode": 410,
                        "flowCode": "X",
                        "cmdCode": "8542",
                        "primaryValue": 100,
                    }
                ]
            },
        )

    settings = Settings(un_comtrade_api_key=SecretStr("fake-comtrade-key"))
    with ComtradeClient(settings=settings, transport=httpx.MockTransport(handler)) as client:
        rows = client.get_monthly_trade(
            ["202607"],
            "410",
            "0",
            ["8541", "8542", "8486"],
            ["X", "M"],
        )

    assert rows[0]["primaryValue"] == 100


def test_comtrade_client_retries_rate_limit_response() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(200, request=request, json={"data": []})

    settings = Settings(un_comtrade_api_key=SecretStr("fake-comtrade-key"))
    with (
        patch("fair_value.collectors.comtrade.client.time.sleep"),
        ComtradeClient(
            settings=settings,
            transport=httpx.MockTransport(handler),
            request_interval=0,
            max_retries=1,
        ) as client,
    ):
        rows = client.get_monthly_trade(["202607"], "410", "0", ["8542"], ["X"])

    assert rows == []
    assert request_count == 2
