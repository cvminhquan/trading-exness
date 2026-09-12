# PHASE 17.3 — SETUP QUALITY AUDIT
## ENTRY ZONE STABILITY + SUPPORT/RESISTANCE OVERLAP

**Ngày audit:** 2026-09-12  
**Mục tiêu:** Kiểm tra tính ổn định của Trade Setup, hiện tượng Price Chasing, sự chồng lấn Support/Resistance và lý do thực tế khiến bot hiếm khi hoặc chưa bao giờ đạt trạng thái `ENTRY_ZONE` → `ExecutionCandidate` → DEMO execution.  
**Nguyên tắc:** CODE là source of truth. KHÔNG sửa code sản xuất trong audit này. Không thay đổi execution architecture.

---

## PART A — TRACE THE COMPLETE SETUP FLOW

### 1. ASCII Call Graph thực tế

```
MT5 Broker / Terminal
  │ [READ ONLY: OHLCV bars M15, H1, H4, D1]
  ▼
closed_candles_only(candles, tf, now)  [market_data/candles.py]
  │ (Loại bỏ nến đang hình thành, chỉ giữ nến đã đóng)
  ▼
analyze_timeframe(candles, tf, ...)  [market_analysis/timeframe_analyzer.py]
  ├── IndicatorCalculator.compute(bars)  [indicators/calculator.py: EMA, RSI, ATR14, MACD]
  ├── detect_confirmed_swings(candles, left=2, right=2)  [market_analysis/swings.py]
  ├── label_swings() + classify_structure()  [market_analysis/structure.py]
  ├── build_support_resistance(swings, atr14, cluster_atr_mult=0.25)  [market_analysis/levels.py]
  │     ├── nearest_support_below(supports, close)
  │     └── nearest_resistance_above(resistances, close)
  └── compute_timeframe_score(...)  [market_analysis/scoring.py]
  │
  ▼
MultiTimeframeAnalysisService.analyze(symbol)  [market_analysis/mtf_service.py]
  ├── _aggregate(tf_results, weights) → final_signal (LONG/SHORT/WAIT), confidence
  ├── tick = data.get_tick(symbol) → current = (bid + ask) / 2  [LIVE TICK MID]
  ├── build_trade_setup(final_signal, current_price=current, primary=M15, higher=H1/H4, ...)
  │     └── [market_analysis/setup.py] → TradeSetup (ephemeral)
  └── MultiTimeframeAnalysis (data object)
  │
  ▼
ExecutionContractService.evaluate_from_analysis()  [market_analysis/contract/service.py]
  ├── _propose_setup(analysis, now)
  │     ├── compute_setup_id(strategy_id, symbol, M15, source_candle_timestamp, direction)
  │     ├── compute_analysis_fingerprint(...)
  │     ├── compute_expires_at(source_candle_timestamp, M15, max_candles=8)
  │     ├── derive_state_from_price(direction, current_price, entry_low, entry_high, SL)
  │     └── CanonicalTradeSetup (proposed)
  │
  ├── active = _store.get_active_for_symbol(symbol)  [market_analysis/contract/store.py]
  ├── _reconcile_lifecycle(active, proposed, analysis, now)
  │     ├── active.setup_id == proposed.setup_id:
  │     │     refreshed = CanonicalTradeSetup(**proposed.__dict__, created_at=active.created_at)
  │     │     _store.upsert(refreshed)  <-- [MUTATION TRÊN MỖI LẦN ĐỌC]
  │     └── active.setup_id != proposed.setup_id:
  │           _store.upsert(active with state=SUPERSEDED)
  │           _store.upsert(proposed)
  │
  ├── evaluate_eligibility(strategy_id, analysis, setup, tick, symbol_info, ...)
  │     └── [market_analysis/contract/eligibility.py]
  │           setup.state != ENTRY_ZONE → BLOCK ("PRICE_NOT_IN_ENTRY_ZONE")
  │
  └── build_execution_candidate()  [market_analysis/contract/candidate.py]
        ├── Chỉ tạo khi setup.state == ENTRY_ZONE VÀ eligible == True
        └── Nếu WAITING_FOR_ENTRY → candidate = None
  │
  ▼
API (FastAPI: /analysis/{symbol}/multi-timeframe, /execution-candidate)
  │
  ▼
Dashboard UI (UnifiedTradingAnalysisCard, KeyLevelsPanel, TradePlanSection)
```

### 2. Chi tiết từng bước

| Bước | File | Class / Function | Input | Output | Current Quote tham gia? | Closed Candle tham gia? | Persisted State tham gia? |
|---|---|---|---|---|---|---|---|
| 1 | `market_data/candles.py` | `closed_candles_only` | `candles: list[Candle]`, `tf`, `now` | `list[Candle]` | **NO** | **YES** | **NO** |
| 2 | `indicators/calculator.py` | `IndicatorCalculator.compute` | `bars: DataFrame` | `IndicatorSnapshot` (EMA, RSI, ATR14) | **NO** | **YES** | **NO** |
| 3 | `market_analysis/swings.py` | `detect_confirmed_swings` | `candles: list[Candle]`, `left=2, right=2` | `list[ConfirmedSwing]` | **NO** | **YES** | **NO** |
| 4 | `market_analysis/structure.py` | `classify_structure` | `labeled: list[LabeledSwing]` | `StructureSnapshot` | **NO** | **YES** | **NO** |
| 5 | `market_analysis/levels.py` | `build_support_resistance` | `swings`, `atr14`, `cluster_atr_multiplier=0.25` | `supports_l`, `resistances_l` | **NO** | **YES** | **NO** |
| 6 | `market_analysis/timeframe_analyzer.py` | `analyze_timeframe` | `candles`, `timeframe`, params | `TimeframeAnalysis` | **NO** | **YES** | **NO** |
| 7 | `market_analysis/mtf_service.py` | `MultiTimeframeAnalysisService.analyze` | `symbol`, 4 TFs closed candles, `tick` | `MultiTimeframeAnalysis` | **YES** (`current = (bid+ask)/2`) | **YES** | **NO** |
| 8 | `market_analysis/setup.py` | `build_trade_setup` | `final_signal`, `current_price`, M15, H1/H4 | `TradeSetup` | **YES** (`current_price`) | **YES** | **NO** |
| 9 | `market_analysis/contract/service.py` | `_propose_setup` | `MultiTimeframeAnalysis`, `now` | `CanonicalTradeSetup` (proposed) | **YES** (`current_price`) | **YES** | **NO** |
| 10 | `market_analysis/contract/service.py` | `_reconcile_lifecycle` | `active`, `proposed`, `now` | `CanonicalTradeSetup` (reconciled) | **YES** (`proposed.state`) | **YES** | **YES** (`active` từ SQLite) |
| 11 | `market_analysis/contract/eligibility.py` | `evaluate_eligibility` | `setup`, `analysis`, `tick`, metadata | `EligibilityResult` | **YES** (tick, spread, zone check) | **YES** | **YES** (`setup.state`) |
| 12 | `market_analysis/contract/candidate.py` | `build_execution_candidate` | `setup`, `sizing`, `eligibility` | `ExecutionCandidate | None` | **YES** | **YES** | **YES** |
| 13 | `dashboard/.../KeyLevelsPanel.tsx` | `buildKeyLevelsSnapshot` | `MultiTimeframeAnalysis`, `currentPrice` | UI View Models | **YES** (`currentPrice`) | **YES** | **NO** |

