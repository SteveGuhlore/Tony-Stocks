# prod-shaped degraded-data fixtures

Recorded-real-shaped JSON inputs used by `tests/test_degraded_data_contract.py`
to prove the FastAPI read surface NEVER 500s on the production breakages this
operator keeps hitting at market open (Codex review #12):

- empty CC files / missing reports dir
- malformed JSON in `tony_stocks_verdicts.json` / `tony_stocks_record.json`
- unknown CC verdict values ("pass", "frobnicate")
- no Alpaca keys (503 prices, but cockpit/tape still 200)
- stale/old watch-run heartbeats

These are intentionally small, hand-shaped to mirror the real producer files
(the Command Center writes the verdicts/record; the off-hours engine writes
morning-prep). Do not delete — the contract test loads them by name.
