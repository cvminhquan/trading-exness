"""Read-only /api/v1 routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from exness_bot.api.dependencies import get_read_service
from exness_bot.api.schemas.common import DataEnvelope, PaginatedEnvelope
from exness_bot.api.schemas.dashboard import (
    AccountSnapshotDTO,
    BacktestReportDTO,
    DashboardOverviewDTO,
    PositionDTO,
    RiskSnapshotDTO,
    SessionContextDTO,
    StrategySnapshotDTO,
    SystemSettingsDTO,
    TradeDTO,
)
from exness_bot.api.services.read_service import BacktestQuery, ReadService, TradeQuery

router = APIRouter(prefix="/api/v1", tags=["Dashboard API v1"])


def _envelope(data: Any, meta: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"data": data}
    if meta is not None:
        payload["meta"] = meta
    return payload


def _paginated(data: list[Any], meta: Any) -> dict[str, object]:
    return {"data": data, "meta": meta.model_dump(by_alias=True)}


@router.get(
    "/status",
    summary="Trạng thái phiên vận hành",
    description="Trả về trạng thái bot, kết nối broker và mode giao dịch.",
    response_model=DataEnvelope[SessionContextDTO],
    response_model_by_alias=True,
)
def get_status(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_session_context().model_dump(by_alias=True))


@router.get(
    "/account",
    summary="Snapshot tài khoản",
    response_model=DataEnvelope[AccountSnapshotDTO],
    response_model_by_alias=True,
)
def get_account(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_account_snapshot().model_dump(by_alias=True))


@router.get(
    "/overview",
    summary="Tổng quan Dashboard",
    response_model=DataEnvelope[DashboardOverviewDTO],
    response_model_by_alias=True,
)
def get_overview(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_dashboard_overview().model_dump(by_alias=True))


@router.get(
    "/positions",
    summary="Vị thế đang mở",
    response_model=PaginatedEnvelope[PositionDTO],
    response_model_by_alias=True,
)
def get_positions(
    service: Annotated[ReadService, Depends(get_read_service)],
    page: Annotated[int, Query(ge=1, description="Số trang")] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 50,
) -> dict[str, object]:
    items, meta = service.get_positions(page=page, page_size=page_size)
    return _paginated([item.model_dump(by_alias=True) for item in items], meta)


@router.get(
    "/trades",
    summary="Nhật ký giao dịch đã đóng",
    response_model=PaginatedEnvelope[TradeDTO],
    response_model_by_alias=True,
)
def get_trades(
    service: Annotated[ReadService, Depends(get_read_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 50,
    symbol: Annotated[str | None, Query()] = None,
    direction: Annotated[str | None, Query()] = None,
    strategy: Annotated[str | None, Query()] = None,
    result: Annotated[str | None, Query()] = None,
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    query = TradeQuery(
        page=page,
        page_size=page_size,
        symbol=symbol,
        direction=direction,
        strategy=strategy,
        result=result,
        start=start,
        end=end,
    )
    items, meta = service.get_trades(query)
    return _paginated([item.model_dump(by_alias=True) for item in items], meta)


@router.get(
    "/strategy",
    summary="Trạng thái chiến lược",
    response_model=DataEnvelope[StrategySnapshotDTO],
    response_model_by_alias=True,
)
def get_strategy(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_strategy_snapshot().model_dump(by_alias=True))


@router.get(
    "/risk",
    summary="Giới hạn rủi ro",
    response_model=DataEnvelope[RiskSnapshotDTO],
    response_model_by_alias=True,
)
def get_risk(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_risk_snapshot().model_dump(by_alias=True))


@router.get(
    "/settings",
    summary="Cấu hình hệ thống (read-only)",
    response_model=DataEnvelope[SystemSettingsDTO],
    response_model_by_alias=True,
)
def get_settings_route(
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(service.get_system_settings().model_dump(by_alias=True))


@router.get(
    "/backtests",
    summary="Danh sách báo cáo backtest",
    response_model=PaginatedEnvelope[BacktestReportDTO],
    response_model_by_alias=True,
)
def list_backtests(
    service: Annotated[ReadService, Depends(get_read_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 50,
    strategy: Annotated[str | None, Query()] = None,
    symbol: Annotated[str | None, Query()] = None,
    timeframe: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    query = BacktestQuery(
        page=page,
        page_size=page_size,
        strategy=strategy,
        symbol=symbol,
        timeframe=timeframe,
    )
    items, meta = service.list_backtests(query)
    return _paginated([item.model_dump(by_alias=True) for item in items], meta)


@router.get(
    "/backtests/{report_id}",
    summary="Chi tiết báo cáo backtest",
    response_model=DataEnvelope[BacktestReportDTO],
    response_model_by_alias=True,
)
def get_backtest(
    report_id: str,
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    report = service.get_backtest(report_id)
    return _envelope(report.model_dump(by_alias=True))
