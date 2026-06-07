"""
B5.2 — Tests unitarios del AuditLogger (contextvar de actor + soft-fail).
Sin DB.
"""

from __future__ import annotations

import pytest

from borsenhirn import db as bdb
from borsenhirn.audit import (
    AuditLogger, get_actor, actor_scope, AuditAction,
    get_audit_logger, set_audit_logger, reset_audit_logger,
)

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


def test_actor_scope_nested():
    with actor_scope("user_a"):
        assert get_actor() == "user_a"
        with actor_scope("user_b"):
            assert get_actor() == "user_b"
        assert get_actor() == "user_a"


def test_record_soft_fails_on_conn_error():
    """Si la conexión falla, record() NO debe propagar (auditar no rompe la op)."""
    def boom(role):
        raise RuntimeError("sin db")
    bdb.set_connection_factory(boom)
    try:
        # No debe lanzar.
        AuditLogger().record(DEFAULT_TENANT, AuditAction.CRED_READ, resource="alpaca")
    finally:
        bdb.clear_connection_factory()


def test_singleton_inject_and_reset():
    class _Spy(AuditLogger):
        def __init__(self):
            self.calls = []
        def record(self, tenant_id, action, **kw):
            self.calls.append((tenant_id, action, kw))
    spy = _Spy()
    set_audit_logger(spy)
    try:
        get_audit_logger().record(DEFAULT_TENANT, AuditAction.BILLING_UPDATED, resource="sub_1")
        assert spy.calls and spy.calls[0][1] == "billing.subscription.updated"
    finally:
        reset_audit_logger()


def test_action_constants():
    assert AuditAction.CRED_ROTATE == "credentials.rotate"
    assert AuditAction.TENANT_SUSPENDED == "tenant.suspended"
    assert AuditAction.KS_HALT == "killswitch.halt"
