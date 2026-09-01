"""
Normalize raw SBIR API records into the shape expected by load.py.

The SBIR API field names are mostly consistent but occasionally differ across
agency-specific responses. This module centralises all the mapping so the rest
of the pipeline never touches raw field names.
"""

import hashlib
import re
from typing import Any


# Map from API field names → our canonical column names.
# Order matters: first matching key wins for aliases.
_FIELD_MAP: dict[str, list[str]] = {
    # canonical name → [api field, csv column, aliases...]
    "firm":                    ["firm", "awardee_name", "company", "Company"],
    "title":                   ["title", "award_title", "Award Title"],
    "abstract":                ["abstract", "description", "Abstract"],
    "program":                 ["program", "Program"],
    "phase":                   ["phase", "Phase"],
    "agency":                  ["agency", "Agency"],
    "branch":                  ["branch", "Branch"],
    "solicitation_id":         ["solicitation_id", "Agency Tracking Number"],
    "solicitation_number":     ["solicitation_number", "solicitation_num", "Solicitation Number"],
    "solicitation_year":       ["solicitation_year", "Solicitation Year"],
    "contract":                ["contract", "Contract"],
    "award_amount":            ["award_amount", "amount", "Award Amount"],
    "duns":                    ["duns", "duns_number", "Duns"],
    "hubzone_owned":           ["hubzone_owned", "HUBZone Owned"],
    "sdb_owned":               ["socially_economically_disadvantaged", "sdb",
                                "Socially and Economically Disadvantaged"],
    "woman_owned":             ["woman_owned", "Women Owned"],
    "number_employees":        ["number_employees", "employee_count", "Number Employees"],
    "address1":                ["address1", "Address1"],
    "address2":                ["address2", "Address2"],
    "city":                    ["city", "City"],
    "state_code":              ["state", "state_code", "State"],
    "zip":                     ["zip", "zipcode", "Zip"],
    "url":                     ["url", "company_url", "Company Website"],
    "poc_name":                ["poc_name", "contact_name", "Contact Name"],
    "poc_phone":               ["poc_phone", "Contact Phone"],
    "poc_email":               ["poc_email", "Contact Email"],
    "pi_name":                 ["pi_name", "principal_investigator", "PI Name"],
    "pi_title":                ["pi_title", "PI Title"],
    "pi_email":                ["pi_email", "PI Email"],
    "ri_name":                 ["ri_name", "research_institution", "RI Name"],
    "award_year":              ["award_year", "year", "Award Year"],
    "award_start_date":        ["award_start_date", "start_date", "Proposal Award Date"],
    "award_end_date":          ["award_end_date", "end_date", "Contract End Date"],
    "keywords":                ["keywords", "Topic Code"],
}


def _first(record: dict, keys: list[str]) -> Any:
    for k in keys:
        v = record.get(k)
        if v is not None and v != "":
            return v
    return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    # Remove excessive whitespace inside the string
    s = re.sub(r"\s+", " ", s)
    return s or None


def _clean_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _clean_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y"):
        return True
    if s in ("0", "false", "no", "n"):
        return False
    return None


