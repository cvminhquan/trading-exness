# BÁO CÁO KỸ THUẬT: PHASE 17.3.1 — IMMUTABLE SETUP LIFECYCLE HARDENING

## TỔNG QUAN DỰ ÁN
- **Trạng thái:** HOÀN TẤT (PASS)
- **Mục tiêu:** Khắc phục triệt để các lỗi vòng đời và hiện tượng đột biến hình học setup (Geometry Mutation / Price Chasing) đã được phát hiện trong cuộc audit `docs/PHASE_17_3_SETUP_QUALITY_AUDIT.md`.
- **Phạm vi an toàn:** Không tối ưu hóa tham số lợi nhuận, không nới lỏng ngưỡng rủi ro, không thay đổi kiến trúc thực thi (Execution Architecture), không kết nối AI vào execution, và **tuyệt đối không gửi lệnh thật (0 real `order_send`)**.

---

## 1. CÁC NGUYÊN NHÂN GỐC RỄ ĐÃ ĐƯỢC KHẮC PHỤC (ROOT CAUSES FIXED)

1. **Lỗi ghi đè hình học Setup khi Reconcile (`_reconcile_lifecycle` Geometry Mutation):**
   - *Trước đây:* Khi cùng một `setup_id` được đối soát, hàm `_reconcile_lifecycle` trong `contract/service.py` đã dùng `**proposed.__dict__` để tái tạo `CanonicalTradeSetup`, khiến các tọa độ giá (`entry_price`, `entry_zone_low`, `entry_zone_high`, `stop_loss`, `take_profits`) bị ghi đè theo giá thị trường mới nhất của tick.
   - *Khắc phục:* Khi `active` setup đang hoạt động và không có thay đổi hướng cơ bản, hệ thống **bảo tồn nguyên vẹn hình học ban đầu của `active`**. Tuyệt đối không thay thế các trường hình học kỹ thuật đã đóng băng.

2. **Lỗi triệt tiêu vòng đời sau mỗi nến 15 phút (Premature Supersession across M15):**
   - *Trước đây:* Khi nến M15 mới đóng, `source_candle_timestamp` thay đổi dẫn đến `setup_id` mới khác với `active.setup_id`. Hàm `materially_different` cũ trả về `True` chỉ vì `setup_id` khác nhau, khiến setup đang chờ (`WAITING_FOR_ENTRY`) lập tức bị đánh dấu `SUPERSEDED` sau đúng 15 phút, triệt tiêu thiết kế vòng đời 8 nến M15 (~2 giờ).
   - *Khắc phục:* `materially_different` chỉ trả về `True` khi có sự thay đổi thực sự về **hướng giao dịch** (`direction` LONG $\leftrightarrow$ SHORT), cặp tiền (`symbol`), hoặc chiến lược (`strategy_id`). Setup cũ tiếp tục tồn tại độc lập qua các nến M15 tiếp theo cho đến khi khớp, chạm SL hoặc hết hạn 8 nến.

3. **Hiện tượng đuổi giá khi thiếu Support/Resistance (Live Quote S/R Fallback):**
   - *Trước đây:* Khi không có mức `nearest_support` (LONG) hoặc `nearest_resistance` (SHORT), hàm `build_trade_setup` tự ý bịa ra Entry Zone bằng công thức `current_price ± 0.5 * ATR`. Vì `current_price` là giá MID live tick, Entry Zone bị trôi đuổi theo thị trường liên tục.
   - *Khắc phục:* Loại bỏ hoàn toàn fallback dựa trên giá thị trường. Khi thiếu mức S/R xác nhận, hệ thống **fail closed** trả về `SetupState.NO_SETUP` (`entry_price=None`, `entry_zone_low=None`, `entry_zone_high=None`, `stop_loss=None`, `entry_reason="NO_SUPPORT_LEVEL"` hoặc `"NO_RESISTANCE_LEVEL"`). Không sinh ra `ExecutionCandidate`.

