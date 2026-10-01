from datetime import date

from pydantic import BaseModel


class ForecastDay(BaseModel):
    date: date
    predicted_demand: float


class DemandForecastRead(BaseModel):
    product_id: int
    sku: str
    product_name: str
    model: str
    history_days: int
    horizon_days: int
    current_stock: int
    average_daily_demand: float
    demand_std_dev: float
    lead_time_days: int
    service_level: float
    safety_stock: float
    reorder_point: float
    recommended_order_quantity: int
    forecast_total_demand: float
    should_reorder: bool
    daily_forecast: list[ForecastDay]


class ReorderAnalysisRead(BaseModel):
    products_analyzed: int
    reorders_created: int
    forecasts: list[DemandForecastRead]