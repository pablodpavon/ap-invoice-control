"""Run the full AP control: python run.py [--run-date YYYY-MM-DD]"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from apcontrol import pipeline, report  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-date", default="2026-09-01")
    args = ap.parse_args()
    src = pipeline.load(ROOT / "data")
    df = pipeline.prepare(src, args.run_date)
    result, flags = pipeline.run_rules(df)
    summary = pipeline.summarize(result, flags)
    checks = pipeline.reconcile(src["invoices"], result)
    if not (checks["count_ok"] and checks["amount_ok"]):
        raise SystemExit(f"Control totals do not reconcile: {checks}")
    report.write(result, summary, checks, ROOT / "output")
    print(json.dumps(checks, indent=2))
    print(result.status.value_counts().to_string())


if __name__ == "__main__":
    main()