def _make_id(record: dict) -> str:
    """Stable, deterministic ID from the award's natural key fields."""
    # Use _FIELD_MAP so CSV column names (e.g. "Contract") are covered alongside API names.
    contract = _clean_str(_first(record, _FIELD_MAP["contract"]))
    if contract and len(contract) > 3:
        return contract

    firm  = _clean_str(_first(record, _FIELD_MAP["firm"])) or ""
    title = _clean_str(_first(record, _FIELD_MAP["title"])) or ""
    year  = str(_clean_int(_first(record, _FIELD_MAP["award_year"])) or "")
    phase = _clean_str(_first(record, _FIELD_MAP["phase"])) or ""
    key   = f"{firm}|{title}|{year}|{phase}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def normalize(raw: dict) -> dict | None:
    """
    Convert a raw SBIR API record to a canonical dict ready for Supabase.

    Returns None if the record lacks both a firm name and a title (unusable).
    """
    firm  = _clean_str(_first(raw, _FIELD_MAP["firm"]))
    title = _clean_str(_first(raw, _FIELD_MAP["title"]))
    if not firm and not title:
        return None

    return {
        "id":                  _make_id(raw),
        "firm":                firm,
        "title":               title,
        "abstract":            _clean_str(_first(raw, _FIELD_MAP["abstract"])),
        "program":             _clean_str(_first(raw, _FIELD_MAP["program"])),
        "phase":               _clean_str(_first(raw, _FIELD_MAP["phase"])),
        "agency":              _clean_str(_first(raw, _FIELD_MAP["agency"])),
        "branch":              _clean_str(_first(raw, _FIELD_MAP["branch"])),
        "solicitation_id":     _clean_str(_first(raw, _FIELD_MAP["solicitation_id"])),
        "solicitation_number": _clean_str(_first(raw, _FIELD_MAP["solicitation_number"])),
        "solicitation_year":   _clean_int(_first(raw, _FIELD_MAP["solicitation_year"])),
        "contract":            _clean_str(_first(raw, _FIELD_MAP["contract"])),
        "award_amount":        _clean_int(_first(raw, _FIELD_MAP["award_amount"])),
        "duns":                _clean_str(_first(raw, _FIELD_MAP["duns"])),
        "hubzone_owned":       _clean_bool(_first(raw, _FIELD_MAP["hubzone_owned"])),
        "sdb_owned":           _clean_bool(_first(raw, _FIELD_MAP["sdb_owned"])),
        "woman_owned":         _clean_bool(_first(raw, _FIELD_MAP["woman_owned"])),
        "number_employees":    _clean_int(_first(raw, _FIELD_MAP["number_employees"])),
        "address1":            _clean_str(_first(raw, _FIELD_MAP["address1"])),
        "address2":            _clean_str(_first(raw, _FIELD_MAP["address2"])),
        "city":                _clean_str(_first(raw, _FIELD_MAP["city"])),
        "state_code":          _clean_str(_first(raw, _FIELD_MAP["state_code"])),
        "zip":                 _clean_str(_first(raw, _FIELD_MAP["zip"])),
        "url":                 _clean_str(_first(raw, _FIELD_MAP["url"])),
        "poc_name":            _clean_str(_first(raw, _FIELD_MAP["poc_name"])),
        "poc_phone":           _clean_str(_first(raw, _FIELD_MAP["poc_phone"])),
        "poc_email":           _clean_str(_first(raw, _FIELD_MAP["poc_email"])),
        "pi_name":             _clean_str(_first(raw, _FIELD_MAP["pi_name"])),
        "pi_title":            _clean_str(_first(raw, _FIELD_MAP["pi_title"])),
        "pi_email":            _clean_str(_first(raw, _FIELD_MAP["pi_email"])),
        "ri_name":             _clean_str(_first(raw, _FIELD_MAP["ri_name"])),
        "award_year":          _clean_int(_first(raw, _FIELD_MAP["award_year"])),
        "award_start_date":    _clean_str(_first(raw, _FIELD_MAP["award_start_date"])),
        "award_end_date":      _clean_str(_first(raw, _FIELD_MAP["award_end_date"])),
        "keywords":            _clean_str(_first(raw, _FIELD_MAP["keywords"])),
    }


def embed_text(award: dict) -> str:
    """
    Build the string that gets embedded for semantic search.

    Concatenates the most semantically rich fields. Absent fields are skipped
    so the embedding reflects only real content.
    """
    parts = []
    if award.get("title"):
        parts.append(f"Title: {award['title']}")
    if award.get("abstract"):
        parts.append(f"Abstract: {award['abstract']}")
    if award.get("keywords"):
        parts.append(f"Keywords: {award['keywords']}")
    if award.get("agency"):
        parts.append(f"Agency: {award['agency']}")
    if award.get("phase"):
        parts.append(f"Phase: {award['phase']}")
    return "\n".join(parts)
