"""Exception category → audit source document mapping.

Single source of truth for compliance/standard references used in workpapers and dashboards.
Keyed by CATEGORIES id (matching fcmr_core/rules/registry.py CATEGORIES).
"""

# Category ID → (display label, audit objective, assertion type, source standard)
CATEGORY_SOURCE_DOCS = [
    (
        "missing_data",
        "Missing Data",
        "Mandatory KYC fields captured",
        "Completeness",
        "RBI KYC",
    ),
    (
        "kyc_format",
        "KYC & Document Format",
        "Customer identity is valid & verifiable",
        "Accuracy",
        "RBI KYC / ICAI",
    ),
    (
        "address_pin",
        "Address & PIN",
        "Address is complete & valid",
        "Completeness",
        "RBI KYC / ICAI",
    ),
    (
        "duplicates",
        "Duplicate Detection",
        "No duplicate / fictitious customers",
        "Existence",
        "NFRA fraud indicators",
    ),
    (
        "identity_grouping",
        "Identity Grouping (UCID + Beneficiary)",
        "Related parties identified",
        "Existence",
        "ICAI / NFRA",
    ),
]


def get_source_doc_for_category(category_id: str) -> dict | None:
    """Lookup source-doc info by category ID.

    Returns: {"label": str, "objective": str, "assertion": str, "standard": str}
    or None if not found.
    """
    for cat_id, label, objective, assertion, standard in CATEGORY_SOURCE_DOCS:
        if cat_id == category_id:
            return {
                "label": label,
                "objective": objective,
                "assertion": assertion,
                "standard": standard,
            }
    return None
