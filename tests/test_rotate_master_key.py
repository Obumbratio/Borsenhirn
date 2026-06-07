"""
B2 — Tests de los helpers operacionales de rotate_master_key.

Sin DB: prueban la resolución de keys (vía secret providers) y el guard de
visibilidad cross-tenant (con un conn fake). Corren en la baseline.
"""

from __future__ import annotations

import pytest

from scripts.rotate_master_key import (
    resolve_rotation_keys,
    assert_cross_tenant_visibility,
)

OLD = "TEST_OLD_MK"
NEW = "TEST_NEW_MK"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for base in (OLD, NEW):
        for suffix in ("", "_FILE", "_CMD"):
            monkeypatch.delenv(base + suffix, raising=False)
    yield


# ── resolve_rotation_keys ───────────────────────────────────────

def test_resolve_keys_from_env(monkeypatch):
    monkeypatch.setenv(OLD, "vieja")
    monkeypatch.setenv(NEW, "nueva")
    assert resolve_rotation_keys(OLD, NEW) == ("vieja", "nueva")


def test_resolve_keys_old_from_file_new_from_env(monkeypatch, tmp_path):
    f = tmp_path / "old.key"; f.write_text("vieja-archivo\n")
    monkeypatch.setenv(f"{OLD}_FILE", str(f))   # key activa en un secrets mount
    monkeypatch.setenv(NEW, "nueva")
    assert resolve_rotation_keys(OLD, NEW) == ("vieja-archivo", "nueva")


def test_resolve_keys_missing_raises(monkeypatch):
    monkeypatch.setenv(OLD, "vieja")            # falta la nueva
    with pytest.raises(ValueError):
        resolve_rotation_keys(OLD, NEW)


def test_resolve_keys_equal_raises(monkeypatch):
    monkeypatch.setenv(OLD, "igual")
    monkeypatch.setenv(NEW, "igual")
    with pytest.raises(ValueError):
        resolve_rotation_keys(OLD, NEW)


# ── assert_cross_tenant_visibility (guard anti no-op) ───────────

class _FakeCursor:
    def __init__(self, row):
        self._row = row
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def execute(self, sql, params=None):
        pass
    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, row):
        self._row = row
    def cursor(self):
        return _FakeCursor(self._row)


def test_visibility_ok_when_superuser_or_bypass():
    # rolsuper OR rolbypassrls = True
    assert_cross_tenant_visibility(_FakeConn((True,))) is None


def test_visibility_raises_when_subject_to_rls():
    with pytest.raises(RuntimeError):
        assert_cross_tenant_visibility(_FakeConn((False,)))


def test_visibility_raises_when_no_row():
    with pytest.raises(RuntimeError):
        assert_cross_tenant_visibility(_FakeConn(None))
