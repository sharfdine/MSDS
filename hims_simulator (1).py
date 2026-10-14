"""
Universal Multi-Hospital Telemetry Connector & 12-Month Simulator.
Supports Camden Health System HIMS, Oracle/SQL Server HIS, MySQL/Postgres,
Smart CSV/Excel Column Mapping, and Ward Tablet Micro-Tally inputs.
Includes built-in DEFAULT_MSDS_CONFIG_YAML so FileNotFoundError can never occur.
"""
from typing import Dict, List, Tuple
import yaml
import os
from engine import evaluate_kpi_deterministic, compute_spc_metrics, classify_alert_severity

DEFAULT_MSDS_CONFIG_YAML = """edition_metadata:
  edition_id: "PHC-MSDS-Cat1-Ed2-2024.2"
  authority: "Punjab Healthcare Commission (PHC)"
  facility_category: "Category I Hospitals (50+ Beds / Teaching & Tertiary Care)"
  total_standards: 30
  total_indicators: 162
  monitored_continuous_indicators: 15
  effective_date: "2024-09-01"
  version_hash: "sha256:9c84b10e42f8a3d1"
  out_of_scope_note: "Presence/absence indicators (policies, SOP manuals, valid licences, signage) are excluded from continuous HIMS telemetry and tracked in annual licensing audits."

scoring_engine_defaults:
  spc_sigma_limit: 3.0
  spc_warning_sigma: 2.0
  consecutive_trend_length: 6
  same_side_of_mean_length: 8
  missing_data_threshold_hours: 24
  phi_redaction_enforced: true

indicators:
  - id: "IND-004"
    indicator_number: 4
    code: "AAC-2.1"
    standard_no: 2
    standard_name: "Access, Assessment and Continuity of Care (AAC)"
    name: "Laboratory Turnaround Time (TAT) Compliance"
    short_name: "Lab Turnaround (TAT)"
    ingestion_mode: "Automatic"
    hims_source: "HIMS LIS -> lab_orders_tat_view"
    schedule_cron: "*/15 * * * *"
    owner_role: "Head of Pathology & Clinical Lab"
    owner_name: "Dr. Tariq Mahmood (HOD Pathology)"
    unit: "%"
    rule_type: "dual_urgency_tat"
    direction: "higher_is_better"
    emergency_target_pct: 100.0
    routine_full_pct: 95.0
    routine_partial_pct: 90.0
    numerator_label: "Lab tests reported within defined TAT window"
    denominator_label: "Total verified lab orders (Emergency STAT + Routine)"
    hims_mapping_status: "Simulated (Awaiting LIS HL7/SQL mapping)"

  - id: "IND-005"
    indicator_number: 5
    code: "AAC-2.2"
    standard_no: 2
    standard_name: "Access, Assessment and Continuity of Care (AAC)"
    name: "Critical Diagnostic Result Reporting (<15 min Read-Back)"
    short_name: "Critical Result Reporting"
    ingestion_mode: "Automatic"
    hims_source: "HIMS LIS/RIS -> critical_panic_alerts_log"
    schedule_cron: "*/5 * * * *"
    owner_role: "Diagnostic Quality Officer"
    owner_name: "Dr. Ayesha Siddiqa (Diagnostic QA)"
    unit: "%"
    rule_type: "zero_tolerance_pct"
    direction: "higher_is_better"
    full_threshold: 100.0
    numerator_label: "Critical panic values communicated with clinician read-back <=15m"
    denominator_label: "Total critical panic results generated (Lab + Radiology)"
    hims_mapping_status: "Simulated (Awaiting LIS Panic Log mapping)"

  - id: "IND-011"
    indicator_number: 11
    code: "AAC-3.2"
    standard_no: 3
    standard_name: "Access, Assessment and Continuity of Care (AAC)"
    name: "Diagnostic Imaging Turnaround Time (TAT) Compliance"
    short_name: "Imaging Turnaround (TAT)"
    ingestion_mode: "Automatic"
    hims_source: "HIMS RIS/PACS -> rad_study_tat_view"
    schedule_cron: "*/30 * * * *"
    owner_role: "Head of Radiology & Imaging"
    owner_name: "Dr. Kamran Rashid (HOD Radiology)"
    unit: "%"
    rule_type: "dual_urgency_tat"
    direction: "higher_is_better"
    emergency_target_pct: 100.0
    routine_full_pct: 95.0
    routine_partial_pct: 90.0
    numerator_label: "Imaging studies signed off within defined TAT window"
    denominator_label: "Total diagnostic imaging exams (STAT ER + Routine)"
    hims_mapping_status: "Simulated (Awaiting RIS/PACS study timestamp mapping)"

  - id: "IND-050"
    indicator_number: 50
    code: "HIC-2.1"
    standard_no: 14
    standard_name: "Hospital Infection Control (HIC)"
    name: "Surgical Site Infection (SSI) Surveillance Rate"
    short_name: "Surgical Site Infection (SSI)"
    ingestion_mode: "Imported"
    hims_source: "IPC Surveillance Export -> ssi_30d_cohort_csv"
    schedule_cron: "0 6 * * *"
    owner_role: "Infection Prevention & Control (IPC) Lead"
    owner_name: "Dr. Nadia Hassan (IPC Chair)"
    unit: "%"
    rule_type: "rate_upper_bound"
    direction: "lower_is_better"
    full_threshold: 1.5
    partial_threshold: 3.0
    numerator_label: "Confirmed 30-day clean/clean-contaminated SSI cases"
    denominator_label: "Total clean & clean-contaminated surgical procedures"
    hims_mapping_status: "Simulated (Daily CSV import from IPC Registry)"

  - id: "IND-054"
    indicator_number: 54
    code: "MOM-2.1"
    standard_no: 10
    standard_name: "Management of Medication (MOM)"
    name: "Medication Order Quality & Complete Prescribing Compliance"
    short_name: "Medication Order Quality"
    ingestion_mode: "Automatic"
    hims_source: "HIMS CPOE -> rx_order_completeness_view"
    schedule_cron: "0 * * * *"
    owner_role: "Chief Pharmacist"
    owner_name: "Dr. Usman Farooq (Chief Pharmacist)"
    unit: "%"
    rule_type: "standard_pct"
    direction: "higher_is_better"
    full_threshold: 95.0
    partial_threshold: 85.0
    numerator_label: "Orders with complete dose, route, frequency, generic name & sign-off"
    denominator_label: "Total inpatient & emergency medication orders audited"
    hims_mapping_status: "Simulated (Awaiting CPOE validation schema)"

  - id: "IND-057"
    indicator_number: 57
    code: "MOM-3.1"
    standard_no: 11
    standard_name: "Management of Medication (MOM)"
    name: "High-Risk / LASA Medication Independent Double-Verification"
    short_name: "High-Risk Order Verification"
    ingestion_mode: "Automatic"
    hims_source: "HIMS eMAR -> high_alert_double_sign_view"
    schedule_cron: "*/15 * * * *"
    owner_role: "Chief Pharmacist & Nursing Superintendent"
    owner_name: "Dr. Usman Farooq / Matron Samina Bibi"
    unit: "%"
    rule_type: "zero_tolerance_pct"
    direction: "higher_is_better"
    full_threshold: 100.0
    numerator_label: "High-alert medication administrations with 2-clinician eMAR sign-off"
    denominator_label: "Total high-alert/LASA medication administrations"
    hims_mapping_status: "Simulated (Awaiting eMAR dual-auth field mapping)"

  - id: "IND-060"
    indicator_number: 60
    code: "MOM-4.2"
    standard_no: 12
    standard_name: "Management of Medication (MOM)"
    name: "Expired Stock Zero-Tolerance Surveillance (Wards & Crash Carts)"
    short_name: "Expired Stock Units"
    ingestion_mode: "Imported"
    hims_source: "Pharmacy Barcode Audit -> ward_stock_expiry_export"
    schedule_cron: "0 7 * * *"
    owner_role: "Inventory & Pharmacy Store Manager"
    owner_name: "Rizwan Ahmed (Pharmacy Inventory Lead)"
    unit: "defects"
    rule_type: "zero_tolerance_defects"
    direction: "lower_is_better"
    max_defects_allowed: 0
    numerator_label: "Expired medication units found in active ward/crash-cart stock"
    denominator_label: "Total medication stock units scanned across wards & ER"
    hims_mapping_status: "Simulated (Daily Pharmacy ERP Batch Export)"

  - id: "IND-061"
    indicator_number: 61
    code: "MOM-4.3"
    standard_no: 12
    standard_name: "Management of Medication (MOM)"
    name: "Dispensed Medication & Multi-Dose Vial Labelling Compliance"
    short_name: "Medication Labelling"
    ingestion_mode: "Manual"
    hims_source: "Ward Pharmacy Inspection Sheet (Pending Barcode Integration)"
    schedule_cron: "0 12 * * *"
    owner_role: "Inpatient Pharmacy Supervisor"
    owner_name: "Dr. Hina Zahid (Inpatient Pharmacy)"
    unit: "defects"
    rule_type: "zero_tolerance_defects"
    direction: "lower_is_better"
    max_defects_allowed: 0
    numerator_label: "Unlabelled or incompletely labelled vials/syringes/dispensed packs"
    denominator_label: "Total dispensed units & open multi-dose vials inspected"
    hims_mapping_status: "Manual Entry (Pending Zebra Barcode Printer HIMS Link)"

  - id: "IND-099"
    indicator_number: 99
    code: "CQI-2.1"
    standard_no: 17
    standard_name: "Continuous Quality Improvement - Standard 17 (CQI-2)"
    name: "Patient Initial Assessment Completion Within Defined Timeframe"
    short_name: "CQI: Patient Assessment"
    ingestion_mode: "Automatic"
    hims_source: "HIMS ADT & Triage -> initial_assessment_sla_view"
    schedule_cron: "*/30 * * * *"
    owner_role: "Director Emergency & Inpatient Nursing"
    owner_name: "Dr. Salman Majeed (Head of Emergency)"
    unit: "%"
    rule_type: "dual_urgency_tat"
    direction: "higher_is_better"
    emergency_target_pct: 100.0
    routine_full_pct: 95.0
    routine_partial_pct: 90.0
    numerator_label: "Admissions with complete nursing & medical assessment within SLA"
    denominator_label: "Total ER Triage + Inpatient Ward Admissions"
    hims_mapping_status: "Simulated (Awaiting HIMS ADT timestamp mapping)"

  - id: "IND-100"
    indicator_number: 100
    code: "CQI-2.2"
    standard_no: 17
    standard_name: "Continuous Quality Improvement - Standard 17 (CQI-2)"
    name: "Diagnostic Quality Control (Lab & Radiology Daily IQC/EQAS Pass Rate)"
    short_name: "CQI: Diagnostic QC"
    ingestion_mode: "Automatic"
    hims_source: "HIMS LIS/RIS Analyzer QC -> daily_iqc_eqas_view"
    schedule_cron: "0 8 * * *"
    owner_role: "Diagnostic Quality Officer"
    owner_name: "Dr. Ayesha Siddiqa (Diagnostic QA)"
    unit: "%"
    rule_type: "standard_pct"
    direction: "higher_is_better"
    full_threshold: 95.0
    partial_threshold: 85.0
    numerator_label: "Analyzer QC runs passing Westgard 1-2s/2-2s rules prior to clinical release"
    denominator_label: "Total scheduled daily Lab & Radiology QC calibration runs"
    hims_mapping_status: "Simulated (Awaiting Cobas/ Abbott LIS middleware feed)"

  - id: "IND-101"
    indicator_number: 101
    code: "CQI-2.3"
    standard_no: 17
    standard_name: "Continuous Quality Improvement - Standard 17 (CQI-2)"
    name: "Invasive Procedures WHO Safety Checklist & Consent Verification"
    short_name: "CQI: Invasive Procedures"
    ingestion_mode: "Automatic"
    hims_source: "HIMS OT Module -> surgical_safety_verification_view"
    schedule_cron: "0 * * * *"
    owner_role: "Chair Department of Surgery & OT Manager"
    owner_name: "Prof. Dr. Farhan Qureshi (Chair Surgery)"
    unit: "%"
    rule_type: "standard_pct"
    direction: "higher_is_better"
    full_threshold: 95.0
    partial_threshold: 85.0
    numerator_label: "Invasive procedures with complete Sign-In, Time-Out, Sign-Out & Consent"
    denominator_label: "Total major & minor invasive procedures performed"
    hims_mapping_status: "Simulated (Awaiting HIMS OT checklist table mapping)"

  - id: "IND-102"
    indicator_number: 102
    code: "CQI-2.4"
    standard_no: 17
    standard_name: "Continuous Quality Improvement - Standard 17 (CQI-2)"
    name: "Adverse Drug Events (ADE) & Medication Error Rate per 1,000 Orders"
    short_name: "CQI: Adverse Drug Events"
    ingestion_mode: "Automatic"
    hims_source: "HIMS Pharmacovigilance -> ade_incident_rate_view"
    schedule_cron: "0 6 * * *"
    owner_role: "Pharmacovigilance & CQI Officer"
    owner_name: "Dr. Usman Farooq (Chief Pharmacist)"
    unit: "per 1,000"
    rule_type: "rate_upper_bound"
    direction: "lower_is_better"
    full_threshold: 2.0
    partial_threshold: 4.0
    scale_factor: 1000.0
    numerator_label: "Confirmed preventable ADEs and intercepted/actual medication errors"
    denominator_label: "Total inpatient medication orders dispensed (scaled per 1,000)"
    hims_mapping_status: "Simulated (Awaiting HIMS Incident & eMAR trigger feed)"

  - id: "IND-103"
    indicator_number: 103
    code: "CQI-2.5"
    standard_no: 17
    standard_name: "Continuous Quality Improvement - Standard 17 (CQI-2)"
    name: "Anaesthesia Pre-Op Evaluation, Intra-Op Monitoring & Recovery Compliance"
    short_name: "CQI: Anaesthesia Safety"
    ingestion_mode: "Imported"
    hims_source: "OT Anaesthesia Registry -> anaesthesia_monitoring_csv"
    schedule_cron: "0 20 * * *"
    owner_role: "Head of Anaesthesiology & Pain Medicine"
    owner_name: "Dr. Zafar Iqbal (HOD Anaesthesia)"
    unit: "%"
    rule_type: "standard_pct"
    direction: "higher_is_better"
    full_threshold: 95.0
    partial_threshold: 85.0
    numerator_label: "Surgical cases with complete pre-op ASA, intra-op vitals & Aldrete score"
    denominator_label: "Total surgical procedures under General, Regional or Sedation anaesthesia"
    hims_mapping_status: "Simulated (Daily CSV import from OT Anaesthesia Log)"

  - id: "IND-104"
    indicator_number: 104
    code: "CQI-2.6"
    standard_no: 17
    standard_name: "Continuous Quality Improvement - Standard 17 (CQI-2)"
    name: "Blood & Blood Products Transfusion Safety & Reaction Surveillance"
    short_name: "CQI: Blood Transfusion QC"
    ingestion_mode: "Automatic"
    hims_source: "HIMS Blood Bank IS -> haemovigilance_compliance_view"
    schedule_cron: "*/30 * * * *"
    owner_role: "Blood Bank In-Charge & Haematologist"
    owner_name: "Dr. Rabia Waheed (Haematology Lead)"
    unit: "%"
    rule_type: "zero_tolerance_pct"
    direction: "higher_is_better"
    full_threshold: 100.0
    numerator_label: "Transfusions with verified cross-match, 15m vitals & zero incompatibility"
    denominator_label: "Total blood and blood component units transfused"
    hims_mapping_status: "Simulated (Awaiting Blood Bank IS HL7 feed)"

  - id: "IND-105"
    indicator_number: 105
    code: "CQI-2.7"
    standard_no: 17
    standard_name: "Continuous Quality Improvement - Standard 17 (CQI-2)"
    name: "Medical Records Completeness, ICD-10 Coding & Timely Discharge Summary"
    short_name: "CQI: Medical Records Audit"
    ingestion_mode: "Automatic"
    hims_source: "HIMS EMR Audit -> mr_completeness_discharge_view"
    schedule_cron: "0 2 * * *"
    owner_role: "Medical Record Officer (MRO) & CQI Lead"
    owner_name: "khalid Mehmood (Chief MRO)"
    unit: "%"
    rule_type: "standard_pct"
    direction: "higher_is_better"
    full_threshold: 95.0
    partial_threshold: 85.0
    numerator_label: "Discharged records with complete ICD-10 code, consent & signed summary <24h"
    denominator_label: "Total inpatient discharged medical records audited"
    hims_mapping_status: "Simulated (Awaiting HIMS EMR Discharge Schema)"

hospital_adapter_profiles:
  - profile_id: "CAMDEN-HIMS-V4"
    name: "Camden Health System HIMS (Direct SQL/HL7 Adapter)"
    db_engine: "PostgreSQL / HL7 v2.5"
    description: "Pre-mapped to Camden HIMS ADT, LIS, RIS, CPOE, eMAR, and OT views."
  - profile_id: "ORACLE-HIS-ENT"
    name: "Enterprise Oracle / SQL Server HIS (Custom View Adapter)"
    db_engine: "Oracle 19c / MS SQL Server"
    description: "Uses read-only SQL translator views mapped to Universal KPI Contract."
  - profile_id: "HYBRID-CSV-TALLY"
    name: "Hybrid Standalone LIS/Pharmacy CSV + Ward Tablet Micro-Tally"
    db_engine: "CSV Drop-Folder + Streamlit Micro-Tally"
    description: "Combines daily CSV exports from Lab/Pharmacy with 30-second ward round tallies."

licence_and_policy_vault:
  - code: "Ind. 7 & 121"
    item: "PNRA Radiation Protection Licence (Radiology)"
    authority: "Pakistan Nuclear Regulatory Authority (PNRA)"
    expiry_date: "2026-11-05"
    days_remaining: 22
    status: "Expiring <30d"
  - code: "Ind. 22"
    item: "PBTA Hospital Blood Bank Licence"
    authority: "Punjab Blood Transfusion Authority (PBTA)"
    expiry_date: "2027-04-15"
    days_remaining: 183
    status: "Valid"
  - code: "Ind. 88"
    item: "Hospital Waste Management (PHWM Rules 2014) MOU"
    authority: "EPA / Specialized Healthcare Dept"
    expiry_date: "2027-01-31"
    days_remaining: 109
    status: "Valid"
  - code: "Ind. 126"
    item: "Rescue 1122 / Civil Defence Fire Safety Certificate"
    authority: "Punjab Emergency Service (Rescue 1122)"
    expiry_date: "2026-11-10"
    days_remaining: 27
    status: "Expiring <30d"
  - code: "Ind. 98"
    item: "Annual CQI Programme Review & Update"
    authority: "Hospital CQI Committee"
    expiry_date: "2027-03-01"
    days_remaining: 138
    status: "Valid"
"""

