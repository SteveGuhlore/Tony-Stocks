"""Environment-role fence for money-adjacent dashboard actions.

The dashboard exposes control POSTs (stop-watch, pause-paper, flatten-all, ...).
The hard safety requirement (DEPLOY_RULES + Codex review): a LOCAL DEV instance
must be *physically incapable* of firing a money-adjacent action against the VM
production paper account — config text alone is not enough.

This module enforces a fail-closed gate. A money action is allowed ONLY when:
  1. ``ENV_ROLE`` is exactly ``prod``; AND
  2. an expected prod account fingerprint is configured (``TRADINGBOT_PROD_ACCOUNT_ID``); AND
  3. the *runtime* broker account identity (read live from the broker, not a YAML
     label) matches that fingerprint.

Anything else → forbidden. Read views never touch this gate.

The core decision function ``money_action_decision`` is PURE (account id injected),
so it is fully unit-testable without a broker or network. ``resolve_runtime_account_id``
does the best-effort live broker lookup and is fail-quiet (returns None on any error),
which — because the gate is fail-closed — means "unknown identity ⇒ forbidden".
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class MoneyActionForbidden(Exception):
    """Raised (→ HTTP 403) when a money-adjacent action is not permitted in this environment."""


@dataclass(frozen=True)
class FenceDecision:
    allowed: bool
    reason: str
    env_role: str
    runtime_account_id: str | None
    expected_account_id: str | None


def env_role() -> str:
    return os.environ.get("ENV_ROLE", "dev").strip().lower()


def is_prod_role() -> bool:
    return env_role() == "prod"


def expected_prod_account_id() -> str | None:
    val = os.environ.get("TRADINGBOT_PROD_ACCOUNT_ID")
    return val.strip() if val and val.strip() else None


def money_action_decision(runtime_account_id: str | None) -> FenceDecision:
    """Pure, fail-closed decision. ``runtime_account_id`` is the LIVE broker account
    identity (e.g. Alpaca account number), injected by the caller so this is testable."""
    role = env_role()
    expected = expected_prod_account_id()

    def deny(reason: str) -> FenceDecision:
        return FenceDecision(False, reason, role, runtime_account_id, expected)

    if role != "prod":
        return deny(f"money actions disabled: ENV_ROLE='{role}' (not 'prod') — this is a dev instance")
    if not expected:
        return deny("money actions disabled: no TRADINGBOT_PROD_ACCOUNT_ID fingerprint configured")
    if not runtime_account_id:
        return deny("money actions disabled: live broker account identity unavailable (fail-closed)")
    if str(runtime_account_id).strip() != str(expected).strip():
        return deny("money actions disabled: live broker account does not match the prod fingerprint")
    return FenceDecision(True, "ok", role, runtime_account_id, expected)


def resolve_runtime_account_id() -> str | None:
    """Best-effort LIVE broker account id from the configured Alpaca paper broker.

    Fail-quiet: any error (no keys, network, import) → None, which the fail-closed
    gate treats as forbidden. Never raises into the request path.
    """
    try:  # pragma: no cover - exercised via integration, not unit tests
        from trading_bot.execution import load_paper_trading_config  # type: ignore
        from trading_bot.execution.alpaca_paper import AlpacaPaperBroker  # type: ignore
        from trading_bot.settings import load_scanner_settings  # type: ignore

        settings = load_scanner_settings("config/default_config.yaml")
        cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
        broker = AlpacaPaperBroker(cfg)
        account = broker.get_account()
        # alpaca-py Account exposes .account_number; tolerate dict-likes too.
        acct_id = getattr(account, "account_number", None)
        if acct_id is None and isinstance(account, dict):
            acct_id = account.get("account_number") or account.get("id")
        return str(acct_id) if acct_id else None
    except Exception:
        return None


def assert_money_action_allowed(runtime_account_id: str | None = None) -> FenceDecision:
    """Resolve identity (if not supplied), decide, and raise ``MoneyActionForbidden`` if denied.

    Use as the guard at the top of every money-adjacent control endpoint.
    """
    acct = runtime_account_id if runtime_account_id is not None else resolve_runtime_account_id()
    decision = money_action_decision(acct)
    if not decision.allowed:
        raise MoneyActionForbidden(decision.reason)
    return decision
