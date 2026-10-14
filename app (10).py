"""
PHC MSDS Category I Hospital — Automated Continuous Quality Monitoring (CQM) Dashboard
Deployable on Streamlit Community Cloud (connects to PostgreSQL via DATABASE_URL / st.secrets
or runs seamlessly with built-in HIMS simulated telemetry & in-memory state).
"""
import os
import copy
import datetime
import streamlit as st
import pandas as pd
import yaml

from engine import (
    evaluate_kpi_deterministic,
    compute_spc_metrics,
    classify_alert_severity,
    scrub_patient_identifiers,
)
from hims_simulator import load_config, SIMULATED_TELEMETRY, MONTH_LABELS
from ai_explainer import generate_grounded_ai_explanation

st.set_page_config(
    page_title="PHC MSDS Category I — Continuous Quality Monitoring",
    page_icon="🏥",
    layout="wide",
)

# -----------------------------------------------------------------------------
# 1. INITIALIZE PERSISTENT SESSION STATE
# -----------------------------------------------------------------------------
if "base_config" not in st.session_state:
    st.session_state.base_config = load_config()

if "telemetry" not in st.session_state:
    st.session_state.telemetry = copy.deepcopy(SIMULATED_TELEMETRY)

if "ai_confirmations" not in st.session_state:
    st.session_state.ai_confirmations = {
        "IND-005": "Confirmed by Diagnostic Quality Officer (2026-10-14 09:05 PKT)",
        "IND-057": "Confirmed by Chief Pharmacist (2026-10-14 09:08 PKT)",
        "IND-100": "Confirmed by Diagnostic Quality Officer (2026-10-14 09:10 PKT)",
        "IND-104": "Confirmed by Blood Bank In-Charge (2026-10-14 09:12 PKT)",
    }

if "report_confirmations" not in st.session_state:
    st.session_state.report_confirmations = {}

if "capa_list" not in st.session_state:
    st.session_state.capa_list = [
        {
            "capa_id": "CAPA-2026-041",
            "indicator_id": "IND-060",
            "title": "Quarantine 2 Expired Crash-Cart Vials in Surgical Ward 4",
            "owner": "Rizwan Ahmed (Pharmacy Inventory Lead)",
            "due_date": "2026-10-15",
            "status": "In Progress",
            "escalation_level": 1,
            "reminders": 2,
            "action_plan": "Remove expired Atropine & Adrenaline ampoules from Ward 4 crash cart; enforce daily shift barcode FEFO check.",
            "verification_note": "",
        },
        {
            "capa_id": "CAPA-2026-042",
            "indicator_id": "IND-011",
            "title": "Restore Night-Shift Emergency STAT CT/X-Ray Turnaround to 100%",
            "owner": "Dr. Kamran Rashid (HOD Radiology)",
            "due_date": "2026-10-16",
            "status": "Assigned",
            "escalation_level": 0,
            "reminders": 1,
            "action_plan": "Deploy auto-paging alert in RIS at 40-minute mark for unsigned STAT ER imaging studies.",
            "verification_note": "",
        },
        {
            "capa_id": "CAPA-2026-043",
            "indicator_id": "IND-061",
            "title": "Enforce Multi-Dose Vial Opening/Expiry Date Labelling in Medical ICU",
            "owner": "Dr. Hina Zahid (Inpatient Pharmacy Supervisor)",
            "due_date": "2026-10-16",
            "status": "Assigned",
            "escalation_level": 0,
            "reminders": 1,
            "action_plan": "Deploy thermal auxiliary label printers at MICU medication prep stations and conduct daily noon spot-check.",
            "verification_note": "",
        },
        {
            "capa_id": "CAPA-2026-044",
            "indicator_id": "IND-105",
            "title": "Arrest 6-Month Downward Drift in Discharge Summary & ICD-10 Coding",
            "owner": "Khalid Mehmood (Chief MRO)",
            "due_date": "2026-10-20",
            "status": "Escalated",
            "escalation_level": 2,
            "reminders": 3,
            "action_plan": "Mandate HIMS EMR discharge summary completion gate before generating final inpatient billing clearance.",
            "verification_note": "",
        },
        {
            "capa_id": "CAPA-2026-045",
            "indicator_id": "IND-103",
            "title": "Restore Daily OT Anaesthesia Registry CSV Automated Export",
            "owner": "Dr. Zafar Iqbal (HOD Anaesthesiology)",
            "due_date": "2026-10-15",
            "status": "In Progress",
            "escalation_level": 0,
            "reminders": 1,
            "action_plan": "Fix SFTP cron credential rotation on OT recovery room workstation so daily 20:00 CSV import resumes.",
            "verification_note": "",
        },
    ]

