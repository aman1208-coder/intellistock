from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    total_capacity: int = Field(ge=0)
    available_capacity: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_capacity(self) -> "WarehouseCreate":
        if self.available_capacity > self.total_capacity:
            raise ValueError("Available capacity cannot exceed total capacity")
        return self


class WarehouseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    location: Optional[str] = Field(default=None, min_length=1, max_length=255)
    total_capacity: Optional[int] = Field(default=None, ge=0)
    available_capacity: Optional[int] = Field(default=None, ge=0)


class WarehouseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str
    total_capacity: int
    available_capacity: int