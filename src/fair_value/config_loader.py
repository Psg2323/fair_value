from datetime import date
from math import isfinite
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from fair_value.settings import PROJECT_ROOT


class CompanyConfig(BaseModel):
    """Analysis company configuration."""

    name_ko: str
    name_en: str
    ticker: str
    exchange: str
    currency: str
    enabled: bool = True
    opendart_corp_code: str
    segment: str = "semiconductor"


class CompaniesConfig(BaseModel):
    """All analysis company configurations."""

    companies: dict[str, CompanyConfig]


class AccountConfig(BaseModel):
    """Canonical OpenDART account mapping."""

    statements: list[Literal["BS", "IS", "CIS", "CF"]]
    ids: list[str]


class AccountsConfig(BaseModel):
    """Canonical account mappings keyed by output column."""

    accounts: dict[str, AccountConfig]


class CorporateActionConfig(BaseModel):
    """Explicit price-basis adjustment backed by a primary source."""

    ticker: str
    action_type: Literal["stock_split"]
    effective_date: date
    share_multiplier: float
    source_name: str
    source_url: str
    note: str

    def model_post_init(self, __context: object) -> None:
        if self.share_multiplier <= 0 or self.share_multiplier == 1:
            raise ValueError("share_multiplier must be positive and different from one")


class CorporateActionsConfig(BaseModel):
    corporate_actions: list[CorporateActionConfig]


class EcosIndicatorConfig(BaseModel):
    name: str
    stat_code: str
    item_code: str
    frequency: Literal["D", "M"]
    unit: str
    start_period: str


class KosisIndicatorConfig(BaseModel):
    name: str
    org_id: str
    table_id: str
    item_code: str
    region_code: str
    industry_code: str
    frequency: Literal["M"]
    unit: str
    start_period: str
    availability_lag_days: int = 35


class FredIndicatorConfig(BaseModel):
    name: str
    series_id: str
    frequency: Literal["M"]
    unit: str
    start_period: str
    vintage_mode: Literal["initial_release"] = "initial_release"


class CycleIndicatorsConfig(BaseModel):
    ecos: dict[str, EcosIndicatorConfig]
    kosis: dict[str, KosisIndicatorConfig]
    fred: dict[str, FredIndicatorConfig]


class CustomsTradeConfig(BaseModel):
    hs_codes: dict[str, str]
    start_period: str


class ComtradeReporterConfig(BaseModel):
    name: str
    code: str


class ComtradeConfig(BaseModel):
    reporters: dict[str, ComtradeReporterConfig]
    hs_codes: dict[str, str]
    flow_codes: list[Literal["X", "M"]]
    partner_code: str = "0"
    start_period: str
    max_records: int = 2500


class TradeIndicatorsConfig(BaseModel):
    customs: CustomsTradeConfig
    comtrade: ComtradeConfig


class CostOfEquityConfig(BaseModel):
    """Research assumptions used to estimate a point-in-time cost of equity."""

    risk_free_indicator: str
    risk_free_rate_scale: float
    equity_risk_premium: float
    beta: float
    minimum: float
    maximum: float


class CycleRimScenarioConfig(BaseModel):
    """Sensitivity parameters for one fair-value range scenario."""

    normalized_roe_delta: float
    equity_risk_premium_delta: float


class CycleNormalizedRimConfig(BaseModel):
    """Research configuration for finite-fade, cycle-normalized RIM."""

    version: str
    forecast_years: int
    retention_ratio: float
    minimum_normalized_roe: float
    maximum_normalized_roe: float
    maximum_cycle_roe_adjustment: float
    industrial_production_column: str
    producer_price_column: str
    industrial_production_scale: float
    producer_price_scale: float
    scenarios: dict[Literal["low", "base", "high"], CycleRimScenarioConfig]


class ValuationConfig(BaseModel):
    """Versioned benchmark and research valuation assumptions."""

    assumptions_version: str
    cost_of_equity: CostOfEquityConfig
    cycle_normalized_rim: CycleNormalizedRimConfig


class CycleRimSensitivityConfig(BaseModel):
    """Predeclared one-at-a-time research alternatives."""

    version: str
    forecast_years: list[int]
    retention_ratios: list[float]
    maximum_cycle_roe_adjustments: list[float]
    equity_risk_premium_deltas: list[float]
    initial_training_years: int

    def model_post_init(self, __context: object) -> None:
        if self.initial_training_years < 1 or any(value <= 0 for value in self.forecast_years):
            raise ValueError("training and forecast years must be positive")
        if any(not 0 <= value <= 1 for value in self.retention_ratios):
            raise ValueError("retention ratios must be between zero and one")
        if any(value < 0 for value in self.maximum_cycle_roe_adjustments):
            raise ValueError("cycle adjustments must not be negative")
        if any(not isfinite(value) for value in self.equity_risk_premium_deltas):
            raise ValueError("equity risk premium deltas must be finite")


def _load_yaml(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_companies(path: Path | None = None) -> CompaniesConfig:
    """Load and validate company configuration."""
    config_path = path or PROJECT_ROOT / "config" / "companies.yaml"
    return CompaniesConfig.model_validate(_load_yaml(config_path))


def load_accounts(path: Path | None = None) -> AccountsConfig:
    """Load and validate canonical OpenDART account mappings."""
    config_path = path or PROJECT_ROOT / "config" / "accounts.yaml"
    return AccountsConfig.model_validate(_load_yaml(config_path))


def load_corporate_actions(path: Path | None = None) -> CorporateActionsConfig:
    """Load explicit corporate actions used to align adjusted market-price units."""
    config_path = path or PROJECT_ROOT / "config" / "corporate_actions.yaml"
    return CorporateActionsConfig.model_validate(_load_yaml(config_path))


def load_cycle_indicators(path: Path | None = None) -> CycleIndicatorsConfig:
    """Load and validate economic and semiconductor-cycle series mappings."""
    config_path = path or PROJECT_ROOT / "config" / "cycle_indicators.yaml"
    return CycleIndicatorsConfig.model_validate(_load_yaml(config_path))


def load_trade_indicators(path: Path | None = None) -> TradeIndicatorsConfig:
    """Load and validate customs and UN Comtrade series mappings."""
    config_path = path or PROJECT_ROOT / "config" / "trade_indicators.yaml"
    return TradeIndicatorsConfig.model_validate(_load_yaml(config_path))


def load_valuation(path: Path | None = None) -> ValuationConfig:
    """Load versioned benchmark valuation assumptions."""
    config_path = path or PROJECT_ROOT / "config" / "valuation.yaml"
    return ValuationConfig.model_validate(_load_yaml(config_path))


def load_valuation_sensitivity(path: Path | None = None) -> CycleRimSensitivityConfig:
    """Load predeclared cycle-RIM sensitivity alternatives."""
    config_path = path or PROJECT_ROOT / "config" / "valuation_sensitivity.yaml"
    return CycleRimSensitivityConfig.model_validate(_load_yaml(config_path))
