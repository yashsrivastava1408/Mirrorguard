"""What each role may do."""

from mirrorguard.tenancy.roles import Permission, Role, allows


def test_role_permissions():
    table = {
        Role.ADMIN: {Permission.CHAT, Permission.READ, Permission.REVIEW, Permission.MANAGE},
        Role.ENGINEER: {Permission.CHAT, Permission.READ},
        Role.REVIEWER: {Permission.READ, Permission.REVIEW},
        Role.VIEWER: {Permission.READ},
    }
    for role, granted in table.items():
        assert {p for p in Permission if allows(role, p)} == granted
