"""Read-only /api/v1 routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from exness_bot.api.dependencies import get_position_close_service, get_read_service
from exness_bot.api.schemas.common import DataEnvelope, PaginatedEnvelope
from exness_bot.api.schemas.dashboard import (
    AccountOverviewDTO,
    AccountSnapshotDTO,
    AccountSwitchStateDTO,
    ActivateAccountRequest,
    AnalystChatRequest,
    AutoDemoStatusDTO,
    BacktestReportDTO,
    ClosePositionRequest,
    ClosePositionsBulkRequest,
    ClosePositionsResultDTO,
    DailyRealizedPnlDTO,
    DashboardOverviewDTO,
    ExecutionCandidateStatusDTO,
    LiveReadinessDTO,
    MultiTimeframeAnalysisDTO,
    PaperTradingDTO,
    PositionDTO,
    QuoteDTO,
    RiskSnapshotDTO,
    SessionContextDTO,
    StrategySnapshotDTO,
    SystemSettingsDTO,
    TradeAnalysisDTO,
    TradeDTO,
)
from exness_bot.api.services.position_close_service import PositionCloseService
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
    "/live-readiness",
    summary="Preflight live enablement (chỉ đọc)",
    description=(
        "Đánh giá cổng an toàn live. Không kích hoạt live, không đặt lệnh. "
        "PREFLIGHT_READY ≠ LIVE READY khi MT5Executor chưa tồn tại."
    ),
    response_model=DataEnvelope[LiveReadinessDTO],
    response_model_by_alias=True,
)
def get_live_readiness(
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(service.get_live_readiness().model_dump(by_alias=True))


@router.get(
    "/paper",
    summary="Paper trading (ảo, chỉ đọc)",
    description="Trạng thái khớp lệnh giấy. Không có endpoint đặt lệnh.",
    response_model=DataEnvelope[PaperTradingDTO],
    response_model_by_alias=True,
)
def get_paper(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_paper_trading().model_dump(by_alias=True))


@router.get(
    "/account",
    summary="Snapshot tài khoản",
    response_model=DataEnvelope[AccountSnapshotDTO],
    response_model_by_alias=True,
)
def get_account(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_account_snapshot().model_dump(by_alias=True))


@router.get(
    "/account/overview",
    summary="Tổng quan tài khoản & PnL (chỉ đọc)",
    description=(
        "Balance/equity/margin, realized/unrealized PnL hôm nay, freshness LIVE|STALE|"
        "DISCONNECTED|UNAVAILABLE. Không đặt lệnh."
    ),
    response_model=DataEnvelope[AccountOverviewDTO],
    response_model_by_alias=True,
)
def get_account_overview(
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(service.get_account_overview().model_dump(by_alias=True))


@router.get(
    "/account/pnl/daily",
    summary="Lịch sử realized PnL theo ngày (UTC)",
    description="Chỉ realized từ deals đã đóng — không bịa equity lịch sử.",
    response_model=DataEnvelope[list[DailyRealizedPnlDTO]],
    response_model_by_alias=True,
)
def get_account_pnl_daily(
    service: Annotated[ReadService, Depends(get_read_service)],
    days: Annotated[int, Query(ge=1, le=90, description="Số ngày UTC gần nhất")] = 7,
) -> dict[str, object]:
    rows = service.get_daily_realized_pnl(days=days)
    return _envelope([item.model_dump(by_alias=True) for item in rows])


@router.get(
    "/overview",
    summary="Tổng quan Dashboard",
    response_model=DataEnvelope[DashboardOverviewDTO],
    response_model_by_alias=True,
)
def get_overview(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_dashboard_overview().model_dump(by_alias=True))


@router.get(
    "/quotes",
    summary="Giá thị trường realtime",
    description=(
        "Tick bid/ask/last, spread và freshness LIVE/STALE/UNAVAILABLE. "
        "Symbol trên Dashboard luôn canonical (XAUUSD)."
    ),
    response_model=DataEnvelope[list[QuoteDTO]],
    response_model_by_alias=True,
)
def get_quotes(
    service: Annotated[ReadService, Depends(get_read_service)],
    symbols: Annotated[
        str | None,
        Query(
            description="Danh sách symbol cách nhau bởi dấu phẩy. Mặc định dùng WATCHLIST_SYMBOLS."
        ),
    ] = None,
) -> dict[str, object]:
    requested = [item.strip() for item in symbols.split(",")] if symbols else None
    quotes = service.get_quotes(requested)
    return _envelope([item.model_dump(by_alias=True) for item in quotes])


@router.get(
    "/analysis",
    summary="Phân tích thị trường & đề xuất giao dịch (chỉ đọc)",
    description=(
        "Closed M15 → indicators → regime → BUY/SELL/WAIT + sizing. "
        "Chỉ đọc: không gửi lệnh, không khớp DEMO/LIVE."
    ),
    response_model=DataEnvelope[TradeAnalysisDTO],
    response_model_by_alias=True,
)
def get_analysis(
    service: Annotated[ReadService, Depends(get_read_service)],
    symbol: Annotated[str | None, Query(description="Canonical symbol, mặc định XAUUSD")] = None,
) -> dict[str, object]:
    return _envelope(service.get_trade_analysis(symbol).model_dump(by_alias=True))


@router.get(
    "/analysis/{symbol}/execution-candidate",
    summary="Trạng thái ExecutionCandidate (chỉ đọc)",
    description=(
        "Phase 16.3 contract: MTF → CanonicalTradeSetup → eligibility. "
        "Không gửi lệnh. Candidate chỉ từ mtf_technical_v1."
    ),
    response_model=DataEnvelope[ExecutionCandidateStatusDTO],
    response_model_by_alias=True,
)
def get_execution_candidate(
    symbol: str,
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(
        service.get_execution_candidate_status(symbol).model_dump(by_alias=True)
    )


@router.get(
    "/analysis/{symbol}/multi-timeframe",
    summary="Phân tích đa khung thời gian (chỉ đọc)",
    description=(
        "M15/H1/H4/D1 closed-candle analysis + aggregation. "
        "Confidence = EVIDENCE_ALIGNMENT, không phải xác suất thắng. "
        "Chỉ đọc — không gửi lệnh."
    ),
    response_model=DataEnvelope[MultiTimeframeAnalysisDTO],
    response_model_by_alias=True,
)
def get_multi_timeframe_analysis(
    symbol: str,
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(
        service.get_multi_timeframe_analysis(symbol).model_dump(by_alias=True)
    )


@router.get(
    "/analysis/{symbol}/technical-snapshot",
    summary="Technical Market Snapshot (chỉ đọc)",
    description=(
        "Phase 16.3.1 deterministic technical truth: M15/H1/H4/D1 closed candles, "
        "trend segment, swings, S/R, wick morphology, MTF alignment, bot analysis. "
        "Không LLM, không Google, không gửi lệnh. "
        "Dùng ?view=compact cho compact AI context."
    ),
)
def get_technical_market_snapshot(
    symbol: str,
    service: Annotated[ReadService, Depends(get_read_service)],
    view: Annotated[
        str | None,
        Query(description="full (mặc định) hoặc compact"),
    ] = None,
) -> dict[str, object]:
    compact = (view or "").strip().lower() == "compact"
    return _envelope(
        service.get_technical_market_snapshot(symbol, compact=compact)
    )


@router.get(
    "/analysis/{symbol}/external-context",
    summary="External Market Context (chỉ đọc)",
    description=(
        "Phase 16.3.2 grounded external intelligence (Gemini + Google Search). "
        "Không thay đổi strategy/execution. Default disabled khi "
        "EXTERNAL_INTELLIGENCE_ENABLED=false. "
        "?view=compact | ?force_refresh=true"
    ),
)
def get_external_market_context(
    symbol: str,
    service: Annotated[ReadService, Depends(get_read_service)],
    view: Annotated[str | None, Query()] = None,
    force_refresh: Annotated[
        bool,
        Query(alias="forceRefresh", description="Bỏ qua cache (analysis-only)"),
    ] = False,
) -> dict[str, object]:
    compact = (view or "").strip().lower() == "compact"
    return _envelope(
        service.get_external_market_context(
            symbol, force_refresh=force_refresh, compact=compact
        )
    )


@router.get(
    "/analysis/{symbol}/market-synthesis",
    summary="AI Market Synthesis (chỉ đọc)",
    description=(
        "Phase 16.3.3 hybrid synthesis: TechnicalMarketSnapshot + "
        "ExternalMarketContext. Deterministic state luôn có; AI narrative "
        "optional (AI_MARKET_SYNTHESIS_ENABLED). Không web search, không gửi lệnh. "
        "?view=compact | ?forceRefresh=true"
    ),
)
def get_market_synthesis(
    symbol: str,
    service: Annotated[ReadService, Depends(get_read_service)],
    view: Annotated[str | None, Query()] = None,
    force_refresh: Annotated[
        bool,
        Query(alias="forceRefresh", description="Bỏ qua cache (analysis-only)"),
    ] = False,
) -> dict[str, object]:
    compact = (view or "").strip().lower() == "compact"
    return _envelope(
        service.get_market_synthesis(
            symbol, force_refresh=force_refresh, compact=compact
        )
    )


@router.post(
    "/analysis/{symbol}/analyst-chat",
    summary="AI Market Analyst Chat (chỉ phân tích)",
    description=(
        "Phase 16.3.5 context-aware analyst chat. Server builds canonical "
        "TechnicalMarketSnapshot + ExternalMarketContext + MarketSynthesis. "
        "Không web search mỗi tin nhắn, không gửi lệnh, không đổi strategy."
    ),
)
def post_analyst_chat(
    symbol: str,
    body: AnalystChatRequest,
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(
        service.post_analyst_chat(
            symbol,
            message=body.message,
            session_id=body.session_id,
        )
    )


@router.get(
    "/analysis/{symbol}",
    summary="Phân tích thị trường theo symbol (chỉ đọc)",
    response_model=DataEnvelope[TradeAnalysisDTO],
    response_model_by_alias=True,
)
def get_analysis_by_symbol(
    symbol: str,
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(service.get_trade_analysis(symbol).model_dump(by_alias=True))


@router.get(
    "/execution/auto-demo/status",
    summary="Trạng thái vòng lặp autonomous DEMO (chỉ đọc)",
    description=(
        "Phase 17.3 read-only status. Không start/stop loop, không order_send. "
        "Operator điều khiển process: python -m exness_bot.execution.auto_demo"
    ),
    response_model=DataEnvelope[AutoDemoStatusDTO],
    response_model_by_alias=True,
)
def get_auto_demo_status(
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(service.get_auto_demo_status())


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


@router.post(
    "/positions/close",
    summary="Đóng nhiều vị thế hoặc đóng tất cả",
    description=(
        "closeAll=true hoặc positionIds[]. Confirm: CLOSE-ALL (DEMO) "
        "hoặc LIVE-CLOSE-ALL (LIVE)."
    ),
    response_model=DataEnvelope[ClosePositionsResultDTO],
    response_model_by_alias=True,
)
def close_positions_bulk(
    body: ClosePositionsBulkRequest,
    closer: Annotated[PositionCloseService, Depends(get_position_close_service)],
) -> dict[str, object]:
    result = closer.close_many(
        confirm=body.confirm,
        position_ids=body.position_ids,
        close_all=body.close_all,
    )
    return _envelope(result.model_dump(by_alias=True))


@router.post(
    "/positions/{position_id}/close",
    summary="Đóng một vị thế đang mở",
    description=(
        "Đóng vị thế theo ticket. Yêu cầu DASHBOARD_ALLOW_CLOSE_POSITION=true "
        "và confirm: CLOSE (DEMO) hoặc LIVE-CLOSE (LIVE + allow_live + kill switch off)."
    ),
    response_model=DataEnvelope[ClosePositionsResultDTO],
    response_model_by_alias=True,
)
def close_position(
    position_id: str,
    body: ClosePositionRequest,
    closer: Annotated[PositionCloseService, Depends(get_position_close_service)],
) -> dict[str, object]:
    result = closer.close_one(position_id, body.confirm)
    return _envelope(result.model_dump(by_alias=True))


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
    "/accounts",
    summary="Danh sách tài khoản MT5 demo / thật",
    description="Không trả về mật khẩu. Chuyển tài khoản không bật đặt lệnh live.",
    response_model=DataEnvelope[AccountSwitchStateDTO],
    response_model_by_alias=True,
)
def get_accounts(service: Annotated[ReadService, Depends(get_read_service)]) -> dict[str, object]:
    return _envelope(service.get_account_switch_state().model_dump(by_alias=True))


@router.post(
    "/accounts/active",
    summary="Chuyển tài khoản MT5 đang xem",
    description=(
        "Đăng nhập lại MT5 với profile demo hoặc live. "
        "Không thay đổi TRADING_MODE và không bật ALLOW_LIVE_TRADING."
    ),
    response_model=DataEnvelope[AccountSwitchStateDTO],
    response_model_by_alias=True,
)
def set_active_account(
    body: ActivateAccountRequest,
    service: Annotated[ReadService, Depends(get_read_service)],
) -> dict[str, object]:
    return _envelope(service.set_active_account(body.profile).model_dump(by_alias=True))


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
