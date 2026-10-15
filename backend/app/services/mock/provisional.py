"""PROVISIONAL status values for the mock service, until the contract defines them. Owner: Jian.

contract/models.py leaves Option.eligibility, Option.validity and ValidationResult.validation_result as free
strings (TODO). These are the values the mock uses. When the contract is agreed, rename them here only.
Cheich's stub tools and harness currently check for "valid" and "eligible".
"""
ELIGIBLE = "eligible"
INELIGIBLE = "ineligible"
UNKNOWN = "unknown"

VALIDITY_VALID = "valid"
VALIDITY_EXPIRED = "expired"
VALIDITY_UNAVAILABLE = "unavailable"

RESULT_VALID = "valid"
RESULT_CHANGED = "changed"
RESULT_UNAVAILABLE = "unavailable"
RESULT_INVALID = "invalid"
