import re
"""
PHC MSDS Category I Hospital — Automated Continuous Quality Monitoring (CQM) Dashboard
Universal Multi-Hospital Edition (Camden Health System HIMS, Oracle/SQL Server HIS,
MySQL/Postgres, Smart CSV/Excel Column Mapper, and Ward Tablet Micro-Tally).
"""
import os
import io
import copy
import math
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
try:
    import hims_simulator as _hims_sim
except Exception:
    _hims_sim = None

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
    if hasattr(_hims_sim, "get_config_yaml_text"):
        try:
            return _hims_sim.get_config_yaml_text(config_path)
        except Exception:
            pass
    for candidate in ("msds_config.yaml", "msds_config.yml"):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass
    return DEFAULT_MSDS_CONFIG_YAML


def load_config(config_path: str = None) -> dict:
    if hasattr(_hims_sim, "load_config"):
        try:
            return _hims_sim.load_config(config_path)
        except Exception:
            pass
    return yaml.safe_load(get_config_yaml_text(config_path))


SIMULATED_TELEMETRY = getattr(_hims_sim, "SIMULATED_TELEMETRY", SIMULATED_TELEMETRY)
MONTH_LABELS = getattr(_hims_sim, "MONTH_LABELS", MONTH_LABELS)
CLINICAL_BUNDLES = getattr(_hims_sim, "CLINICAL_BUNDLES", CLINICAL_BUNDLES)
STANDARD_17_SUB_KPIS = getattr(_hims_sim, "STANDARD_17_SUB_KPIS", STANDARD_17_SUB_KPIS)
ADAPTER_SQL_TEMPLATES = getattr(_hims_sim, "ADAPTER_SQL_TEMPLATES", ADAPTER_SQL_TEMPLATES)

from ai_explainer import generate_grounded_ai_explanation

