"""Generate a synthetic AP dataset for a fictional Argentine company.

Everything here is invented: suppliers, CUITs, purchase orders and invoices.
Known issues are injected at a fixed rate so the rules have something to find,
and the injected issues are written to data/_injected_issues.csv so tests can
check that the rules catch them (recall) without flagging clean invoices.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from apcontrol import cuit  # noqa: E402

SEED = 20261013
rng = random.Random(SEED)
np_rng = np.random.default_rng(SEED)
OUT = Path(__file__).resolve().parents[1] / "data"
START, END = date(2026, 3, 1), date(2026, 8, 31)

PREFIX = ["Distribuidora", "Logística", "Servicios", "Insumos", "Tecnología", "Papelera",
          "Transportes", "Consultora", "Metalúrgica", "Envases", "Mantenimiento", "Limpieza"]
PLACE = ["Andina", "del Plata", "Pampeana", "Austral", "Litoral", "Norte Grande",
         "Río Sur", "Patagónica", "de Cuyo", "del Delta", "Serrana", "Atlántica"]
FORM = ["SA", "SRL", "SAS"]
CATEGORIES = {"Insumos de oficina": (800, 25_000), "Logística": (40_000, 900_000),
              "Mantenimiento": (15_000, 400_000), "Servicios IT": (120_000, 2_500_000),
              "Packaging": (2_000, 60_000), "Limpieza": (5_000, 150_000)}


def make_cuit(prefix: str) -> str:
    while True:
        body = f"{prefix}{rng.randint(10_000_000, 99_999_999)}"
        dv = cuit.check_digit(body)
        if dv is not None:
            return body + str(dv)


def rand_date(a=START, b=END):
    return a + timedelta(days=rng.randint(0, (b - a).days))


def main():
    OUT.mkdir(exist_ok=True)
    # Suppliers: mostly companies (Responsable Inscripto), some monotributistas (people)
    suppliers, names = [], set()
    while len(suppliers) < 60:
        is_mono = rng.random() < 0.2
        if is_mono:
            name = f"{rng.choice(['Servicios', 'Mantenimiento', 'Consultoría'])} {rng.choice(['G.', 'M.', 'L.', 'R.', 'S.'])} {rng.choice(['Pérez', 'Gómez', 'Sosa', 'Díaz', 'Ruiz', 'Acosta', 'Benítez'])}"
            c = make_cuit(rng.choice(["20", "27"]))
        else:
            name = f"{rng.choice(PREFIX)} {rng.choice(PLACE)} {rng.choice(FORM)}"
            c = make_cuit("30")
        if name in names:
            continue
        names.add(name)
        suppliers.append({"supplier_cuit": c, "supplier_name": name,
                          "tax_status": "MONOTRIBUTO" if is_mono else "RI",
                          "category": rng.choice(list(CATEGORIES)),
                          "payment_terms_days": rng.choice([0, 15, 30, 45, 60])})
    sup = pd.DataFrame(suppliers)

    # Purchase orders and goods receipts
    pos, grs = [], []
    for i in range(1, 1101):
        s = sup.sample(1, random_state=np_rng.integers(1e9)).iloc[0]
        lo, hi = CATEGORIES[s.category]
        qty = rng.choice([1, 1, 1, 2, 3, 5, 10, 20])
        unit = round(rng.uniform(lo, hi) / max(qty, 1), 2)
        po_no = f"OC-{i:05d}"
        po_date = rand_date(START, END - timedelta(days=20))
        pos.append({"po_number": po_no, "supplier_cuit": s.supplier_cuit, "po_date": po_date,
                    "category": s.category, "quantity": qty, "unit_price": unit})
        grs.append({"gr_number": f"REC-{i:05d}", "po_number": po_no,
                    "receipt_date": po_date + timedelta(days=rng.randint(1, 10)), "received_qty": qty})
    po = pd.DataFrame(pos)
    gr = pd.DataFrame(grs)

    # Invoices: one per PO plus some service invoices without PO (small amounts)
    invoices, issues = [], []
    pos_counter = {c: rng.randint(1, 9) for c in sup.supplier_cuit}
    num_counter = {c: rng.randint(100, 5000) for c in sup.supplier_cuit}

    def new_invoice(s, po_row=None):
        num_counter[s.supplier_cuit] += 1
        if po_row is not None:
            qty, unit = po_row.quantity, po_row.unit_price
            inv_date = po_row.po_date + timedelta(days=rng.randint(3, 20))
        else:
            qty, unit = 1, round(rng.uniform(3_000, 200_000), 2)
            inv_date = rand_date()
        rate = 0.0 if s.tax_status == "MONOTRIBUTO" else rng.choice([0.21, 0.21, 0.21, 0.105, 0.27])
        net = round(qty * unit, 2)
        iva = round(net * rate, 2)
        other = round(net * 0.03, 2) if (s.tax_status == "RI" and rng.random() < 0.25) else 0.0
        return {"invoice_id": None, "supplier_cuit": s.supplier_cuit,
                "invoice_type": "C" if s.tax_status == "MONOTRIBUTO" else "A",
                "point_of_sale": f"{pos_counter[s.supplier_cuit]:05d}",
                "invoice_number": f"{num_counter[s.supplier_cuit]:08d}",
                "invoice_date": inv_date, "due_date": inv_date + timedelta(days=int(s.payment_terms_days)),
                "po_number": po_row.po_number if po_row is not None else None,
                "quantity": qty, "unit_price": unit, "net_amount": net, "iva_rate": rate,
                "iva_amount": iva, "other_taxes": other, "total_amount": round(net + iva + other, 2),
                "cae": "".join(rng.choice("0123456789") for _ in range(14)),
                "cae_due_date": inv_date + timedelta(days=10)}

    sup_by_cuit = {row.supplier_cuit: row for row in sup.itertuples(index=False)}
    for p in po.itertuples(index=False):
        invoices.append(new_invoice(sup_by_cuit[p.supplier_cuit], p))
    for _ in range(140):  # small service invoices without purchase order (allowed below threshold)
        s = sup_by_cuit[rng.choice(list(sup_by_cuit))]
        inv = new_invoice(s)
        inv["net_amount"] = round(rng.uniform(3_000, 180_000), 2)
        inv["unit_price"] = inv["net_amount"]
        inv["iva_amount"] = round(inv["net_amount"] * inv["iva_rate"], 2)
        inv["other_taxes"] = 0.0
        inv["total_amount"] = round(inv["net_amount"] + inv["iva_amount"], 2)
        invoices.append(inv)

    rng.shuffle(invoices)
    for i, inv in enumerate(invoices, 1):
        inv["invoice_id"] = f"FC-{i:05d}"

    # Inject issues on ~13 % of invoices (one issue each, recorded for the tests)
    def pick(cond=lambda x: True):
        while True:
            inv = rng.choice(invoices)
            if not inv.get("_issue") and cond(inv):
                return inv

    def mark(inv, code):
        inv["_issue"] = code
        issues.append({"invoice_id": inv["invoice_id"], "injected_rule": code})

    for _ in range(10):  # R01 invalid CUIT: corrupt the check digit (invoice-side typo)
        inv = pick()
        d = inv["supplier_cuit"]
        inv["supplier_cuit"] = d[:10] + str((int(d[10]) + 1) % 10)
        mark(inv, "R01")
    for _ in range(8):  # R02 unknown supplier: valid CUIT that is not in the master
        inv = pick()
        inv["supplier_cuit"] = make_cuit("30")
        mark(inv, "R02")
    for _ in range(14):  # R03 exact duplicate: same invoice keyed twice
        inv = pick()
        dup = dict(inv)
        dup["invoice_id"] = f"FC-{len(invoices) + 1:05d}"
        dup["invoice_date"] = inv["invoice_date"] + timedelta(days=rng.randint(0, 3))
        dup["due_date"] = dup["invoice_date"] + (inv["due_date"] - inv["invoice_date"])
        dup["cae_due_date"] = dup["invoice_date"] + timedelta(days=10)
        dup["_issue"] = "R03"
        invoices.append(dup)
        issues.append({"invoice_id": dup["invoice_id"], "injected_rule": "R03"})
        inv["_issue"] = "R03-original"
    for _ in range(6):  # R04 same bill re-sent with a new number a few days later
        inv = pick()
        dup = dict(inv)
        num_counter[inv["supplier_cuit"]] += 1
        dup["invoice_number"] = f"{num_counter[inv['supplier_cuit']]:08d}"
        dup["invoice_id"] = f"FC-{len(invoices) + 1:05d}"
        dup["invoice_date"] = inv["invoice_date"] + timedelta(days=rng.randint(1, 5))
        dup["due_date"] = dup["invoice_date"] + (inv["due_date"] - inv["invoice_date"])
        dup["cae_due_date"] = dup["invoice_date"] + timedelta(days=10)
        dup["_issue"] = "R04"
        invoices.append(dup)
        issues.append({"invoice_id": dup["invoice_id"], "injected_rule": "R04"})
        inv["_issue"] = "R04-original"
    for _ in range(12):  # R05 IVA wrong
        inv = pick(lambda x: x["iva_rate"] > 0)
        inv["iva_amount"] = round(inv["iva_amount"] * rng.choice([1.1, 0.9, 1.5]), 2)
        inv["total_amount"] = round(inv["net_amount"] + inv["iva_amount"] + inv["other_taxes"], 2)
        mark(inv, "R05")
    for _ in range(8):  # R06 total does not add up
        inv = pick()
        inv["total_amount"] = round(inv["total_amount"] + rng.choice([1000, -500, 2500.5]), 2)
        mark(inv, "R06")
    for _ in range(18):  # R08 price above PO
        inv = pick(lambda x: x["po_number"] is not None)
        bump = rng.uniform(1.04, 1.25)
        inv["unit_price"] = round(inv["unit_price"] * bump, 2)
        inv["net_amount"] = round(inv["quantity"] * inv["unit_price"], 2)
        inv["iva_amount"] = round(inv["net_amount"] * inv["iva_rate"], 2)
        inv["other_taxes"] = 0.0
        inv["total_amount"] = round(inv["net_amount"] + inv["iva_amount"], 2)
        mark(inv, "R08")
    for _ in range(12):  # R09 more quantity than received
        inv = pick(lambda x: x["po_number"] is not None)
        inv["quantity"] = inv["quantity"] + rng.randint(1, 3)
        inv["net_amount"] = round(inv["quantity"] * inv["unit_price"], 2)
        inv["iva_amount"] = round(inv["net_amount"] * inv["iva_rate"], 2)
        inv["other_taxes"] = 0.0
        inv["total_amount"] = round(inv["net_amount"] + inv["iva_amount"], 2)
        mark(inv, "R09")
    for _ in range(10):  # R07 big invoice without PO
        inv = pick(lambda x: x["po_number"] is not None and x["total_amount"] > 300_000)
        inv["po_number"] = None
        mark(inv, "R07")
    for _ in range(8):  # R10 type A from a monotributista
        inv = pick(lambda x: x["invoice_type"] == "C")
        inv["invoice_type"] = "A"
        mark(inv, "R10")
    for _ in range(9):  # R11 CAE missing or expired
        inv = pick()
        if rng.random() < 0.5:
            inv["cae"] = None
        else:
            inv["cae_due_date"] = inv["invoice_date"] - timedelta(days=rng.randint(1, 30))
        mark(inv, "R11")
    for _ in range(6):  # R12 due date before invoice date
        inv = pick()
        inv["due_date"] = inv["invoice_date"] - timedelta(days=rng.randint(1, 15))
        mark(inv, "R12")

    inv_df = pd.DataFrame(invoices).drop(columns=["_issue"], errors="ignore")
    sup.to_csv(OUT / "suppliers.csv", index=False)
    po.to_csv(OUT / "purchase_orders.csv", index=False)
    gr.to_csv(OUT / "goods_receipts.csv", index=False)
    inv_df.to_csv(OUT / "invoices.csv", index=False)
    pd.DataFrame(issues).to_csv(OUT / "_injected_issues.csv", index=False)
    print(f"suppliers={len(sup)} pos={len(po)} invoices={len(inv_df)} injected={len(issues)}")


if __name__ == "__main__":
    main()