---

## PART B — SUPPORT / RESISTANCE ALGORITHM

### 1. Cách phát hiện Swing High
Hàm `detect_confirmed_swings` trong `market_analysis/swings.py`:
Với mỗi nến index `i` (đã đóng):
- `left_slice = candles[i - left : i]`
- `right_slice = candles[i + 1 : i + right + 1]`
- Điều kiện: `is_high = all(hi > float(c.high) for c in left_slice) and all(hi > float(c.high) for c in right_slice)`.
- Giá cao nhất của nến `i` phải lớn hơn tuyệt đối tất cả nến trong cửa sổ trái và phải.

### 2. Cách phát hiện Swing Low
- Điều kiện: `is_low = all(lo < float(c.low) for c in left_slice) and all(lo < float(c.low) for c in right_slice)`.
- Giá thấp nhất của nến `i` phải nhỏ hơn tuyệt đối tất cả nến trong cửa sổ trái và phải.

### 3. Cửa sổ Swing hiện tại
- `left = 2`, `right = 2` (từ `Settings.swing_left_bars = 2`, `Settings.swing_right_bars = 2`).
- Nến swing chỉ được coi là confirmed tại nến `i + right` (sau 2 nến đóng tiếp theo).

### 4. Cách gom cụm (Clustering)
Hàm `_cluster_prices(swings, level_type, tolerance)` trong `market_analysis/levels.py`:
1. Sắp xếp swings theo thứ tự thời gian nến tăng dần: `sorted(swings, key=lambda s: s.index)`.
2. Duyệt qua từng swing:
   - Với mỗi cluster đã có: tính tâm `center = sum(s.price for s in cluster) / len(cluster)`.
   - Nếu `abs(swing.price - center) <= tolerance`: thêm swing vào cluster đó và dừng tìm kiếm.
   - Nếu không vừa cluster nào: tạo cluster mới `[swing]`.
3. Tính giá đại diện cho mỗi cluster: trung bình cộng giá các swing trong cluster `price = round(sum(s.price for s in cluster) / len(cluster), 8)`.

### 5. Dung sai gom cụm (Tolerance)
- Trong `build_support_resistance`:
  `tolerance = atr14 * cluster_atr_multiplier` nếu `atr14 > 0`, ngược lại fallback `point * 50`.
- Giá trị mặc định trong settings: `cluster_atr_multiplier = 0.25` (`sr_cluster_atr_multiplier`).
- Dung sai gom cụm là **`0.25 × ATR14`**.

### 6. ATR có được dùng không?
- **CÓ**. Dùng ATR14 của chính timeframe đó tính trên các nến đã đóng.

### 7. Timeframe nào tạo ra S/R?
- Mỗi timeframe (M15, H1, H4, D1) tự tính S/R độc lập bằng nến và ATR của chính nó.
- **Sử dụng trong setup thực tế (`build_trade_setup`):**
  - **M15:** Cung cấp `primary.nearest_support` và `primary.nearest_resistance`. **Đây là nguồn DUY NHẤT dùng để neo Entry Zone!**
  - **H1:** Chỉ cung cấp `higher.nearest_resistance` (cho LONG) hoặc `higher.nearest_support` (cho SHORT) vào danh sách ứng viên Take Profit. **Không tham gia neo Entry Zone.**
  - **H4:** Không tham gia tạo Entry Zone hay Take Profit. Chỉ được gom vào `key_supports` / `key_resistances` để trả ra API/Dashboard hiển thị.
  - **D1:** Hoàn toàn không tham gia vào S/R hay setup (chỉ dùng tính điểm MTF score).

### 8. Một cụm trở thành SUPPORT như thế nào?
- `lows = [s for s in swings if s.kind == SwingKind.LOW]`
- `supports = _cluster_prices(lows, level_type=LevelType.SUPPORT, tolerance=tolerance)`
- **Bất kỳ cụm nào tạo bởi SWING LOW đều được gắn nhãn SUPPORT**, bất kể giá hiện tại đang ở trên hay ở dưới nó.

### 9. Một cụm trở thành RESISTANCE như thế nào?
- `highs = [s for s in swings if s.kind == SwingKind.HIGH]`
- `resistances = _cluster_prices(highs, level_type=LevelType.RESISTANCE, tolerance=tolerance)`
- **Bất kỳ cụm nào tạo bởi SWING HIGH đều được gắn nhãn RESISTANCE**, bất kể giá hiện tại đang ở đâu.

### 10. Biên của Zone (Zone Boundaries) được tính thế nào?
- Trong backend `levels.py`: `StructureLevel` **CHỈ LÀ MỘT MỨC GIÁ ĐƠN LẺ** (`price = round(price, 8)`). Backend KHÔNG tính zone low/high cho S/R.
- Vùng S/R có biên độ hiển thị trên Dashboard (`KeyLevelsPanel.tsx`) là do frontend tự gom cụm lại bằng hàm `_clusterAround(levels, anchor, atr)` với khoảng cách `± 0.5 × ATR`.
- Biên của **Entry Zone** (trong `setup.py`):
  `entry = float(anchor)`
  `half = atr * entry_zone_atr_width` (mặc định `0.25 × ATR14`)
  `entry_zone_low = entry - half`
  `entry_zone_high = entry + half`

