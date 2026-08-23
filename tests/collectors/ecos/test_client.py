import httpx
from pydantic import SecretStr

from fair_value.collectors.ecos.client import EcosClient
from fair_value.settings import Settings


def test_ecos_client_reads_statistic_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "StatisticSearch" in request.url.path
        return httpx.Response(
            200,
            json={
                "StatisticSearch": {
                    "list_total_count": 1,
                    "row": [{"TIME": "20260102", "DATA_VALUE": "2.50"}],
                }
            },
        )

    settings = Settings(ecos_api_key=SecretStr("fake-ecos-key"))
    with EcosClient(settings=settings, transport=httpx.MockTransport(handler)) as client:
        rows = client.get_statistics("722Y001", "D", "20260101", "20260131", "0101000")
    assert rows[0]["DATA_VALUE"] == "2.50"
