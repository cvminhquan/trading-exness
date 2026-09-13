# CHATGPT REVIEW

Status: FIX_REQUIRED
Phase: 17.3.3 — Pre-DEMO Execution Correctness Gate
Task SHA256: 6B499F807284FB462A3AD7FAD54115775636D796E6DCDB28B692E27C6A2398B5
Updated: 2026-09-13T19:19:46.875748+00:00

## Summary
The Ask/Bid frozen-zone gate blocks latched setups when the executable quote is outside the zone and does not loosen strategy, risk, or LIVE controls, but the candidate DEMO pre-submit path still fail-opens trade permission, and the required missing/non-finite quote tests do not prove zero submissions.

## Findings
- ReadOnlyMt5DemoProbe.fetch_account in controlled_demo/identity.py still uses getattr(raw, "trade_allowed", True). If terminal_info cannot be read, terminal_trade_allowed stays None and trade_allowed becomes True. _gate_terminal_trade_permission then PASSes because it only blocks False or both None. demo_cli copies those values into enablement and the gated snapshot used immediately before submission, so this is a hardcoded PASS on the candidate DEMO pre-submit path and violates required behavior 7. Auto-demo runtime_snapshot already fail-closes with None/False and must not be loosened.
- Required missing/non-finite quote coverage does not prove BLOCKED with zero submissions. test_9_missing_tick_latched_outside_helper does not pass tick=None and does not go through consume. test_8 only calls revalidate_candidate_market and does not assert FakeMT5ExecutionTransport.calls == 0. Precheck already has QUOTE_UNAVAILABLE and QUOTE_NON_FINITE, so this is a required test gap, not a zone-latch logic hole.