4. **Trạng thái không được chốt chặn (Unlatched Lifecycle States):**
   - *Trước đây:* Nếu giá chạm SL rồi nảy lại, setup bị "un-invalidated" trở lại `WAITING_FOR_ENTRY`. Nếu giá chạm vào vùng Entry rồi nảy ra ngoài 1 cent, trạng thái bị tụt từ `ENTRY_ZONE` về `WAITING_FOR_ENTRY`.
   - *Khắc phục:* Chốt chặn một chiều (One-way State Latching):
     - `INVALIDATED`: Trạng thái kết thúc (terminal), không bao giờ phục hồi về `WAITING_FOR_ENTRY` hay `ENTRY_ZONE`.
     - `EXPIRED`: Trạng thái kết thúc (terminal), không bao giờ kích hoạt lại.
     - `SUPERSEDED`: Trạng thái kết thúc (terminal), không bao giờ kích hoạt lại.
     - `ENTRY_ZONE`: Một khi đã lọt vào Entry Zone, setup duy trì trạng thái `ENTRY_ZONE` (latched) cho đến khi khớp lệnh, chạm SL (chuyển sang `INVALIDATED`) hoặc hết hạn (`EXPIRED`). Giá nảy ra ngoài zone không làm mất trạng thái `ENTRY_ZONE`.

---

## 2. VÒNG ĐỜI TRƯỚC VÀ SAU (PREVIOUS VS NEW LIFECYCLE)

### Vòng đời trước (Flawed Ephemeral Lifecycle)
```text
T0: M15 đóng -> Sinh setup_id_A (Entry = 2520–2522, Current = 2525) -> WAITING_FOR_ENTRY
T+5m: Polling API -> Lấy proposed mới -> Ghi đè DB -> Entry Zone bị di chuyển!
T+15m: M15 mới đóng -> Sinh setup_id_B -> setup_id_A bị SUPERSEDED (Bị hủy sau 15 phút!)
T+20m: Không có S/R -> Entry = live_price - 0.5*ATR -> Entry Zone chạy theo từng tick!
T+25m: Giá chạm SL -> INVALIDATED -> Giá nảy lại -> Trở lại WAITING_FOR_ENTRY! (Sai logic)
```

### Vòng đời mới (Immutable Prediction Snapshot Lifecycle)
```text
T0: M15 đóng -> Đóng băng CanonicalTradeSetup (ID=setup_A, Entry=2520–2522, SL=2515, Exp=T0+2h)
T+5m: Polling API / Quote thay đổi -> Tọa độ giá KHÔNG ĐỔI (Entry vẫn 2520–2522, SL vẫn 2515)
T+15m: M15 mới đóng -> Không có đảo chiều xu hướng -> setup_A VẪN LÀ ACTIVE SETUP (Sống đủ 2h)
T+30m: Giá giảm về 2521.50 -> Chuyển sang ENTRY_ZONE
T+31m: Giá nảy lên 2523.50 -> VẪN GIỮ TRẠNG THÁI ENTRY_ZONE (Latched, sẵn sàng khớp lệnh)
T+45m: Nếu giá chạm 2514.0 (<= SL 2515) -> Chuyển sang INVALIDATED vĩnh viễn (Terminal)
       Giá sau đó nảy lên 2522 -> Vẫn giữ nguyên INVALIDATED, không bao giờ hồi sinh!
T+120m: Nếu không chạm SL và không khớp lệnh -> Chuyển sang EXPIRED (Terminal)
```

---

## 3. BẢNG PHÂN ĐỊNH TRƯỜNG DỮ LIỆU SETUP (FROZEN VS MUTABLE)

| Tên trường | Trạng thái | Diễn giải |
| :--- | :--- | :--- |
| `setup_id` | **BẤT BIẾN (FROZEN)** | Định danh tất định dựa trên nến M15 gốc tạo ra setup |
| `source_candle_timestamp` | **BẤT BIẾN (FROZEN)** | Timestamp của nến M15 đóng tạo ra dự báo |
| `created_at` | **BẤT BIẾN (FROZEN)** | Thời điểm setup được sinh ra lần đầu |
| `expires_at` | **BẤT BIẾN (FROZEN)** | Thời điểm hết hạn (8 nến M15 = 120 phút) |
| `direction` | **BẤT BIẾN (FROZEN)** | Hướng giao dịch (`LONG` hoặc `SHORT`) |
| `entry_price` | **BẤT BIẾN (FROZEN)** | Mức giá vào lệnh kỳ vọng |
| `entry_zone_low` | **BẤT BIẾN (FROZEN)** | Biên dưới của vùng vào lệnh |
| `entry_zone_high` | **BẤT BIẾN (FROZEN)** | Biên trên của vùng vào lệnh |
| `stop_loss` | **BẤT BIẾN (FROZEN)** | Mức cắt lỗ kỹ thuật |
| `take_profits` | **BẤT BIẾN (FROZEN)** | Danh sách các mức chốt lời (TP1, TP2, TP3) |
| `analysis_fingerprint` | **BẤT BIẾN (FROZEN)** | Mã băm hình học kỹ thuật |
| `state` | **MUTABLE (THEO LUẬT)** | Chỉ chuyển dịch trạng thái theo quy tắc chốt chặn |
| `updated_at` (DB) | **MUTABLE** | Thời điểm ghi nhận chuyển dịch trạng thái gần nhất trong SQLite |