### 11. Các vùng S/R được xếp hạng thế nào?
- Trong `levels.py`: `levels.sort(key=lambda level: level.price)`.
- **CHỈ XẾP HẠNG THEO GIÁ (tăng dần)**.
- `touch_count`, `recency`, `strength`, `volume`, `market structure` **HOÀN TOÀN KHÔNG ĐƯỢC DÙNG ĐỂ XẾP HẠNG HAY LỌC**.
- Backend chỉ đơn giản lấy:
  `supports = [level.price for level in supports_l[-5:]]` (5 mức swing low cao nhất)
  `resistances = [level.price for level in resistances_l[:5]]` (5 mức swing high thấp nhất)

### 12. "Nearest Support" được chọn thế nào?
- Hàm `nearest_support_below(supports, entry)`:
  `below = [level for level in supports if level.price < entry]`
  `return max(below, key=lambda level: level.price)`
- Lọc các mức support có giá `< close` của nến M15 đóng gần nhất. Lấy mức có giá lớn nhất trong số đó.

### 13. "Nearest Resistance" được chọn thế nào?
- Hàm `nearest_resistance_above(resistances, entry)`:
  `above = [level for level in resistances if level.price > entry]`
  `return min(above, key=lambda level: level.price)`
- Lọc các mức resistance có giá `> close` của nến M15 đóng gần nhất. Lấy mức có giá nhỏ nhất trong số đó.

### 14. Một swing cluster có thể gián tiếp đóng góp vào cả support và resistance không?
- Trong backend, swing low chỉ vào support, swing high chỉ vào resistance.
- **TUY NHIÊN**: Trong các giai đoạn thị trường đi ngang (consolidation/range), các swing low và swing high nằm xen kẽ ở cùng một vùng giá. Một swing low có thể nằm ở 2525.0, trong khi một swing high lại nằm ở 2524.0. Không có bước kiểm tra chéo (cross-validation) nào giữa support và resistance.

---

## PART C — S/R OVERLAP / CONGESTION

### 1. Phân tích số liệu ca ETHUSD
- Support zone: `2521.83 – 2529.75`
- Resistance zone: `2523.99 – 2530.38`
- Current price: `2523.26`

Các thông số hình học:
- `support_width = 2529.75 - 2521.83 = 7.92`
- `resistance_width = 2530.38 - 2523.99 = 6.39`
- `overlap_low = max(2521.83, 2523.99) = 2523.99`
- `overlap_high = min(2529.75, 2530.38) = 2529.75`
- `overlap_width = 2529.75 - 2523.99 = 5.76`

Tỷ lệ chồng lấn:
- `overlap_ratio_support = 5.76 / 7.92 = 72.73%` (72.73% của Support nằm bên trong Resistance)
- `overlap_ratio_resistance = 5.76 / 6.39 = 90.14%` (90.14% của Resistance nằm bên trong Support)
- **Symmetric Overlap (Intersection over Union - IoU):**
  `Union width = max(2529.75, 2530.38) - min(2521.83, 2523.99) = 2530.38 - 2521.83 = 8.55`
  `IoU = 5.76 / 8.55 = 67.37%`
- **Dice Coefficient:** `(2 × 5.76) / (7.92 + 6.39) = 11.52 / 14.31 = 80.50%`.

### 2. Kiểm tra Code
- Trong `levels.py`: **KHÔNG CÓ** dòng code nào kiểm tra `support ∩ resistance != empty`.
- Trong `timeframe_analyzer.py`: **KHÔNG CÓ** kiểm tra.
- Trong `setup.py`: **KHÔNG CÓ** kiểm tra.
- Trong `eligibility.py`: **KHÔNG CÓ** kiểm tra.
- Hệ thống có phân loại `CLEAN_STRUCTURE`, `MODERATE_OVERLAP`, `HEAVY_OVERLAP`, `CONGESTION` không? **KHÔNG**.
- Kết luận:
```
S/R OVERLAP HANDLING: MISSING
```

---

## PART D — ETHUSD CASE RECONSTRUCTION

Giải thích chi tiết cách trạng thái này tồn tại trong code:

1. **WHY LONG?**
   Điểm tổng hợp đa khung thời gian (`MTF score`) đạt `+34.60`. Vì `34.60 >= +20.0` (`MTF_LONG_THRESHOLD`) và không có xung đột xu hướng H4/D1, hệ thống quyết định `final_signal = "LONG"`.

2. **WHY this Support (2521.83 – 2529.75)?**
   - Trên backend, nến M15 đóng gần nhất có `close ≈ 2523`. Mức swing low gần nhất bên dưới `close` là `2521.83` (`primary.nearest_support`).
   - Tuy nhiên, trong danh sách `primary.supports` hoặc `H4.supports`, có tồn tại một swing low cũ hơn ở mức `2529.75` (trước khi giá giảm nhẹ).
   - Trên frontend (`dashboard/lib/trading-analysis/key-levels.ts`), hàm `buildKeyLevelsSnapshot` lấy `supportAnchor = 2521.83` (mức dưới `currentPrice = 2523.26`).
   - Sau đó `_clusterAround` gom tất cả các mức support nằm trong phạm vi `± 0.5 × ATR` quanh anchor. Với ATR của ETH lúc đó ~16, khoảng gom là ~8 giá. Vì `2529.75 - 2521.83 = 7.92 <= 8`, frontend đã gộp mức `2529.75` vào cùng cụm với `2521.83`, tạo ra vùng hiển thị `2521.83 – 2529.75` — dù đỉnh của vùng này (2529.75) nằm CAO HƠN GIÁ HIỆN TẠI!

3. **WHY this Resistance (2523.99 – 2530.38)?**
   - Mức swing high gần nhất bên trên `close` là `2523.99` (`primary.nearest_resistance`).
   - Một mức swing high khác ở `2530.38` cũng nằm trong khoảng `0.5 × ATR` nên frontend gộp thành vùng `2523.99 – 2530.38`.

4. **WHY Entry Zone is below current (2520.83 – 2522.83)?**
   - Trong `build_trade_setup`:
     `anchor = primary.nearest_support = 2521.83`
     `entry = 2521.83`
     `half = atr * 0.25 = 1.00` (với ATR = 4.0)
     `entry_zone_low = 2521.83 - 1.00 = 2520.83`
     `entry_zone_high = 2521.83 + 1.00 = 2522.83`
   - Entry zone được neo quanh mức 2521.83.
   - Giá thị trường lúc đó là `2523.26`, nằm trên `entry_zone_high` (2522.83) một khoảng 0.43 giá.

