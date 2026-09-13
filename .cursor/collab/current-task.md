# CURRENT TASK

Status: IMPLEMENTED
Owner: Cursor
Reviewer/Lead: Cursor Review Service
Phase: 17.3.3 — Pre-DEMO Execution Correctness Gate â€” Review Fix

## Má»¥c tiÃªu fix
Stay on Phase 17.3.3 only. Fix the candidate DEMO pre-submit permission snapshot so a missing account trade_allowed field or an unreadable terminal_info cannot authorize submission: do not default trade_allowed to True, and make the outer permission gate fail closed for that unverified snapshot. Do not loosen auto-demo runtime_snapshot. Add a fake-transport regression proving that case is BLOCKED with zero submissions. Also add consume/smoke tests, fake transport only, proving a missing tick and a non-finite bid/ask are BLOCKED with transport call count 0 and deterministic reasons QUOTE_UNAVAILABLE or QUOTE_NON_FINITE. Do not change strategy, risk, Entry Zone width, SL/TP, kill-switch, or lifecycle semantics. Do not run a real DEMO smoke and do not enable live trading. Re-run the targeted 17.3.3 regressions, ruff, and mypy --strict, update the phase doc and cursor-report, set Status IMPLEMENTED, then stop.

## Boundaries
- Chá»‰ sá»­a finding cá»§a review hiá»‡n táº¡i.
- KhÃ´ng Ä‘á»•i strategy/risk thresholds ngoÃ i finding.
- KhÃ´ng thÃªm broker mutation, LIVE trading, order_send hoáº·c secret changes.
- Cháº¡y targeted regressions vÃ  ghi cursor-report.md.
- Khi xong Ä‘á»•i Status: IMPLEMENTED rá»“i Dá»ªNG.
