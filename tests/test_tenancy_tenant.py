"""Tests de borsenhirn.tenancy.tenant (helpers)."""

from __future__ import annotations

import pytest

from borsenhirn.tenancy.tenant import (
    SYSTEM_TENANT_ID,
    Tenant,
    TenantStatus,
    is_valid_email,
    is_valid_slug,
    is_valid_tenant_id,
    new_tenant_id,
)


# ── new_tenant_id ────────────────────────────────────────


def test_new_tenant_id_returns_valid_uuid():
    tid = new_tenant_id()
    assert is_valid_tenant_id(tid)


def test_new_tenant_id_unique():
    ids = {new_tenant_id() for _ in range(50)}
    assert len(ids) == 50


# ── is_valid_tenant_id ───────────────────────────────────


def test_valid_tenant_id_accepts_canonical():
    assert is_valid_tenant_id("12345678-1234-1234-1234-123456789012")
    assert is_valid_tenant_id("abcdef00-1234-5678-9abc-def012345678")


def test_valid_tenant_id_case_insensitive():
    assert is_valid_tenant_id("ABCDEF00-1234-5678-9ABC-DEF012345678")


def test_invalid_tenant_id_rejects_garbage():
    assert not is_valid_tenant_id("not-a-uuid")
    assert not is_valid_tenant_id("")
    assert not is_valid_tenant_id("12345678-1234-1234-1234-123")  # too short
    assert not is_valid_tenant_id(None)   # type: ignore
    assert not is_valid_tenant_id(123)    # type: ignore


def test_system_tenant_id_is_valid():
    assert is_valid_tenant_id(SYSTEM_TENANT_ID)


# ── is_valid_slug ────────────────────────────────────────


def test_valid_slug_basic():
    assert is_valid_slug("uriel-castano")
    assert is_valid_slug("user_123")
    assert is_valid_slug("test-tenant-2026")


def test_valid_slug_min_length():
    assert is_valid_slug("abc")          # 3 chars
    assert not is_valid_slug("ab")       # 2 chars (< min)


def test_valid_slug_max_length():
    assert is_valid_slug("a" * 40)
    assert not is_valid_slug("a" * 41)


def test_invalid_slug_rejects_capitals():
    assert not is_valid_slug("UrielCastano")


def test_invalid_slug_rejects_special_chars():
    assert not is_valid_slug("user@domain")
    assert not is_valid_slug("user.name")
    assert not is_valid_slug("user space")


def test_invalid_slug_rejects_starts_with_dash():
    assert not is_valid_slug("-uriel")
    assert not is_valid_slug("uriel-")


# ── is_valid_email ───────────────────────────────────────


def test_valid_emails():
    for e in ["a@b.co", "user@domain.com", "first.last@sub.domain.io"]:
        assert is_valid_email(e), f"esperaba válido: {e!r}"


def test_invalid_emails():
    for e in ["not-an-email", "@no-local.com", "no-at-symbol", "x@y", ""]:
        assert not is_valid_email(e), f"esperaba inválido: {e!r}"


# ── Tenant dataclass ─────────────────────────────────────


def test_tenant_construction_minimal():
    t = Tenant(
        tenant_id=new_tenant_id(),
        slug="test-user",
        email="test@example.com",
        display_name="Test User",
    )
    assert t.is_active()
    assert t.can_trade()
    assert t.metadata == {}


def test_tenant_suspended_cannot_trade():
    t = Tenant(
        tenant_id=new_tenant_id(),
        slug="test-user",
        email="test@example.com",
        display_name="Test User",
        status=TenantStatus.SUSPENDED,
    )
    assert not t.is_active()
    assert not t.can_trade()


def test_tenant_disabled_cannot_trade():
    t = Tenant(
        tenant_id=new_tenant_id(),
        slug="test-user",
        email="test@example.com",
        display_name="Test User",
        status=TenantStatus.DISABLED,
    )
    assert not t.can_trade()