5. **WHY WAITING_FOR_ENTRY?**
   - `setup.py` dòng 158 và `contract/lifecycle.py` dòng 45: Vì `current_price (2523.26) > entry_zone_high (2522.83)`, trạng thái setup được xác định là `WAITING_FOR_ENTRY`. Bot đang chờ giá hồi (pullback) về vùng 2520.83 – 2522.83.

6. **WHY BLOCKED?**
   - Trong `contract/eligibility.py` dòng 111:
     ```python
     if setup.state != SetupLifecycleState.ENTRY_ZONE:
         if setup.state == SetupLifecycleState.WAITING_FOR_ENTRY:
             blocking.append("PRICE_NOT_IN_ENTRY_ZONE")
     ```
   - Khi trạng thái là `WAITING_FOR_ENTRY`, hệ thống coi đây là điều kiện chặn (blocking reason `PRICE_NOT_IN_ENTRY_ZONE`).
   - Do đó `eligible = False`, `ExecutionCandidate = None`. Dashboard hiển thị `BLOCKED`.

---

## PART E — ENTRY ZONE FORMULA

### Công thức chính xác (`setup.py` lines 105–185)

Đối với **LONG**:
```python
if primary.nearest_support is not None:
    anchor = primary.nearest_support
    entry_reason = "PULLBACK_TO_SUPPORT"
else:
    anchor = current_price - atr * 0.5
    entry_reason = "PULLBACK_ESTIMATED_FROM_ATR"

entry_reference = anchor
entry = float(anchor)
half = atr * entry_zone_atr_width  # default: 0.25 * ATR14
entry_low = round(entry - half, 5)
entry_high = round(entry + half, 5)
```

Đối với **SHORT**:
```python
if primary.nearest_resistance is not None:
    anchor = primary.nearest_resistance
    entry_reason = "PULLBACK_TO_RESISTANCE"
else:
    anchor = current_price + atr * 0.5
    entry_reason = "PULLBACK_ESTIMATED_FROM_ATR"

entry_reference = anchor
entry = float(anchor)
half = atr * entry_zone_atr_width  # default: 0.25 * ATR14
entry_low = round(entry - half, 5)
entry_high = round(entry + half, 5)
```

### Bảng các yếu tố ảnh hưởng

| Yếu tố | Có ảnh hưởng Entry Zone không? | Chi tiết trong Code |
|---|---|---|
| Current price | **CÓ (khi anchor is None)** | Nếu không có S/R, `anchor = current_price ± 0.5 × ATR`. |
| BID / ASK | **CÓ (gián tiếp)** | `current_price` là `(bid + ask) / 2` từ live tick. |
| Current spread | **KHÔNG** | Spread không xuất hiện trong công thức tính vùng vào lệnh. |
| Latest closed M15 close | **CÓ (gián tiếp)** | Dùng làm mốc tìm `nearest_support_below(supports, close)`. |
| ATR (`atr14`) | **CÓ** | Quyết định độ rộng vùng (`± 0.25 × ATR`) và khoảng lùi ước tính (`0.5 × ATR`). |
| Nearest support | **CÓ** | Quyết định trực tiếp giá tâm `entry` cho lệnh LONG khi có mức hỗ trợ. |
| Nearest resistance | **CÓ** | Quyết định trực tiếp giá tâm `entry` cho lệnh SHORT khi có mức kháng cự. |
| Signal direction | **CÓ** | Quyết định chọn Support hay Resistance làm anchor. |
| Market structure | **CÓ (gián tiếp)** | Swings tạo nên các mức S/R. |
| MTF score | **KHÔNG** | MTF score chỉ quyết định hướng tín hiệu (LONG/SHORT/WAIT). |

**Phân biệt rõ:**
- **MARKET PRICE:** Giá tick trực tiếp `(bid + ask) / 2`.
- **TECHNICAL REFERENCE PRICE:** Tâm cụm swing low/high lịch sử (`primary.nearest_support` hoặc `primary.nearest_resistance`). Khi không tìm thấy mức kỹ thuật này, hệ thống **bị thoái biến dùng Market Price** (`current_price ± 0.5 × ATR`).

---

## PART F — PRICE CHASING AUDIT

### 1. Hành vi Price Chasing thực tế
Hệ thống **CÓ HIỆN TƯỢNG PRICE CHASING** theo hai cơ chế:

1. **Price Chasing ngay trong cùng một nến (Intra-candle) khi thiếu S/R:**
   Nếu `primary.nearest_support` là `None`:
   - `anchor = current_price - 0.5 × atr`.
   - Khi giá nhảy từ 2523 → 2528 → 2533, `entry` lập tức nhảy từ 2521 → 2526 → 2531.
   - Vùng Entry Zone liên tục chạy đuổi theo giá thị trường trên từng tick.
   - Trong `ExecutionContractService._reconcile_lifecycle`: vì `setup_id` chỉ tính theo thời gian đóng nến M15, `active.setup_id == proposed.setup_id`. Code thực hiện:
     ```python
     refreshed = CanonicalTradeSetup(**{**proposed.__dict__, "created_at": active.created_at})
     self._store.upsert(refreshed)
     ```
     **Cùng một `setup_id` nhưng các mức `entry_zone_low`, `entry_zone_high`, `entry_price` bị ghi đè thay đổi liên tục trong database!**

2. **Price Chasing qua các nến M15 (Inter-candle):**
   Mỗi khi một nến M15 mới đóng:
   - `source_candle_timestamp` tăng thêm 15 phút.
   - `setup_id` thay đổi hoàn toàn.
   - Trong `_reconcile_lifecycle`: `active.setup_id != proposed.setup_id` kích hoạt `materially_different = True`. Setup cũ bị đánh dấu `SUPERSEDED` và bị hủy bỏ ngay lập tức!
   - Setup mới được tạo ra với giá đóng cửa nến mới. Nếu giá vừa tăng mạnh, setup mới sẽ yêu cầu mức Entry Zone cao hơn, đuổi theo giá vừa tăng.

### 2. Trả lời cụ thể

- Dashboard polling có tự ý mutate setup không? **CÓ**. Request `GET /analysis/{symbol}/execution-candidate` gọi `_reconcile_lifecycle` và gọi `self._store.upsert(refreshed)`, ghi dữ liệu mới vào SQLite ngay trong HTTP GET.
- Biến động quote có mutate setup không? **CÓ** (khi anchor is None hoặc khi trạng thái chuyển đổi giữa `WAITING_FOR_ENTRY` và `ENTRY_ZONE`).
- Mỗi API request có build lại setup không? **CÓ** (tính toán lại từ đầu).
- Mỗi nến M15 mới có build lại setup không? **CÓ** (tạo setup_id mới và supersede setup cũ).
- Cùng một `setup_id` có thể có `entry_low/high` khác nhau không? **CÓ** (khi anchor fallback theo `current_price`).