MONTH_LABELS = [
    "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
    "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"
]

CLINICAL_BUNDLES = {
    "1. Emergency & Admission Bundle": ["IND-099"],
    "2. Diagnostics Speed & QC Bundle": ["IND-004", "IND-005", "IND-011", "IND-100"],
    "3. Safe Surgery, Anaesthesia & IPC Bundle": ["IND-050", "IND-101", "IND-103"],
    "4. Medication & Blood Safety Bundle": ["IND-054", "IND-057", "IND-060", "IND-061", "IND-102", "IND-104"],
    "5. Medical Records & Governance Bundle": ["IND-105"],
}

# Exact sub-KPIs from 2024 PHC MSDS Manual (CG-01MS-Ed2-01092023, pp. 113-118)
STANDARD_17_SUB_KPIS: Dict[str, List[Dict]] = {
    "IND-099": [
        {"code": "99.i.a", "name": "% of OPD & Emergency patients assessed within prescribed timeline", "value": "98.4% (ER: 100%)", "status": "Met"},
        {"code": "99.i.b", "name": "% of Inpatient cases with clinician-countersigned care plan & desired outcome", "value": "96.8%", "status": "Met"},
        {"code": "99.i.c", "name": "% of Inpatient cases screened for nutritional needs (links to Ind. 28)", "value": "95.9%", "status": "Met"},
        {"code": "99.i.d", "name": "% of Inpatient cases with documented nursing care plan", "value": "97.5%", "status": "Met"},
    ],
    "IND-100": [
        {"code": "100.iii.a", "name": "% of reporting errors out of total Lab & Radiology tests", "value": "0.18% (<=0.5% target)", "status": "Met"},
        {"code": "100.iii.b", "name": "% of re-dos / repeat tests & exposures in Lab and Radiology (Ind. 13)", "value": "1.12% (<=2.0% target)", "status": "Met"},
        {"code": "100.iii.c", "name": "% of Histopathology & CT/MRI reports correlating with clinical diagnosis", "value": "98.9%", "status": "Met"},
        {"code": "100.v", "name": "% of Diagnostic employees adhering to OH&S safety/radiation precautions", "value": "99.2%", "status": "Met"},
    ],
    "IND-101": [
        {"code": "101.i.a", "name": "% of unplanned invasive procedures (incl. 24h return to OT / readmission)", "value": "0.43%", "status": "Met"},
        {"code": "101.i.b", "name": "% of rescheduling / cancellation of invasive procedures", "value": "6.52% (>5% watch)", "status": "Breach"},
        {"code": "101.ii", "name": "% of cases practicing wrong-site / wrong-patient / WHO Time-Out SOPs (Ind. 44)", "value": "100.0%", "status": "Met"},
        {"code": "101.iii", "name": "% of surgical cases receiving prophylactic antibiotics within timeframe", "value": "93.5% (<95% target)", "status": "Breach"},
    ],
    "IND-102": [
        {"code": "102.i.a-c", "name": "Prescribing (18), Dispensing (11) & Administration (9) medication errors", "value": "38 / 23,000 (1.65/1k)", "status": "Met"},
        {"code": "102.ii", "name": "Number of confirmed Adverse Drug Reactions (ADRs) analyzed", "value": "6 cases (100% reviewed)", "status": "Met"},
        {"code": "102.iii", "name": "Number of medication charts with error-prone abbreviations", "value": "4 charts (0.2%)", "status": "Met"},
        {"code": "102.iv", "name": "Patients receiving high-risk medications developing ADRs", "value": "1 case (investigated)", "status": "Met"},
    ],
    "IND-103": [
        {"code": "103.I.a", "name": "% of modification of anaesthesia plan (pre-op vs pre-induction Ind. 34)", "value": "1.3%", "status": "Met"},
        {"code": "103.I.b", "name": "% of unplanned ventilation following anaesthesia", "value": "0.13%", "status": "Met"},
        {"code": "103.I.c", "name": "% of adverse anaesthesia events (Ind. 40)", "value": "0.26%", "status": "Met"},
        {"code": "103.I.d", "name": "Anaesthesia-related mortality rate", "value": "0.0%", "status": "Met"},
    ],
    "IND-104": [
        {"code": "104.I.a", "name": "% of transfusion reactions analyzed & reported to PBTA (Ind. 25)", "value": "0.15% (100% PBTA notified)", "status": "Met"},
        {"code": "104.I.b", "name": "% of wastage of blood and blood products", "value": "1.4% (<=2% target)", "status": "Met"},
        {"code": "104.I.c", "name": "% of rational blood component usage (RCC/FFP/Platelets vs Whole Blood)", "value": "99.1%", "status": "Met"},
        {"code": "104.I.d", "name": "Turnaround time (TAT) compliance for blood product issuance (ER <=15m)", "value": "100.0%", "status": "Met"},
    ],
    "IND-105": [
        {"code": "105.i", "name": "% of medical records missing signed 6-part discharge summary (Ind. 152)", "value": "11.2% missing (>5% breach)", "status": "Breach"},
        {"code": "105.ii", "name": "% of medical records lacking single unique identifier (Ind. 144)", "value": "0.0% missing", "status": "Met"},
        {"code": "105.iii", "name": "% of records missing procedures, vitals, or shift progress notes (Ind. 146)", "value": "5.4% missing", "status": "Breach"},
        {"code": "105.iv", "name": "% of records with incomplete/improper general or informed consent (Ind. 72-74)", "value": "2.1% incomplete", "status": "Breach"},
        {"code": "105.v", "name": "% of requested medical records that could not be produced (Ind. 155)", "value": "0.0%", "status": "Met"},
        {"code": "105.vi-vii", "name": "Mortality chart review & ICD-10 codification completeness", "value": "83.4% (<95% target)", "status": "Breach"},
    ],
}

