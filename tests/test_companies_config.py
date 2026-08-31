from fair_value.config_loader import load_companies


def test_mvp_universe_has_twenty_unique_enabled_tickers() -> None:
    companies = load_companies().companies.values()
    enabled = [company for company in companies if company.enabled]
    tickers = [company.ticker for company in enabled]

    assert len(enabled) == 20
    assert len(set(tickers)) == 20
    assert "005930" in tickers
    assert "000660" in tickers
    assert all(len(ticker) == 6 and ticker.isdigit() for ticker in tickers)
