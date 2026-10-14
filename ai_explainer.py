"""
Privacy-Preserving AI Narrative & Root-Cause Explainer Module.
Enforces:
1. LLM NEVER sets a score or compliance status (reads deterministic output only).
2. Every AI output cites its exact source data (Indicator ID, HIMS view, N/D, SPC Z-score, Rule ID).
3. Strict PII/PHI redaction check before prompt assembly.
4. Mandatory Human-in-the-Loop confirmation state.
"""
import hashlib
from engine import scrub_patient_identifiers


def generate_grounded_ai_explanation(kpi_row: dict) -> dict:
    eval_res = kpi_row["eval"]
    spc_res = kpi_row["spc"]
    ind_id = kpi_row["id"]
    hims_src = kpi_row["hims_source"]
    num = int(kpi_row["numerator"])
    den = int(kpi_row["denominator"])

    citation_tag = (
        f"[Cite: {ind_id} | Source: {hims_src} | Period: 2026-10 | "
        f"N={num:,} / D={den:,} | Deterministic Status: {eval_res.status} | "
        f"SPC Mean={spc_res.mean}, SD={spc_res.sd}, Z={spc_res.latest_z_score:+.2f}]"
    )

    raw_narrative = (
        f"Deterministic Engine Verdict ({eval_res.status}): {eval_res.rule_trace} "
        f"Statistical Process Control analysis across the 12-month baseline (Mean = {spc_res.mean} {kpi_row['unit']}, "
        f"3-SD band = [{spc_res.lcl_3sd}, {spc_res.ucl_3sd}]) indicates: {spc_res.trend_description}. "
        f"Recommended CQI Action for {kpi_row['owner_name']} ({kpi_row['owner_role']}): "
        f"Review de-identified HIMS cohort logs in `{hims_src}` and verify workflow compliance prior to next CQI review. "
        f"{citation_tag}"
    )

    scrubbed_text, redactions = scrub_patient_identifiers(raw_narrative)
    prompt_hash = hashlib.sha256(scrubbed_text.encode("utf-8")).hexdigest()[:16]

    return {
        "indicator_id": ind_id,
        "phi_scrubbed": True,
        "redactions_count": redactions,
        "prompt_hash": f"sha256:{prompt_hash}",
        "citation": citation_tag,
        "narrative_text": scrubbed_text,
        "confirmation_status": "Pending Human Confirmation",
        "governance_notice": "AI narrative is advisory only; score/status is locked by the deterministic MSDS engine.",
    }