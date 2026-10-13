"""Write the reviewer outputs: exception list, rule summary, Excel workbook and a chart."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

INK, MUTED, BLOCK, REVIEW, OK = "#1d2433", "#6b7280", "#b42318", "#b54708", "#2e7d5b"
plt.rcParams.update({"font.family": "Inter", "font.size": 10, "axes.edgecolor": "#d0d5dd",
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": INK})

COLS = ["invoice_id", "status", "rules_hit", "supplier_cuit", "supplier_name_master", "invoice_type",
        "point_of_sale", "invoice_number", "invoice_date", "due_date", "po_number", "quantity",
        "received_qty", "unit_price", "po_unit_price", "net_amount", "iva_rate", "iva_amount",
        "other_taxes", "total_amount"]


def write(result: pd.DataFrame, summary: pd.DataFrame, checks: dict, out_dir: Path) -> None:
    out_dir.mkdir(exist_ok=True)
    exc = result[result.status != "ready_to_pay"].sort_values(["status", "total_amount"], ascending=[True, False])
    exc[COLS].to_csv(out_dir / "exceptions.csv", index=False)
    summary.to_csv(out_dir / "rule_summary.csv", index=False)

    status = (result.groupby("status")["total_amount"].agg(invoices="count", amount_ars="sum")
              .reindex(["ready_to_pay", "review", "blocked"]).reset_index())
    with pd.ExcelWriter(out_dir / "ap_review.xlsx") as xw:
        status.to_excel(xw, sheet_name="Status", index=False)
        summary.to_excel(xw, sheet_name="Rules", index=False)
        exc[COLS].to_excel(xw, sheet_name="Exceptions", index=False)
        pd.DataFrame([checks]).T.rename(columns={0: "value"}).to_excel(xw, sheet_name="Control totals")

    _chart(status, summary, out_dir / "ap_review.png")


def _chart(status, summary, path):
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw={"width_ratios": [1.2, 1]})
    colors = {"ready_to_pay": OK, "review": REVIEW, "blocked": BLOCK}
    labels = {"ready_to_pay": "Ready to pay", "review": "Needs review", "blocked": "Blocked"}
    s = status.set_index("status")
    a.barh([labels[k] for k in s.index][::-1], (s.amount_ars / 1e6)[::-1],
           color=[colors[k] for k in s.index][::-1], height=0.55)
    for i, (k, row) in enumerate(list(s.iterrows())[::-1]):
        a.text(row.amount_ars / 1e6, i, f"  ARS {row.amount_ars/1e6:,.1f} M · {int(row.invoices)} inv.",
               va="center", color=INK, fontsize=9)
    a.set_title("Where the money sits", loc="left", fontweight="bold", color=INK, pad=16)
    a.set_xlabel("ARS millions"); a.spines[["top", "right"]].set_visible(False)
    a.set_xlim(0, s.amount_ars.max() / 1e6 * 1.6)

    sm = summary[summary.invoices > 0].sort_values("invoices")
    b.barh(sm.rule + "  " + sm.short, sm.invoices,
           color=[BLOCK if v == "block" else REVIEW for v in sm.severity], height=0.6)
    for i, v in enumerate(sm.invoices):
        b.text(v, i, f" {v}", va="center", fontsize=9, color=INK)
    b.set_title("Exceptions by rule", loc="left", fontweight="bold", color=INK, pad=16)
    b.text(0, 1.02, "red = payment blocked · amber = needs review", transform=b.transAxes, color=MUTED, fontsize=8.5)
    b.xaxis.get_major_locator().set_params(integer=True)
    b.spines[["top", "right"]].set_visible(False); b.tick_params(axis="y", labelsize=8.5)
    fig.text(0.01, 0.01, "Synthetic data. Fictional company and suppliers.", color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)
