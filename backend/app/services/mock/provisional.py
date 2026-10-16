"""Status values the services use, named once. Owner: Jian.

The allowed values are defined by contract v1 in backend/app/contract/models.py (Eligibility, Validity,
ValidationOutcome); these constants only give them names so the services do not repeat raw strings.
"""
from ...contract.models import Eligibility, ValidationOutcome, Validity

ELIGIBLE: Eligibility = "eligible"
INELIGIBLE: Eligibility = "ineligible"
UNKNOWN: Eligibility = "unknown"

VALIDITY_VALID: Validity = "valid"
VALIDITY_EXPIRED: Validity = "expired"
VALIDITY_UNAVAILABLE: Validity = "unavailable"

RESULT_VALID: ValidationOutcome = "valid"
RESULT_CHANGED: ValidationOutcome = "changed"
RESULT_UNAVAILABLE: ValidationOutcome = "unavailable"
RESULT_INVALID: ValidationOutcome = "invalid"
