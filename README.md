# Exness Trading

Monorepo hệ thống giao dịch thuật toán **Exness** — engine Python + dashboard Next.js.

## Cấu trúc

```
trading-exness/
├── trading-engine/     # Python — backend API + engine MT5
├── dashboard/          # Next.js — bảng điều khiển vận hành
├── docs/               # Tài liệu sản phẩm & kiến trúc
├── .gitignore
└── README.md
```

---

## Chạy Backend (BE) — mỗi lần mở dự án

**Trước tiên:** mở app **MetaTrader 5** và đăng nhập (DEMO/LIVE).  
API gắn vào phiên terminal đang mở. Nếu muốn API tự login khi terminal chưa mở, điền `MT5_PASSWORD` trong `trading-engine/.env`.

### PowerShell (Windows + MT5) — dùng hàng ngày

```powershell
cd trading-engine
.\.venv\Scripts\Activate.ps1
$env:MT5_ENABLED="true"
$env:DATA_SOURCE="mt5"
exness-bot-api
```

Lệnh tương đương (cùng venv đã activate):

```powershell
python -m exness_bot.api
```

| | URL |
|---|-----|
| API | http://127.0.0.1:8000 |
| OpenAPI | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/health |
| Status | http://127.0.0.1:8000/api/v1/status |

Status cần thấy `connectionStatus: CONNECTED` khi MT5 gắn thành công.

Dừng BE: `Ctrl+C` trong terminal đang chạy API.

### Mock (không cần MT5)

```powershell
cd trading-engine
.\.venv\Scripts\Activate.ps1
$env:DATA_SOURCE="mock"
$env:MT5_ENABLED="false"
exness-bot-api
```

### Biến môi trường quan trọng (BE)

Có thể set trong session PowerShell **hoặc** ghi trong `trading-engine/.env`:

```env
MT5_ENABLED=true
DATA_SOURCE=mt5
MT5_LOGIN=...
MT5_SERVER=Exness-MT5Trial17
# MT5_PASSWORD="..."   # tùy chọn nếu MT5 đã mở sẵn và đã login
API_HOST=127.0.0.1
API_PORT=8000
```

> Env trên PowerShell (`$env:...`) ghi đè giá trị trong `.env` cho process hiện tại.

---

## Chạy Dashboard (FE) — Terminal 2

```powershell
cd dashboard
$env:NEXT_PUBLIC_DATA_SOURCE="api"
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
npm run dev
```

- Dashboard: http://localhost:3000/dashboard

Tùy chọn — tạo `dashboard/.env.local` để khỏi gõ env mỗi lần:

```env
NEXT_PUBLIC_DATA_SOURCE=api
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

> Giữ cả 2 terminal (BE + FE) mở khi dùng dashboard live.

---

## Lần đầu cài Backend (chỉ 1 lần)

```powershell
cd trading-engine
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[api,dev,mt5]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Nếu `Activate.ps1` bị chặn:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Sau đó chỉnh `trading-engine/.env` (login/server/…).  
**Không** chạy lại `Copy-Item .env.example .env` nếu đã cấu hình — sẽ ghi đè mất credentials.

Kiểm tra nhanh sau cài:

```powershell
pytest
ruff check src tests
```

### Lần đầu cài Dashboard

```powershell
cd dashboard
npm install
```

### Linux / macOS (mock, không MT5 terminal)

```bash
cd trading-engine
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[api,dev]"
cp -n .env.example .env
DATA_SOURCE=mock MT5_ENABLED=false exness-bot-api
```

Chi tiết thêm: [trading-engine/README.md](trading-engine/README.md) · [dashboard/README.md](dashboard/README.md).

## Tài liệu

| Tài liệu | Mô tả |
|----------|--------|
| [docs/PRD.md](docs/PRD.md) | Yêu cầu sản phẩm |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Kiến trúc hệ thống |
| [docs/TRADING_RULES.md](docs/TRADING_RULES.md) | Quy tắc chiến lược & rủi ro |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Lộ trình triển khai |

Tài liệu riêng của engine nằm trong `trading-engine/docs/`.
