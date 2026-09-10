# Exness Trading

Monorepo hệ thống giao dịch thuật toán **Exness** — engine Python + dashboard Next.js.

## Cấu trúc

```
trading-exness/
├── trading-engine/     # Python — engine giao dịch MT5
├── dashboard/          # Next.js — bảng điều khiển vận hành
├── docs/               # Tài liệu sản phẩm & kiến trúc
├── .gitignore
└── README.md
```

---

## Mỗi lần mở dự án (copy → chạy)

**Trước tiên:** mở app **MetaTrader 5** và đăng nhập (DEMO/LIVE).  
API sẽ gắn vào phiên terminal đang mở. Nếu muốn API tự login lại khi terminal chưa mở, điền `MT5_PASSWORD` trong `trading-engine/.env`.

### Terminal 1 — API + MT5

```powershell
cd trading-engine
.\.venv\Scripts\Activate.ps1
$env:MT5_ENABLED="true"
$env:DATA_SOURCE="mt5"
exness-bot-api
```

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health nhanh: mở [http://127.0.0.1:8000/api/v1/status](http://127.0.0.1:8000/api/v1/status) — cần thấy `connectionStatus: CONNECTED`

### Terminal 2 — Dashboard

```powershell
cd C:\Users\Quan\OneDrive\Desktop\trading-exness\dashboard
$env:NEXT_PUBLIC_DATA_SOURCE="api"
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
npm run dev
```

- Dashboard: [http://localhost:3000/dashboard](http://localhost:3000/dashboard)

> Giữ cả 2 terminal mở. Dừng: `Ctrl+C` trong từng cửa sổ.

---

## Lần đầu cài đặt (chỉ chạy 1 lần)

### Trading Engine

```powershell
cd C:\Users\Quan\OneDrive\Desktop\trading-exness\trading-engine
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[api,dev,mt5]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Nếu `Activate.ps1` bị chặn:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Trong `trading-engine/.env` đặt tối thiểu:

```env
MT5_ENABLED=true
DATA_SOURCE=mt5
MT5_LOGIN=...
MT5_SERVER=Exness-MT5Trial17
# MT5_PASSWORD="..."   # tùy chọn nếu MT5 đã mở sẵn và đã login
```

**Không** chạy lại `Copy-Item .env.example .env` nếu đã cấu hình — sẽ ghi đè mất login/password.
### Dashboard

```powershell
cd C:\Users\Quan\OneDrive\Desktop\trading-exness\dashboard
npm install
```

Tùy chọn — tạo `dashboard/.env.local` để khỏi gõ env mỗi lần:

```env
NEXT_PUBLIC_DATA_SOURCE=api
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### Linux / macOS (mock, không MT5 terminal)

```bash
cd trading-engine
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[api,dev]"
cp -n .env.example .env
DATA_SOURCE=mock exness-bot-api
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
