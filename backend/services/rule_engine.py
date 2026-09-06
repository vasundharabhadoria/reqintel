from collections import defaultdict


AMBIGUOUS_WORDS = (
    "quickly",
    "good",
    "easy",
    "secure",
    "user-friendly",
    "efficient",
    "appropriate",
    "fast",
)

ACTION_WORDS = (
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
)

ACTOR_WORDS = (
    "system",
    "user",
    "users",
    "admin",
    "administrator",
    "application",
    "customer",
    "customers",
)

COMPOUND_PATTERNS = (
    " and then ",
    " and also ",
    " and provide ",
    " and send ",
    " and store ",
    " and display ",
    " and update ",
    " and delete ",
    " and maintain ",
    " and process ",
    " and validate ",
    " and generate ",
    " and reset ",
)

PASSWORD_CONTEXT_WORDS = (
    "password",
    "passcode",
    "credential",
    "credentials",
    "login",
    "log in",
    "authenticate",
    "authentication",
    "register",
    "registration",
)

PASSWORD_POLICY_WORDS = (
    "minimum",
    "min",
    "length",
    "complexity",
    "special character",
    "special characters",
    "uppercase",
    "upper case",
    "lowercase",
    "lower case",
    "number",
    "numbers",
    "numeric",
    "digit",
    "digits",
    "character",
    "characters",
)


def _finding(
    rule_name,
    passed,
    description,
    why_it_matters,
    recommendation,
):
    return {
        "rule_name": rule_name,
        "passed": passed,
        "message": description,
        "severity": None,
        "description": description,
        "why_it_matters": why_it_matters,
        "recommendation": recommendation,
    }


def _check_password_policy(lower_text):
    has_password_context = any(
        word in lower_text
        for word in PASSWORD_CONTEXT_WORDS
    )

    if not has_password_context:
        return None

    has_password_policy = any(
        word in lower_text
        for word in PASSWORD_POLICY_WORDS
    )

    if has_password_policy:
        return _finding(
            "Password Policy",
            True,
            "The requirement defines a password-related policy or constraint.",
            "Explicit password policies make authentication requirements clear, measurable, and testable.",
            "No action is required.",
        )

    return _finding(
        "Missing Password Policy",
        False,
        "The requirement involves authentication or registration but does not define a password policy.",
        "Without a defined password policy, password requirements may be implemented inconsistently and can introduce security risks.",
        "Specify password requirements such as minimum length, complexity, and required character types.",
    )


def analyze_requirements(requirements):
    normalized = []

    for requirement in requirements:
        text = (requirement.get("text") or "").strip()

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
            seen[requirement["lower_text"]].append(
                requirement["id"]
            )

    results = []

    for requirement in normalized:

        req_id = requirement["id"]
        text = requirement["text"]
        lower_text = requirement["lower_text"]

        findings = []

        if not text:

            findings.append(
                _finding(
                    "Complete Requirement",
                    False,
                    "No requirement text was provided.",
                    "An empty requirement cannot be implemented or tested.",
                    "Add a clear description of the required system behavior.",
                )
            )

        else:

            words = lower_text.split()

            has_actor = any(
                word in words
                for word in ACTOR_WORDS
            )

            has_action = any(
                word in lower_text
                for word in ACTION_WORDS
            )

            enough_detail = len(words) >= 5

            if enough_detail and has_actor and has_action:

                findings.append(
                    _finding(
                        "Complete Requirement",
                        True,
                        "The requirement contains a clear actor, action, and sufficient detail.",
                        "Complete requirements reduce assumptions during implementation and testing.",
                        "No action is required.",
                    )
                )

            else:

                missing = []

                if not enough_detail:
                    missing.append("more detail")

                if not has_actor:
                    missing.append("a clear actor")

                if not has_action:
                    missing.append("a clear action")

                findings.append(
                    _finding(
                        "Complete Requirement",
                        False,
                        "The requirement is missing "
                        + ", ".join(missing)
                        + ".",
                        "A requirement should clearly describe who or what performs an action and the expected behavior.",
                        "Add the missing actor, action, or implementation detail.",
                    )
                )

            matched = next(
                (
                    word
                    for word in AMBIGUOUS_WORDS
                    if word in lower_text
                ),
                None,
            )

            findings.append(
                _finding(
                    "No Ambiguous Term",
                    matched is None,
                    (
                        "No vague or ambiguous term was detected."
                        if matched is None
                        else f"The requirement contains the vague term '{matched}'."
                    ),
                    "Vague terms can be interpreted differently by developers and testers.",
                    (
                        "No action is required."
                        if matched is None
                        else f"Replace '{matched}' with a clear and measurable statement."
                    ),
                )
            )

            is_compound = any(
                pattern in lower_text
                for pattern in COMPOUND_PATTERNS
            )

            findings.append(
                _finding(
                    "No Compound Requirement",
                    not is_compound,
                    (
                        "The requirement contains one clear action flow."
                        if not is_compound
                        else "The requirement appears to contain multiple independent actions."
                    ),
                    "Multiple independent actions in one requirement can make implementation and testing harder.",
                    (
                        "No action is required."
                        if not is_compound
                        else "Consider splitting the requirement into separate requirements."
                    ),
                )
            )

            password_finding = _check_password_policy(lower_text)

            if password_finding:
                findings.append(password_finding)

        duplicate_ids = [
            candidate
            for candidate in seen[lower_text]
            if candidate != req_id
        ]

        findings.append(
            _finding(
                "No Duplicate Found",
                not duplicate_ids,
                (
                    "No identical requirement was found in the analyzed set."
                    if not duplicate_ids
                    else f"This requirement is identical to {', '.join(duplicate_ids)}."
                ),
                "Duplicate requirements can cause redundant implementation and confusion.",
                (
                    "No action is required."
                    if not duplicate_ids
                    else "Remove or merge the duplicate requirement."
                ),
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