---

## 4. QUY TẮC CHUYỂN DỊCH TRẠNG THÁI (LIFECYCLE TRANSITIONS)

Hàm `derive_state_from_price` tuân thủ nghiêm ngặt máy trạng thái sau:

1. **Terminal Latch:**
   Nếu `current_state` thuộc `{INVALIDATED, EXPIRED, SUPERSEDED, NO_SETUP}`, hàm lập tức trả về `current_state`. Không có bất kỳ biến động giá nào được phép hồi sinh setup đã kết thúc.

2. **Expiration Check:**
   Nếu `now >= expires_at`, lập tức chuyển sang `SetupLifecycleState.EXPIRED`.

3. **LONG Evaluation:**
   - Nếu `current_price <= stop_loss` $\rightarrow$ `INVALIDATED`.
   - Nếu `current_state == ENTRY_ZONE` $\rightarrow$ Giữ nguyên `ENTRY_ZONE` (Latched).
   - Nếu `entry_zone_low <= current_price <= entry_zone_high` $\rightarrow$ `ENTRY_ZONE`.
   - Ngược lại $\rightarrow$ `WAITING_FOR_ENTRY`.

4. **SHORT Evaluation:**
   - Nếu `current_price >= stop_loss` $\rightarrow$ `INVALIDATED`.
   - Nếu `current_state == ENTRY_ZONE` $\rightarrow$ Giữ nguyên `ENTRY_ZONE` (Latched).
   - Nếu `entry_zone_low <= current_price <= entry_zone_high` $\rightarrow$ `ENTRY_ZONE`.
   - Ngược lại $\rightarrow$ `WAITING_FOR_ENTRY`.

---

## 5. HÀNH VI KHI CÓ NẾN M15 MỚI (NEW M15 BEHAVIOR)

Khi nến M15 mới đóng cửa:
- Hệ thống tính toán một đề xuất kỹ thuật mới (`proposed`).
- Nếu đang có một setup `active` đang sống (`WAITING_FOR_ENTRY` hoặc `ENTRY_ZONE`):
  - Setup `active` **tiếp tục được duy trì làm setup chính quy (canonical)** với đầy đủ tọa độ giá ban đầu.
  - Setup `active` **không bị supersede** chỉ vì nến M15 mới đóng cửa.
  - Setup tiếp tục tồn tại cho đến khi khớp, chạm SL hoặc chạm mốc `expires_at` (đủ 8 nến = 2 giờ).

---

## 6. CHÍNH SÁCH THAY ĐỔI CƠ BẢN (MATERIAL CHANGE POLICY)

Setup `active` chỉ bị thay thế trước khi hết hạn trong các trường hợp tất định sau:
1. **Đảo chiều tín hiệu (Direction Reversal):**
   Tín hiệu phân tích chuyển từ `LONG` $\rightarrow$ `SHORT` hoặc ngược lại:
   - Setup `active` cũ được đánh dấu là `SUPERSEDED` trong SQLite store.
   - Setup `proposed` mới với hướng ngược lại được chấp thuận làm active setup mới.
2. **Tín hiệu chuyển sang WAIT:**
   Khi xu hướng bị phá vỡ và chiến lược chuyển sang `WAIT`:
   - Setup `active` cũ được chuyển thành `EXPIRED` (hoặc `SUPERSEDED`).
   - Không còn setup nào hoạt động.
3. **Setup chạm SL:**
   Chuyển sang `INVALIDATED`. Store không còn active setup, cho phép setup mới từ nến sau được chấp nhận.
4. **Setup hết hạn:**
   Chuyển sang `EXPIRED`.

---

