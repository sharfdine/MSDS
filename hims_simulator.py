"""
Simulated HIMS Scheduled ETL Connector & 12-Month Telemetry Generator.
Used until the hospital's production HIMS HL7/SQL field mapping is completed.
"""
from typing import Dict, List, Tuple
import yaml
import os
from engine import evaluate_kpi_deterministic, compute_spc_metrics, classify_alert_severity

MONTH_LABELS = [
    "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
    "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"
]

# Realistic 12-month telemetry for a 500-bed Category I Hospital in Lahore
# Includes deliberate test cases for:
# - Zero-tolerance breach on Expired Stock (IND-060: 2 expired units in Oct 2026)
# - Zero-tolerance breach on Emergency Imaging TAT (IND-011: Emergency = 98.4% < 100%)
# - Zero-tolerance breach on Labelling (IND-061: 1 incomplete label in Oct 2026)
# - Consecutive SPC adverse drift on Medical Records Completeness (IND-105: 6 months declining)
# - Partially Met + SPC warning on Order Quality (IND-054) and Invasive Procedures (IND-101)
SIMULATED_TELEMETRY: Dict[str, Dict] = {
    "IND-004": {
        "history": [96.2, 96.5, 96.8, 96.1, 97.0, 96.9, 97.2, 96.8, 97.1, 97.4, 97.3, 97.5],
        "numerator": 14430, "denominator": 14800,
        "emergency_num": 3200, "emergency_den": 3200,
        "routine_num": 11230, "routine_den": 11600,
        "hours_since_last_pull": 0.25,
    },
    "IND-005": {
        "history": [100.0, 100.0, 100.0, 99.5, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "numerator": 412, "denominator": 412,
        "hours_since_last_pull": 0.1,
    },
    "IND-011": {
        "history": [96.4, 96.1, 96.8, 96.5, 96.9, 96.2, 96.7, 96.5, 96.3, 96.0, 95.8, 95.6],
        "numerator": 4015, "denominator": 4200,
        "emergency_num": 610, "emergency_den": 620,  # 98.39% -> Breaches 100% emergency rule!
        "routine_num": 3405, "routine_den": 3580,    # 95.11% -> Routine met, but Emergency < 100%
        "hours_since_last_pull": 0.5,
    },
    "IND-050": {
        "history": [1.20, 1.15, 1.30, 1.25, 1.18, 1.22, 1.35, 1.40, 1.32, 1.28, 1.38, 1.34],
        "numerator": 12, "denominator": 895,
        "hours_since_last_pull": 4.0,
    },
    "IND-054": {
        "history": [95.4, 95.6, 95.2, 95.8, 95.5, 95.1, 94.8, 94.2, 93.6, 92.8, 91.9, 91.2],
        "numerator": 16872, "denominator": 18500,
        "hours_since_last_pull": 0.8,
    },
    "IND-057": {
        "history": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "numerator": 2840, "denominator": 2840,
        "hours_since_last_pull": 0.25,
    },
    "IND-060": {
        "history": [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 2],
        "numerator": 2, "denominator": 9400,  # 2 expired units found in Ward 4 Crash Cart -> Critical Not Met!
        "hours_since_last_pull": 3.5,
    },
    "IND-061": {
        "history": [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
        "numerator": 1, "denominator": 1250,  # 1 incomplete multi-dose insulin vial label -> Critical Not Met!
        "hours_since_last_pull": 6.0,
    },
    "IND-099": {
        "history": [96.8, 97.1, 96.9, 97.3, 97.0, 97.4, 97.2, 97.5, 97.1, 97.6, 97.4, 97.8],
        "numerator": 6259, "denominator": 6400,
        "emergency_num": 2900, "emergency_den": 2900,  # 100.0%
        "routine_num": 3359, "routine_den": 3500,    # 95.97%
        "hours_since_last_pull": 0.4,
    },
    "IND-100": {
        "history": [98.2, 98.5, 98.0, 98.4, 98.6, 98.3, 98.7, 98.5, 98.4, 98.8, 98.6, 98.9],
        "numerator": 1780, "denominator": 1800,
        "hours_since_last_pull": 2.0,
    },
    "IND-101": {
        "history": [96.5, 96.8, 96.2, 96.4, 96.1, 95.9, 95.5, 95.2, 94.8, 94.3, 93.9, 93.5],
        "numerator": 860, "denominator": 920,
        "hours_since_last_pull": 0.9,
    },
    "IND-102": {
        "history": [1.45, 1.52, 1.38, 1.48, 1.42, 1.50, 1.44, 1.55, 1.49, 1.58, 1.62, 1.65],
        "numerator": 38, "denominator": 23000,  # 1.65 per 1,000 orders (<= 2.0 Fully Met)
        "hours_since_last_pull": 5.0,
    },
    "IND-103": {
        "history": [97.4, 97.6, 97.2, 97.8, 97.5, 97.3, 97.7, 97.4, 97.6, 97.5, 97.2, 97.4],
        "numerator": 740, "denominator": 760,
        "hours_since_last_pull": 28.5,  # Stale > 24h CSV import -> triggers Data gap alert!
    },
    "IND-104": {
        "history": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "numerator": 645, "denominator": 645,
        "hours_since_last_pull": 0.3,
    },
    "IND-105": {
        "history": [95.8, 95.6, 95.4, 95.5, 95.2, 95.0, 94.1, 92.8, 90.5, 88.4, 86.2, 83.4],
        "numerator": 2585, "denominator": 3100,  # 83.39% -> Not Met (<85%) + 6-period downward drift + >3 SD!
        "hours_since_last_pull": 1.5,
    },
}


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "msds_config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_simulated_snapshot(config: dict = None) -> Tuple[List[dict], List[dict]]:
    if config is None:
        config = load_config()
    max_stale = float(config["scoring_engine_defaults"].get("missing_data_threshold_hours", 24.0))
    kpi_rows = []
    alerts = []

    for ind in config["indicators"]:
        ind_id = ind["id"]
        sim = SIMULATED_TELEMETRY[ind_id]
        eval_res = evaluate_kpi_deterministic(
            indicator_cfg=ind,
            numerator=sim["numerator"],
            denominator=sim["denominator"],
            emergency_num=sim.get("emergency_num"),
            emergency_den=sim.get("emergency_den"),
            routine_num=sim.get("routine_num"),
            routine_den=sim.get("routine_den"),
            hours_since_last_pull=sim.get("hours_since_last_pull", 1.0),
            max_stale_hours=max_stale,
        )
        spc_res = compute_spc_metrics(
            series=sim["history"],
            direction=ind["direction"],
            unit=ind["unit"],
        )
        alert = classify_alert_severity(ind, eval_res, spc_res)
        if alert:
            alerts.append(alert)

        kpi_rows.append({
            **ind,
            "numerator": sim["numerator"],
            "denominator": sim["denominator"],
            "emergency_num": sim.get("emergency_num"),
            "emergency_den": sim.get("emergency_den"),
            "routine_num": sim.get("routine_num"),
            "routine_den": sim.get("routine_den"),
            "hours_since_last_pull": sim.get("hours_since_last_pull", 1.0),
            "history": sim["history"],
            "months": MONTH_LABELS,
            "eval": eval_res,
            "spc": spc_res,
        })

    alerts.sort(key=lambda a: (a["severity_rank"], a["indicator_id"]))
    return kpi_rows, alerts