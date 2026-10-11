"""Two-role permission matrix (PRD 4.1).

Stakeholders always have every permission; this cannot be changed.
Volunteer permissions are configurable by Stakeholders (stored in app_settings
under the "permissions" key), but whatever they are allowed is always
restricted to their single assigned village.
"""

from enum import StrEnum


class Role(StrEnum):
    STAKEHOLDER = "stakeholder"
    VOLUNTEER = "volunteer"


RESOURCES = [
    "users",
    "master_data",
    "contacts",
    "girls",
    "health",
    "cases",
    "home_visits",
    "activity_reports",
    "events",
    "targets",
    "dashboard",
    "reports",
    "notifications",
    "config",
    "audit",
]
ACTIONS = ["read", "create", "update", "delete", "approve", "export"]

# Resources a Volunteer can never be granted, whatever the configuration says.
STAKEHOLDER_ONLY = {"users", "master_data", "config", "audit"}

DEFAULT_VOLUNTEER_PERMISSIONS: dict[str, list[str]] = {
    "contacts": ["read"],
    "girls": ["read", "create", "update"],
    "health": ["read", "create"],
    "cases": ["read", "create", "update"],
    "home_visits": ["read", "create", "update"],
    "activity_reports": ["read", "create", "update"],
    "events": ["read", "update"],
    "targets": ["read"],
    "dashboard": ["read"],
    "reports": [],
    "notifications": ["read", "update"],
}


def full_matrix(volunteer_permissions: dict[str, list[str]]) -> dict[str, dict[str, list[str]]]:
    return {
        Role.STAKEHOLDER: {r: list(ACTIONS) for r in RESOURCES},
        Role.VOLUNTEER: {
            r: ([] if r in STAKEHOLDER_ONLY else [a for a in volunteer_permissions.get(r, []) if a in ACTIONS])
            for r in RESOURCES
        },
    }