---

## PART G — SETUP IDENTITY

### 1. Định nghĩa "cùng một setup"
Hàm `compute_setup_id` trong `market_analysis/contract/identity.py`:
```python
raw = "|".join([
    strategy_id,
    symbol.upper(),
    primary_timeframe,
    _iso(source_candle_timestamp),
    direction,
    contract_version,
])
return f"setup_{_stable_hash(raw)[:24]}"
```

Các trường tham gia định danh:
1. `strategy_id` ("mtf_technical_v1")
2. `symbol` (ví dụ "ETHUSD")
3. `primary_timeframe` ("M15")
4. `source_candle_timestamp` (thời điểm mở của nến M15 đã đóng)
5. `direction` ("LONG" hoặc "SHORT")
6. `contract_version` ("1")

**`setup_id` HOÀN TOÀN KHÔNG CHỨA:** `entry_price`, `entry_zone_low`, `entry_zone_high`, `stop_loss`, `take_profits`, hay `current_price`.

### 2. Các tình huống cụ thể

- Nếu chỉ có giá hiện tại thay đổi: **CÙNG SETUP** (về `setup_id`), nhưng `analysis_fingerprint` có thể thay đổi (nếu anchor is None) và `state` thay đổi.
- Nếu một nến M15 mới đóng: **SETUP MỚI** (`source_candle_timestamp` thay đổi).
- Nếu S/R dịch chuyển nhẹ: Trong cùng 1 nến, S/R tính trên nến đóng nên không đổi. Qua nến mới: **SETUP MỚI**.
- Nếu MTF score thay đổi nhưng vẫn là LONG: **CÙNG SETUP**.
- Nếu cấu trúc thị trường thay đổi (HH→LH): Nếu xảy ra sau nến mới: **SETUP MỚI**.

---

## PART H — SETUP PERSISTENCE

### Bảng cấu trúc lưu trữ (`market_analysis/contract/store.py`)
Bảng `setup_lifecycle` trong SQLite lưu:
- `setup_id TEXT PRIMARY KEY`
- `symbol TEXT`
- `strategy_id TEXT`
- `direction TEXT`
- `state TEXT`
- `created_at TEXT`
- `expires_at TEXT`
- `payload TEXT` (JSON đầy đủ của `CanonicalTradeSetup`: entry, SL, TP, fingerprint, v.v.)
- `updated_at TEXT`

### Bản chất của Snapshot
Mỗi khi có request API hoặc chu kỳ auto demo:
Hàm `_reconcile_lifecycle` lấy setup vừa tính toán (`proposed`) đè lên bản ghi hiện tại trong database:
```python
refreshed = CanonicalTradeSetup(
    **{
        **proposed.__dict__,
        "created_at": active.created_at,
        "state": proposed.state,
    }
)
self._store.upsert(refreshed)
```
Setup trong database **KHÔNG HỀ BẤT BIẾN (IMMUTABLE)**. Toàn bộ thông số giá hình học được tái tạo (regenerated) và ghi đè trên mỗi lần đánh giá.

```
SETUP SNAPSHOT: REGENERATED
```

---

## PART I — LIFECYCLE

### 1. Các trạng thái trong code (`SetupLifecycleState`)
- `NO_SETUP`
- `WAITING_FOR_ENTRY`
- `ENTRY_ZONE`
- `INVALIDATED`
- `EXPIRED`
- `SUPERSEDED`

*(Lưu ý: Trạng thái `TRIGGERED` KHÔNG TỒN TẠI trong code).*

### 2. Điều kiện chuyển trạng thái chính xác (`contract/lifecycle.py`)

Hàm `derive_state_from_price`:
```python
def derive_state_from_price(*, direction, current_price, entry_zone_low, entry_zone_high, stop_loss, now, expires_at):
    if now >= expires_at:
        return SetupLifecycleState.EXPIRED

    if direction == "LONG":
        if current_price <= stop_loss:
            return SetupLifecycleState.INVALIDATED
        if entry_zone_low <= current_price <= entry_zone_high:
            return SetupLifecycleState.ENTRY_ZONE
        return SetupLifecycleState.WAITING_FOR_ENTRY

    # SHORT
    if current_price >= stop_loss:
        return SetupLifecycleState.INVALIDATED
    if entry_zone_low <= current_price <= entry_zone_high:
        return SetupLifecycleState.ENTRY_ZONE
    return SetupLifecycleState.WAITING_FOR_ENTRY
```

### 3. Điều kiện `WAITING_FOR_ENTRY → ENTRY_ZONE`
- Điều kiện so sánh: `entry_zone_low <= current_price <= entry_zone_high`.
- Giá được sử dụng: **`current_price` = Giá MID của live tick** (`(bid + ask) / 2`). Không phải Bid, không phải Ask, không phải nến đóng.
- **Hạn chế nghiêm trọng (Latching defect):** Hàm này là pure function không có bộ nhớ (stateless). Nếu giá chạm vào vùng `ENTRY_ZONE`, trạng thái là `ENTRY_ZONE`. Nhưng ngay tick sau đó nếu giá nhích lên 1 cent vượt qua `entry_zone_high`, trạng thái **TỰ ĐỘNG BẬT NGƯỢC LẠI** thành `WAITING_FOR_ENTRY`! Không có cơ chế giữ trạng thái (latch) khi giá đã kích hoạt vùng.

---

## PART J — INVALIDATION

### 1. Logic Invalidation thực tế
- Đối với **LONG**: `current_price <= stop_loss`.
- Đối với **SHORT**: `current_price >= stop_loss`.

### 2. Các yếu tố được sử dụng
- S/R break: **KHÔNG**.
- Swing structure: **KHÔNG**.
- ATR: **KHÔNG**.
- Candle close: **KHÔNG**.
- Current quote: **CÓ** (giá MID tức thời).
- SL: **CÓ** (`stop_loss`).
- Đảo chiều MTF: **KHÔNG** (nếu MTF đổi chiều, setup bị đánh dấu `SUPERSEDED` hoặc `EXPIRED`, không phải `INVALIDATED`).

