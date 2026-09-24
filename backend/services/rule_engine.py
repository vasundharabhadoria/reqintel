from collections import defaultdict

from core.supabase import supabase


POSITIVE_CATEGORIES = {
    "actor",
    "action",
}


def _finding(
    rule_name,
    passed,
    description,
    why_it_matters,
    recommendation,
    severity=None,
    category=None,
    rules=None,
):
    return {
        "rule_name": rule_name,
        "passed": passed,
        "message": description,
        "severity": severity,
        "description": description,
        "why_it_matters": why_it_matters,
        "recommendation": recommendation,
        "category": category,
        "rules": rules or [],
    }


def _load_active_rules():
    """
    Load active rules configured through the Master Module.

    Returns active rules together with their category names.
    """

    try:
        rules_response = (
            supabase.from_("master_rules")
            .select(
                """
                id,
                category_id,
                rule,
                description,
                why_it_matters,
                recommendation,
                rule_type,
                severity,
                is_active
                """
            )
            .eq("is_active", True)
            .execute()
        )

        rules = rules_response.data or []

        if not rules:
            return []

        category_ids = list(
            {
                rule["category_id"]
                for rule in rules
                if rule.get("category_id")
            }
        )

        if not category_ids:
            return rules

        categories_response = (
            supabase.from_("rule_categories")
            .select(
                "id, name, description, is_active"
            )
            .in_("id", category_ids)
            .execute()
        )

        categories = categories_response.data or []

        category_map = {
            category["id"]: category
            for category in categories
        }

        enriched_rules = []

        for rule in rules:
            category = category_map.get(
                rule.get("category_id")
            )

            enriched_rule = {
                **rule,
                "category_name": (
                    category.get("name")
                    if category
                    else "Other"
                ),
                "category_description": (
                    category.get("description")
                    if category
                    else ""
                ),
            }

            enriched_rules.append(
                enriched_rule
            )

        return enriched_rules

    except Exception as exc:
        print(
            "RULE ENGINE MASTER RULE LOAD ERROR:",
            repr(exc),
        )

        return []


def _matches_keyword(lower_text, rule):
    """
    Keyword rule.

    Checks whether the configured keyword or phrase
    occurs in the requirement text.
    """

    rule_text = (
        rule.get("rule") or ""
    ).strip().lower()

    if not rule_text:
        return False

    return rule_text in lower_text


def _matches_pattern(lower_text, rule):
    """
    Pattern rule.

    Checks whether the configured pattern occurs
    in the requirement text.
    """

    pattern = (
        rule.get("rule") or ""
    ).strip().lower()

    if not pattern:
        return False

    return pattern in lower_text


def _matches_presence(lower_text, rule):
    """
    Presence rule.

    Checks whether the configured value is present
    in the requirement text.
    """

    value = (
        rule.get("rule") or ""
    ).strip().lower()

    if not value:
        return False

    return value in lower_text


def _rule_matches(lower_text, rule):
    rule_type = (
        rule.get("rule_type") or "Keyword"
    ).strip().lower()

    if rule_type == "keyword":
        return _matches_keyword(
            lower_text,
            rule,
        )

    if rule_type == "pattern":
        return _matches_pattern(
            lower_text,
            rule,
        )

    if rule_type == "presence":
        return _matches_presence(
            lower_text,
            rule,
        )

    return False


def _build_matched_rule(rule):
    """
    Convert a Master Module rule into the compact
    rule information shown inside a category finding.
    """

    rule_name = (
        rule.get("rule")
        or "Unnamed Rule"
    )

    return {
        "id": rule.get("id"),
        "rule": rule_name,
        "rule_type": (
            rule.get("rule_type")
            or "Keyword"
        ),
        "severity": (
            rule.get("severity")
            or "Medium"
        ),
        "description": (
            rule.get("description")
            or "The configured rule was detected."
        ),
        "why_it_matters": (
            rule.get("why_it_matters")
            or "This rule helps improve requirement quality."
        ),
        "recommendation": (
            rule.get("recommendation")
            or "Review the requirement according to this rule."
        ),
    }


