"""Persisted usage rows always carry a billing_mode: 'subscription_included' when the cost is
included, otherwise the billing route's mode (nous -> official_models_api), never blank."""
from types import SimpleNamespace

from agent.turn_usage import _billing_mode


def _agent(provider, base_url, model="m"):
    return SimpleNamespace(provider=provider, base_url=base_url, model=model)


def test_included_cost_is_subscription_included():
    a = _agent("nous", "https://inference-api.nousresearch.com/v1")
    assert _billing_mode(a, SimpleNamespace(status="included")) == "subscription_included"


def test_nous_non_included_falls_back_to_route_mode():
    a = _agent("nous", "https://inference-api.nousresearch.com/v1", "deepseek/deepseek-v4-flash")
    assert _billing_mode(a, SimpleNamespace(status="estimated")) == "official_models_api"


def test_route_lookup_failure_is_not_fatal(monkeypatch):
    import agent.turn_usage as tu

    def boom(*a, **k):
        raise RuntimeError("route table broke")

    monkeypatch.setattr(tu, "resolve_billing_route", boom)
    assert tu._billing_mode(_agent("nous", None), SimpleNamespace(status="unknown")) is None
