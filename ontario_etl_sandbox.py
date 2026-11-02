"""Synthetic Ontario Public-Dataset ETL, Address/Entity Resolution & Multi-Signal Lead Scoring Demo.

IMPORTANT DISCLOSURE:
This module is a synthetic demonstration created specifically for an Upwork proposal.
It operates on in-memory synthetic fixtures only and is NOT a prior commercial client deployment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STREET_TYPE_MAP = {
    "STREET": "ST",
    "ST": "ST",
    "AVENUE": "AVE",
    "AVE": "AVE",
    "ROAD": "RD",
    "RD": "RD",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "DRIVE": "DR",
    "DR": "DR",
    "COURT": "CRT",
    "CRT": "CRT",
    "CRESCENT": "CRES",
    "CRES": "CRES",
    "HIGHWAY": "HWY",
    "HWY": "HWY",
}

CORP_STOPWORDS = {
    "INC",
    "INCORPORATED",
    "LTD",
    "LIMITED",
    "CORP",
    "CORPORATION",
    "ONTARIO",
    "CANADA",
    "HOLDINGS",
    "HOLDING",
    "PROPERTIES",
    "PROPERTY",
    "DEVELOPMENTS",
    "DEVELOPMENT",
    "GROUP",
    "LP",
    "LLP",
    "ULC",
    "THE",
}


def normalize_postal_code(postal_code: str) -> str:
    """Normalize a Canadian FSA+LDU postal code (e.g. 'm5v-2t6' -> 'M5V2T6')."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", postal_code or "").upper()
    if not re.fullmatch(r"[A-Z]\d[A-Z]\d[A-Z]\d", cleaned):
        raise ValueError(f"Invalid Canadian postal code format: {postal_code!r}")
    return cleaned


def normalize_ontario_address(raw_address: str, postal_code: str, municipality: str = "TORONTO") -> str:
    """Create a deterministic Ontario address_resolution_key from civic address + postal code.

    Handles suite/unit prefixes ('Suite 400, 120 Adelaide St. W.' or '400-120 Adelaide Street West')
    and standardizes street suffixes and directionals.
    """
    fsaldu = normalize_postal_code(postal_code)
    muni = re.sub(r"[^A-Z0-9]", "", (municipality or "ONTARIO").upper())
    text = (raw_address or "").upper().replace(",", " ").replace(".", " ")

    unit = ""
    unit_match = re.search(r"\b(?:SUITE|STE|UNIT|APT|#)\s*([A-Z0-9]+)\b", text)
    if unit_match:
        unit = unit_match.group(1)
        text = text[:unit_match.start()] + " " + text[unit_match.end():]
    else:
        hyph = re.match(r"^\s*([A-Z0-9]+)\s*-\s*(\d+\b.*)$", text)
        if hyph:
            unit = hyph.group(1)
            text = hyph.group(2)

    tokens = [t for t in re.findall(r"[A-Z0-9]+", text) if t]
    if not tokens or not tokens[0].isdigit():
        raise ValueError(f"Missing civic street number in address: {raw_address!r}")

    street_num = tokens[0]
    norm_tokens: list[str] = []
    for tok in tokens[1:]:
        norm_tokens.append(STREET_TYPE_MAP.get(tok, tok))

    street_body = "_".join(norm_tokens)
    return f"ON|{muni}|{fsaldu}|{street_num}|{street_body}|U:{unit or 'NONE'}"


def normalize_corporate_entity(legal_name: str) -> str:
    """Produce a deterministic entity_resolution_key for Corporations Canada / docket matching."""
    tokens = [t for t in re.findall(r"[A-Z0-9]+", (legal_name or "").upper()) if t not in CORP_STOPWORDS]
    if not tokens:
        raise ValueError(f"Empty corporate entity name after normalization: {legal_name!r}")
    return "ENT|" + "_".join(tokens)


