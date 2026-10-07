"""What each role may do."""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"  # everything, including policy and keys
    ENGINEER = "engineer"  # send chat traffic and read everything
    REVIEWER = "reviewer"  # read conversations and review them
    VIEWER = "viewer"  # read only


class Permission(StrEnum):
    CHAT = "chat"
    READ = "read"
    REVIEW = "review"
    MANAGE = "manage"


_GRANTS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.ENGINEER: frozenset({Permission.CHAT, Permission.READ}),
    Role.REVIEWER: frozenset({Permission.READ, Permission.REVIEW}),
    Role.VIEWER: frozenset({Permission.READ}),
}


def allows(role: Role, permission: Permission) -> bool:
    return permission in _GRANTS[role]