### 3. Vấn đề "Un-invalidation"
Vì `derive_state_from_price` tính toán thuần túy trên `current_price` tức thời:
Nếu một tick nhúng qua SL → setup thành `INVALIDATED`.
Nhưng nếu ngay tick sau giá bật ngược trở lại trên SL → hàm trả về `WAITING_FOR_ENTRY`!
Trong `_reconcile_lifecycle`:
`refreshed.state = proposed.state`.
Trạng thái `INVALIDATED` không bị khóa (not terminal/latched). Setup bị un-invalidated ngay lập tức.

### 4. Setup có chạy đuổi giá thay vì Invalidated không?
**CÓ**. Nếu giá đi ngược hướng pullback (ví dụ LONG nhưng giá tăng vọt đi luôn), giá không bao giờ chạm SL. Thay vì bị invalidate, cứ sau 15 phút setup cũ bị supersede và setup mới lại được sinh ra ở mức giá cao hơn, tiếp tục đuổi theo giá.

---

## PART K — EXPIRATION

### 1. Logic Expiration trong code
- `compute_expires_at`: `expires_at = source_candle_timestamp + 8 × 15 phút = source_candle_timestamp + 2 giờ`.
- Kiểm tra: `if now >= expires_at: return EXPIRED`.

### 2. Thực tế vận hành
Mặc dù công thức ghi là hết hạn sau 8 nến (2 giờ), nhưng trong thực tế:
**Cứ sau đúng 1 nến M15 (15 phút), khi nến mới đóng, setup cũ đã bị đánh dấu là `SUPERSEDED`!**
Do đó, điều kiện hết hạn 8 nến **gần như không bao giờ được kích hoạt trong điều kiện thị trường bình thường**, vì setup đã bị thay thế sau 15 phút.

```
SETUP EXPIRATION: PARTIAL
```

---

## PART L — MỐI QUAN HỆ S/R vs ENTRY

### 1. Đối với lệnh LONG
- Thứ tự hình học kỳ vọng: `Support <= Entry < Current Price < Resistance`.
- Thực tế trong code:
  `anchor = primary.nearest_support`
  `entry = float(anchor)`
  `zone_low = entry - 0.25 * ATR`
  `zone_high = entry + 0.25 * ATR`
- Entry Zone được **neo chính xác tại tâm của Nearest Support**.
- Giá vào lệnh kỳ vọng bằng đúng mức hỗ trợ M15.

### 2. Đối với lệnh SHORT
- Thứ tự hình học kỳ vọng: `Support < Current Price < Entry <= Resistance`.
- Thực tế trong code: Entry Zone được neo chính xác tại tâm của `nearest_resistance`.

---

## PART M — TRADE SPACE / OBSTACLE CHECK

### 1. Kiểm tra khoảng trống giao dịch (Obstacle Check)
- Khi vào lệnh LONG tại Entry, có một Resistance ngay sát phía trên:
  Liệu hệ thống có tính:
  `reward_space = nearest_resistance - entry`
  `risk_space = entry - stop_loss`
  `effective_rr = reward_space / risk_space`
  để chặn lệnh nếu không đủ không gian tăng giá?

### 2. Kết quả kiểm tra Code
- Trong `eligibility.py`: **HOÀN TOÀN KHÔNG CÓ** bất kỳ kiểm tra nào về khoảng cách tới cản đối diện.
- Trong `setup.py`: Hoàn toàn không chặn lệnh nếu cản đối diện nằm ngay sát trên đầu Entry.
- Trả lời: **NO**.
```
TRADE SPACE CHECK: MISSING
```

---

## PART N — TP vs STRUCTURE

### 1. Cơ chế tính Take Profit (`setup.py` lines 250–320)
- Hệ thống lấy các mức resistance `> entry`.
- Nếu có resistance: đưa vào danh sách mục tiêu `targets`.
- Nếu thiếu: bù bằng các bội số R: `entry + 1.0 * risk`, `entry + 2.0 * risk`, `entry + 3.0 * risk`.
- Gán `TP1 = targets[0]`, `TP2 = targets[1]`, `TP3 = targets[2]`.

### 2. Các lỗ hổng cấu trúc TP
1. **LONG TP1 có thể nằm trên cản đối diện mà không bị chặn:**
   Trong code dòng 284: `if crossed and idx >= 2: warnings.append(...)`.
   Code **chỉ kiểm tra cản bị xuyên qua đối với TP2 và TP3 (`idx >= 2`)**.
   Đối với **TP1 (`idx == 1`)**, code HOÀN TOÀN BỎ QUA việc có cản nằm chắn giữa Entry và TP1 hay không!
2. **Cảnh báo không chặn lệnh:**
   Ngay cả với TP2/TP3, nó chỉ sinh ra `warning` ("TP_BEYOND_MAJOR_RESISTANCE"), mà warning thì không chặn `eligibility`!
3. **TP1_ONLY trong Execution:**
   Vì hệ thống thực thi DEMO chỉ khớp `TP1_ONLY`, nếu TP1 nằm sau một cản mạnh hoặc TP1 bị ép vào một cản quá gần (R:R < 0.5), lệnh vẫn được coi là hợp lệ!
```
TP STRUCTURE CHECK: MISSING
```

---

## PART O — TẠI SAO CHƯA CÓ LỆNH DEMO NÀO? (FUNNEL ANALYSIS)

### 1. Phân tích phễu thực tế (Funnel)

```
[1] Closed M15 Candle (100%)
      │
      ▼  (Chỉ ~10-25% nến đạt ngưỡng MTF Score >= +20 hoặc <= -20)
[2] final_signal = LONG / SHORT
      │
      ▼  (Tạo setup với anchor = nearest_support ở đáy cũ)
[3] Trade Setup (WAITING_FOR_ENTRY)
      │
      ▼  (NGHẼN CHÍNH Ở ĐÂY: Giá đang tăng mạnh, cách Support 1-3 ATR)
[4] ENTRY_ZONE (entry - 0.25*ATR <= price <= entry + 0.25*ATR)  <-- TỶ LỆ CỰC THẤP (<2%)
      │
      ▼
[5] ExecutionCandidate (chỉ tạo khi ở ENTRY_ZONE)  <-- GẦN NHƯ LUÔN BẰNG 0
      │
      ▼
[6] Risk Gates / Precheck (chỉ đánh giá khi có Candidate)
      │
      ▼
[7] DEMO Order Submission
```

### 2. Nguyên nhân cốt lõi (Root Cause)
Nguyên nhân bot chưa bao giờ đặt lệnh DEMO không phải do lỗi API hay lỗi kết nối MT5, mà nằm ở:

