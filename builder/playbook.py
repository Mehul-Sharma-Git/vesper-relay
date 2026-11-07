"""Shipped lessons and the workflows where they apply."""

RULES = {
    "reproduce-first": ("bug", "Reproduce the failure on the committed baseline before making a fix. "
                        "Keep that case in an independent regression check."),
    "confirm-file-scope": ("*", "Compare planned files with the writable scope before editing. "
                          "Ask the planner to resolve a required file outside the approved scope."),
}


def matching_guidance(active, mode):
    return {rule: text for rule, (scope, text) in RULES.items()
            if rule in active and scope in {"*", mode}}
