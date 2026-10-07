"""Commands for running a server: tenants, API keys and data retention."""

import argparse
import sys
from datetime import UTC, datetime, timedelta

from mirrorguard.benchmark.report import format_table
from mirrorguard.config import get_settings
from mirrorguard.db import Database
from mirrorguard.guardrail.event_store import EventRepository
from mirrorguard.loader import Library
from mirrorguard.tenancy.audit import AuditLog
from mirrorguard.tenancy.repository import TenantRepository
from mirrorguard.tenancy.roles import Role

CLI_ACTOR = "command-line"


async def _with_database(action) -> int:
    database = Database(get_settings().database_url)
    await database.create_tables()
    try:
        return await action(database)
    except ValueError as exc:
        print(f"Error: {exc}.", file=sys.stderr)
        return 1
    finally:
        await database.dispose()


async def _cmd_tenant_create(args: argparse.Namespace, library: Library) -> int:
    async def action(database: Database) -> int:
        await TenantRepository(database).create_tenant(args.id, args.name or args.id)
        await AuditLog(database).record(args.id, CLI_ACTOR, "tenant.created")
        print(f"Created tenant '{args.id}'.")
        return 0

    return await _with_database(action)


async def _cmd_tenant_list(args: argparse.Namespace, library: Library) -> int:
    async def action(database: Database) -> int:
        tenants = await TenantRepository(database).list_tenants()
        print(
            format_table(["id", "name", "created"], [[t.id, t.name, t.created_at] for t in tenants])
        )
        return 0

    return await _with_database(action)


async def _cmd_key_create(args: argparse.Namespace, library: Library) -> int:
    async def action(database: Database) -> int:
        role = Role(args.role)
        key_id, key = await TenantRepository(database).create_key(
            args.tenant, role=role, name=args.name
        )
        await AuditLog(database).record(
            args.tenant, CLI_ACTOR, "key.created", target=key_id, detail={"role": role.value}
        )
        print(f"Key id : {key_id}")
        print(f"API key: {key}")
        print("Store this key now. It is not shown again.")
        return 0

    return await _with_database(action)


async def _cmd_key_list(args: argparse.Namespace, library: Library) -> int:
    async def action(database: Database) -> int:
        keys = await TenantRepository(database).list_keys(args.tenant)
        rows = [
            [k.id, k.name, k.role, f"{k.prefix}...", "revoked" if k.revoked_at else "active"]
            for k in keys
        ]
        print(format_table(["id", "name", "role", "starts with", "state"], rows))
        return 0

    return await _with_database(action)


async def _cmd_key_revoke(args: argparse.Namespace, library: Library) -> int:
    async def action(database: Database) -> int:
        if not await TenantRepository(database).revoke_key(args.tenant, args.key_id):
            print("No such active key for this tenant.", file=sys.stderr)
            return 1
        await AuditLog(database).record(args.tenant, CLI_ACTOR, "key.revoked", target=args.key_id)
        print("Key revoked. It stops working within 30 seconds.")
        return 0

    return await _with_database(action)


async def _cmd_purge(args: argparse.Namespace, library: Library) -> int:
    days = args.days if args.days is not None else get_settings().retention_days
    if days < 1:
        print("Error: days must be at least 1.", file=sys.stderr)
        return 1

    async def action(database: Database) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        removed = await EventRepository(database).purge_older_than(cutoff)
        print(f"Removed {removed} guardrail events older than {days} days.")
        return 0

    return await _with_database(action)


def register(sub: argparse._SubParsersAction) -> None:
    tenants = sub.add_parser("tenants", help="tenant commands").add_subparsers(required=True)
    create = tenants.add_parser("create", help="add a tenant")
    create.add_argument("id")
    create.add_argument("--name")
    create.set_defaults(handler=_cmd_tenant_create)
    tenants.add_parser("list", help="list tenants").set_defaults(handler=_cmd_tenant_list)

    keys = sub.add_parser("keys", help="API key commands").add_subparsers(required=True)
    new = keys.add_parser("create", help="make a new API key for a tenant")
    new.add_argument("tenant")
    new.add_argument("--role", choices=[r.value for r in Role], default=Role.ADMIN.value)
    new.add_argument("--name", default="")
    new.set_defaults(handler=_cmd_key_create)
    listing = keys.add_parser("list", help="list a tenant's keys")
    listing.add_argument("tenant")
    listing.set_defaults(handler=_cmd_key_list)
    revoke = keys.add_parser("revoke", help="switch a key off")
    revoke.add_argument("tenant")
    revoke.add_argument("key_id")
    revoke.set_defaults(handler=_cmd_key_revoke)

    retention = sub.add_parser("retention", help="data retention").add_subparsers(required=True)
    purge = retention.add_parser("purge", help="delete old guardrail events")
    purge.add_argument("--days", type=int, help="default: MG_RETENTION_DAYS")
    purge.set_defaults(handler=_cmd_purge)
