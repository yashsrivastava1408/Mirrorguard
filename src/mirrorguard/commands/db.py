"""Database commands: create the tables, or bring them up to date."""

import argparse

from mirrorguard.config import get_settings
from mirrorguard.db import Database
from mirrorguard.library.loader import Library


async def _cmd_db_init(args: argparse.Namespace, library: Library) -> int:
    settings = get_settings()
    database = Database(settings.database_url)
    await database.create_tables()
    await database.dispose()
    print("Database tables are ready.")
    return 0


def _cmd_db_migrate(args: argparse.Namespace, library: Library) -> int:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    import mirrorguard

    config = Config()
    config.set_main_option("script_location", str(Path(mirrorguard.__file__).parent / "migrations"))
    command.upgrade(config, "head")
    print("Database is up to date.")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    db_sub = sub.add_parser("db", help="database commands").add_subparsers(required=True)
    db_sub.add_parser("init", help="create the tables directly (local SQLite)").set_defaults(
        handler=_cmd_db_init
    )
    db_sub.add_parser("migrate", help="bring a production database up to date").set_defaults(
        handler=_cmd_db_migrate
    )
