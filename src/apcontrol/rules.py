"""Validation rules for supplier invoices.

Each rule is a function that receives the prepared invoice table and returns a boolean
Series (True = exception). Rules are declared in RULES with a code, a severity and a
plain-language description, so the catalogue in docs/rules.md and the code stay in sync.
"""
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from . import cuit

IVA_RATES = {0.21, 0.105, 0.27, 0.0}
PRICE_TOLERANCE = 0.02      # 2 % price variance vs purchase order
AMOUNT_TOLERANCE = 0.01     # ARS rounding tolerance
NO_PO_THRESHOLD = 250_000   # ARS: invoices above this need a purchase order
POSSIBLE_DUP_DAYS = 7


@dataclass(frozen=True)
class Rule:
    code: str
    severity: str  # "block" = do not pay, "review" = needs a human look
    description: str
    short: str
    check: Callable[[pd.DataFrame], pd.Series]


def _invalid_cuit(df):
    return ~df["supplier_cuit"].map(cuit.is_valid)


def _unknown_supplier(df):
    return df["supplier_name_master"].isna()


def _exact_duplicate(df):
    key = ["supplier_cuit", "invoice_type", "point_of_sale", "invoice_number"]
    return df.duplicated(subset=key, keep="first")


def _possible_duplicate(df):
    d = df.sort_values("invoice_date")
    flags = pd.Series(False, index=df.index)
    for _, g in d.groupby(["supplier_cuit", "total_amount"]):
        if len(g) < 2:
            continue
        dates = g["invoice_date"].tolist()
        idx = g.index.tolist()
        nums = g["invoice_number"].tolist()
        for i in range(1, len(g)):
            gap = (dates[i] - dates[i - 1]).days
            if gap <= POSSIBLE_DUP_DAYS and nums[i] != nums[i - 1]:
                flags.loc[idx[i]] = True
    return flags


def _iva_mismatch(df):
    rate_ok = df["iva_rate"].isin(IVA_RATES)
    calc_ok = (df["net_amount"] * df["iva_rate"] - df["iva_amount"]).abs() <= AMOUNT_TOLERANCE
    return ~(rate_ok & calc_ok)


def _total_mismatch(df):
    expected = df["net_amount"] + df["iva_amount"] + df["other_taxes"]
    return (expected - df["total_amount"]).abs() > AMOUNT_TOLERANCE


def _missing_po(df):
    return df["po_number"].isna() & (df["total_amount"] > NO_PO_THRESHOLD)


def _price_variance(df):
    has_po = df["po_unit_price"].notna()
    var = (df["unit_price"] - df["po_unit_price"]) / df["po_unit_price"]
    return has_po & (var > PRICE_TOLERANCE)


def _qty_over_received(df):
    has_gr = df["received_qty"].notna()
    return has_gr & (df["quantity"] > df["received_qty"])


def _type_vs_tax_status(df):
    # We are a VAT-registered company (Responsable Inscripto):
    # RI suppliers issue type A, monotributistas issue type C.
    expected = df["supplier_tax_status"].map({"RI": "A", "MONOTRIBUTO": "C"})
    return expected.notna() & (expected != df["invoice_type"])


def _cae_problem(df):
    missing = df["cae"].isna() | (df["cae"].astype(str).str.len() != 14)
    expired = df["cae_due_date"].notna() & (df["cae_due_date"] < df["invoice_date"])
    return missing | expired


def _date_problem(df):
    future = df["invoice_date"] > df["run_date"]
    due_before = df["due_date"] < df["invoice_date"]
    return future | due_before


RULES: list[Rule] = [
    Rule("R01", "block", "Supplier CUIT fails the check-digit validation", "Invalid CUIT", _invalid_cuit),
    Rule("R02", "block", "Supplier not found in the supplier master", "Unknown supplier", _unknown_supplier),
    Rule("R03", "block", "Exact duplicate (same CUIT, type, point of sale and number)", "Exact duplicate", _exact_duplicate),
    Rule("R04", "review", f"Possible duplicate: same supplier and total within {POSSIBLE_DUP_DAYS} days", "Possible duplicate", _possible_duplicate),
    Rule("R05", "block", "IVA rate not allowed or IVA amount does not match net x rate", "IVA error", _iva_mismatch),
    Rule("R06", "block", "Total does not equal net + IVA + other taxes", "Total does not add up", _total_mismatch),
    Rule("R07", "review", f"No purchase order on an invoice above ARS {NO_PO_THRESHOLD:,.0f}", "No PO above threshold", _missing_po),
    Rule("R08", "review", f"Unit price above the purchase order price by more than {PRICE_TOLERANCE:.0%}", "Price above PO", _price_variance),
    Rule("R09", "block", "Invoiced quantity above quantity received (goods receipt)", "Qty above received", _qty_over_received),
    Rule("R10", "review", "Invoice type inconsistent with the supplier's tax status", "Type vs tax status", _type_vs_tax_status),
    Rule("R11", "block", "CAE missing, malformed or expired at invoice date", "CAE missing/expired", _cae_problem),
    Rule("R12", "review", "Invoice date in the future or due date before invoice date", "Date inconsistency", _date_problem),
]