def _build_category_finding(
    category_name,
    category_description,
    matched_rules,
):
    """
    Build one finding for a category.

    Instead of creating:
        quickly
        easily
        appropriately

    as separate findings, this creates:

        Ambiguous
            -> quickly
    """

    category_key = (
        category_name or "Other"
    ).strip().lower()

    is_positive_category = (
        category_key in POSITIVE_CATEGORIES
    )

    rule_names = [
        rule["rule"]
        for rule in matched_rules
    ]

    if is_positive_category:

        if len(rule_names) == 1:
            description = (
                f"The requirement contains "
                f"the expected {category_key} "
                f"'{rule_names[0]}'."
            )
        else:
            description = (
                f"The requirement contains "
                f"the expected {category_key} "
                f"terms: {', '.join(rule_names)}."
            )

        recommendation = (
            "No action is required."
        )

        passed = True

    else:

        if len(rule_names) == 1:
            description = (
                f"The requirement matches "
                f"the {category_name} rule "
                f"'{rule_names[0]}'."
            )
        else:
            description = (
                f"The requirement matches "
                f"{len(rule_names)} "
                f"{category_name} rules: "
                f"{', '.join(rule_names)}."
            )

        recommendations = [
            rule["recommendation"]
            for rule in matched_rules
            if rule.get("recommendation")
        ]

        recommendation = (
            " ".join(
                dict.fromkeys(recommendations)
            )
            if recommendations
            else (
                f"Review the requirement "
                f"against the {category_name} rules."
            )
        )

        passed = False

    severities = [
        rule["severity"]
        for rule in matched_rules
        if rule.get("severity")
    ]

    severity_priority = {
        "high": 3,
        "medium": 2,
        "low": 1,
    }

    severity = (
        max(
            severities,
            key=lambda value: severity_priority.get(
                value.lower(),
                0,
            ),
        )
        if severities
        else "Medium"
    )

    why_it_matters_values = [
        rule["why_it_matters"]
        for rule in matched_rules
        if rule.get("why_it_matters")
    ]

    why_it_matters = (
        " ".join(
            dict.fromkeys(
                why_it_matters_values
            )
        )
        if why_it_matters_values
        else (
            category_description
            or "This category helps improve requirement quality."
        )
    )

    return _finding(
        rule_name=category_name,
        passed=passed,
        description=description,
        why_it_matters=why_it_matters,
        recommendation=recommendation,
        severity=severity,
        category=category_name,
        rules=matched_rules,
    )


def _check_complete_requirement(
    lower_text,
):
    """
    Structural requirement completeness check.

    This remains part of the Rule Engine because
    completeness is not simply a configurable keyword.
    """

    if not lower_text:

        return _finding(
            "Complete Requirement",
            False,
            "No requirement text was provided.",
            "An empty requirement cannot be implemented or tested.",
            "Add a clear description of the required system behavior.",
            "High",
        )

    words = lower_text.split()

    action_words = (
        "allow",
        "provide",
        "register",
        "login",
        "log in",
        "authenticate",
        "create",
        "update",
        "delete",
        "send",
        "receive",
        "store",
        "display",
        "maintain",
        "reset",
        "support",
        "validate",
        "generate",
        "process",
        "search",
        "calculate",
        "check",
        "record",
        "manage",
        "view",
    )

    actor_words = (
        "system",
        "user",
        "users",
        "admin",
        "administrator",
        "application",
        "customer",
        "customers",
        "librarian",
        "member",
        "members",
    )

    has_actor = any(
        word in words
        for word in actor_words
    )

    has_action = any(
        word in lower_text
        for word in action_words
    )

    enough_detail = len(words) >= 5

    if (
        enough_detail
        and has_actor
        and has_action
    ):
        return _finding(
            "Complete Requirement",
            True,
            "The requirement contains a clear actor, action, and sufficient detail.",
            "Complete requirements reduce assumptions during implementation and testing.",
            "No action is required.",
            "Low",
        )

    missing = []

    if not enough_detail:
        missing.append(
            "more detail"
        )

    if not has_actor:
        missing.append(
            "a clear actor"
        )

    if not has_action:
        missing.append(
            "a clear action"
        )

    return _finding(
        "Complete Requirement",
        False,
        "The requirement is missing "
        + ", ".join(missing)
        + ".",
        "A requirement should clearly describe who or what performs an action and the expected behavior.",
        "Add the missing actor, action, or implementation detail.",
        "High",
    )