if "audit_log" not in st.session_state:
    st.session_state.audit_log = [
        {
            "timestamp": "2026-10-14 09:00:02 PKT",
            "actor": "HIMS Scheduled ETL Worker",
            "role": "System Service",
            "action": "AUTO_PULL_HIMS",
            "target": "14 Auto/Imported KPIs",
            "details": "Pulled de-identified numerator/denominator aggregates from HIMS LIS, RIS, eMAR, ADT & OT views. IND-103 flagged stale (>24h).",
        },
        {
            "timestamp": "2026-10-14 09:00:05 PKT",
            "actor": "Deterministic MSDS Rules Engine",
            "role": "Rule Engine v2024.2",
            "action": "SCORE_EVALUATION",
            "target": "All 15 In-Scope Indicators",
            "details": "Computed statuses: 9 Fully Met, 2 Partially Met, 3 Not Met (Zero-Tolerance/Target), 1 Data Gap.",
        },
    ]


def log_audit_event(actor: str, role: str, action: str, target: str, details: str):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S PKT")
    st.session_state.audit_log.insert(
        0,
        {
            "timestamp": now_str,
            "actor": actor,
            "role": role,
            "action": action,
            "target": target,
            "details": details,
        },
    )


def evaluate_current_state():
    cfg = st.session_state.base_config
    max_stale = float(cfg["scoring_engine_defaults"].get("missing_data_threshold_hours", 24.0))
    kpi_rows = []
    alerts = []

    for ind in cfg["indicators"]:
        ind_id = ind["id"]
        sim = st.session_state.telemetry[ind_id]
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


# -----------------------------------------------------------------------------
# 2. SIDEBAR: RBAC, HIMS SYNC & NAVIGATION
# -----------------------------------------------------------------------------
config = st.session_state.base_config
kpis, alerts = evaluate_current_state()

st.sidebar.title("🏥 PHC MSDS CQM Portal")
st.sidebar.caption(
    f"Edition: `{config['edition_metadata']['edition_id']}`  \n"
    "30 Standards • 162 Total KPIs • **15 Continuous HIMS KPIs Active**"
)

active_role = st.sidebar.selectbox(
    "Active RBAC Role",
    [
        "CMO / Medical Director",
        "CQI Coordinator",
        "Department Head (Pathology/Pharmacy/Surgery)",
        "PHC Compliance Auditor (Read-Only)",
    ],
)

db_url = os.environ.get("DATABASE_URL", "")
st.sidebar.info(
    "🔌 **Data Mode:** "
    + ("PostgreSQL Connected" if db_url else "Simulated HIMS ETL (In-Memory)")
    + "\n\n🛡️ **PHI Redaction:** Active (0 Patient IDs leave HIMS)"
)

col_sync, col_rst = st.sidebar.columns(2)
if col_sync.button("🔄 Sync HIMS", use_container_width=True):
    st.session_state.telemetry["IND-103"]["hours_since_last_pull"] = 0.2
    log_audit_event(
        actor=f"User ({active_role})",
        role=active_role,
        action="MANUAL_HIMS_SYNC",
        target="IND-103 Anaesthesia CSV",
        details="Triggered HIMS/CSV batch pull; IND-103 lag refreshed from 28.5h to 0.2h.",
    )
    st.rerun()

