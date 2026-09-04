"""MetaTrader 5 broker adapter implementing BrokerPort."""

from __future__ import annotations

import structlog

from exness_bot.broker.mt5.client import MT5Client
from exness_bot.broker.mt5.exceptions import (
    MT5AuthenticationError,
    MT5ConnectionError,
    MT5DataError,
    MT5MarketClosedError,
    MT5NotConnectedError,
    MT5SymbolError,
    MT5UnavailableError,
)
from exness_bot.broker.mt5.mapper import (
    build_close_position_request,
    build_market_order_request,
    build_modify_sltp_request,
    close_price_for_position,
    is_market_closed,
    map_account_info,
    map_order_send_result,
    map_pending_order,
    map_position,
    map_rates_to_candles,
    map_symbol_info,
    map_tick,
    market_price_for_direction,
    timeframe_to_mt5,
)
from exness_bot.config.settings import Settings
from exness_bot.domain.enums import SignalDirection, Timeframe
from exness_bot.domain.models import (
    AccountInfo,
    Candle,
    HealthStatus,
    OrderRequest,
    OrderResult,
    PendingOrder,
    Position,
    SymbolInfo,
    Tick,
)

logger = structlog.get_logger(__name__)

DEFAULT_CANDLE_COUNT = 250
MIN_CANDLE_COUNT = 1
MAX_CANDLE_COUNT = 10_000


