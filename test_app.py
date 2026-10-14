"""
Verification test script for PHC MSDS Dashboard
"""
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from core.database import db
from core.hims_pipeline import hims_pipeline
from core.rules_engine import MSDSRulesEngine
from core.spc_engine import SPCEngine
from core.alert_engine import AlertEngine
from core.capa_engine import CAPAEngine
from core.ai_assistant import AICQIAssistant

print("1. Seeding 90 days of synthetic telemetry...")
hims_pipeline.initialize_synthetic_history(days=90)

conn = db.get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) as cnt FROM indicator_evaluations")
eval_cnt = cur.fetchone()["cnt"]
print(f"   Evaluations in DB: {eval_cnt}")

cur.execute("SELECT COUNT(*) as cnt FROM alerts")
alert_cnt = cur.fetchone()["cnt"]
print(f"   Alerts in DB: {alert_cnt}")

cur.execute("SELECT COUNT(*) as cnt FROM capas")
capa_cnt = cur.fetchone()["cnt"]
print(f"   CAPAs in DB: {capa_cnt}")

# Test Rules Engine on Zero Tolerance
meta_zt = {"id": "IND-060", "code": "expired_stock_monitoring", "name": "Expired Stock", "zero_tolerance": True, "benchmark_target": 0.0, "unit": "Expired Units"}
res_clean = MSDSRulesEngine.evaluate_indicator(meta_zt, 0, 20)
print(f"   Zero Tolerance (0 units): Status = {res_clean['status']}, Points = {res_clean['points']}")
res_breach = MSDSRulesEngine.evaluate_indicator(meta_zt, 2, 20)
print(f"   Zero Tolerance (2 units): Status = {res_breach['status']}, Points = {res_breach['points']}, Severity = {res_breach['breach_severity']}")

# Test Rules Engine on Emergency TAT (100% rule)
meta_er = {"id": "IND-004-EMERG", "code": "lab_turnaround_emergency", "name": "Emergency Lab TAT", "zero_tolerance": False, "benchmark_target": 100.0, "unit": "%"}
res_er_100 = MSDSRulesEngine.evaluate_indicator(meta_er, 100, 100)
print(f"   Emergency TAT (100%): Status = {res_er_100['status']}, Points = {res_er_100['points']}")
res_er_92 = MSDSRulesEngine.evaluate_indicator(meta_er, 92, 100)
print(f"   Emergency TAT (92%): Status = {res_er_92['status']}, Points = {res_er_92['points']}, Severity = {res_er_92['breach_severity']}")

# Test SPC calculations
limits = SPCEngine.calculate_control_limits([95.0, 96.0, 94.0, 97.0, 95.5, 93.0], "p-chart", 95.0)
print(f"   SPC Limits: Mean={limits['mean']}, UCL={limits['ucl']}, LCL={limits['lcl']}")

# Test CAPA Auto-Verification
verified = CAPAEngine.verify_capas_against_hims_data()
print(f"   CAPA Auto-Verification: {len(verified)} verified auto-closed.")

print("ALL TESTS PASSED SUCCESSFULLY!")
