import httpx
from pydantic import SecretStr

from fair_value.collectors.kosis.client import KosisClient
from fair_value.settings import Settings


def test_kosis_client_maps_table_classifications() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        assert params["tblId"] == "DT_1F02001"
        assert params["objL1"] == "00"
        assert params["objL2"] == "C261"
        assert params["itmId"] == "T10"
        return httpx.Response(
            200,
            json=[{"PRD_DE": "202601", "DT": "123.4"}],
        )

    settings = Settings(kosis_api_key=SecretStr("fake-kosis-key"))
    with KosisClient(settings=settings, transport=httpx.MockTransport(handler)) as client:
        rows = client.get_statistics(
            "101",
            "DT_1F02001",
            "T10",
            "00",
            "C261",
            "M",
            "202601",
            "202601",
        )
    assert rows[0]["DT"] == "123.4"
