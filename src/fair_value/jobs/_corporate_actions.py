from fair_value.config_loader import load_corporate_actions
from fair_value.features.share_basis import StockSplit


def load_stock_splits() -> tuple[StockSplit, ...]:
    """Map validated configuration into calculation-layer stock split values."""
    config = load_corporate_actions()
    return tuple(
        StockSplit(
            ticker=action.ticker,
            effective_date=action.effective_date,
            share_multiplier=action.share_multiplier,
        )
        for action in config.corporate_actions
    )
