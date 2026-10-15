"""Errors shared by the booking services (mock and Duffel). Owner: Jian.

Messages are safe to show to the agent and the traveler: they never contain tokens, raw responses or
passenger data. An error that is NOT a ServiceError (for example a dropped connection while confirming)
means the outcome is uncertain, and callers must treat it as pending rather than failed.
"""


class ServiceError(Exception):
    """Base class: the call failed and nothing was changed."""


class UnknownBookingError(ServiceError):
    pass


class UnknownOptionError(ServiceError):
    pass


class RebookingNotAllowedError(ServiceError):
    """The option failed validation, was not prepared, or changed since it was prepared."""


class AlreadyRebookedError(ServiceError):
    """This booking was already rebooked."""
