"""The command that starts the API server."""

import argparse

from mirrorguard.library.loader import Library


def _cmd_serve(args: argparse.Namespace, library: Library) -> int:
    import uvicorn

    uvicorn.run(
        "mirrorguard.api.app:app_from_settings",
        factory=True,
        host=args.host,
        port=args.port,
        workers=args.workers,
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    serve = sub.add_parser("serve", help="start the guardrail API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workers", type=int, default=1, help="server processes to run")
    serve.set_defaults(handler=_cmd_serve)
