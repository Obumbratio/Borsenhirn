"""
B7 — Tests unitarios del servicio legal (sin DB: validación + versiones).
"""

from __future__ import annotations

import pytest

import config
from borsenhirn.legal import current_versions, record_acceptance, REQUIRED_DOCS


def test_current_versions_from_config(monkeypatch):
    monkeypatch.setattr(config, "LEGAL_TERMS_VERSION", "vT", raising=False)
    monkeypatch.setattr(config, "LEGAL_PRIVACY_VERSION", "vP", raising=False)
    v = current_versions()
    assert v == {"terms": "vT", "privacy": "vP"}


def test_required_docs():
    assert set(REQUIRED_DOCS) == {"terms", "privacy"}


def test_record_acceptance_rejects_bad_document():
    with pytest.raises(ValueError):
        record_acceptance("00000000-0000-0000-0000-000000000001", "cookies", "v1")


def test_record_acceptance_rejects_empty_version():
    with pytest.raises(ValueError):
        record_acceptance("00000000-0000-0000-0000-000000000001", "terms", "")