ADAPTER_SQL_TEMPLATES: Dict[str, str] = {
    "Camden Health System HIMS (PostgreSQL / HL7 Adapter)": """-- Camden HIMS Read-Only Translator View -> Universal KPI Contract
SELECT
    CURRENT_DATE AS period_date,
    'IND-004' AS indicator_id,
    COUNT(*) FILTER (WHERE is_within_tat = TRUE) AS numerator,
    COUNT(*) AS denominator,
    COUNT(*) FILTER (WHERE priority = 'STAT_ER' AND tat_minutes <= 60) AS emergency_num,
    COUNT(*) FILTER (WHERE priority = 'STAT_ER') AS emergency_den,
    COUNT(*) FILTER (WHERE priority = 'ROUTINE' AND tat_minutes <= 240) AS routine_num,
    COUNT(*) FILTER (WHERE priority = 'ROUTINE') AS routine_den
FROM camden_lis.lab_order_turnaround_v
WHERE verified_at >= CURRENT_DATE - INTERVAL '1 day';""",
    "Enterprise Oracle / SQL Server HIS (Custom View Adapter)": """-- Oracle / MS SQL Server HIS Translator Query -> Universal KPI Contract
SELECT
    CAST(GETDATE() AS DATE) AS period_date,
    'IND-011' AS indicator_id,
    SUM(CASE WHEN report_tat_mins <= sla_mins THEN 1 ELSE 0 END) AS numerator,
    COUNT(study_id) AS denominator,
    SUM(CASE WHEN urgency_code = 'ER' AND report_tat_mins <= 60 THEN 1 ELSE 0 END) AS emergency_num,
    SUM(CASE WHEN urgency_code = 'ER' THEN 1 ELSE 0 END) AS emergency_den
FROM dbo.RIS_RADIOLOGY_STUDIES
WHERE study_status = 'SIGNED' AND study_date >= DATEADD(day, -1, CAST(GETDATE() AS DATE));""",
    "Universal CSV / Excel Drop-Folder Schema": """period_date,indicator_id,numerator,denominator,emergency_num,emergency_den,routine_num,routine_den,segregated_dimensions
2026-10-14,IND-004,14520,14800,3200,3200,11320,11600,"LIS_Auto"
2026-10-14,IND-011,4120,4200,620,620,3500,3580,"RIS_Auto"
2026-10-14,IND-050,11,895,,,,,"Surgeon_ID+Procedure+OT_Room"
2026-10-14,IND-060,0,9400,,,,,"Pharmacy_Barcode_Scan"
2026-10-14,IND-061,0,1250,,,,,"Ward_Micro_Tally"
""",
}

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
        "emergency_num": 610, "emergency_den": 620,
        "routine_num": 3405, "routine_den": 3580,
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
        "numerator": 2, "denominator": 9400,
        "hours_since_last_pull": 3.5,
    },
    "IND-061": {
        "history": [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
        "numerator": 1, "denominator": 1250,
        "hours_since_last_pull": 6.0,
    },
    "IND-099": {
        "history": [96.8, 97.1, 96.9, 97.3, 97.0, 97.4, 97.2, 97.5, 97.1, 97.6, 97.4, 97.8],
        "numerator": 6259, "denominator": 6400,
        "emergency_num": 2900, "emergency_den": 2900,
        "routine_num": 3359, "routine_den": 3500,
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
        "numerator": 38, "denominator": 23000,
        "hours_since_last_pull": 5.0,
    },
    "IND-103": {
        "history": [97.4, 97.6, 97.2, 97.8, 97.5, 97.3, 97.7, 97.4, 97.6, 97.5, 97.2, 97.4],
        "numerator": 740, "denominator": 760,
        "hours_since_last_pull": 28.5,
    },
    "IND-104": {
        "history": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
        "numerator": 645, "denominator": 645,
        "hours_since_last_pull": 0.3,
    },
    "IND-105": {
        "history": [95.8, 95.6, 95.4, 95.5, 95.2, 95.0, 94.1, 92.8, 90.5, 88.4, 86.2, 83.4],
        "numerator": 2585, "denominator": 3100,
        "hours_since_last_pull": 1.5,
    },
}


def get_config_yaml_text(config_path: str = None) -> str:
    candidates = []
    if config_path:
        candidates.append(config_path)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.extend([
        os.path.join(base_dir, "msds_config.yaml"),
        os.path.join(base_dir, "msds_config.yml"),
        "msds_config.yaml",
        "msds_config.yml",
    ])
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass

    target_path = os.path.join(base_dir, "msds_config.yaml")
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_MSDS_CONFIG_YAML)
    except OSError:
        pass
    return DEFAULT_MSDS_CONFIG_YAML


def load_config(config_path: str = None) -> dict:
    raw_yaml = get_config_yaml_text(config_path)
    return yaml.safe_load(raw_yaml)


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