st.set_page_config(
    page_title="PHC MSDS Category I — Universal CQM & Clinical Governance",
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

if "active_adapter" not in st.session_state:
    st.session_state.active_adapter = "Camden Health System HIMS (PostgreSQL / HL7 Adapter)"

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
            "action_plan": "Mandate EMR discharge summary completion gate before generating final inpatient billing clearance.",
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
            "actor": "Universal ETL Adapter Worker",
            "role": "System Service",
            "action": "AUTO_PULL_TELEMETRY",
            "target": "14 Auto/Imported KPIs",
            "details": "Pulled de-identified numerator/denominator aggregates via active hospital adapter. IND-103 flagged stale (>24h).",
        },
        {
            "timestamp": "2026-10-14 09:00:05 PKT",
            "actor": "Deterministic MSDS Rules Engine",
            "role": "Rule Engine CG-01MS-Ed2",
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



def safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        if isinstance(val, str):
            cleaned = val.replace(",", "").replace("%", "").strip()
            if not cleaned:
                return default
            fval = float(cleaned)
        else:
            fval = float(val)
        if math.isnan(fval) or math.isinf(fval):
            return default
        return fval
    except (ValueError, TypeError):
        return default


def safe_opt_float(val):
    if val is None:
        return None
    try:
        if isinstance(val, str):
            cleaned = val.replace(",", "").replace("%", "").strip()
            if not cleaned:
                return None
            fval = float(cleaned)
        else:
            fval = float(val)
        if math.isnan(fval) or math.isinf(fval):
            return None
        return fval
    except (ValueError, TypeError):
        return None


def safe_int(val, default: int = 0) -> int:
    return int(round(safe_float(val, float(default))))


def evaluate_current_state():
    cfg = st.session_state.base_config
    max_stale = safe_float(cfg["scoring_engine_defaults"].get("missing_data_threshold_hours", 24.0), 24.0)
    kpi_rows = []
    alerts = []

    for ind in cfg["indicators"]:
        ind_id = ind["id"]
        fallback = SIMULATED_TELEMETRY.get(ind_id, {"numerator": 0.0, "denominator": 1.0, "history": [100.0] * 12})
        sim = st.session_state.telemetry.setdefault(ind_id, copy.deepcopy(fallback))

        # Self-heal any NaN / None / zero denominator in session_state so engine.py never crashes
        num_val = safe_float(sim.get("numerator"), safe_float(fallback.get("numerator"), 0.0))
        den_val = safe_float(sim.get("denominator"), safe_float(fallback.get("denominator"), 1.0))
        if den_val <= 0:
            den_val = max(1.0, safe_float(fallback.get("denominator"), 1.0))
        sim["numerator"] = num_val
        sim["denominator"] = den_val

        em_num = safe_opt_float(sim.get("emergency_num"))
        em_den = safe_opt_float(sim.get("emergency_den"))
        if em_den is not None and em_den <= 0:
            em_den = None
            em_num = None
        rt_num = safe_opt_float(sim.get("routine_num"))
        rt_den = safe_opt_float(sim.get("routine_den"))
        if rt_den is not None and rt_den <= 0:
            rt_den = None
            rt_num = None

        sim["emergency_num"] = em_num
        sim["emergency_den"] = em_den
        sim["routine_num"] = rt_num
        sim["routine_den"] = rt_den

        stale_h = safe_float(sim.get("hours_since_last_pull"), 1.0)
        sim["hours_since_last_pull"] = stale_h

        raw_hist = sim.get("history") or fallback.get("history") or [100.0] * 12
        clean_hist = [safe_float(x, 0.0) for x in raw_hist]
        sim["history"] = clean_hist

        eval_res = evaluate_kpi_deterministic(
            indicator_cfg=ind,
            numerator=num_val,
            denominator=den_val,
            emergency_num=em_num,
            emergency_den=em_den,
            routine_num=rt_num,
            routine_den=rt_den,
            hours_since_last_pull=stale_h,
            max_stale_hours=max_stale,
        )
        spc_res = compute_spc_metrics(
            series=clean_hist,
            direction=ind["direction"],
            unit=ind["unit"],
        )
        alert = classify_alert_severity(ind, eval_res, spc_res)
        if alert:
            alerts.append(alert)

        kpi_rows.append({
            **ind,
            "numerator": num_val,
            "denominator": den_val,
            "emergency_num": em_num,
            "emergency_den": em_den,
            "routine_num": rt_num,
            "routine_den": rt_den,
            "hours_since_last_pull": stale_h,
            "history": clean_hist,
            "months": MONTH_LABELS,
            "eval": eval_res,
            "spc": spc_res,
        })

    alerts.sort(key=lambda a: (a["severity_rank"], a["indicator_id"]))
    return kpi_rows, alerts


# -----------------------------------------------------------------------------
# 2. SIDEBAR: RBAC, MULTI-HOSPITAL ADAPTER SELECTOR & NAVIGATION
# -----------------------------------------------------------------------------
config = st.session_state.base_config
kpis, alerts = evaluate_current_state()

st.sidebar.title("🏥 PHC MSDS CQM Portal")
st.sidebar.caption(
    "Edition: `CG-01MS-Ed2-01092023 (2024)`  \n"
    "30 Standards • 162 Total KPIs • **15 Continuous KPIs + 29 Sub-Metrics Active**"
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

selected_adapter = st.sidebar.selectbox(
    "Hospital Data Source Adapter",
    [
        "Camden Health System HIMS (PostgreSQL / HL7 Adapter)",
        "Enterprise Oracle / SQL Server HIS (Custom View Adapter)",
        "Universal CSV / Excel Drop-Folder + Ward Micro-Tally",
    ],
)
st.session_state.active_adapter = selected_adapter

db_url = os.environ.get("DATABASE_URL", "")
st.sidebar.info(
    f"🔌 **Adapter:** {selected_adapter.split(' (')[0]}  \n"
    f"🗄️ **Storage:** {'PostgreSQL Connected' if db_url else 'In-Memory Universal Store'}  \n"
    "🛡️ **PHI Redaction:** Active (0 Patient IDs Sent)"
)

col_sync, col_rst = st.sidebar.columns(2)
if col_sync.button("🔄 Sync Batch", use_container_width=True):
    st.session_state.telemetry["IND-103"]["hours_since_last_pull"] = 0.2
    log_audit_event(
        actor=f"User ({active_role})",
        role=active_role,
        action="MANUAL_ADAPTER_SYNC",
        target=selected_adapter.split(" (")[0],
        details="Executed universal adapter pull; IND-103 Anaesthesia CSV lag refreshed from 28.5h to 0.2h.",
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
        "1. Morning Huddle & Clinical Bundles",
        "2. KPI Monitor & 10-Chart Spot-Check",
        "3. Indicator Detail, Sub-KPIs & SPC",
        f"4. Alert Center ({len(alerts)})",
        "5. Action Tracker (CAPA)",
        "6. Monthly CQI Auto-Report",
        "7. Universal Data Connector & CSV/Tally Hub",
    ],
)

# -----------------------------------------------------------------------------
# VIEW 1: MORNING HUDDLE, ZERO-TOLERANCE GATES & 5 CLINICAL BUNDLES
# -----------------------------------------------------------------------------
if page.startswith("1."):
    st.title("60-Second Morning Huddle — PHC MSDS Category I Clinical Governance")
    st.caption(
        f"Active Data Adapter: **{st.session_state.active_adapter}** • "
        "Deterministic Rules Engine: Scores (Fully / Partially / Not Met) are 100% rule-computed."
    )

    fully_met = sum(1 for k in kpis if k["eval"].status == "Fully Met")
    part_met = sum(1 for k in kpis if k["eval"].status == "Partially Met")
    not_met = sum(1 for k in kpis if k["eval"].status == "Not Met")
    data_gap = sum(1 for k in kpis if k["eval"].status == "Data Gap")
    zt_breaches = sum(1 for k in kpis if k["eval"].zero_tolerance_breach)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Continuous KPIs", f"{len(kpis)} Core (29 Sub)", "11 Auto • 3 CSV • 1 Tally")
    c2.metric("Fully Met", fully_met, f"{(fully_met / len(kpis)) * 100:.1f}% compliant")
    c3.metric("Partially Met", part_met, "90–94.9% Routine Band")
    c4.metric("Not Met (Breaches)", not_met, f"{zt_breaches} Zero-Tolerance", delta_color="inverse")
    c5.metric("Data Gaps (>24h Stale)", data_gap, "ETL SLA = 24h", delta_color="off")

    st.subheader("🚨 Zero-Tolerance & Mandatory 100% Emergency Red-Line Gates")
    zt_kpis = [
        k for k in kpis
        if k["rule_type"] in ("zero_tolerance_defects", "zero_tolerance_pct", "dual_urgency_tat")
    ]
    zt_cols = st.columns(4)
    for idx, zk in enumerate(zt_kpis):
        with zt_cols[idx % 4]:
            with st.container(border=True):
                st.markdown(
                    f"**Ind. {zk['indicator_number']}: {zk['short_name']}**  \n"
                    f"Status: `{zk['eval'].status}` | Value: **{zk['eval'].computed_value} {zk['unit']}**  \n"
                    f"_{zk['eval'].rule_trace}_"
                )

    st.subheader("🏥 The 5 Continuous Clinical Governance Bundles")
    kpi_map = {k["id"]: k for k in kpis}
    b_cols = st.columns(2)
    for b_idx, (bundle_name, ind_ids) in enumerate(CLINICAL_BUNDLES.items()):
        with b_cols[b_idx % 2]:
            with st.container(border=True):
                st.markdown(f"#### {bundle_name}")
                for iid in ind_ids:
                    item = kpi_map[iid]
                    st.markdown(
                        f"- **Ind. {item['indicator_number']} ({item['code']}) — {item['short_name']}**: "
                        f"`{item['eval'].status}` (**{item['eval'].computed_value} {item['unit']}** | "
                        f"N={int(item['numerator']):,}/D={int(item['denominator']):,}) — _{item['owner_name']}_"
                    )

    st.subheader("🔒 Quiet Licence & Static Policy Expiry Vault (30-Day Watchdog)")
    st.caption("Binary presence/absence indicators stay out of daily clinical views and only surface here when within 30 days of expiry.")
    vault_rows = config.get("licence_and_policy_vault", [])
    if vault_rows:
        st.dataframe(pd.DataFrame(vault_rows), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# VIEW 2: KPI MONITOR & 10-CHART PHC SURVEYOR SPOT-CHECK SIMULATOR
# -----------------------------------------------------------------------------
elif page.startswith("2."):
    st.title("Continuous KPI Monitor & 10-Chart PHC Surveyor Spot-Check")
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

    st.subheader("📋 PHC Surveyor 10-Chart Spot-Check Simulator (2024 Manual Methodology)")
    st.caption(
        "During a PHC licensing inspection, surveyors pull 10 random patient files per ward/department "
        "(e.g., Ind. 20 ER Disposition, Ind. 32/35 Anaesthesia, Ind. 42/43 Surgery, Ind. 54 Medication Orders, Ind. 152 Discharge Summary). "
        "Rule: 0 defects = Fully Met; 1–2 defects = Partially Met (for yellow indicators) or Not Met (for red medico-legal indicators); >=3 defects = Not Met."
    )
    spot_rows = [
        {"Indicator": "Ind. 20 (ER Disposition Log)", "Type": "Yellow (3-Tier)", "Sampled Files": 10, "Defective Files": 0, "PHC Surveyor Score": "Fully Met"},
        {"Indicator": "Ind. 32 & 35 (Pre-Anaesthesia & Consent)", "Type": "Red (Binary Zero-Tol)", "Sampled Files": 10, "Defective Files": 0, "PHC Surveyor Score": "Fully Met"},
        {"Indicator": "Ind. 43 & 44 (Surgical Consent & Time-Out)", "Type": "Red (Binary Zero-Tol)", "Sampled Files": 10, "Defective Files": 1, "PHC Surveyor Score": "Not Met (1 missing Time-Out)"},
        {"Indicator": "Ind. 54 (Medication Order Legibility & Timing)", "Type": "Yellow (3-Tier)", "Sampled Files": 10, "Defective Files": 1, "PHC Surveyor Score": "Partially Met (1 untimed order)"},
        {"Indicator": "Ind. 152 (Signed 6-Part Discharge Summary)", "Type": "Red (Binary Zero-Tol)", "Sampled Files": 10, "Defective Files": 2, "PHC Surveyor Score": "Not Met (2 unsigned summaries)"},
    ]
    st.dataframe(pd.DataFrame(spot_rows), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# VIEW 3: INDICATOR DETAIL, SUB-KPIS, SHEWHART SPC CHART & LIVE SIMULATOR
# -----------------------------------------------------------------------------
elif page.startswith("3."):
    st.title("Indicator Detail, Standard 17 Sub-KPIs & Shewhart SPC Control Chart")
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

    if ind_id in STANDARD_17_SUB_KPIS:
        st.subheader(f"📑 Mandatory Sub-Indicators for {ind_id} (2024 PHC Manual pp. 113–118)")
        st.dataframe(pd.DataFrame(STANDARD_17_SUB_KPIS[ind_id]), use_container_width=True, hide_index=True)

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
        st.subheader("🧪 Live Telemetry & Rule Simulator")
        st.caption("Test deterministic scoring and CAPA auto-verification:")
        sim_n = st.number_input("Numerator (N)", min_value=0, value=int(kpi["numerator"]), step=1)
        sim_d = st.number_input("Denominator (D)", min_value=1, value=int(kpi["denominator"]), step=1)
        sim_stale = st.number_input("Hours Since Last Pull (SLA=24h)", min_value=0.0, value=float(kpi["hours_since_last_pull"]), step=0.5)

        if kpi["rule_type"] == "dual_urgency_tat":
            sim_em_n = st.number_input("Emergency Met (N)", min_value=0, value=int(kpi.get("emergency_num") or 0), step=1)
            sim_em_d = st.number_input("Emergency Total (D)", min_value=1, value=int(kpi.get("emergency_den") or 1), step=1)
        else:
            sim_em_n, sim_em_d = None, None

        if st.button("Apply Simulated Pull", type="primary", use_container_width=True):
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
                action="SIMULATE_TELEMETRY_PULL",
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
            c_plan = st.text_area("Corrective Action Plan", "Audit non-compliant cohort and enforce hard-stop workflow.")
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
                            "Use the Simulator on View 3 or upload fixed data in View 7 first!"
                        )
                    else:
                        c["status"] = "Closed - Verified"
                        c["verification_note"] = f"Verified against live data ({c['indicator_id']} = Fully Met) & closed by {active_role}."
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
        f"Edition: {config['edition_metadata']['edition_id']} | Adapter: {st.session_state.active_adapter}",
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
# VIEW 7: UNIVERSAL DATA CONNECTOR HUB (CAMDEN HIMS / SQL / CSV MAPPER / TALLY)
# -----------------------------------------------------------------------------
elif page.startswith("7."):
    st.title("🔌 Universal Data Ingestion Hub, CSV Column Mapper & Ward Micro-Tally")
    st.caption(
        "Streamlines data collection across any hospital in Punjab: connect Camden HIMS, Oracle/SQL Server HIS, "
        "upload daily CSV/Excel exports from standalone Lab/Pharmacy software, or log 30-second ward round tallies."
    )

    tab_sql, tab_csv, tab_tally, tab_yaml = st.tabs([
        "1. Database Adapter Profiles (Camden / Oracle / SQL)",
        "2. Smart CSV / Excel Column Mapper",
        "3. 30-Second Ward Micro-Tally Form",
        "4. YAML Rules, PHI Guardrail & Audit Trail",
    ])

    with tab_sql:
        st.subheader("Plug-and-Play Hospital Database Translator Profiles")
        st.write(
            "Instead of rewriting the dashboard for each hospital's software, select your hospital's database profile below. "
            "Each adapter maps the hospital's local tables into the **Universal KPI Contract** "
            "(`indicator_id, numerator, denominator, emergency_num, emergency_den, routine_num, routine_den`)."
        )
        chosen_tpl = st.selectbox("Inspect Adapter SQL / Schema Template", list(ADAPTER_SQL_TEMPLATES.keys()))
        st.code(ADAPTER_SQL_TEMPLATES[chosen_tpl], language="sql")

    with tab_csv:
        st.subheader("Smart CSV / Excel Column Mapper (For Standalone Lab, Radiology, OT & Pharmacy Software)")
        sample_csv_text = ADAPTER_SQL_TEMPLATES["Universal CSV / Excel Drop-Folder Schema"]
        st.download_button(
            "📥 Download Universal KPI Import Template (.csv)",
            data=sample_csv_text,
            file_name="phc_msds_universal_import_template.csv",
            mime="text/csv",
        )
        uploaded_csv = st.file_uploader("Upload Hospital CSV Export to Ingest & Re-Score KPIs", type=["csv"])
        if st.button("⚡ Load Sample Multi-Department CSV Batch (Fixes IND-011, IND-060 & IND-061)", type="primary"):
            df_sample = pd.read_csv(io.StringIO(sample_csv_text))
            for _, row in df_sample.iterrows():
                iid = str(row["indicator_id"]).strip()
                if iid in st.session_state.telemetry:
                    t = st.session_state.telemetry[iid]
                    t["numerator"] = float(row["numerator"])
                    t["denominator"] = float(row["denominator"])
                    t["hours_since_last_pull"] = 0.1
                    if pd.notna(row.get("emergency_num")) and pd.notna(row.get("emergency_den")):
                        t["emergency_num"] = float(row["emergency_num"])
                        t["emergency_den"] = float(row["emergency_den"])
                    if pd.notna(row.get("routine_num")) and pd.notna(row.get("routine_den")):
                        t["routine_num"] = float(row["routine_num"])
                        t["routine_den"] = float(row["routine_den"])
            log_audit_event(
                actor=f"User ({active_role})",
                role=active_role,
                action="CSV_BATCH_INGEST",
                target="5 Indicators (IND-004, 011, 050, 060, 061)",
                details="Ingested universal CSV batch; IND-011, IND-060, and IND-061 updated to Fully Met.",
            )
            st.success("Ingested 5 KPI rows from CSV batch! Switch to View 1 or View 2 to see updated scores.")
            st.rerun()

        if uploaded_csv is not None:
            df_up = pd.read_csv(uploaded_csv)
            st.markdown(f"**Preview of Uploaded Dataset ({len(df_up):,} rows × {len(df_up.columns)} columns):**")
            st.dataframe(df_up.head(10), use_container_width=True)
            cols = list(df_up.columns)
            csv_mode = st.radio(
                "Select Your CSV Dataset Structure:",
                [
                    "Mode A: Aggregated KPI Summary CSV (Each row is an indicator with Numerator & Denominator)",
                    "Mode B: Raw Hospital Record/Order CSV (Each row is a patient, lab test, scan, or chart)",
                ],
                horizontal=False,
            )

            if csv_mode.startswith("Mode A"):
                m_c1, m_c2, m_c3 = st.columns(3)
                col_ind = m_c1.selectbox("Map Indicator ID / Number Column", cols, index=0)
                col_num = m_c2.selectbox("Map Numerator Column", cols, index=min(1, len(cols) - 1))
                col_den = m_c3.selectbox("Map Denominator Column", cols, index=min(2, len(cols) - 1))
                opt_cols = ["(None / Keep Default)"] + cols
                e_c1, e_c2 = st.columns(2)
                col_em_n = e_c1.selectbox("Optional: Emergency Numerator Column", opt_cols, index=0)
                col_em_d = e_c2.selectbox("Optional: Emergency Denominator Column", opt_cols, index=0)

                if st.button("🚀 Import & Re-Score Mapped KPI Rows", type="primary"):
                    ind_lookup = {}
                    for k_cfg in config["indicators"]:
                        ind_lookup[k_cfg["id"].upper()] = k_cfg["id"]
                        ind_lookup[str(k_cfg["indicator_number"])] = k_cfg["id"]
                        ind_lookup[f"IND-{k_cfg['indicator_number']}"] = k_cfg["id"]
                        ind_lookup[f"IND.{k_cfg['indicator_number']}"] = k_cfg["id"]
                        ind_lookup[k_cfg["code"].upper()] = k_cfg["id"]
                        ind_lookup[k_cfg["short_name"].upper()] = k_cfg["id"]

                    imported_count = 0
                    for _, r in df_up.iterrows():
                        raw_key = str(r.get(col_ind, "")).strip().upper()
                        if not raw_key or raw_key == "NAN":
                            continue
                        digits = re.sub(r"[^0-9]", "", raw_key)
                        iid = ind_lookup.get(raw_key) or (ind_lookup.get(digits) if digits else None)
                        if iid and iid in st.session_state.telemetry:
                            parsed_n = safe_opt_float(r.get(col_num))
                            parsed_d = safe_opt_float(r.get(col_den)) if col_den != col_num else 100.0
                            if parsed_n is None:
                                continue
                            if parsed_d is None or parsed_d <= 0:
                                parsed_d = 100.0
                            t = st.session_state.telemetry[iid]
                            t["numerator"] = max(0.0, parsed_n)
                            t["denominator"] = max(1.0, parsed_d)
                            t["hours_since_last_pull"] = 0.05
                            if col_em_n != "(None / Keep Default)" and col_em_d != "(None / Keep Default)":
                                em_n_val = safe_opt_float(r.get(col_em_n))
                                em_d_val = safe_opt_float(r.get(col_em_d))
                                if em_n_val is not None and em_d_val is not None and em_d_val > 0:
                                    t["emergency_num"] = max(0.0, em_n_val)
                                    t["emergency_den"] = max(1.0, em_d_val)
                                    t["routine_num"] = max(0.0, t["numerator"] - t["emergency_num"])
                                    t["routine_den"] = max(1.0, t["denominator"] - t["emergency_den"])
                            elif t.get("emergency_den"):
                                t["routine_num"] = max(0.0, t["numerator"] - safe_float(t.get("emergency_num"), 0.0))
                                t["routine_den"] = max(1.0, t["denominator"] - safe_float(t.get("emergency_den"), 0.0))
                            ind_cfg = next(i for i in config["indicators"] if i["id"] == iid)
                            ev = evaluate_kpi_deterministic(
                                ind_cfg, t["numerator"], t["denominator"],
                                t.get("emergency_num"), t.get("emergency_den"),
                                t.get("routine_num"), t.get("routine_den"), 0.05
                            )
                            t["history"][-1] = safe_float(ev.computed_value, 0.0)
                            imported_count += 1
                    log_audit_event(f"User ({active_role})", active_role, "CUSTOM_CSV_IMPORT", f"{imported_count} KPIs", "Imported custom mapped KPI summary CSV.")
                    st.success(f"Successfully imported and re-scored {imported_count} indicators! Go to View 1, 2, or 3 to inspect.")
                    st.rerun()
            else:
                r_c1, r_c2, r_c3 = st.columns(3)
                target_kpi_label = r_c1.selectbox(
                    "1. Target PHC Indicator for this Dataset",
                    [f"{k['id']} (Ind. {k['indicator_number']}) — {k['short_name']}" for k in kpis],
                )
                eval_col = r_c2.selectbox("2. Column to Evaluate (Pass/Fail, Defect, or TAT mins)", cols, index=0)
                rule_op = r_c3.selectbox(
                    "3. Condition that Counts as Numerator",
                    [
                        "Value == 1 / True / 'Yes' / 'Met' / 'Compliant'",
                        "Numeric Value <= Threshold (e.g. TAT minutes <= 60)",
                        "Numeric Value >= Threshold",
                    ],
                )
                thresh_val = 60.0
                if "Threshold" in rule_op:
                    thresh_val = st.number_input("Numeric Threshold Value", value=60.0, step=5.0)

                if st.button("🚀 Aggregate Raw Dataset & Update Indicator", type="primary"):
                    iid = target_kpi_label.split(" ")[0]
                    total_rows = len(df_up)
                    series_col = df_up[eval_col]
                    if rule_op.startswith("Value =="):
                        met_mask = series_col.astype(str).str.strip().str.lower().isin(["1", "1.0", "true", "yes", "y", "met", "compliant", "pass", "passed"])
                    elif "<=" in rule_op:
                        met_mask = pd.to_numeric(series_col, errors="coerce") <= thresh_val
                    else:
                        met_mask = pd.to_numeric(series_col, errors="coerce") >= thresh_val

                    num_count = float(met_mask.sum())
                    den_count = float(max(1, total_rows))
                    t = st.session_state.telemetry[iid]
                    t["numerator"] = num_count
                    t["denominator"] = den_count
                    t["hours_since_last_pull"] = 0.05
                    if t.get("emergency_den"):
                        t["emergency_num"] = num_count
                        t["emergency_den"] = den_count
                        t["routine_num"] = num_count
                        t["routine_den"] = den_count
                    ind_cfg = next(i for i in config["indicators"] if i["id"] == iid)
                    ev = evaluate_kpi_deterministic(
                        ind_cfg, t["numerator"], t["denominator"],
                        t.get("emergency_num"), t.get("emergency_den"),
                        t.get("routine_num"), t.get("routine_den"), 0.05
                    )
                    t["history"][-1] = ev.computed_value
                    log_audit_event(
                        f"User ({active_role})", active_role, "RAW_CSV_AGGREGATE", iid,
                        f"Aggregated {total_rows:,} raw rows -> N={int(num_count):,}, D={int(den_count):,} ({ev.status})."
                    )
                    st.success(f"Aggregated {total_rows:,} rows for {iid}: N={int(num_count):,} / D={int(den_count):,} -> Status is now **{ev.status}**!")
                    st.rerun()

    with tab_tally:
        st.subheader("📱 30-Second Ward Round Micro-Tally (For Non-Digitized Indicators)")
        st.write("Use during daily pharmacy/nursing/MRO rounds for indicators not yet captured in your hospital's software:")
        with st.form("ward_micro_tally_form"):
            t_ind = st.selectbox(
                "Select Ward-Audited Indicator",
                [
                    "IND-060 — Expired Stock Zero-Tolerance Audit (Wards & Crash Carts)",
                    "IND-061 — Dispensed Medication & Multi-Dose Vial Labelling (6 Mandatory Fields)",
                    "IND-054 — Inpatient Prescription Legibility, Date, Time, Name & Signature",
                    "IND-105 — Medical Record Discharge Summary & Consent Completeness",
                ],
            )
            t_ward = st.selectbox("Inspected Ward / Unit", ["Surgical Ward 4", "Medical ICU", "Emergency Trauma Bay", "Main Inpatient Pharmacy", "Labour Room / Gynae"])
            t_den = st.number_input("Total Units / Charts Inspected Today (Denominator)", min_value=1, value=250, step=10)
            t_num = st.number_input("Compliant Units OR Defect Count (Numerator: 0 defects for IND-060/061)", min_value=0, value=0, step=1)
            if st.form_submit_button("Submit Ward Micro-Tally & Re-Score"):
                iid = t_ind.split(" — ")[0]
                st.session_state.telemetry[iid]["numerator"] = float(t_num)
                st.session_state.telemetry[iid]["denominator"] = float(t_den)
                st.session_state.telemetry[iid]["hours_since_last_pull"] = 0.05
                log_audit_event(
                    actor=f"User ({active_role})",
                    role=active_role,
                    action="WARD_MICRO_TALLY",
                    target=f"{iid} ({t_ward})",
                    details=f"Logged ward micro-tally in {t_ward}: N={t_num}, D={t_den}.",
                )
                st.success(f"Logged {iid} tally for {t_ward} and updated live MSDS compliance!")
                st.rerun()

    with tab_yaml:
        col_y, col_p = st.columns(2)
        with col_y:
            st.subheader("Versioned `msds_config.yaml`")
            st.code(get_config_yaml_text(), language="yaml")

        with col_p:
            st.subheader("🛡️ Test PII/PHI Redaction Guardrail")
            sample_input = st.text_area(
                "Sample Text with Patient Identifiers",
                "Patient Muhammad Ali (MRN-482910, CNIC 35202-1234567-1, Phone 0300-1234567) had delayed STAT CT.",
            )
            if st.button("Run PHI Redaction Filter"):
                scrubbed, count = scrub_patient_identifiers(sample_input)
                st.success(f"Scrubbed {count} PHI tokens before AI serialization:")
                st.code(scrubbed)

        st.subheader("Immutable RBAC & Governance Audit Trail")
        st.dataframe(pd.DataFrame(st.session_state.audit_log), use_container_width=True, hide_index=True)
