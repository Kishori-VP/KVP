"""
Two-role permission matrix (PRD 4.1).

Stakeholders always have every permission; this cannot be changed.

Volunteer permissions are configurable by Stakeholders and stored in
app_settings under the "permissions" key. Regardless of configuration,
Volunteers are always restricted to their single assigned village.
"""

from enum import Enum
from typing import Dict, List


class Role(str, Enum):
    """Application roles."""

    STAKEHOLDER = "stakeholder"  # Top-level monitor (oversight over Admin and Tai)
    ADMIN = "admin"              # Administrator / Program Coordinator
    VOLUNTEER = "volunteer"      # Tai (field worker)
    SUPER_ADMIN = "super_admin"  # Alias for Stakeholder


# Resources supported by the permission system.
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

# Actions that can be granted on a resource.
ACTIONS = [
    "read",
    "create",
    "update",
    "delete",
    "approve",
    "export",
]

# Resources that Volunteers can never access through this permission matrix.
# Stakeholder permissions are not configurable.
STAKEHOLDER_ONLY = {
    "users",
    "master_data",
    "config",
    "audit",
}

# Default permissions assigned to Volunteers.
# Stakeholders may customize these permissions through app_settings.
DEFAULT_VOLUNTEER_PERMISSIONS = {
    "contacts": ["read"],
    "girls": ["read", "create", "update"],
    "health": ["read", "create"],
    "cases": ["read", "create", "update"],
    "home_visits": ["read", "create", "update"],
    "activity_reports": ["read", "create", "update"],
    "events": ["read", "update"],
    "targets": ["read"],
    "dashboard": ["read"],
    "reports": ["read"],
    "notifications": ["read", "update"],
}


def full_matrix(
    volunteer_permissions: Dict[str, List[str]]
) -> Dict[Role, Dict[str, List[str]]]:
    """
    Build the complete permission matrix for both application roles.

    Stakeholders:
        Receive every defined action on every resource.

    Volunteers:
        Receive only configured actions that are listed in ACTIONS.
        Resources in STAKEHOLDER_ONLY always have an empty permission list.

    Unknown actions are ignored. Resources not present in the supplied
    Volunteer permissions receive no permissions unless explicitly configured.
    """
    stakeholder_permissions = {
        resource: list(ACTIONS)
        for resource in RESOURCES
    }

    volunteer_matrix = {}

    for resource in RESOURCES:
        if resource in STAKEHOLDER_ONLY:
            volunteer_matrix[resource] = []
        else:
            configured_actions = volunteer_permissions.get(resource, [])

            volunteer_matrix[resource] = [
                action
                for action in configured_actions
                if action in ACTIONS
            ]

    return {
        Role.STAKEHOLDER: stakeholder_permissions,
        Role.ADMIN: stakeholder_permissions,
        Role.SUPER_ADMIN: stakeholder_permissions,
        Role.VOLUNTEER: volunteer_matrix,
    }
