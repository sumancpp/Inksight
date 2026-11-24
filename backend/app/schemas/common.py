from typing import Generic, List, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T] = Field(..., description="List of items for the current page")
    total: int = Field(..., ge=0, description="Total count of items matching the query")
    limit: int = Field(..., ge=1, description="Requested limit")
    offset: int = Field(..., ge=0, description="Requested offset")
