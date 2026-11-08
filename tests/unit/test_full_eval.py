import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from opspilot.evals.full import CATEGORIES, accounting, corpus, schedule


def test_frozen_corpus_security_traceability_and_real_denominators():
    cases = corpus()
    assert Counter(c.category for c in cases) == CATEGORIES
    backlog = json.loads(Path("docs/security/asvs-l2-requirement-backlog.json").read_text())
    ids = {r["id"] for r in backlog["requirements"]}
    assert all(set(c.asvs_ids) <= ids for c in cases)
    real = schedule("real")
    assert len(real) == 90
    assert sum(c.split == "dev" for c, _ in real) == 30
    assert sum(c.split == "holdout" for c, _ in real) == 60
    assert sum(n == 1 for _, n in real) == 50
    with pytest.raises(ValueError):
        schedule("best-of")


def test_release_gate_rejects_missing_duplicate_failed_and_setup_results():
    results = [dict(id=c.id, repeat=n, passed=True) for c, n in schedule("scripted")]
    assert accounting(results)["scripted_gate"]
    assert accounting(results)["release_gate"] == "NOT_MET"
    assert not accounting(results[:-1])["scripted_gate"]
    assert not accounting(results + [results[0]])["scripted_gate"]
    results[0] = dict(results[0], passed=False, setup_error="ConnectionError")
    assert not accounting(results)["scripted_gate"]
    assert accounting(results)["setup_errors"] == 1


async def test_real_execution_denied_before_settings_or_database(monkeypatch):
    from tests import f22_lab

    def forbidden_settings(*args, **kwargs):
        raise AssertionError("Settings/credentials must not be loaded before authorization")

    monkeypatch.setattr(f22_lab, "Settings", forbidden_settings)
    with pytest.raises(ValueError, match="explicit separate owner authorization"):
        await f22_lab.main(SimpleNamespace(mode="real", authorize_real=False))