## 7. BẢO TỒN VÀ BỀN VỮNG TRÊN SQLITE (PERSISTENCE & RESTART BEHAVIOR)

- Toàn bộ đối tượng `CanonicalTradeSetup` được lưu dưới dạng JSON tuần tự hóa chuẩn trong bảng `analysis_setup_lifecycle` của SQLite.
- Khi bot hoặc API service khởi động lại:
  - Hàm `get_active_for_symbol` nạp lại nguyên vẹn JSON payload từ SQLite.
  - Toàn bộ `entry_price`, `entry_zone_low`, `entry_zone_high`, `stop_loss`, `take_profits`, `created_at`, `expires_at` được phục hồi chính xác 100%.
  - Tuyệt đối không tính toán lại hình học setup sau khi restart.

---

## 8. BẰNG CHỨNG KIỂM THỬ (TEST EVIDENCE)

Tất cả 16 kịch bản yêu cầu tại Part L đã được hiện thực đầy đủ trong test suite:
`trading-engine/tests/unit/test_phase_17_3_1_immutable_setup_lifecycle.py`

| Test ID | Tên bài kiểm thử | Kết quả | Ý nghĩa kiểm chứng |
| :--- | :--- | :---: | :--- |
| Test 1 | `test_1_same_setup_quote_moves_geometry_unchanged` | **PASSED** | Giá tick thay đổi (2525 $\rightarrow$ 2527 $\rightarrow$ 2535), hình học setup vẫn giữ nguyên 2521.83 (2520.83–2522.83). |
| Test 2 | `test_2_dashboard_api_repoll_geometry_unchanged` | **PASSED** | Polling API / Dashboard nhiều lần không làm thay đổi tọa độ giá setup. |
| Test 3 | `test_3_same_closed_m15_deterministic_identity` | **PASSED** | Cùng nến M15 sinh ra cùng một `setup_id` tất định. |
| Test 4 | `test_4_new_m15_does_not_auto_supersede` | **PASSED** | Nến M15 mới đóng không tự ý supersede setup cũ đang chờ. |
| Test 5 | `test_5_multiple_new_m15_candles_setup_survives` | **PASSED** | Setup tồn tại xuyên suốt nhiều nến M15 (5 nến = 75 phút) mà không bị mất. |
| Test 6 | `test_6_expiration_reached_and_latched` | **PASSED** | Đến đúng phút thứ 121 (vượt 120 phút), setup chuyển sang `EXPIRED` và chốt chặn vĩnh viễn. |
| Test 7a | `test_7_invalidation_latch_long` | **PASSED** | LONG: Giá thủng SL $\rightarrow$ `INVALIDATED`. Giá nảy lại $\rightarrow$ vẫn `INVALIDATED`, không phục hồi. |
| Test 7b | `test_7_invalidation_latch_short` | **PASSED** | SHORT: Giá vượt SL $\rightarrow$ `INVALIDATED`. Giá rơi lại $\rightarrow$ vẫn `INVALIDATED`. |
| Test 8 | `test_8_entry_zone_latches_and_does_not_revert` | **PASSED** | Giá lọt vào zone $\rightarrow$ `ENTRY_ZONE`. Giá nảy ra ngoài $\rightarrow$ vẫn giữ `ENTRY_ZONE`. |
| Test 9 | `test_9_no_sr_long_fails_closed` | **PASSED** | LONG thiếu support $\rightarrow$ trả về `NO_SETUP`, không sinh Entry Zone từ giá live tick, candidate = None. |
| Test 10 | `test_10_no_sr_short_fails_closed` | **PASSED** | SHORT thiếu resistance $\rightarrow$ trả về `NO_SETUP`, fail closed an toàn. |
| Test 11 | `test_11_material_direction_change_supersedes_active` | **PASSED** | Tín hiệu đổi từ LONG sang SHORT $\rightarrow$ setup cũ bị `SUPERSEDED`, setup mới được kích hoạt. |
| Test 12 | `test_12_signal_wait_expires_active_setup` | **PASSED** | Tín hiệu chuyển sang WAIT $\rightarrow$ active setup hết hiệu lực, không còn candidate. |
| Test 13 | `test_13_restart_persistence_sqlite` | **PASSED** | Khởi động lại process với instance SQLite mới: phục hồi chính xác 100% hình học và trạng thái. |
| Test 14 | `test_14_candidate_requires_entry_zone` | **PASSED** | `WAITING_FOR_ENTRY` bị chặn bởi `PRICE_NOT_IN_ENTRY_ZONE`. Chỉ khi `ENTRY_ZONE` mới tạo candidate. |
| Test 15 | `test_15_materially_different_rules` | **PASSED** | Kiểm chứng logic so sánh thay đổi cơ bản giữa các setup. |
| Test 16 | `test_16_zero_broker_mutation_safety` | **PASSED** | Quét mã nguồn kiểm tra: các module contract không chứa `order_send` hay transport thật. |