@dataclass
class ScoredLeadCohort:
    address_key: str
    entity_key: str
    property_class: str
    total_score: int
    cohort_tier: str
    signals: list[str] = field(default_factory=list)
    source_record_ids: list[str] = field(default_factory=list)


def stitch_and_score_property_signals(
    permits: list[dict[str, Any]],
    corporations: list[dict[str, Any]],
    court_dockets: list[dict[str, Any]],
    cmhc_zone_factors: dict[str, float] | None = None,
) -> list[ScoredLeadCohort]:
    """Stitch municipal permits, Corporations Canada filings, and court dockets into scored lead cohorts."""
    cmhc_zone_factors = cmhc_zone_factors or {}

    corp_by_entity: dict[str, dict[str, Any]] = {}
    for c in corporations:
        ekey = normalize_corporate_entity(c["legal_name"])
        corp_by_entity[ekey] = c

    docket_by_entity: dict[str, list[dict[str, Any]]] = {}
    docket_by_address: dict[str, list[dict[str, Any]]] = {}
    for d in court_dockets:
        if d.get("respondent_name"):
            ekey = normalize_corporate_entity(d["respondent_name"])
            docket_by_entity.setdefault(ekey, []).append(d)
        if d.get("raw_address") and d.get("postal_code"):
            akey = normalize_ontario_address(d["raw_address"], d["postal_code"], d.get("municipality", "TORONTO"))
            docket_by_address.setdefault(akey, []).append(d)

    cohorts: list[ScoredLeadCohort] = []
    for p in permits:
        akey = normalize_ontario_address(p["raw_address"], p["postal_code"], p.get("municipality", "TORONTO"))
        ekey = normalize_corporate_entity(p["applicant_entity"])
        prop_class = (p.get("property_class") or "RESIDENTIAL").upper()

        score = 0
        signals: list[str] = []
        sources: list[str] = [str(p["permit_id"])]

        est_val = float(p.get("estimated_cost_cad", 0.0))
        if est_val >= 1_000_000:
            score += 45
            signals.append("major_capex_permit_1m_plus")
        elif est_val >= 250_000:
            score += 30
            signals.append("mid_capex_permit_250k_plus")

        corp = corp_by_entity.get(ekey)
        if corp:
            sources.append(str(corp["corp_id"]))
            if corp.get("status", "").upper() == "ACTIVE":
                score += 20
                signals.append("active_corporations_canada_match")
            if int(corp.get("recent_director_change_days", 999)) <= 180:
                score += 15
                signals.append("recent_director_or_share_amendment")

        matched_dockets = docket_by_entity.get(ekey, []) + docket_by_address.get(akey, [])
        seen_docket_ids: set[str] = set()
        for doc in matched_dockets:
            did = str(doc["docket_id"])
            if did in seen_docket_ids:
                continue
            seen_docket_ids.add(did)
            sources.append(did)
            dtype = (doc.get("docket_type") or "").upper()
            if dtype in ("CONSTRUCTION_LIEN", "MORTGAGE_ENFORCEMENT", "REFINANCE_DISPUTE"):
                score += 30
                signals.append(f"docket_signal:{dtype.lower()}")

        fsa = normalize_postal_code(p["postal_code"])[:3]
        if cmhc_zone_factors.get(fsa, 1.0) >= 1.15:
            score += 10
            signals.append(f"cmhc_high_velocity_fsa:{fsa}")

        if score >= 70:
            tier = f"HIGH_INTENT_{prop_class}"
        elif score >= 40:
            tier = f"MEDIUM_INTENT_{prop_class}"
        else:
            tier = "WATCHLIST"

        cohorts.append(
            ScoredLeadCohort(
                address_key=akey,
                entity_key=ekey,
                property_class=prop_class,
                total_score=score,
                cohort_tier=tier,
                signals=signals,
                source_record_ids=sources,
            )
        )

    cohorts.sort(key=lambda c: c.total_score, reverse=True)
    return cohorts
