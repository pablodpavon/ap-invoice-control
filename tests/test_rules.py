"""The generator records every issue it injects; the rules must catch all of them
(recall) and must not flag invoices that were left clean (precision)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from apcontrol import pipeline  # noqa: E402


@pytest.fixture(scope="module")
def run():
    src = pipeline.load(ROOT / "data")
    df = pipeline.prepare(src, "2026-09-01")
    result, flags = pipeline.run_rules(df)
    injected = pd.read_csv(ROOT / "data" / "_injected_issues.csv")
    return src, result, flags, injected


def test_every_injected_issue_is_caught_by_its_rule(run):
    _, result, flags, injected = run
    flags = flags.set_index(result["invoice_id"])
    missed = [(i, r) for i, r in zip(injected.invoice_id, injected.injected_rule) if not flags.loc[i, r]]
    assert missed == [], f"rules missed injected issues: {missed}"


def test_clean_invoices_are_not_flagged(run):
    _, result, _, injected = run
    clean = result[~result.invoice_id.isin(injected.invoice_id)]
    assert (clean.status == "ready_to_pay").all(), clean.loc[clean.status != "ready_to_pay", ["invoice_id", "rules_hit"]]


def test_control_totals_reconcile(run):
    src, result, _, _ = run
    checks = pipeline.reconcile(src["invoices"], result)
    assert checks["count_ok"] and checks["amount_ok"], checks


def test_joins_do_not_duplicate_invoices(run):
    src, result, _, _ = run
    assert len(result) == len(src["invoices"])
    assert result.invoice_id.is_unique
