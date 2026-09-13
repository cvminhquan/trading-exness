# PHASE 17.3.2 — Signal & Setup Forward Observation

## 1. Mục tiêu

Xây lớp **observation chỉ-đọc** để đo chất lượng các immutable setup của `mtf_technical_v1` sau Phase 17.3.1.

Phase này **không** tối ưu profitability, **không** đổi strategy/risk/execution, **không** gửi broker order.

Câu hỏi nghiên cứu được trả lời bằng dữ liệu closed-candle:

- Setup có chạm Entry Zone trong lifetime không?
- MFE/MAE sau khi setup được tạo là bao nhiêu?
- TP1 hay SL xảy ra trước?
- Trạng thái tại +15m / +30m / +1h / +2h?
- Bao nhiêu setup hết hạn mà chưa chạm Entry Zone?

---

## 2. Kiến trúc

Package độc lập:

```text
trading-engine/src/exness_bot/market_analysis/observation/
  models.py      # SetupObservationRecord, FirstOutcome, checkpoints
  engine.py      # đo entry/MFE/MAE/TP1/SL/AMBIGUOUS trên closed candles
  store.py       # SQLite + InMemory, idempotent theo setup_id
  service.py     # capture / ingest / resume / summary
  __main__.py    # CLI read-only
```

**Tách biệt tuyệt đối:**

- Observation **không** import eligibility / candidate / execution stack.
- Observation **không** feed ngược vào eligibility hay candidate creation.
- Setup prediction vẫn đo được dù execution bị BLOCKED / không eligible.

---

## 3. Persistence schema / path

Bảng SQLite (cùng `DATABASE_URL`, mặc định `sqlite:///exness_bot.db`):

```sql
CREATE TABLE IF NOT EXISTS setup_forward_observation (
    setup_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    payload TEXT NOT NULL,
    first_outcome TEXT NOT NULL,
    entry_touched INTEGER NOT NULL,
    last_processed_candle_ts TEXT,
    updated_at TEXT NOT NULL
);
```

- Primary key = `setup_id` → một observation / một immutable setup.
- Capture trùng `setup_id` là **idempotent**: giữ geometry gốc, không duplicate.
- Restart-safe: reload payload JSON đầy đủ từ SQLite.

---

## 4. Snapshot fields (capture)

Từ `CanonicalTradeSetup` đóng băng:

| Field | Nguồn |
|-------|--------|
| setup_id, strategy_id, symbol, direction | setup |
| created_at, expires_at, source_candle_timestamp | setup |
| signal_price / reference | optional capture arg (mặc định entry_price) |
| entry_price, entry_zone_low/high, stop_loss, tp1 | frozen geometry |
| risk_distance | `abs(entry − SL)` nếu > 0 |

Sau capture chỉ cập nhật measurement / outcome / checkpoints — **không** đổi geometry.

---

## 5. Outcome semantics

| Outcome | Ý nghĩa |
|---------|---------|
| `OPEN` | Chưa đủ dữ liệu; chưa chạm entry; chưa hết hạn |
| `ENTRY_TOUCHED` | Closed candle range giao Entry Zone; chưa resolve TP1/SL |
| `TP1_FIRST` | **Sau khi** đã chạm Entry Zone, TP1 được chạm trên closed candle trước SL |
| `SL_FIRST` | **Sau khi** đã chạm Entry Zone, SL được chạm trước TP1 |
| `AMBIGUOUS` | **Cùng một** closed candle (từ candle entry trở đi) chứa cả TP1 và SL — không giả định thứ tự |
| `EXPIRED_NO_ENTRY` | `now >= expires_at`, chưa chạm Entry Zone, **và** đã có đủ closed-candle coverage toàn lifetime |
| `UNRESOLVED` | Hết lifetime nhưng thiếu coverage / đã chạm entry mà không resolve rõ TP1 vs SL |

### Quy tắc coverage (fail-closed)

`EXPIRED_NO_ENTRY` **không** được kết luận chỉ vì đồng hồ đã qua `expires_at`.

Phải chứng minh mọi open-timestamp M15 trong khoảng `(source_candle, expires_at)` đều đã được quan sát bằng closed candle. Thiếu gap/coverage → giữ `UNRESOLVED` + note `INCOMPLETE_LIFETIME_COVERAGE` — không đếm vào `expired_no_entry_count`.

### Quy tắc TP1/SL race

Race chỉ bắt đầu **sau** khi Entry Zone đã được chạm.

- Candle trước entry chạm TP1 hoặc SL → **không** tạo `TP1_FIRST` / `SL_FIRST`.
- Candle đầu tiên chạm Entry Zone **được phép** cùng lúc resolve TP1/SL.
- Cùng candle chạm cả TP1 và SL → `AMBIGUOUS`.

MFE/MAE:

- Direction-aware theo `entry_price` (đo từ lúc setup được tạo, kể cả trước entry).
- Đơn vị price + R (`/ risk_distance`) khi có đủ khoảng rủi ro đóng băng.
- **Không** gọi bất kỳ metric nào là win probability.

Checkpoints `+15m / +30m / +1h / +2h`:

- Chỉ `FINALIZED` khi có closed candle với `close_time >= due_at`.
- Thiếu data → giữ `PENDING` (không fabricate).

Nguồn outcome: **closed candles only**. Forming candle bị loại bằng `is_candle_closed`.

---

## 6. CLI

```bash
python -m exness_bot.market_analysis.observation capture --setup-id <id>
python -m exness_bot.market_analysis.observation capture-active --symbol XAUUSD
python -m exness_bot.market_analysis.observation ingest --setup-id <id> --from-csv path.csv
python -m exness_bot.market_analysis.observation resume --from-csv path.csv
python -m exness_bot.market_analysis.observation summary
```

Mặc định `--database-url sqlite:///exness_bot.db`.

---

## 7. Bằng chứng kiểm thử

| Suite | Kết quả |
|-------|---------|
| Phase 17.3.2 observation | **19 passed** |
| Regression 17.3.1 + 17.3 durability + 17.3 loop + 17.2 + 16.3 + 12.3 + 12.8 | **178 passed** |
| Phase 17.1 + 17.2.2 | **47 passed** |
| **Tổng targeted** | **225 passed** |
| ruff (observation + tests) | All checks passed |
| mypy `--strict` (`exness_bot`) | Success: no issues found in **338** source files |

`FakeMT5ExecutionTransport.calls == []` trong test regression observation.

`real_order_send_calls = 0`

---

## 8. Safety confirmation

| Hạng mục | Kết quả |
|----------|---------|
| Strategy parameters changed? | **NO** |
| Risk parameters changed? | **NO** |
| Execution architecture changed? | **NO** |
| Lifecycle 17.3.1 semantics changed? | **NO** |
| LIVE enabled? | **NO** |
| Observation → execution dependency? | **NO** |
| Real broker mutation? | **0** |

---

## 9. Known gaps (không thuộc phase này)

- Chưa gắn tự động capture vào mỗi lần contract upsert (CLI/manual hoặc caller riêng).
- Ingest production-friendly từ MT5 live count API chưa có subcommand (CSV offline đủ cho research).
- Không có dashboard UI redesign.
- Không kết luận profitability / win rate từ observation metrics.

---

## 10. Kết luận

Phase 17.3.2 cung cấp lớp đo forward **độc lập**, restart-safe, closed-candle-only, với quy tắc `AMBIGUOUS` fail-closed khi không biết thứ tự intrabar.

Đây là công cụ research/diagnostics — **không** phải bằng chứng strategy đã profitable.
