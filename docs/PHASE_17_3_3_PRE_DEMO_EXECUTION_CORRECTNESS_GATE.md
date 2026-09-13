# PHASE 17.3.3 — Pre-DEMO Execution Correctness Gate

## 1. Mục tiêu

Đóng correctness/safety gate cuối **trước** khi cho phép bất kỳ real DEMO broker mutation nào.

Phân biệt rõ:

| Khái niệm | Ý nghĩa |
|-----------|---------|
| `ENTRY_ZONE_LATCHED` | Fact lifecycle lịch sử: `setup.state == ENTRY_ZONE` (Phase 17.3.1 — không revert) |
| `CURRENT_PRICE_IN_ENTRY_ZONE` | Fact pre-submit: giá **executable** hiện tại nằm trong frozen `[entry_zone_low, entry_zone_high]` |

Latch **không** đủ để gửi market DEAL.

---

## 2. Vị trí gate

**Primary:** `execution/integration/demo_revalidate.py` → `revalidate_candidate_market`

Được gọi từ `CandidateExecutionService.precheck` khi `require_demo_market_revalidate=True`
(auto-demo factory + controlled demo factory).

**Helper mới:**

- `executable_price(side, tick)` — LONG→Ask, SHORT→Bid (không dùng MID)
- `quote_is_finite(tick)` — fail-closed NaN/Inf
- `current_price_in_frozen_entry_zone(...)` — so sánh Ask/Bid với frozen zone, **không** đọc latch

**Reason mới:** `CURRENT_PRICE_OUTSIDE_ENTRY_ZONE` (+ `QUOTE_NON_FINITE`)

Precheck cũng reject `QUOTE_NON_FINITE` / `STALE_QUOTE` / `QUOTE_UNAVAILABLE`.

Frozen geometry **không** bị mutate bởi revalidation.

---

## 3. Quote semantics (market DEAL)

| Side | Executable quote |
|------|------------------|
| BUY / LONG | **Ask** |
| SELL / SHORT | **Bid** |

MID chỉ dùng cho analysis latch — **không** đủ điều kiện gửi lệnh.

Ví dụ: MID trong zone nhưng Ask ngoài zone → LONG **BLOCKED**.

---

## 4. EXECUTION_MODE fail-closed

Trên auto-demo enablement (`evaluate_auto_demo_enablement`):

- `EXECUTION_MODE=paper` → PASS (nếu các gate khác OK)
- `EXECUTION_MODE=live` (hoặc non-paper) → **BLOCKED**

Không nới quyền execution.

---

## 5. Durability / snapshot (đã xác nhận)

- `resolve_auto_demo_state_path()` → durable `.auto_demo_execution_state.json`
- Runtime snapshot từ broker provider thật — không hardcode `trade_allowed=True` / `quote_fresh=True`
- Candidate DEMO pre-submit: thiếu field `trade_allowed` hoặc không đọc được `terminal_info` **không** authorize submission. Outer gate `_gate_terminal_trade_permission` chỉ PASS khi cả account lẫn terminal đều `True`. Auto-demo `runtime_snapshot` không bị nới.

---

## 6. Kiểm thử

| Suite | Kết quả |
|-------|---------|
| Phase 17.3.3 | **chưa chạy trong phiên này** — shell bị từ chối |
| Targeted regression (17.3.3→17.1) | **chưa chạy trong phiên này** |
| ruff | **chưa chạy trong phiên này** |
| mypy `--strict` | **chưa chạy trong phiên này** |

Real broker mutation: **0**

Strategy / risk / SL-TP / Entry Zone algorithm: **NO change**

Lifecycle 17.3.1 latch: **preserved**

Observation 17.3.2: **untouched**

---

## 7. Kết luận

Setup đã latch `ENTRY_ZONE` vẫn **không** được `order_send` nếu Ask/Bid hiện tại đã rời frozen Entry Zone, hoặc quote stale/missing/non-finite (`QUOTE_UNAVAILABLE` / `QUOTE_NON_FINITE`, transport call count 0), hoặc `EXECUTION_MODE=live`, hoặc snapshot quyền giao dịch chưa xác minh (thiếu `trade_allowed` / `terminal_info` không đọc được).

Phase này **không** chạy real DEMO smoke.