def _check_duplicate(
    lower_text,
    req_id,
    seen,
):
    duplicate_ids = [
        candidate
        for candidate in seen[lower_text]
        if candidate != req_id
    ]

    return _finding(
        "No Duplicate Found",
        not duplicate_ids,
        (
            "No identical requirement was found in the analyzed set."
            if not duplicate_ids
            else (
                f"This requirement is identical to "
                f"{', '.join(duplicate_ids)}."
            )
        ),
        "Duplicate requirements can cause redundant implementation and confusion.",
        (
            "No action is required."
            if not duplicate_ids
            else "Remove or merge the duplicate requirement."
        ),
        (
            "Medium"
            if duplicate_ids
            else "Low"
        ),
    )


def analyze_requirements(requirements):
    """
    Analyze requirements using rules configured
    through the Master Module.

    Result structure:

        Complete Requirement

        Ambiguous
            -> quickly

        Actor
            -> system
            -> user

        Action
            -> allow

        No Duplicate Found

    Only rules that actually match the requirement
    are included inside a category.
    """

    master_rules = _load_active_rules()

    print(
        f"[RULE ENGINE] Loaded "
        f"{len(master_rules)} active master rules."
    )

    normalized = []

    for requirement in requirements:

        text = (
            requirement.get("text")
            or ""
        ).strip()

        normalized.append(
            {
                **requirement,
                "text": text,
                "lower_text": text.lower(),
            }
        )

    seen = defaultdict(list)

    for requirement in normalized:

        if requirement["lower_text"]:

            seen[
                requirement["lower_text"]
            ].append(
                requirement["id"]
            )

    results = []

    for requirement in normalized:

        req_id = requirement["id"]
        text = requirement["text"]
        lower_text = requirement[
            "lower_text"
        ]

        findings = []

        # =========================================================
        # COMPLETE REQUIREMENT
        # =========================================================

        findings.append(
            _check_complete_requirement(
                lower_text
            )
        )

        # =========================================================
        # MASTER MODULE RULES
        # =========================================================

        rules_by_category = defaultdict(
            list
        )

        if lower_text:

            for rule in master_rules:

                if _rule_matches(
                    lower_text,
                    rule,
                ):

                    category_name = (
                        rule.get(
                            "category_name"
                        )
                        or "Other"
                    )

                    rules_by_category[
                        category_name
                    ].append(
                        _build_matched_rule(
                            rule
                        )
                    )

        # =========================================================
        # CREATE ONE FINDING PER CATEGORY
        # =========================================================

        category_metadata = {}

        for rule in master_rules:

            category_name = (
                rule.get(
                    "category_name"
                )
                or "Other"
            )

            if category_name not in category_metadata:

                category_metadata[
                    category_name
                ] = {
                    "description": (
                        rule.get(
                            "category_description"
                        )
                        or ""
                    )
                }

        for (
            category_name,
            matched_rules,
        ) in rules_by_category.items():

            metadata = category_metadata.get(
                category_name,
                {},
            )

            findings.append(
                _build_category_finding(
                    category_name=category_name,
                    category_description=metadata.get(
                        "description",
                        "",
                    ),
                    matched_rules=matched_rules,
                )
            )

        # =========================================================
        # DUPLICATE REQUIREMENT
        # =========================================================

        findings.append(
            _check_duplicate(
                lower_text,
                req_id,
                seen,
            )
        )

        results.append(
            {
                "id": req_id,
                "text": text,
                "findings": findings,
            }
        )

    return results