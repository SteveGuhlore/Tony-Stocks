"""Unit tests for the money-action environment fence (fail-closed)."""
from __future__ import annotations

import pytest

from trading_bot.api.env_fence import (
    FenceDecision,
    MoneyActionForbidden,
    assert_money_action_allowed,
    money_action_decision,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("ENV_ROLE", raising=False)
    monkeypatch.delenv("TRADINGBOT_PROD_ACCOUNT_ID", raising=False)


def test_default_dev_role_denies_even_with_matching_account(monkeypatch):
    # No ENV_ROLE set → defaults to dev → denied regardless of account.
    monkeypatch.setenv("TRADINGBOT_PROD_ACCOUNT_ID", "PA3P0RN75VL1")
    d = money_action_decision("PA3P0RN75VL1")
    assert d.allowed is False
    assert "dev" in d.reason


def test_prod_role_without_fingerprint_denies(monkeypatch):
    monkeypatch.setenv("ENV_ROLE", "prod")
    d = money_action_decision("PA3P0RN75VL1")
    assert d.allowed is False
    assert "fingerprint" in d.reason


def test_prod_role_unknown_runtime_identity_denies(monkeypatch):
    # fail-closed: identity unavailable → forbidden even in prod with a fingerprint.
    monkeypatch.setenv("ENV_ROLE", "prod")
    monkeypatch.setenv("TRADINGBOT_PROD_ACCOUNT_ID", "PA3P0RN75VL1")
    d = money_action_decision(None)
    assert d.allowed is False
    assert "unavailable" in d.reason


def test_prod_role_mismatched_account_denies(monkeypatch):
    monkeypatch.setenv("ENV_ROLE", "prod")
    monkeypatch.setenv("TRADINGBOT_PROD_ACCOUNT_ID", "PROD_ACCT")
    d = money_action_decision("SOME_OTHER_ACCT")
    assert d.allowed is False
    assert "match" in d.reason


def test_prod_role_matching_account_allows(monkeypatch):
    monkeypatch.setenv("ENV_ROLE", "prod")
    monkeypatch.setenv("TRADINGBOT_PROD_ACCOUNT_ID", "PROD_ACCT")
    d = money_action_decision("PROD_ACCT")
    assert d.allowed is True
    assert d.reason == "ok"
    assert isinstance(d, FenceDecision)


def test_account_id_whitespace_tolerated(monkeypatch):
    monkeypatch.setenv("ENV_ROLE", "PROD")  # case-insensitive
    monkeypatch.setenv("TRADINGBOT_PROD_ACCOUNT_ID", "  PROD_ACCT  ")
    d = money_action_decision("PROD_ACCT")
    assert d.allowed is True


def test_assert_raises_when_denied(monkeypatch):
    monkeypatch.setenv("ENV_ROLE", "dev")
    with pytest.raises(MoneyActionForbidden):
        assert_money_action_allowed("anything")


def test_assert_returns_decision_when_allowed(monkeypatch):
    monkeypatch.setenv("ENV_ROLE", "prod")
    monkeypatch.setenv("TRADINGBOT_PROD_ACCOUNT_ID", "PROD_ACCT")
    d = assert_money_action_allowed("PROD_ACCT")
    assert d.allowed is True
