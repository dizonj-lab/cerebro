"""
CEREBRO AI routing capability.

Determines whether a task should use:
- no AI,
- local AI,
- frontier AI.

The router makes a decision only.
It does NOT invoke a model.

Principle:
Use the lightest capable model.
Escalate only when necessary and permitted.
"""


def route_ai_task(
    task: str,
    *,
    ai_required: bool = True,
    privacy_sensitive: bool = True,
    prefer_local: bool = True,
    local_available: bool = True,
    frontier_allowed: bool = True,
    escalation_allowed: bool = True,
    complexity: str = "low",
    required_quality: str = "standard",
):
    """
    Produce an explainable CEREBRO routing decision.
    """

    valid_complexity = {"low", "medium", "high"}
    valid_quality = {"standard", "high"}

    if complexity not in valid_complexity:
        raise ValueError(
            f"Unsupported complexity: {complexity}"
        )

    if required_quality not in valid_quality:
        raise ValueError(
            f"Unsupported required_quality: {required_quality}"
        )

    factors = {
        "privacy_sensitive": privacy_sensitive,
        "prefer_local": prefer_local,
        "local_available": local_available,
        "frontier_allowed": frontier_allowed,
        "escalation_allowed": escalation_allowed,
        "complexity": complexity,
        "required_quality": required_quality,
    }

    # -----------------------------------------------------
    # No AI required
    # -----------------------------------------------------

    if not ai_required:
        return {
            "task": task,
            "selected_tier": "none",
            "reason": "Task does not require AI.",
            "factors": factors,
            "fallback_tier": None,
            "status": "ROUTED",
        }

    # -----------------------------------------------------
    # Prefer local capability
    # -----------------------------------------------------

    if prefer_local and local_available:
        selected_tier = "local"

        if escalation_allowed and frontier_allowed:
            fallback_tier = "frontier"
        else:
            fallback_tier = None

        reason = (
            "Local AI selected as the lightest available "
            "capability consistent with routing policy."
        )

    # -----------------------------------------------------
    # Local unavailable
    # -----------------------------------------------------

    elif frontier_allowed:
        selected_tier = "frontier"
        fallback_tier = None

        reason = (
            "Local AI unavailable or not preferred; "
            "frontier AI permitted."
        )

    else:
        selected_tier = "unavailable"
        fallback_tier = None

        reason = (
            "No permitted AI capability is currently available."
        )

    return {
        "task": task,
        "selected_tier": selected_tier,
        "reason": reason,
        "factors": factors,
        "fallback_tier": fallback_tier,
        "status": "ROUTED",
    }


def should_escalate(
    validation_result: dict,
    routing_decision: dict
):
    """
    Determine whether a local result should escalate.

    Uses the validation gates established by the CEREBRO
    AI enrichment experiments.
    """

    required_gates = [
        "structured_output_valid",
        "grounding_passed",
        "required_fields_present",
        "entity_preservation_passed",
    ]

    gates_passed = all(
        validation_result.get(gate, False)
        for gate in required_gates
    )

    unsupported_claims = validation_result.get(
        "unsupported_claims_detected",
        False
    )

    quality_passed = (
        gates_passed
        and not unsupported_claims
    )

    escalation_permitted = (
        routing_decision["factors"]["escalation_allowed"]
        and routing_decision["factors"]["frontier_allowed"]
        and routing_decision["fallback_tier"] == "frontier"
    )

    return {
        "quality_passed": quality_passed,
        "escalate": (
            not quality_passed
            and escalation_permitted
        ),
        "status": (
            "PASS"
            if quality_passed
            else "ESCALATE"
            if escalation_permitted
            else "FAIL"
        ),
    }