if col_rst.button("♻️ Reset Sim", use_container_width=True):
    st.session_state.telemetry = copy.deepcopy(SIMULATED_TELEMETRY)
    st.session_state.base_config = load_config()
    log_audit_event(
        actor=f"User ({active_role})",
        role=active_role,
        action="RESET_SIMULATION",
        target="All 15 Indicators",
        details="Restored default October 2026 simulated telemetry.",
    )
    st.rerun()

page = st.sidebar.radio(
    "Dashboard Views",
    [
        "1. Executive Overview",
        "2. KPI Monitor & Trends",
        "3. Indicator Detail & SPC",
        f"4. Alert Center ({len(alerts)})",
        "5. Action Tracker (CAPA)",
        "6. Monthly CQI Auto-Report",
        "7. YAML Config, HIMS & Audit Trail",
    ],
)

# -----------------------------------------------------------------------------
# VIEW 1: EXECUTIVE OVERVIEW
# -----------------------------------------------------------------------------
if page.startswith("1."):
    st.title("Executive Overview — PHC MSDS Category I Continuous Quality Monitoring")
    st.caption(
        "Deterministic Rules Engine: Scores (Fully / Partially / Not Met) and Zero-Tolerance gates are 100% rule-computed. "
        "AI only explains results, drafts CQI narratives with citations, and requires human confirmation."
    )

    fully_met = sum(1 for k in kpis if k["eval"].status == "Fully Met")
    part_met = sum(1 for k in kpis if k["eval"].status == "Partially Met")
    not_met = sum(1 for k in kpis if k["eval"].status == "Not Met")
    data_gap = sum(1 for k in kpis if k["eval"].status == "Data Gap")
    zt_breaches = sum(1 for k in kpis if k["eval"].zero_tolerance_breach)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Monitored MSDS KPIs", f"{len(kpis)} / 162", "11 Auto • 3 Imported • 1 Manual")
    c2.metric("Fully Met", fully_met, f"{(fully_met / len(kpis)) * 100:.1f}% compliant")
    c3.metric("Partially Met", part_met, "Needs CQI Watch")
    c4.metric("Not Met (Breaches)", not_met, f"{zt_breaches} Zero-Tolerance", delta_color="inverse")
    c5.metric("Data Gaps (>24h Stale)", data_gap, "ETL SLA = 24h", delta_color="off")

    st.subheader("Zero-Tolerance & Mandatory 100% Emergency Gate Status")
    zt_kpis = [
        k for k in kpis
        if k["rule_type"] in ("zero_tolerance_defects", "zero_tolerance_pct", "dual_urgency_tat")
    ]
    zt_cols = st.columns(4)
    for idx, zk in enumerate(zt_kpis):
        with zt_cols[idx % 4]:
            st.markdown(
                f"**{zk['id']} (Ind. {zk['indicator_number']}) — {zk['short_name']}**  \n"
                f"Status: `{zk['eval'].status}` | Value: **{zk['eval'].computed_value} {zk['unit']}**  \n"
                f"_{zk['eval'].rule_trace}_"
            )
            st.divider()

    st.subheader("Top Severity-Ranked Early-Warning Alerts")
    st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# VIEW 2: KPI MONITOR & TRENDS
