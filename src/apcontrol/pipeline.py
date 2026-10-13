"""Load source extracts, run the 3-way match and all rules, and reconcile the result."""
from pathlib import Path

import pandas as pd

from .rules import RULES


def load(data_dir: Path) -> dict[str, pd.DataFrame]:
    parse = {"invoices": ["invoice_date", "due_date", "cae_due_date"]}
    out = {}
    for name in ["suppliers", "purchase_orders", "goods_receipts", "invoices"]:
        out[name] = pd.read_csv(data_dir / f"{name}.csv", dtype={"supplier_cuit": str, "cae": str},
                                parse_dates=parse.get(name, []))
    return out


def prepare(src: dict[str, pd.DataFrame], run_date: str) -> pd.DataFrame:
    inv = src["invoices"].copy()
    sup = src["suppliers"].rename(columns={"supplier_name": "supplier_name_master",
                                           "tax_status": "supplier_tax_status"})
    po = src["purchase_orders"].rename(columns={"unit_price": "po_unit_price", "quantity": "po_qty"})
    gr = src["goods_receipts"].groupby("po_number", as_index=False)["received_qty"].sum()

    df = inv.merge(sup[["supplier_cuit", "supplier_name_master", "supplier_tax_status"]],
                   on="supplier_cuit", how="left")
    df = df.merge(po[["po_number", "po_unit_price", "po_qty"]], on="po_number", how="left")
    df = df.merge(gr, on="po_number", how="left")
    df["run_date"] = pd.Timestamp(run_date)
    assert len(df) == len(inv), "joins must not duplicate invoices"
    return df


def run_rules(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    flags = pd.DataFrame({r.code: r.check(df).reindex(df.index).fillna(False).astype(bool) for r in RULES})
    severity = {r.code: r.severity for r in RULES}
    out = df.copy()
    out["rules_hit"] = flags.apply(lambda row: ",".join(c for c in flags.columns if row[c]), axis=1)
    out["n_rules"] = flags.sum(axis=1)
    blocks = flags[[c for c in flags.columns if severity[c] == "block"]].any(axis=1)
    reviews = flags[[c for c in flags.columns if severity[c] == "review"]].any(axis=1)
    out["status"] = "ready_to_pay"
    out.loc[reviews, "status"] = "review"
    out.loc[blocks, "status"] = "blocked"
    return out, flags


def summarize(result: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in RULES:
        hit = flags[r.code]
        rows.append({"rule": r.code, "short": r.short, "severity": r.severity, "description": r.description,
                     "invoices": int(hit.sum()),
                     "amount_ars": round(float(result.loc[hit, "total_amount"].sum()), 2)})
    return pd.DataFrame(rows)


def reconcile(src_invoices: pd.DataFrame, result: pd.DataFrame) -> dict:
    """Control totals: every invoice and every peso must land in exactly one status."""
    by_status = result.groupby("status")["total_amount"].agg(["count", "sum"])
    checks = {
        "invoices_in": len(src_invoices),
        "invoices_out": int(by_status["count"].sum()),
        "amount_in": round(float(src_invoices["total_amount"].sum()), 2),
        "amount_out": round(float(by_status["sum"].sum()), 2),
    }
    checks["count_ok"] = checks["invoices_in"] == checks["invoices_out"]
    checks["amount_ok"] = abs(checks["amount_in"] - checks["amount_out"]) < 0.01
    return checks
