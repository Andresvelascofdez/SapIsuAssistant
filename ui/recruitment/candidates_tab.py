"""Candidate list metadata for Recruitment screens."""

TABLE_COLUMNS = (
    "full_name",
    "main_role",
    "skills",
    "sap_modules",
    "phone",
    "email",
    "country",
    "languages",
    "rate_hour",
    "rate_day",
    "currency",
    "work_mode",
    "updated_at",
)

FILTER_FIELDS = (
    "search",
    "skill_text",
    "sap_module_text",
    "language_text",
    "country",
    "seniority",
    "work_mode",
    "max_hourly_rate",
    "max_daily_rate",
)

ACTION_BUTTONS = (
    "New Candidate",
    "Edit Candidate",
    "Delete Candidate",
    "Import CV",
    "Open CV",
    "Clear Filters",
    "Refresh",
)