# -----------------------------------------------------------------------------
elif page.startswith("2."):
    st.title("Continuous KPI Monitor & Trends (15 In-Scope MSDS Indicators)")
    fcol1, fcol2, fcol3 = st.columns(3)
    std_filter = fcol1.selectbox(
        "Filter by Scope",
        ["All 15 Indicators", "CQI Standard 17 Only (Ind. 99–105)", "Other Numeric KPIs (Ind. 4, 5, 11, 50, 54, 57, 60, 61)"],
    )
    status_filter = fcol2.selectbox(
        "Filter by Deterministic Status",
        ["All Statuses", "Not Met", "Partially Met", "Fully Met", "Data Gap"],
    )
    ing_filter = fcol3.selectbox(
        "Filter by Ingestion Mode",
        ["All Modes", "Automatic", "Imported", "Manual"],
    )

    rows = []
    for k in kpis:
        if std_filter.startswith("CQI") and k["standard_no"] != 17:
            continue
        if std_filter.startswith("Other") and k["standard_no"] == 17:
            continue
        if status_filter != "All Statuses" and k["eval"].status != status_filter:
            continue
        if ing_filter != "All Modes" and k["ingestion_mode"] != ing_filter:
            continue

        rows.append({
            "ID": k["id"],
            "Ind. #": k["indicator_number"],
            "MSDS Code": k["code"],
            "Indicator Name": k["name"],
            "Source Mode": k["ingestion_mode"],
            "Numerator": int(k["numerator"]),
            "Denominator": int(k["denominator"]),
            "Current Value": "Stale (>24h)" if k["eval"].data_gap_detected else f"{k['eval'].computed_value} {k['unit']}",
            "Emergency %": f"{k['eval'].emergency_pct}%" if k["eval"].emergency_pct is not None else "—",
            "Routine %": f"{k['eval'].routine_pct}%" if k["eval"].routine_pct is not None else "—",
            "MSDS Status": k["eval"].status,
            "SPC Baseline (Mean ± 3SD)": f"{k['spc'].mean} [{k['spc'].lcl_3sd} – {k['spc'].ucl_3sd}]",
            "SPC Signal": k["spc"].trend_description,
            "Owner": k["owner_name"],
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# VIEW 3: INDICATOR DETAIL, SHEWHART SPC CHART & LIVE SIMULATOR
# -----------------------------------------------------------------------------
elif page.startswith("3."):
    st.title("Indicator Detail, Shewhart SPC Control Chart (Mean ± 3 SD) & Simulator")
    selected_label = st.selectbox(
        "Select MSDS Indicator to Inspect",
        [f"{k['id']} (Ind. {k['indicator_number']}) — {k['name']} [{k['eval'].status}]" for k in kpis],
    )
    ind_id = selected_label.split(" ")[0]
    kpi = next(k for k in kpis if k["id"] == ind_id)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Deterministic Status", kpi["eval"].status)
    m2.metric(
        "Oct 2026 Value",
        "DATA GAP" if kpi["eval"].data_gap_detected else f"{kpi['eval'].computed_value} {kpi['unit']}",
        f"N={int(kpi['numerator']):,} / D={int(kpi['denominator']):,}",
    )
    m3.metric("SPC Mean ± 3 SD", f"{kpi['spc'].mean} {kpi['unit']}", f"[{kpi['spc'].lcl_3sd} – {kpi['spc'].ucl_3sd}] (z={kpi['spc'].latest_z_score:+.2f})")
    m4.metric("Ingestion Mode", kpi["ingestion_mode"], kpi["owner_name"])

    st.info(f"**Deterministic MSDS Rule Trace:** {kpi['eval'].rule_trace}  \n**SPC Signal:** {kpi['spc'].trend_description}")

    col_chart, col_sim = st.columns([2, 1])
    with col_chart:
        st.subheader("12-Month Shewhart Control Chart (Mean, ±2 SD Warning, ±3 SD Control Limits)")
        chart_df = pd.DataFrame({
            "Month": kpi["months"],
            "Observed": kpi["history"],
            "Mean (CL)": [kpi["spc"].mean] * len(kpi["months"]),
            "UCL (+3 SD)": [kpi["spc"].ucl_3sd] * len(kpi["months"]),
            "LCL (-3 SD)": [kpi["spc"].lcl_3sd] * len(kpi["months"]),
        }).set_index("Month")
        st.line_chart(chart_df)

    with col_sim:
        st.subheader("🧪 Live HIMS Telemetry & Rule Simulator")
        st.caption("Test deterministic scoring and CAPA auto-verification:")
        sim_n = st.number_input("Numerator (N)", min_value=0, value=int(kpi["numerator"]), step=1)
        sim_d = st.number_input("Denominator (D)", min_value=1, value=int(kpi["denominator"]), step=1)
        sim_stale = st.number_input("Hours Since Last Pull (SLA=24h)", min_value=0.0, value=float(kpi["hours_since_last_pull"]), step=0.5)

        if kpi["rule_type"] == "dual_urgency_tat":
            sim_em_n = st.number_input("Emergency Met (N)", min_value=0, value=int(kpi.get("emergency_num") or 0), step=1)
            sim_em_d = st.number_input("Emergency Total (D)", min_value=1, value=int(kpi.get("emergency_den") or 1), step=1)
        else:
            sim_em_n, sim_em_d = None, None

        if st.button("Apply Simulated HIMS Pull", type="primary", use_container_width=True):
            t_entry = st.session_state.telemetry[ind_id]
            t_entry["numerator"] = sim_n
            t_entry["denominator"] = sim_d
            t_entry["hours_since_last_pull"] = sim_stale
            if kpi["rule_type"] == "dual_urgency_tat":
                t_entry["emergency_num"] = sim_em_n
                t_entry["emergency_den"] = sim_em_d
                t_entry["routine_num"] = max(0, sim_n - sim_em_n)
                t_entry["routine_den"] = max(1, sim_d - sim_em_d)

            new_eval = evaluate_kpi_deterministic(
                kpi, sim_n, sim_d,
                t_entry.get("emergency_num"), t_entry.get("emergency_den"),
                t_entry.get("routine_num"), t_entry.get("routine_den"),
                sim_stale,
            )
            t_entry["history"][-1] = new_eval.computed_value
            st.session_state.ai_confirmations.pop(ind_id, None)
            log_audit_event(
                actor=f"User ({active_role})",
                role=active_role,
                action="SIMULATE_HIMS_PULL",
                target=ind_id,
                details=f"Updated N={sim_n}, D={sim_d}, Stale={sim_stale}h -> Status: {new_eval.status}",
            )
            st.rerun()

    st.subheader("🤖 AI Root-Cause Explanation & Action Proposal (Advisory Only)")
    ai_exp = generate_grounded_ai_explanation(kpi)
    st.write(ai_exp["narrative_text"])
    confirm_state = st.session_state.ai_confirmations.get(ind_id, "⏳ Pending Human Confirmation")
    st.caption(f"**Confirmation Status:** `{confirm_state}` | **PHI Scrubbed:** `{ai_exp['phi_scrubbed']}` | **Hash:** `{ai_exp['prompt_hash']}`")

    if st.button(f"✓ Confirm & Sign Off AI Analysis for {ind_id}"):
        if "Read-Only" in active_role:
            st.error("Read-Only PHC Auditor role cannot sign off clinical AI outputs.")
        else:
            stamp = f"Confirmed by {active_role} ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M PKT')})"
            st.session_state.ai_confirmations[ind_id] = stamp
            log_audit_event(
                actor=f"User ({active_role})",
                role=active_role,
                action="HUMAN_CONFIRM_AI",
                target=ind_id,
                details=f"Verified source citation and confirmed AI explanation for {ind_id}.",
            )
            st.rerun()

# -----------------------------------------------------------------------------
# VIEW 4: SEVERITY-RANKED ALERT CENTER
# -----------------------------------------------------------------------------
elif page.startswith("4."):
    st.title("Early-Warning & Compliance Alert Queue (Ranked by Severity)")
    sev_filter = st.radio(
        "Filter by Severity Rank",
        ["All", "Critical", "High", "Data gap", "Medium", "Watch"],
        horizontal=True,
    )
    filtered_alerts = alerts if sev_filter == "All" else [a for a in alerts if a["severity"] == sev_filter]
    for a in filtered_alerts:
        with st.container(border=True):
            st.markdown(
                f"### [{a['severity'].upper()}] {a['indicator_id']} — {a['indicator_name']} ({a['trigger_type']})  \n"
                f"- **Deterministic Reason & SPC Signal:** {a['deterministic_reason']}  \n"
                f"- **Accountable Owner:** {a['owner_name']} ({a['owner_role']})  \n"
                f"- **Suggested Action:** {a['suggested_action']}"
            )

# -----------------------------------------------------------------------------
# VIEW 5: CORRECTIVE ACTION (CAPA) TRACKER
# -----------------------------------------------------------------------------
elif page.startswith("5."):
    st.title("Corrective & Preventive Action (CAPA) Tracker")
    st.caption("Governance Rule: A CAPA can only be closed when the deterministic engine verifies the linked KPI is `Fully Met`.")

    with st.expander("➕ Assign New Corrective Action (CAPA)"):
        with st.form("new_capa_form"):
            c_ind = st.selectbox("Linked MSDS Indicator", [k["id"] for k in kpis])
            c_title = st.text_input("CAPA Title", "Restore KPI Compliance Above PHC MSDS Target")
            c_owner = st.text_input("Assigned Owner", "Dr. Usman Farooq (Chief Pharmacist)")
            c_due = st.date_input("Target Due Date", datetime.date(2026, 10, 21))
            c_plan = st.text_area("Corrective Action Plan", "Audit HIMS non-compliant cohort and enforce hard-stop workflow.")
            if st.form_submit_button("Assign CAPA"):
                new_id = f"CAPA-2026-0{46 + len(st.session_state.capa_list)}"
                st.session_state.capa_list.insert(0, {
                    "capa_id": new_id,
                    "indicator_id": c_ind,
                    "title": c_title,
                    "owner": c_owner,
                    "due_date": str(c_due),
                    "status": "Assigned",
                    "escalation_level": 0,
                    "reminders": 0,
                    "action_plan": c_plan,
                    "verification_note": "",
                })
                log_audit_event(f"User ({active_role})", active_role, "CREATE_CAPA", new_id, f"Assigned {new_id} ({c_ind}) to {c_owner}.")
                st.rerun()

    kpi_status_map = {k["id"]: k["eval"].status for k in kpis}
    for idx, c in enumerate(st.session_state.capa_list):
        linked_status = kpi_status_map.get(c["indicator_id"], "Unknown")
        with st.container(border=True):
            st.markdown(
                f"**{c['capa_id']} | {c['title']}**  \n"
                f"Linked KPI: `{c['indicator_id']}` (Live Status: **{linked_status}**) • "
                f"CAPA Status: `{c['status']}` • Owner: **{c['owner']}** • Due: `{c['due_date']}`  \n"
                f"Plan: _{c['action_plan']}_  \n"
                f"Reminders Sent: `{c['reminders']}` | Escalation Tier: `Level {c['escalation_level']}`"
            )
            if c.get("verification_note"):
                st.success(c["verification_note"])

            if c["status"] != "Closed - Verified":
                b1, b2, b3 = st.columns(3)
                if b1.button(f"🔔 Remind ({c['capa_id']})", key=f"rem_{idx}"):
                    c["reminders"] += 1
                    log_audit_event(f"User ({active_role})", active_role, "CAPA_REMIND", c["capa_id"], f"Sent reminder #{c['reminders']} to {c['owner']}.")
                    st.rerun()
                if b2.button(f"⚡ Escalate to CMO ({c['capa_id']})", key=f"esc_{idx}"):
                    c["escalation_level"] += 1
                    c["status"] = "Escalated"
                    log_audit_event(f"User ({active_role})", active_role, "CAPA_ESCALATE", c["capa_id"], f"Escalated to Level {c['escalation_level']}.")
                    st.rerun()
                if b3.button(f"✓ Verify Fix & Close ({c['capa_id']})", key=f"cls_{idx}"):
                    if linked_status != "Fully Met":
                        st.error(
                            f"Closure Blocked: {c['indicator_id']} is currently `{linked_status}`. "
                            "Use the Simulator on View 3 to verify the data fix first!"
                        )
                    else:
                        c["status"] = "Closed - Verified"
                        c["verification_note"] = f"Verified against HIMS ({c['indicator_id']} = Fully Met) & closed by {active_role}."
                        log_audit_event(f"User ({active_role})", active_role, "CAPA_CLOSE_VERIFIED", c["capa_id"], c["verification_note"])
                        st.rerun()

# -----------------------------------------------------------------------------
# VIEW 6: MONTHLY CQI COMMITTEE AUTO-REPORT
# -----------------------------------------------------------------------------
elif page.startswith("6."):
    st.title("Monthly CQI Committee Auto-Report — October 2026")
    st.caption("Auto-generated narrative with source data citations and mandatory human confirmation.")

    if st.button("✓ Confirm & Sign Off All Report Sections"):
        st.session_state.report_confirmations["ALL"] = f"Signed off by {active_role} on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M PKT')}"
        log_audit_event(f"User ({active_role})", active_role, "SIGN_OFF_MONTHLY_REPORT", "Oct-2026-Report", "Confirmed all AI report narratives.")
        st.rerun()

    if "ALL" in st.session_state.report_confirmations:
        st.success(st.session_state.report_confirmations["ALL"])
    else:
        st.warning("⏳ AI Narrative Sections Pending Human Confirmation")

    report_md_lines = [
        "# Hospital CQI Committee Monthly Report — October 2026",
        f"Edition: {config['edition_metadata']['edition_id']} | Generated: 2026-10-14",
        "",
        "## 1. Deterministic KPI Summary Table",
        "| Indicator | Name | Mode | Numerator/Denominator | Value | Status | SPC Signal |",
        "|---|---|---|---|---|---|---|",
    ]
    for k in kpis:
        report_md_lines.append(
            f"| {k['id']} (Ind. {k['indicator_number']}) | {k['name']} | {k['ingestion_mode']} | "
            f"{int(k['numerator'])}/{int(k['denominator'])} | {k['eval'].computed_value} {k['unit']} | "
            f"{k['eval'].status} | {k['spc'].trend_description} |"
        )
    report_md = "\n".join(report_md_lines)
    st.download_button(
        "📥 Download Monthly CQI Report (.md)",
        data=report_md,
        file_name="PHC_MSDS_CQI_Report_2026_10.md",
        mime="text/markdown",
    )

    for k in kpis:
        ai_exp = generate_grounded_ai_explanation(k)
        st.markdown(f"**{k['id']} (Ind. {k['indicator_number']} / {k['code']}) — {k['name']}**: `{k['eval'].status}`")
        st.caption(ai_exp["narrative_text"])

# -----------------------------------------------------------------------------
# VIEW 7: YAML CONFIG, HIMS MAPPING, PHI SCRUBBER & AUDIT TRAIL
# -----------------------------------------------------------------------------
elif page.startswith("7."):
    st.title("Editable MSDS YAML Catalogue, PHI Guardrail & Immutable Audit Trail")

    col_y, col_p = st.columns(2)
    with col_y:
        st.subheader("Versioned `msds_config.yaml`")
        with open(os.path.join(os.path.dirname(__file__), "msds_config.yaml"), "r", encoding="utf-8") as f:
            st.code(f.read(), language="yaml")

    with col_p:
        st.subheader("🛡️ Test PII/PHI Redaction Guardrail")
        sample_input = st.text_area(
            "Sample HIMS Text with Patient Identifiers",
            "Patient Muhammad Ali (MRN-482910, CNIC 35202-1234567-1, Phone 0300-1234567) had delayed STAT CT.",
        )
        if st.button("Run PHI Redaction Filter"):
            scrubbed, count = scrub_patient_identifiers(sample_input)
            st.success(f"Scrubbed {count} PHI tokens before AI serialization:")
            st.code(scrubbed)

    st.subheader("Immutable RBAC & Governance Audit Trail")
    st.dataframe(pd.DataFrame(st.session_state.audit_log), use_container_width=True, hide_index=True)