"""Candidate form metadata for Recruitment screens."""

WORK_MODE_OPTIONS = ("Remote", "Hybrid", "Onsite", "Any")
CURRENCY_OPTIONS = ("EUR", "USD", "GBP", "Other")

FORM_FIELDS = (
    "full_name",
    "email",
    "phone",
    "linkedin",
    "country",
    "city",
    "timezone",
    "main_role",
    "seniority",
    "skills",
    "sap_modules",
    "languages",
    "years_experience",
    "work_mode",
    "rate_hour",
    "rate_day",
    "currency",
    "notes",
    "cv_file_path",
    "cv_text",
)

READONLY_FIELDS = ("cv_text",)
