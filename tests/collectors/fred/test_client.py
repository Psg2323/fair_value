import httpx
from pydantic import SecretStr

from fair_value.collectors.fred.client import FredClient
from fair_value.settings import Settings


def test_fred_client_reads_initial_release_observations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_key"] == "fake-fred-key"
        if request.url.path == "/fred/series":
            return httpx.Response(
                200,
                json={
                    "seriess": [
                        {
                            "id": "IPG3344S",
                            "frequency_short": "M",
                            "units_short": "Index 2017=100",
                        }
                    ]
                },
            )
        assert request.url.path == "/fred/series/observations"
        assert request.url.params["output_type"] == "4"
        assert request.url.params["realtime_start"] == "1776-07-04"
        return httpx.Response(
            200,
            json={
                "observations": [
                    {
                        "date": "2026-01-01",
                        "realtime_start": "2026-02-18",
                        "realtime_end": "2026-03-17",
                        "value": "151.25",
                    }
                ]
            },
        )

    settings = Settings(fred_api_key=SecretStr("fake-fred-key"))
    with FredClient(settings=settings, transport=httpx.MockTransport(handler)) as client:
        metadata = client.get_series_metadata("IPG3344S")
        rows = client.get_initial_release_observations(
            "IPG3344S",
            "2026-01-01",
            "2026-01-31",
        )
    assert metadata["frequency_short"] == "M"
    assert rows[0]["value"] == "151.25"