**Phân loại: `ENTRY_ZONE` (PRICE_NOT_IN_ENTRY_ZONE)**

1. **Yêu cầu Pullback quá cứng nhắc:** Khi xu hướng đủ mạnh để MTF Score đạt ≥ 20 (LONG), giá thường đã bứt phá xa khỏi swing low gần nhất. Bot lại đặt vùng Entry Zone ngay tại đỉnh của swing low cũ với biên độ rất hẹp (`± 0.25 × ATR`). Giá rất hiếm khi hồi sâu về đúng vùng này ngay lập tức.
2. **Cơ chế Supersede 15 phút hủy diệt lệnh chờ:** Trong khi giá đang từ từ hồi về, cứ sau đúng 15 phút, nến M15 tiếp theo đóng cửa. Hệ thống sinh ra `setup_id` mới và đánh dấu setup cũ là `SUPERSEDED`. Cơ hội chờ giá hồi của setup cũ bị xóa sổ hoàn toàn sau mỗi 15 phút.
3. **Không có lệnh chờ (Limit Order):** Bot chỉ gửi lệnh Deal (Market order) khi giá MID tức thời rơi đúng vào hộp `entry_zone_low <= price <= entry_zone_high`. Nếu giá chạm nhẹ vào rồi bật ra giữa 2 chu kỳ poll của bot, bot hoàn toàn bỏ lỡ.

---

## PART P — IMMUTABLE SETUP DESIGN REVIEW

### So sánh Kiến trúc Hiện tại vs Thiết kế Đề xuất

| Đặc tính | Kiến trúc Hiện tại | Thiết kế Đề xuất (Immutable Setup) |
|---|---|---|
| **Tính bất biến của Setup** | **REGENERATED**: Ghi đè toàn bộ thông số giá trên mỗi tick/request polling. | **FROZEN**: Một khi đã sinh ra tại nến $T$, toàn bộ tọa độ giá (Entry, SL, TP) đóng băng vĩnh viễn. |
| **Vòng đời qua các nến** | Bị **SUPERSEDED** sau mỗi 15 phút (mỗi nến M15). | Tiếp tục sống và chờ khớp trong tối đa $N$ nến ($N=8$, tức 2 giờ) trừ khi bị Invalidated. |
| **Chuyển trạng thái** | Không có chốt (unlatched): giá chạm Entry Zone rồi vọt ra thì quay lại WAITING; chạm SL rồi hồi thì thoát Invalidated. | **Chốt trạng thái một chiều (State Latching)**: `WAITING → ENTRY_ZONE → TRIGGERED/FILLED`. Một khi chạm SL → `INVALIDATED` vĩnh viễn. |
| **Khi không có S/R** | Chạy đuổi theo giá: `anchor = current_price ± 0.5*ATR`. | Không tạo setup (NO_SETUP) hoặc dùng giá mở nến đóng cố định, tuyệt đối không dùng live tick. |

---

## PART Q — ĐỊNH NGHĨA "MATERIAL CHANGE"

Hệ thống cần phân biệt giữa biến động giá thông thường và thay đổi cấu trúc kỹ thuật trọng yếu:

1. **Biến động giá thông thường (Normal Price Action):**
   - Giá dao động trong phạm vi giữa Entry Zone và Invalidation Level (SL).
   - Các nến M15 tiếp tục đóng cửa nhưng không tạo tín hiệu đảo chiều MTF.
   - **Xử lý:** GIỮ NGUYÊN active setup hiện tại, không supersede, tiếp tục đợi giá hồi về Entry Zone.

2. **Thay đổi kỹ thuật trọng yếu (Material Technical Change):**
   - Tín hiệu MTF đảo chiều (ví dụ đang LONG chuyển sang WAIT hoặc SHORT).
   - Giá phá vỡ mức Invalidation Level (SL hoặc vỡ swing low quan trọng).
   - Xuất hiện cấu trúc phá vỡ xu hướng (Change of Character - CHoCH).
   - Hết thời gian chờ tối đa (đủ 8 nến M15 không khớp).
   - **Xử lý:** Chuyển setup hiện tại sang `INVALIDATED` hoặc `EXPIRED`, sau đó mới được phép tạo setup mới.

---

## PART R — SAFETY BOUNDARY

Kiểm tra ranh giới an toàn:
- Toàn bộ logic Setup, S/R, Entry Zone, Eligibility nằm trong `market_analysis/`.
- Stack thực thi (`ExecutionOrchestrator`, `GatedMT5ExecutionPort`, `MT5Executor`, `LiveMT5ExecutionTransport`, `auto_demo`) chỉ nhận `ExecutionCandidate` đã hoàn chỉnh để chuyển thành `ExecutionPlan` và gửi lệnh có kiểm soát.
- Mọi sửa đổi về chất lượng setup hoàn toàn độc lập và nằm trước phễu thực thi.

```
SETUP QUALITY FIX CAN BE ISOLATED FROM EXECUTION: YES
```

---

## PART S — REQUIRED VERDICTS

```
PRICE CHASING:                                  YES
SAME SETUP CAN MUTATE ENTRY:                    YES
SETUP SNAPSHOT:                                 REGENERATED
S/R OVERLAP HANDLING:                           MISSING
ETHUSD S/R:                                     HEAVILY_OVERLAPPING
TRADE SPACE CHECK:                              MISSING
TP STRUCTURE CHECK:                             MISSING
SETUP EXPIRATION:                               PARTIAL
SETUP INVALIDATION:                             PARTIAL
NO-DEMO-ORDER ROOT CAUSE:                       ENTRY_ZONE
SETUP QUALITY FIX CAN BE ISOLATED FROM EXECUTION: YES
```

---

## PART T — KẾ HOẠCH KHẮC PHỤC (PROPOSED REMEDIATION PLAN)

*(Đề xuất kiến trúc — KHÔNG thực hiện thay đổi code trong báo cáo này)*

### Mức P0 — Ngăn chặn thực thi / Sai lệch logic cốt lõi
1. **Sửa lỗi Setup Mutation trong `_reconcile_lifecycle`:**
   - **File:** `market_analysis/contract/service.py`
   - **Nguyên nhân:** Khi `active.setup_id == proposed.setup_id`, code lấy `**proposed.__dict__` ghi đè lên setup cũ trong database.
   - **Giải pháp:** Chỉ cập nhật `state` nếu thỏa mãn chuyển trạng thái hợp lệ. Giữ nguyên toàn bộ thông số giá (`entry_price`, `entry_zone_low`, `entry_zone_high`, `stop_loss`, `take_profits`) của setup gốc.
