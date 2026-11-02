from typing import Any

from pydantic import BaseModel, Field


class ChatbotRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class ChatbotResponse(BaseModel):
    answer: str
    kind: str
    items: Any


class RecommendationItem(BaseModel):
    product_id: int
    product_name: str
    co_occurrence_count: int
    score: float


class RecommendationResponse(BaseModel):
    product_id: int
    product_name: str
    recommendations: list[RecommendationItem]