class MT5Adapter:
    """
    MT5 implementation of ExecutableBroker.

    LEGACY path used by `exness-bot run` / OrderManager.
    Phase 11 (candle/signal/paper) must use MT5ReadOnlyClient / TradingDataProvider instead.
    Contains order_send via MT5TradingClient — not for Phase 11 research pipeline.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client: MT5Client | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or MT5Client(settings)
        self._connected = False

    def connect(self) -> bool:
        """Initialize MT5 terminal and log in to the configured account."""
        try:
            self._client.initialize()
            self._client.login()
            self._connected = True
            account = self.get_account_info()
            logger.info(
                "mt5_connected",
                login=account.login,
                server=account.server,
                balance=account.balance,
                trade_mode=account.trade_mode,
            )
            return True
        except MT5UnavailableError:
            logger.exception("mt5_unavailable")
            self._connected = False
            return False
        except (MT5ConnectionError, MT5AuthenticationError) as exc:
            logger.error("mt5_connect_failed", error=exc.message, code=exc.code.value)
            self._connected = False
            self._safe_shutdown()
            return False

    def disconnect(self) -> None:
        """Shutdown MT5 connection."""
        self._safe_shutdown()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self._client.is_initialized

    def health_check(self) -> HealthStatus:
        """Verify terminal and account readiness."""
        if not self.is_connected():
            return HealthStatus(
                connected=False,
                terminal_connected=False,
                trade_allowed=False,
                message="Broker is not connected",
            )

        terminal = self._client.terminal_info()
        account = self._client.account_info()

        if terminal is None or account is None:
            return HealthStatus(
                connected=False,
                terminal_connected=False,
                trade_allowed=False,
                message="Unable to retrieve terminal or account info",
            )

        terminal_connected = bool(getattr(terminal, "connected", False))
        trade_allowed = bool(getattr(terminal, "trade_allowed", False))
        message = "OK" if terminal_connected else "Terminal not connected to broker server"

        return HealthStatus(
            connected=self.is_connected() and terminal_connected,
            terminal_connected=terminal_connected,
            trade_allowed=trade_allowed,
            account_login=int(account.login),
            server=str(getattr(account, "server", self._settings.mt5_server)),
            message=message,
        )

    def get_account_info(self) -> AccountInfo:
        self._require_connected()
        raw = self._client.account_info()
        if raw is None:
            msg = "Failed to retrieve account info"
            raise MT5DataError(msg)
        return map_account_info(raw)

    def get_symbol_info(self, symbol: str) -> SymbolInfo:
        self._require_connected()
        self._client.ensure_symbol_selected(symbol)
        raw = self._client.symbol_info(symbol)
        if raw is None:
            msg = f"Invalid symbol: {symbol}"
            raise MT5SymbolError(msg, symbol=symbol)
        return map_symbol_info(raw)

    def get_current_tick(self, symbol: str) -> Tick:
        self._require_connected()
        self._client.ensure_symbol_selected(symbol)
        symbol_info = self.get_symbol_info(symbol)
        raw = self._client.symbol_info_tick(symbol)
        if raw is None:
            if is_market_closed(symbol_info, None):
                msg = f"Market closed or no tick data for {symbol}"
                raise MT5MarketClosedError(msg, symbol=symbol)
            msg = f"No tick data for symbol: {symbol}"
            raise MT5DataError(msg)

        tick = map_tick(symbol, raw)
        if is_market_closed(symbol_info, tick):
            msg = f"Market closed for {symbol}"
            raise MT5MarketClosedError(msg, symbol=symbol)
        return tick

    def get_open_positions(self, symbol: str | None = None) -> list[Position]:
        self._require_connected()
        raw_positions = self._client.positions_get(symbol)
        if raw_positions is None:
            return []
        return [map_position(item) for item in raw_positions]

    def get_pending_orders(self, symbol: str | None = None) -> list[PendingOrder]:
        self._require_connected()
        raw_orders = self._client.orders_get(symbol)
        if raw_orders is None:
            return []
        return [map_pending_order(item) for item in raw_orders]

    def get_historical_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
    ) -> list[Candle]:
        self._require_connected()
        self._validate_candle_count(count)

        self._client.ensure_symbol_selected(symbol)
        mt5_timeframe = timeframe_to_mt5(timeframe)
        rates = self._client.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)

        if rates is None:
            symbol_info = self.get_symbol_info(symbol)
            raw_tick = self._client.symbol_info_tick(symbol)
            tick = None
            if raw_tick is not None:
                try:
                    tick = map_tick(symbol, raw_tick)
                except (TypeError, AttributeError, ValueError):
                    tick = None
            if is_market_closed(symbol_info, tick):
                msg = f"Market closed — no historical data for {symbol}"
                raise MT5MarketClosedError(msg, symbol=symbol)
            msg = f"Failed to retrieve historical candles for {symbol} {timeframe.value}"
            raise MT5DataError(msg)

        candles = map_rates_to_candles(rates, symbol=symbol, timeframe=timeframe)
        if len(candles) < count:
            logger.warning(
                "insufficient_historical_data",
                symbol=symbol,
                timeframe=timeframe.value,
                requested=count,
                received=len(candles),
            )
        if not candles:
            msg = f"No historical candles returned for {symbol} {timeframe.value}"
            raise MT5DataError(msg)

        return candles

    def open_market_order(self, request: OrderRequest) -> OrderResult:
        """Submit a market order with attached SL/TP."""
        self._require_connected()
        self._client.ensure_symbol_selected(request.symbol)
        tick = self.get_current_tick(request.symbol)
        price = market_price_for_direction(tick, request.direction)
        payload = build_market_order_request(request, price=price)
        raw = self._client.order_send(payload)
        return map_order_send_result(
            raw,
            error=self._client._last_error(),
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )

    def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: float | None = None,
        *,
        direction: SignalDirection | None = None,
    ) -> OrderResult:
        """Close an open position by ticket."""
        self._require_connected()
        positions = self.get_open_positions(symbol)
        match = [p for p in positions if p.ticket == ticket]
        if not match:
            return OrderResult(success=False, error_message=f"Position {ticket} not found")

        position = match[0]
        close_volume = volume or position.volume
        pos_direction = direction or position.direction
        tick = self.get_current_tick(symbol)
        price = close_price_for_position(tick, pos_direction)
        payload = build_close_position_request(
            symbol=symbol,
            volume=close_volume,
            direction=pos_direction,
            price=price,
            ticket=ticket,
        )
        raw = self._client.order_send(payload)
        return map_order_send_result(raw, error=self._client._last_error())

    def modify_stop_loss(self, ticket: int, symbol: str, stop_loss: float) -> OrderResult:
        """Modify stop loss on an open position."""
        self._require_connected()
        positions = self.get_open_positions(symbol)
        match = [p for p in positions if p.ticket == ticket]
        if not match:
            return OrderResult(success=False, error_message=f"Position {ticket} not found")

        position = match[0]
        payload = build_modify_sltp_request(
            symbol=symbol,
            ticket=ticket,
            stop_loss=stop_loss,
            take_profit=position.take_profit,
        )
        raw = self._client.order_send(payload)
        return map_order_send_result(
            raw,
            error=self._client._last_error(),
            stop_loss=stop_loss,
            take_profit=position.take_profit,
        )

    def modify_take_profit(self, ticket: int, symbol: str, take_profit: float) -> OrderResult:
        """Modify take profit on an open position."""
        self._require_connected()
        positions = self.get_open_positions(symbol)
        match = [p for p in positions if p.ticket == ticket]
        if not match:
            return OrderResult(success=False, error_message=f"Position {ticket} not found")

        position = match[0]
        payload = build_modify_sltp_request(
            symbol=symbol,
            ticket=ticket,
            stop_loss=position.stop_loss,
            take_profit=take_profit,
        )
        raw = self._client.order_send(payload)
        return map_order_send_result(
            raw,
            error=self._client._last_error(),
            stop_loss=position.stop_loss,
            take_profit=take_profit,
        )

    def _require_connected(self) -> None:
        if not self.is_connected():
            raise MT5NotConnectedError

    def _safe_shutdown(self) -> None:
        try:
            self._client.shutdown()
        except MT5UnavailableError:
            logger.warning("mt5_shutdown_skipped_unavailable")

    @staticmethod
    def _validate_candle_count(count: int) -> None:
        if count < MIN_CANDLE_COUNT or count > MAX_CANDLE_COUNT:
            msg = f"Candle count must be between {MIN_CANDLE_COUNT} and {MAX_CANDLE_COUNT}"
            raise ValueError(msg)
