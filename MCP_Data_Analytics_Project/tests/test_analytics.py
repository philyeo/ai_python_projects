"""Quick smoke test for the Pandas analytics module (run directly)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pandas_mcp import analytics  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def show(label, payload):
    print(f"\n=== {label} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


titanic = analytics.load_dataframe(DATA / "titanic.csv")
show("Titanic shape/columns", {"shape": titanic.shape, "columns": list(titanic.columns)})
show("Titanic info", analytics.get_dataset_info(titanic))
show("avg age", analytics.aggregate_data(titanic, "age", "mean"))
show("avg fare by pclass", analytics.groupby_data(titanic, "pclass", "mean", "fare"))
show("survival rate by sex", analytics.groupby_data(titanic, "sex", "mean", "survived"))
show(
    "filter age>50 & survived",
    analytics.filter_dataset(
        titanic,
        '[{"column":"age","operator":">","value":50},'
        '{"column":"survived","operator":"==","value":1}]',
        limit=5,
    ),
)

plan = analytics.load_dataframe(DATA / "ProjectPlan.xlsx")
show("Plan shape/columns", {"shape": plan.shape, "columns": list(plan.columns)})
show("Plan info", analytics.get_dataset_info(plan))
show("task count", analytics.aggregate_data(plan, "", "count"))
show("tasks by status", analytics.groupby_data(plan, "Status", "count"))
show("tasks by Module", analytics.groupby_data(plan, "Module", "count"))
show("tasks by Assigned To", analytics.groupby_data(plan, "Assigned To", "count"))
show(
    "unassigned tasks",
    analytics.filter_dataset(plan, '[{"column":"Assigned To","operator":"isnull"}]', 10),
)
