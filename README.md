# Punjab Healthcare Commission (PHC) MSDS Category-I Continuous Quality Monitoring Dashboard

An automated, data-driven Continuous Quality Improvement (CQI) dashboard engineered specifically for **Category-I Tertiary Hospitals** (30 Standards, 162 Indicators) compliant with Punjab Healthcare Commission standards.

---

## 🏥 Architecture & Scope

### 1. In-Scope Continuous Data-Driven Indicators
Data originates directly from the hospital's HIMS / LIS / RIS / CPOE / EHR:
- **CQI Standard 17 (Continuous Quality Improvement)**:
  - **Ind. 99**: Inpatient Medical Assessment Completion & Timeliness (Target $\ge 95\%$)
  - **Ind. 100**: Diagnostic Quality Control Compliance (Pathology IQC & Radiology QC $\ge 98\%$)
  - **Ind. 101**: WHO Surgical Safety Checklist & Invasive Procedure Safety (Target $100\%$, Fully Met $\ge 98\%$)
  - **Ind. 102**: Adverse Drug Events (ADE) & Medication Errors ($\le 2.0$ per 1,000 pt-days)
  - **Ind. 103**: Anaesthesia Assessment & Complication Surveillance (Target $\ge 98\%$)
  - **Ind. 104**: Blood & Blood Product Utilization and Transfusion Safety (Target $100\%$, Fully Met $\ge 99\%$)
  - **Ind. 105**: Medical Records Completeness & Discharge Summaries within 48h (Target $\ge 95\%$)
- **Other Numeric Operational Indicators**:
  - **Ind. 4 (Emergency)**: Emergency Lab Turnaround Time (**Strict Rule: 100% required for Fully Met**)
  - **Ind. 4 (Routine)**: Routine Lab Turnaround Time (Target $\ge 95\%$ within $\le 4$ hours)
  - **Ind. 5**: Critical Panic Result Reporting & Verbal Read-Back within $\le 15$ mins (Target $100\%$)
  - **Ind. 11**: Radiology & Imaging Turnaround Time (Emergency 100%, Routine $\ge 95\%$)
  - **Ind. 50**: Surgical Site Infection (SSI) Rate ($\le 1.5\%$ benchmark ceiling)
  - **Ind. 54**: Medication Order Quality, Legibility & Completeness (Target $\ge 95\%$)
  - **Ind. 57**: High-Risk / LASA Medication Independent Double Verification (Target $100\%$)
  - **Ind. 60**: Expired Stock on Active Pharmacy & Ward Shelves (**Zero Tolerance: 1 unit = Not Met**)
  - **Ind. 61**: Medication & Dilution Labelling Compliance (**Zero Tolerance: 1 incomplete label = Not Met**)

---

## ⚡ Core Automation Engines

1. **Automated HIMS Ingestion (`core/hims_pipeline.py`)**:
   - Zero manual data entry.
   - Computes Numerators and Denominators for each 24h operational cycle.
   - Marks each indicator as `AUTOMATIC` (⚡ HIMS Query), `IMPORTED` (📥 Batch Audit), or `MANUAL` (✍️ Spot Check).
   - Bundled with a 90-day clinical telemetry generator simulating realistic hospital volume, weekend variation, and edge case alerts.

2. **Deterministic Rules Engine (`core/rules_engine.py`)**:
   - Computes compliance status strictly mathematically: **Fully Met** (2 points), **Partially Met** (1 point), **Not Met** (0 points), or **Data Gap** (0 points).
   - Zero-Tolerance Enforcement: Even 1 expired medication or 1 unlabelled dilution container triggers instant disqualification (`Not Met`).
   - Accreditation Grading:
     - **Grade A+ / Grade A**: $\ge 80\%$ compliance with zero unresolved zero-tolerance breaches.
     - **Grade B**: $65\% - 79.9\%$ compliance.
     - **Grade C / Conditional**: $< 65\%$ or active zero-tolerance violations.

3. **Statistical Process Control (`core/spc_engine.py`)**:
   - Computes Shewhart control charts ($Centerline = Mean, UCL = Mean + 3SD, LCL = Mean - 3SD$).
   - Nelson / Western Electric trend rules:
     - **Rule 1**: 3-Sigma statistical outlier.
     - **Rule 2**: Process Shift (7 consecutive points on one side of mean).
     - **Rule 3**: Adverse Trend (6 consecutive cycles monotonically deteriorating).
     - **Rule 4**: Benchmark Target Breach.
     - **Rule 5**: Missing-data stream / Data Gap.
     - **Rule 6**: 2-Sigma warning zone proximity.

4. **Alert Prioritization Center (`core/alert_engine.py`)**:
   - Ranks alerts strictly into five prioritized tiers:
     1. **Critical** (Zero-tolerance infractions, emergency TAT collapse)
     2. **High** (Target breaches on Core Standard 17, SSI spikes)
     3. **Data gap** (Missing telemetry stream, zero denominator)
     4. **Medium** (SPC 6-cycle trend or 7-cycle shift)
     5. **Watch** (2-Sigma warning threshold approach)
   - Assigns designated clinical owner and evidence-based remediation protocol.

5. **CAPA Tracking & Data-Driven Auto-Closure (`core/capa_engine.py`)**:
   - Multi-tiered escalation: Level 1 (Dept Head) $\to$ Level 2 (CQI Director) $\to$ Level 3 (Executive CEO).
   - **Automated Data Verification**: When the HIMS stream confirms 7 consecutive compliant days, the system automatically transitions the CAPA to `Closed - Verified by Data` with logged telemetry evidence.

6. **Strict Guardrailed AI Assistant (`core/ai_assistant.py`)**:
   - AI **never** computes or alters a score or compliance status.
   - Drafts executive monthly committee narrative citing source metrics for every single observation.
   - Human-in-the-loop: Requires approval and signature before archiving.
   - Privacy-safe: Zero patient identifiers exposed (aggregate metrics only).

---

## 🚀 Running the Dashboard

```bash
# Launch Streamlit server
python -m streamlit run app.py
```
Open your browser to: **`http://localhost:8501`**

### Regression Test Suite
To verify rules, zero-tolerance logic, SPC limits, and database transactions:
```bash
python test_app.py
```
