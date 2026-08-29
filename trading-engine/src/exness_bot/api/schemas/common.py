"""Common API envelope schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class PaginationMeta(ApiModel):
    page: int
    page_size: int = Field(alias="pageSize")
    total: int


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, object] | list[object] | str | None = None


class ErrorEnvelope(ApiModel):
    error: ErrorBody


class DataEnvelope[T](ApiModel):
    data: T
    meta: dict[str, object] | PaginationMeta | None = None


class PaginatedEnvelope[T](ApiModel):
    data: list[T]
    meta: PaginationMeta
