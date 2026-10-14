"""
Unit & Integration Test Suite for PHC MSDS Category I Deterministic Engine,
Zero-Tolerance Rules, SPC Control Charts, Alert Ranking, and PHI Scrubber.
"""
from engine import evaluate_kpi_deterministic, compute_spc_metrics, classify_alert_severity, scrub_patient_identifiers
from hims_simulator import load_config, build_simulated_snapshot
from ai_explainer import generate_grounded_ai_explanation


def run_tests():
    cfg = load_config()
    ind_map = {i["id"]: i for i in cfg["indicators"]}
    assert len(ind_map) == 15, f"Expected 15 in-scope indicators, got {len(ind_map)}"

    # Test 1: Zero-tolerance defect rule (Ind. 60 Expired Stock & Ind. 61 Labelling)
    res_exp_0 = evaluate_kpi_deterministic(ind_map["IND-060"], numerator=0, denominator=9400)
    assert res_exp_0.status == "Fully Met" and not res_exp_0.zero_tolerance_breach

    res_exp_1 = evaluate_kpi_deterministic(ind_map["IND-060"], numerator=1, denominator=9400)
    assert res_exp_1.status == "Not Met" and res_exp_1.zero_tolerance_breach, "1 expired unit MUST be Not Met!"

    res_lbl_1 = evaluate_kpi_deterministic(ind_map["IND-061"], numerator=1, denominator=1250)
    assert res_lbl_1.status == "Not Met" and res_lbl_1.zero_tolerance_breach, "1 incomplete label MUST be Not Met!"

    # Test 2: Dual urgency TAT rule (Emergency must be 100%, Routine >= 95%)
    res_tat_ok = evaluate_kpi_deterministic(
        ind_map["IND-004"], numerator=980, denominator=1000,
        emergency_num=200, emergency_den=200, routine_num=780, routine_den=800
    )
    assert res_tat_ok.status == "Fully Met"

    res_tat_em_fail = evaluate_kpi_deterministic(
        ind_map["IND-011"], numerator=970, denominator=1000,
        emergency_num=199, emergency_den=200, routine_num=771, routine_den=800
    )
    assert res_tat_em_fail.status == "Not Met" and res_tat_em_fail.zero_tolerance_breach, "Emergency < 100% MUST be Not Met!"

    # Test 3: Missing / Stale data alert
    res_stale = evaluate_kpi_deterministic(
        ind_map["IND-103"], numerator=740, denominator=760, hours_since_last_pull=28.5, max_stale_hours=24.0
    )
    assert res_stale.status == "Data Gap" and res_stale.data_gap_detected

    # Test 4: SPC +/- 3 SD & 6-point consecutive drift detection
    spc_drift = compute_spc_metrics([95.8, 95.6, 95.4, 95.5, 95.2, 95.0, 94.1, 92.8, 90.5, 88.4, 86.2, 83.4], "higher_is_better", "%")
    assert spc_drift.out_of_control_3sd and spc_drift.trend_breach

    # Test 5: Full snapshot & alert ranking order (Critical -> High -> Data gap -> Medium -> Watch)
    kpis, alerts = build_simulated_snapshot(cfg)
    ranks = [a["severity_rank"] for a in alerts]
    assert ranks == sorted(ranks), "Alerts must be sorted strictly by severity rank!"

    # Test 6: PHI Scrubber & AI Citation check
    sample_phi = "Patient Muhammad Ali (MRN-482910, CNIC 35202-1234567-1, Phone 0300-1234567) had delayed lab."
    scrubbed, count = scrub_patient_identifiers(sample_phi)
    assert count == 4 and "35202-1234567-1" not in scrubbed and "MRN-482910" not in scrubbed
    ai_out = generate_grounded_ai_explanation(kpis[0])
    assert "[Cite: IND-004" in ai_out["narrative_text"]
    assert ai_out["confirmation_status"] == "Pending Human Confirmation"

    print("ALL 6 DETERMINISTIC ENGINE, SPC, ALERT RANKING & PHI GOVERNANCE TESTS PASSED!")


if __name__ == "__main__":
    run_tests()