2. **Khắc phục lỗi Supersede nến 15 phút:**
   - **File:** `market_analysis/contract/service.py` (`_reconcile_lifecycle`), `contract/lifecycle.py`
   - **Nguyên nhân:** Mỗi nến M15 đóng tạo ra `setup_id` mới và lập tức supersede setup đang chờ.
   - **Giải pháp:** Nếu active setup đang ở `WAITING_FOR_ENTRY` hoặc `ENTRY_ZONE` và chưa hết hạn (`now < expires_at`), giữ lại active setup đó cho đến khi hết hạn hoặc bị invalidated.
3. **Loại bỏ Price Chasing khi thiếu S/R:**
   - **File:** `market_analysis/setup.py`
   - **Nguyên nhân:** `anchor = current_price ± 0.5 * ATR` đuổi theo live quote.
   - **Giải pháp:** Nếu không có S/R xác nhận bên dưới/trên, trả về `SetupState.NO_SETUP` (không đủ điều kiện kỹ thuật) thay vì bịa anchor từ giá thị trường.

### Mức P1 — Nguy cơ vào lệnh ở cấu trúc xấu
1. **Bổ sung S/R Overlap Detection & Congestion Filter:**
   - **File:** `market_analysis/levels.py`, `contract/eligibility.py`
   - **Giải pháp:** Tính độ chồng lấn giữa Nearest Support và Nearest Resistance. Nếu `overlap_ratio > 0.3` (chồng lấn > 30%), phân loại là `CONGESTED_STRUCTURE` và chặn (block) tạo setup.
2. **Bổ sung Trade Space Check:**
   - **File:** `contract/eligibility.py`
   - **Giải pháp:** Kiểm tra khoảng cách từ Entry tới cản đối diện: `(resistance - entry) >= 1.0 * (entry - sl)`. Nếu cản đối diện quá gần, chặn với lý do `INSUFFICIENT_TRADE_SPACE`.

### Mức P2 — Hoàn thiện chất lượng TP
1. **Kiểm tra cản đối với TP1:**
   - **File:** `market_analysis/setup.py` (`_build_long_tps`, `_build_short_tps`)
   - **Giải pháp:** Không cho phép TP1 vượt qua kháng cự lớn mà không có cảnh báo hoặc điều chỉnh.

### Mức P3 — Tinh chỉnh hiển thị Dashboard
1. **Sửa logic `_clusterAround` trên Frontend:**
   - **File:** `dashboard/lib/trading-analysis/key-levels.ts`
   - **Giải pháp:** Không gom các mức support nằm cao hơn giá hiện tại hoặc cao hơn resistance vào cụm support hiển thị.

---

## PART U — TEST PLAN ĐỀ XUẤT

1. **Test cùng setup + quote thay đổi:** Đảm bảo `entry_zone_low` và `entry_zone_high` trong SQLite không thay đổi khi giá thị trường biến động.
2. **Test Dashboard/API refresh:** Gọi `GET /analysis/{symbol}/execution-candidate` nhiều lần không làm thay đổi tọa độ hình học của setup trong DB.
3. **Test cùng nến M15:** Đảm bảo tính toán lặp lại cho ra cùng `analysis_fingerprint`.
4. **Test nến M15 mới khi đang có setup chờ:** Setup đang `WAITING_FOR_ENTRY` không bị supersede nếu chưa vi phạm SL hoặc chưa quá 8 nến.
5. **Test thay đổi cấu trúc trọng yếu:** Khi MTF đổi chiều sang SHORT, setup LONG cũ lập tức chuyển thành `SUPERSEDED`/`EXPIRED`.
6. **Test LONG giá chạm vùng vào lệnh:** Giá MID đi vào `[entry_low, entry_high]` chuyển trạng thái sang `ENTRY_ZONE`.
7. **Test SHORT giá chạm vùng vào lệnh:** Giá MID đi vào vùng chuyển trạng thái sang `ENTRY_ZONE`.
8. **Test giá rời khỏi vùng:** Sau khi đã vào `ENTRY_ZONE`, vùng không chạy đuổi theo giá.
9. **Test S/R chồng lấn nặng:** Tạo dữ liệu giả lập support/resistance chồng lấn > 50% → hệ thống phân loại `CONGESTION` và chặn lệnh.
10. **Test tính nhất quán S/R:** Đảm bảo không bao giờ có Support nằm trên Resistance.
11. **Test Restart:** Khởi động lại engine, đọc lại setup từ SQLite, tọa độ giá nguyên vẹn 100%.
12. **Regression:** Toàn bộ 49 test Phase 17.3 và 103 test regression tiếp tục PASS.

---

## PART V — DANH MỤC FILES ĐÃ AUDIT

- `trading-engine/src/exness_bot/market_analysis/levels.py`
- `trading-engine/src/exness_bot/market_analysis/swings.py`
- `trading-engine/src/exness_bot/market_analysis/structure.py`
- `trading-engine/src/exness_bot/market_analysis/setup.py`
- `trading-engine/src/exness_bot/market_analysis/timeframe_analyzer.py`
- `trading-engine/src/exness_bot/market_analysis/mtf_service.py`
- `trading-engine/src/exness_bot/market_analysis/contract/service.py`
- `trading-engine/src/exness_bot/market_analysis/contract/lifecycle.py`
- `trading-engine/src/exness_bot/market_analysis/contract/identity.py`
- `trading-engine/src/exness_bot/market_analysis/contract/models.py`
- `trading-engine/src/exness_bot/market_analysis/contract/store.py`
- `trading-engine/src/exness_bot/market_analysis/contract/eligibility.py`
- `trading-engine/src/exness_bot/market_analysis/contract/candidate.py`
- `trading-engine/src/exness_bot/api/services/read_service.py`
- `trading-engine/src/exness_bot/api/routes/v1.py`
- `dashboard/lib/trading-analysis/key-levels.ts`
- `dashboard/components/trading-analysis/KeyLevelsPanel.tsx`

---

## XÁC NHẬN AN TOÀN
- Production strategy logic: **UNCHANGED**
- Execution architecture: **UNCHANGED**
- Risk parameters: **UNCHANGED**
- Real `order_send`: **NONE**
- LIVE trading: **DISABLED**
