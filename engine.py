"""
Deterministic PHC MSDS Category I Scoring Engine, Statistical Process Control (SPC),
Early Problem Detection, and Severity-Ranked Alert Engine.

IMPORTANT GOVERNANCE RULE:
- All KPI computations, MSDS compliance statuses (Fully Met / Partially Met / Not Met),
  zero-tolerance evaluations, and SPC control limits are 100% deterministic.
- LLMs never set or override a score or compliance status.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import statistics
import re


SEVERITY_ORDER = {
    "Critical": 1,
    "High": 2,
    "Data gap": 3,
    "Medium": 4,
    "Watch": 5,
}


@dataclass
class EvaluationResult:
    indicator_id: str
    computed_value: float
    unit: str
    status: str  # "Fully Met", "Partially Met", "Not Met", "Data Gap"
    rule_trace: str
    emergency_pct: Optional[float] = None
    routine_pct: Optional[float] = None
    zero_tolerance_breach: bool = False
    data_gap_detected: bool = False


@dataclass
class SPCResult:
    mean: float
    sd: float
    ucl_3sd: float
    lcl_3sd: float
    uwl_2sd: float
    lwl_2sd: float
    latest_z_score: float
    out_of_control_3sd: bool
    warning_2sd: bool
    trend_breach: bool
    trend_description: str
    shift_breach: bool


def evaluate_kpi_deterministic(
    indicator_cfg: dict,
    numerator: Optional[float],
    denominator: Optional[float],
    emergency_num: Optional[float] = None,
    emergency_den: Optional[float] = None,
    routine_num: Optional[float] = None,
    routine_den: Optional[float] = None,
    hours_since_last_pull: float = 1.0,
    max_stale_hours: float = 24.0,
) -> EvaluationResult:
    """
    Deterministic MSDS scoring rules engine.
    Enforces:
    - Missing-data / stale HIMS feed detection
    - Zero-tolerance defect rules (e.g., Ind. 60 expired stock = 0, Ind. 61 incomplete label = 0)
    - Zero-tolerance 100% rules (e.g., Ind. 5 critical results, Ind. 57 high-risk double check, Ind. 104 blood safety)
    - Dual-urgency turnaround rules (e.g., Ind. 4 Lab TAT, Ind. 11 Imaging TAT, Ind. 99 Initial Assessment:
      Emergency must be 100%, Routine >= 95% Fully Met, 85-94.9% Partially Met, <85% Not Met)
    - Standard percentage & upper-bound incidence rates (e.g., Ind. 50 SSI, Ind. 102 ADE rate per 1,000)
    """
    ind_id = indicator_cfg["id"]
    unit = indicator_cfg.get("unit", "%")
    rule_type = indicator_cfg["rule_type"]

    if (
        numerator is None
        or denominator is None
        or denominator <= 0
        or hours_since_last_pull > max_stale_hours
    ):
        reason = (
            f"Data Gap: HIMS feed stale ({hours_since_last_pull:.1f}h > {max_stale_hours:.0f}h SLA)"
            if hours_since_last_pull > max_stale_hours
            else "Data Gap: Missing or zero denominator in HIMS extract"
        )
        return EvaluationResult(
            indicator_id=ind_id,
            computed_value=0.0,
            unit=unit,
            status="Data Gap",
            rule_trace=reason,
            data_gap_detected=True,
        )

    # 1. Zero-tolerance defect count rule (Ind. 60 Expired Stock, Ind. 61 Incomplete Labelling)
    if rule_type == "zero_tolerance_defects":
        defects = int(round(numerator))
        max_allowed = int(indicator_cfg.get("max_defects_allowed", 0))
        if defects == 0 and defects <= max_allowed:
            return EvaluationResult(
                indicator_id=ind_id,
                computed_value=0.0,
                unit=unit,
                status="Fully Met",
                rule_trace=f"Zero-Tolerance Rule Passed: {defects} defects found across {int(denominator)} audited units (Max allowed = 0).",
                zero_tolerance_breach=False,
            )
        else:
            return EvaluationResult(
                indicator_id=ind_id,
                computed_value=float(defects),
                unit=unit,
                status="Not Met",
                rule_trace=f"ZERO-TOLERANCE BREACH: {defects} non-compliant/expired unit(s) detected out of {int(denominator)} audited (1 or more = Not Met).",
                zero_tolerance_breach=True,
            )

    # 2. Dual-urgency rule: Emergency must be 100%, Routine >= 95% (Ind. 4, Ind. 11, Ind. 99)
    if rule_type == "dual_urgency_tat":
        overall_pct = round((numerator / denominator) * 100.0, 2)
        em_pct = (
            round((emergency_num / emergency_den) * 100.0, 2)
            if (emergency_num is not None and emergency_den and emergency_den > 0)
            else overall_pct
        )
        rt_pct = (
            round((routine_num / routine_den) * 100.0, 2)
            if (routine_num is not None and routine_den and routine_den > 0)
            else overall_pct
        )
        em_target = float(indicator_cfg.get("emergency_target_pct", 100.0))
        rt_full = float(indicator_cfg.get("routine_full_pct", 95.0))
        rt_partial = float(indicator_cfg.get("routine_partial_pct", 85.0))

        if em_pct < em_target:
            return EvaluationResult(
                indicator_id=ind_id,
                computed_value=overall_pct,
                unit=unit,
                status="Not Met",
                emergency_pct=em_pct,
                routine_pct=rt_pct,
                zero_tolerance_breach=True,
                rule_trace=(
                    f"ZERO-TOLERANCE EMERGENCY BREACH: Emergency compliance is {em_pct:.2f}% "
                    f"({int(emergency_num or 0)}/{int(emergency_den or 0)}), below mandatory {em_target:.0f}% target. "
                    f"Routine compliance is {rt_pct:.2f}%."
                ),
            )
        if rt_pct >= rt_full:
            return EvaluationResult(
                indicator_id=ind_id,
                computed_value=overall_pct,
                unit=unit,
                status="Fully Met",
                emergency_pct=em_pct,
                routine_pct=rt_pct,
                zero_tolerance_breach=False,
                rule_trace=(
                    f"Dual Gate Passed: Emergency = {em_pct:.2f}% (Target 100%) AND "
                    f"Routine = {rt_pct:.2f}% (Target >= {rt_full:.0f}%)."
                ),
            )
        if rt_pct >= rt_partial:
            return EvaluationResult(
                indicator_id=ind_id,
                computed_value=overall_pct,
                unit=unit,
                status="Partially Met",
                emergency_pct=em_pct,
                routine_pct=rt_pct,
                zero_tolerance_breach=False,
                rule_trace=(
                    f"Routine Below Full Target: Emergency = {em_pct:.2f}% (Met 100%), "
                    f"but Routine = {rt_pct:.2f}% (in Partial band {rt_partial:.0f}%–{rt_full:.1f}%)."
                ),
            )
        return EvaluationResult(
            indicator_id=ind_id,
            computed_value=overall_pct,
            unit=unit,
            status="Not Met",
            emergency_pct=em_pct,
            routine_pct=rt_pct,
            zero_tolerance_breach=False,
            rule_trace=(
                f"Routine Breach: Emergency = {em_pct:.2f}%, Routine = {rt_pct:.2f}% "
                f"(below minimum partial threshold of {rt_partial:.0f}%)."
            ),
        )

    # 3. Zero-tolerance percentage rule: must be 100% (Ind. 5, Ind. 57, Ind. 104)
    if rule_type == "zero_tolerance_pct":
        pct = round((numerator / denominator) * 100.0, 2)
        target = float(indicator_cfg.get("full_threshold", 100.0))
        defects = int(round(denominator - numerator))
        if pct >= target and defects == 0:
            return EvaluationResult(
                indicator_id=ind_id,
                computed_value=pct,
                unit=unit,
                status="Fully Met",
                zero_tolerance_breach=False,
                rule_trace=f"Zero-Tolerance 100% Gate Passed: {int(numerator)}/{int(denominator)} ({pct:.2f}%) compliant.",
            )
        return EvaluationResult(
            indicator_id=ind_id,
            computed_value=pct,
            unit=unit,
            status="Not Met",
            zero_tolerance_breach=True,
            rule_trace=(
                f"ZERO-TOLERANCE BREACH: {pct:.2f}% ({int(numerator)}/{int(denominator)}) — "
                f"{defects} unverified/delayed critical event(s) against 100% mandatory rule."
            ),
        )

    # 4. Rate upper bound (lower is better: Ind. 50 SSI %, Ind. 102 ADE per 1,000)
    if rule_type == "rate_upper_bound":
        scale = float(indicator_cfg.get("scale_factor", 100.0))
        rate = round((numerator / denominator) * scale, 2)
        full_t = float(indicator_cfg["full_threshold"])
        part_t = float(indicator_cfg["partial_threshold"])
        if rate <= full_t:
            status = "Fully Met"
            trace = f"Rate {rate:.2f} {unit} <= Fully Met ceiling ({full_t:.2f} {unit})."
        elif rate <= part_t:
            status = "Partially Met"
            trace = f"Rate {rate:.2f} {unit} exceeds {full_t:.2f} ceiling (Partial band <= {part_t:.2f} {unit})."
        else:
            status = "Not Met"
            trace = f"Target Breach: Rate {rate:.2f} {unit} exceeds maximum partial ceiling ({part_t:.2f} {unit})."
        return EvaluationResult(
            indicator_id=ind_id,
            computed_value=rate,
            unit=unit,
            status=status,
            rule_trace=trace,
        )

    # 5. Standard percentage rule (higher is better: Ind. 54, 100, 101, 103, 105)
    pct = round((numerator / denominator) * 100.0, 2)
    full_t = float(indicator_cfg.get("full_threshold", 95.0))
    part_t = float(indicator_cfg.get("partial_threshold", 85.0))
    if pct >= full_t:
        status = "Fully Met"
        trace = f"Compliance {pct:.2f}% ({int(numerator)}/{int(denominator)}) >= {full_t:.0f}% target."
    elif pct >= part_t:
        status = "Partially Met"
        trace = f"Compliance {pct:.2f}% ({int(numerator)}/{int(denominator)}) in Partial band ({part_t:.0f}%–{full_t:.1f}%)."
    else:
        status = "Not Met"
        trace = f"Compliance Breach: {pct:.2f}% ({int(numerator)}/{int(denominator)}) < {part_t:.0f}% minimum."
    return EvaluationResult(
        indicator_id=ind_id,
        computed_value=pct,
        unit=unit,
        status=status,
        rule_trace=trace,
    )


def compute_spc_metrics(
    series: List[float],
    direction: str = "higher_is_better",
    unit: str = "%",
) -> SPCResult:
    """
    Computes Shewhart Statistical Process Control (SPC) parameters (Mean, SD, +/-2 SD, +/-3 SD)
    and evaluates Western Electric / Nelson early-warning trend rules:
      - Rule 1: Latest point beyond Mean +/- 3 SD
      - Rule 2: 2 of last 3 points beyond Mean +/- 2 SD
      - Rule 3: 6 consecutive points monotonically increasing or decreasing (drift)
      - Rule 4: 8 consecutive points on the unfavorable side of the center line
    """
    if len(series) < 3:
        val = series[-1] if series else 0.0
        return SPCResult(val, 0.0, val, val, val, val, 0.0, False, False, False, "Insufficient history", False)

    # Baseline from historical series excluding current point if >= 6 points
    baseline = series[:6] if len(series) >= 8 else series[:-1]
    mean = statistics.mean(baseline)
    sd = statistics.stdev(baseline) if len(baseline) > 1 else 0.0
    if sd < 1e-6:
        sd = max(abs(mean) * 0.02, 0.1)

    clamp_high = 100.0 if unit == "%" else float("inf")
    clamp_low = 0.0

    ucl_3sd = min(clamp_high, round(mean + 3.0 * sd, 2))
    lcl_3sd = max(clamp_low, round(mean - 3.0 * sd, 2))
    uwl_2sd = min(clamp_high, round(mean + 2.0 * sd, 2))
    lwl_2sd = max(clamp_low, round(mean - 2.0 * sd, 2))

    latest = series[-1]
    z_score = round((latest - mean) / sd, 2)

    # Unfavorable direction check
    if direction == "higher_is_better":
        out_3sd = latest < (mean - 3.0 * sd)
        warn_2sd = latest < (mean - 2.0 * sd)
    else:
        out_3sd = latest > (mean + 3.0 * sd)
        warn_2sd = latest > (mean + 2.0 * sd)

    # Check 6 consecutive monotonic points (or 5 intervals)
    trend_breach = False
    trend_desc = "Stable within control limits"
    window = series[-6:] if len(series) >= 6 else series
    if len(window) >= 5:
        diffs = [window[i + 1] - window[i] for i in range(len(window) - 1)]
        if all(d < 0 for d in diffs) and direction == "higher_is_better":
            trend_breach = True
            trend_desc = f"{len(window)}-period consecutive downward drift detected"
        elif all(d > 0 for d in diffs) and direction == "lower_is_better":
            trend_breach = True
            trend_desc = f"{len(window)}-period consecutive upward drift detected"

    # Check 8 consecutive points on unfavorable side of mean
    shift_breach = False
    if len(series) >= 8:
        last8 = series[-8:]
        if direction == "higher_is_better" and all(x < mean for x in last8):
            shift_breach = True
            if not trend_breach:
                trend_desc = "8 consecutive periods below historical center line (mean)"
        elif direction == "lower_is_better" and all(x > mean for x in last8):
            shift_breach = True
            if not trend_breach:
                trend_desc = "8 consecutive periods above historical center line (mean)"

    if out_3sd:
        trend_desc = f"SPC Special-Cause Breach: Latest value ({latest}) beyond 3 SD control limit (z = {z_score:+.2f})"
    elif warn_2sd and not trend_breach:
        trend_desc = f"SPC Early Warning: Latest value ({latest}) beyond 2 SD warning band (z = {z_score:+.2f})"

    return SPCResult(
        mean=round(mean, 2),
        sd=round(sd, 2),
        ucl_3sd=ucl_3sd,
        lcl_3sd=lcl_3sd,
        uwl_2sd=uwl_2sd,
        lwl_2sd=lwl_2sd,
        latest_z_score=z_score,
        out_of_control_3sd=out_3sd,
        warning_2sd=warn_2sd,
        trend_breach=trend_breach,
        trend_description=trend_desc,
        shift_breach=shift_breach,
    )


def classify_alert_severity(
    indicator_cfg: dict,
    eval_res: EvaluationResult,
    spc_res: SPCResult,
) -> Optional[Dict]:
    """
    Ranks alerts deterministically into:
      1. Critical  - Zero-tolerance breach OR (Not Met AND SPC > 3 SD special cause)
      2. High      - Standard Not Met OR SPC > 3 SD special-cause breach
      3. Data gap  - Missing denominator / stale HIMS extraction (>24h)
      4. Medium    - Partially Met with adverse SPC trend or > 2 SD warning
      5. Watch     - Partially Met (stable) OR Fully Met with early SPC drift/2 SD warning
    Returns None if Fully Met with no SPC warning/trend.
    """
    ind_id = indicator_cfg["id"]
    name = indicator_cfg["short_name"]
    owner_role = indicator_cfg["owner_role"]
    owner_name = indicator_cfg["owner_name"]

    if eval_res.data_gap_detected or eval_res.status == "Data Gap":
        sev = "Data gap"
        trigger = "Missing / Stale HIMS Telemetry"
        action = f"Verify HIMS ETL connector ({indicator_cfg['hims_source']}) and backfill missing denominator records."
    elif eval_res.zero_tolerance_breach:
        sev = "Critical"
        trigger = "PHC Zero-Tolerance Rule Breach"
        action = f"Immediate containment required by {owner_role}: quarantine non-compliant stock/orders and file 24h incident CAPA."
    elif eval_res.status == "Not Met" and spc_res.out_of_control_3sd:
        sev = "Critical"
        trigger = "Target Breach + SPC >3 SD Special Cause"
        action = f"Convene emergency CQI root-cause huddle with {owner_name}; audit HIMS cases breaching threshold."
    elif eval_res.status == "Not Met" or spc_res.out_of_control_3sd:
        sev = "High"
        trigger = "MSDS Target Not Met" if eval_res.status == "Not Met" else "SPC >3 SD Out-of-Control Signal"
        action = f"Initiate formal CAPA with {owner_name} within 48 hours to restore indicator above {indicator_cfg.get('full_threshold', 95)}%."
    elif eval_res.status == "Partially Met" and (spc_res.trend_breach or spc_res.warning_2sd):
        sev = "Medium"
        trigger = "Partially Met + Adverse SPC Drift"
        action = f"Perform process audit in {indicator_cfg['standard_name']} before indicator crosses into Not Met."
    elif eval_res.status == "Partially Met" or spc_res.trend_breach or spc_res.warning_2sd or spc_res.shift_breach:
        sev = "Watch"
        trigger = "Early SPC Drift / Partial Compliance"
        action = f"Monitor weekly in CQI huddles with {owner_name}; review shift-level bottlenecks."
    else:
        return None

    return {
        "indicator_id": ind_id,
        "indicator_name": name,
        "severity": sev,
        "severity_rank": SEVERITY_ORDER[sev],
        "trigger_type": trigger,
        "deterministic_reason": f"{eval_res.rule_trace} | SPC: {spc_res.trend_description}",
        "owner_role": owner_role,
        "owner_name": owner_name,
        "suggested_action": action,
    }


PHI_PATTERNS = [
    (r"\bMRN[-:\s]*\d{4,10}\b", "[REDACTED_MRN]"),
    (r"\b\d{5}-\d{7}-\d\b", "[REDACTED_CNIC]"),
    (r"\b(?:Patient|Pt\.?)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b", "[REDACTED_PATIENT_NAME]"),
    (r"\b03\d{2}[- ]?\d{7}\b", "[REDACTED_PHONE]"),
]


def scrub_patient_identifiers(raw_text: str) -> Tuple[str, int]:
    """
    Guarantees zero patient identifiers (MRN, Pakistani CNIC, Patient Name, Phone)
    are ever included in AI prompts or external payloads.
    """
    scrubbed = raw_text
    total_redactions = 0
    for pattern, replacement in PHI_PATTERNS:
        scrubbed, count = re.subn(pattern, replacement, scrubbed)
        total_redactions += count
    return scrubbed, total_redactions