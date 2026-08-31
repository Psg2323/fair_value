import httpx
from pydantic import SecretStr

from fair_value.collectors.customs.client import CustomsClient
from fair_value.settings import Settings


def test_customs_client_maps_item_trade_request_and_parses_xml() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["serviceKey"] == "fake/customs-key"
        assert request.url.params["hsSgn"] == "8542"
        return httpx.Response(
            200,
            text=(
                "<response><header><resultCode>00</resultCode></header><body><items>"
                "<item><year>2026.07</year><hsCode>8542</hsCode>"
                "<expDlr>100</expDlr><impDlr>80</impDlr></item>"
                "</items></body></response>"
            ),
        )

    settings = Settings(customs_api_key=SecretStr("fake%2Fcustoms-key"))
    with CustomsClient(settings=settings, transport=httpx.MockTransport(handler)) as client:
        rows = client.get_item_trade("8542", "202601", "202607")

    assert rows == [{"year": "2026.07", "hsCode": "8542", "expDlr": "100", "impDlr": "80"}]
