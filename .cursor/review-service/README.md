# Local Review Service

Dịch vụ local fail-closed cho flow Cursor → watcher → review agent.

## Hiện trạng
- HTTP bind mặc định `127.0.0.1:8765`, không public Internet.
- `POST /webhook/review` nhận duy nhất `REVIEW_REQUESTED` + `IMPLEMENTED`.
- Durable state theo `taskSha256`; duplicate event không chạy lại terminal result.
- Pre-review scan diff trước khi gọi AI reviewer.
- AI reviewer chưa cấu hình nên event hợp lệ dừng ở `BLOCKED` sau pre-scan.

## Safety guardrails
Service không có logic broker, không import trading engine và không gọi `order_send`.
Nó fail-closed nếu diff chạm `.env`, secrets/credentials hoặc thêm các pattern nguy hiểm:
`order_send(`, `LIVE_KILL_SWITCH=false`, `TRADING_ENV=live`, `AUTO_DEMO_EXECUTION_ENABLED=true`.

Service không merge, không push `master`, không sửa strategy/risk/execution.
AI runtime sau này chỉ được phép review/test và ghi file collaboration.

## State machine
`RECEIVED → REVIEWING → BLOCKED | PASS | FIX_REQUIRED | ERROR`.
Ở phiên bản hiện tại chỉ `BLOCKED` hoặc `ERROR` có thể được tạo tự động.
`PASS/FIX_REQUIRED` sẽ chỉ bật sau khi AI reviewer được cấu hình và kiểm thử.

## Endpoints
- `GET /health`
- `GET /state`
- `POST /webhook/review`

## Webhook auth
Nếu environment variable `REVIEW_WEBHOOK_SECRET` được set, client phải gửi:
`X-Review-Signature = HMAC-SHA256(secret, raw_body)`.

Local watcher và service chạy cùng máy nên giai đoạn đầu không cần expose port ra Internet.
Không lưu API key hoặc webhook secret trong repository.

## Chạy
```powershell
python .cursor/review-service/review_service.py
```

Watcher sẽ POST vào `http://127.0.0.1:8765/webhook/review`.
Windows Startup khởi động cả service và watcher sau khi đăng nhập.

## AI reviewer — chưa bật
Bước kế tiếp sẽ thêm adapter headless riêng. Credential phải đặt trong Windows environment/secret store,
không commit vào repo và không gửi qua chat. Khi adapter chưa sẵn sàng, service luôn fail-closed.

## AI reviewer adapter
`ai_reviewer.py` dùng OpenAI Responses API qua HTTPS trực tiếp, không cần cài thêm SDK.
Model mặc định: `gpt-5.6-sol`; có thể override bằng `REVIEW_AI_MODEL`.
Structured Output bắt buộc verdict `PASS | FIX_REQUIRED | BLOCKED`.
Request đặt `store=false`; API key chỉ đọc từ environment `OPENAI_API_KEY`.

`review_service_agent.py` là entrypoint hiện tại. Nó chạy:
1. durable state + duplicate suppression,
2. deterministic safety scan,
3. AI review nếu credential sẵn sàng,
4. ghi `chatgpt-review.md`,
5. PASS → current task `DONE`,
6. FIX_REQUIRED → tạo fix task `READY` cùng phase.

Agent không tự mở phase kế tiếp khi task hiện tại yêu cầu DỪNG; việc chạy Cursor headless là lớp riêng.
Nếu AI/API lỗi, state chuyển `ERROR`; không tự PASS.
