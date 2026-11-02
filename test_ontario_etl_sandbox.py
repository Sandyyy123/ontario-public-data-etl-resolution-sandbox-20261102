"""Unit tests for the synthetic Ontario public-dataset ETL & entity-resolution sandbox."""
from __future__ import annotations

import pytest
from ontario_etl_sandbox import (
    normalize_corporate_entity,
    normalize_ontario_address,
    normalize_postal_code,
    stitch_and_score_property_signals,
)


def test_normalize_postal_code_formats_and_validates():
    assert normalize_postal_code("m5v 2t6") == "M5V2T6"
    assert normalize_postal_code("L4K-1B2") == "L4K1B2"
    with pytest.raises(ValueError):
        normalize_postal_code("90210")


def test_address_resolution_unifies_suite_and_hyphen_formats():
    k1 = normalize_ontario_address("Suite 400, 120 Adelaide St. W.", "M5H 1T1", "Toronto")
    k2 = normalize_ontario_address("400-120 Adelaide Street W", "m5h-1t1", "TORONTO")
    assert k1 == k2
    assert k1 == "ON|TORONTO|M5H1T1|120|ADELAIDE_ST_W|U:400"


def test_address_without_unit_sets_none_unit():
    k = normalize_ontario_address("88 Queenston Road", "L8K 1G2", "Hamilton")
    assert k == "ON|HAMILTON|L8K1G2|88|QUEENSTON_RD|U:NONE"


def test_address_missing_civic_number_raises():
    with pytest.raises(ValueError):
        normalize_ontario_address("Adelaide Street West", "M5H 1T1")


def test_corporate_entity_normalization_strips_suffixes_and_punctuation():
    e1 = normalize_corporate_entity("Maple Crest Holdings (Ontario) Inc.")
    e2 = normalize_corporate_entity("THE MAPLE CREST HOLDINGS LIMITED")
    assert e1 == e2
    assert e1 == "ENT|MAPLE_CREST"


def test_stitch_and_score_identifies_high_intent_commercial_cohort():
    permits = [
        {
            "permit_id": "PRM-2026-901",
            "raw_address": "Suite 400, 120 Adelaide St. W.",
            "postal_code": "M5H 1T1",
            "municipality": "Toronto",
            "applicant_entity": "Maple Crest Developments (Ontario) Inc.",
            "property_class": "COMMERCIAL",
            "estimated_cost_cad": 2_400_000,
        }
    ]
    corporations = [
        {
            "corp_id": "CC-884120",
            "legal_name": "Maple Crest Developments Ltd.",
            "status": "ACTIVE",
            "recent_director_change_days": 45,
        }
    ]
    dockets = [
        {
            "docket_id": "ONSC-2026-114",
            "respondent_name": "THE MAPLE CREST DEVELOPMENTS INC",
            "docket_type": "CONSTRUCTION_LIEN",
        }
    ]
    cohorts = stitch_and_score_property_signals(
        permits, corporations, dockets, cmhc_zone_factors={"M5H": 1.22}
    )
    assert len(cohorts) == 1
    top = cohorts[0]
    assert top.cohort_tier == "HIGH_INTENT_COMMERCIAL"
    assert top.total_score == 45 + 20 + 15 + 30 + 10
    assert set(top.source_record_ids) == {"PRM-2026-901", "CC-884120", "ONSC-2026-114"}


def test_stitch_and_score_matches_docket_by_address_when_entity_differs():
    permits = [
        {
            "permit_id": "PRM-2026-902",
            "raw_address": "14-550 Hurontario St",
            "postal_code": "L5G 3H7",
            "municipality": "Mississauga",
            "applicant_entity": "Lakeview Custom Homes Inc.",
            "property_class": "RESIDENTIAL",
            "estimated_cost_cad": 450_000,
        }
    ]
    dockets = [
        {
            "docket_id": "ONSC-2026-219",
            "raw_address": "Unit 14, 550 Hurontario Street",
            "postal_code": "l5g-3h7",
            "municipality": "MISSISSAUGA",
            "docket_type": "REFINANCE_DISPUTE",
        }
    ]
    cohorts = stitch_and_score_property_signals(permits, [], dockets, cmhc_zone_factors={"L5G": 1.18})
    assert len(cohorts) == 1
    assert cohorts[0].cohort_tier == "HIGH_INTENT_RESIDENTIAL"
    assert cohorts[0].total_score == 30 + 30 + 10


def test_low_signal_permit_falls_into_watchlist():
    permits = [
        {
            "permit_id": "PRM-2026-903",
            "raw_address": "22 Elm Ave",
            "postal_code": "K1P 5G4",
            "municipality": "Ottawa",
            "applicant_entity": "Jane Doe Homeowner",
            "property_class": "RESIDENTIAL",
            "estimated_cost_cad": 45_000,
        }
    ]
    cohorts = stitch_and_score_property_signals(permits, [], [])
    assert cohorts[0].cohort_tier == "WATCHLIST"
    assert cohorts[0].total_score == 0