### Kết quả Regression Suite:
- **Phase 17.3.1 Tests:** 17/17 PASSED (100%)
- **Phase 17.3 Durability Tests:** 12/12 PASSED (100%)
- **Phase 17.3 Autonomous Demo Loop Tests:** 23/23 PASSED (100%)
- **Phase 17.3 Preflight & Config Tests:** 14/14 PASSED (100%)
- **Phase 17.2 Execution Tests:** 44/44 PASSED (100%)
- **Phase 16.3 Execution Contract Tests:** 22/22 PASSED (100%)
- **Phase 16.2 MTF Tests:** 25/25 PASSED (100%)
- **Phase 12 Gated MT5 & Controlled Demo Tests:** 53/53 PASSED (100%)
- **Tổng số test hồi quy chạy thành công:** **210 / 210 PASSED (100%)**

### Kết quả Linter & Type Checker:
- `ruff check`: **0 errors (All checks passed)**
- `mypy -p exness_bot --strict`: **Success: no issues found in 332 source files**

---

## 9. XÁC NHẬN AN TOÀN TUYỆT ĐỐI (SAFETY CONFIRMATION)

1. **Production strategy parameters changed?** KHÔNG (NO). Ngưỡng MTF, trọng số các khung thời gian giữ nguyên 100%.
2. **Risk parameters changed?** KHÔNG (NO). Rủi ro 0.5%, công thức định cỡ vị thế giữ nguyên 100%.
3. **Execution architecture changed?** KHÔNG (NO). Toàn bộ pipeline `ExecutionOrchestrator`, `GatedMT5ExecutionPort`, `MT5Executor`, `LiveMT5ExecutionTransport`, `SnapshotIntentStore` giữ nguyên 100%.
4. **Real `order_send` calls?** 0 (Không có bất kỳ lệnh gửi sàn nào).
5. **LIVE trading enabled?** KHÔNG (NO). Chỉ hỗ trợ chế độ kiểm thử và DEMO có cổng kiểm soát nghiêm ngặt.
6. **Sẵn sàng cho bước tiếp theo?** CÓ (YES). Logic setup hiện đã ổn định, đáng tin cậy và không còn hiện tượng đuổi giá.

---

## 10. POST-REVIEW HARDENING (2026-09-12)

Sau review độc lập trực tiếp trên workspace, phát hiện một edge case P0:

- `proposed is None` không đồng nghĩa với `final_signal == WAIT`.
- Trước patch, một active LONG/SHORT vẫn hợp lệ có thể bị `EXPIRED` sớm nếu proposal mới tạm thời không build được.
- Đã sửa reconciliation để chỉ kết thúc active setup khi chiến lược thực sự chuyển sang `WAIT`; nếu signal vẫn cùng hướng nhưng proposal mới không build được, active setup bất biến tiếp tục sống đến khi invalidated/expired/material direction change.

Test bổ sung:
- `test_10b_same_direction_missing_proposal_preserves_active_setup`
- Harden lại test expiration để reload store sau lần evaluate tiếp theo thay vì assert trên object cũ.

Bằng chứng sau patch:
- Phase 17.3.1 + Phase 16.3 contract: **40 passed**.
- `ruff check`: **PASS**.
- `mypy -p exness_bot --strict`: **PASS, 332 source files**.

Lưu ý workspace hiện tại khi chạy toàn bộ suite: **1238 passed, 5 skipped, 1 deselected, 8 failed**. Tám failure này nằm ngoài thay đổi Phase 17.3.1, chủ yếu do test settings bị ảnh hưởng bởi `.env` operator hiện tại và một assertion read-only API cũ không còn khớp route surface. Không dùng các failure này để hạ verdict của lifecycle patch, nhưng cần được tách xử lý trước khi tuyên bố toàn repo xanh 100%.
