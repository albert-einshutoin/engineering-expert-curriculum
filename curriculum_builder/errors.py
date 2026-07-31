class CurriculumValidationError(ValueError):
    """Raised when version-controlled curriculum content breaks its contract."""


# A dedicated subtype lets consumers translate structural incompleteness
# without coupling control flow to user-facing diagnostic wording.
class IncompleteLessonReleaseError(CurriculumValidationError):
    """Raised when lessons cannot form a structurally complete release."""
