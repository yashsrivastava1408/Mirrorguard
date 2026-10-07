"""Model commands: check that every configured model still answers."""

import argparse

from mirrorguard.config import get_settings
from mirrorguard.library.loader import Library
from mirrorguard.llm import LLMError, Message
from mirrorguard.llm.factory import make_model_factory


async def _cmd_models_check(args: argparse.Namespace, library: Library) -> int:
    settings = get_settings()
    models = make_model_factory(settings)
    names = sorted(
        {
            settings.persona_model,
            settings.judge_model,
            settings.risk_model,
            settings.rewriter_model,
            *settings.target_models,
        }
    )
    failures = 0
    for name in names:
        try:
            await models(name).complete(
                [Message(role="user", content="Reply with the single word OK.")], max_tokens=20
            )
            print(f"  ok      {name}")
        except LLMError as exc:
            failures += 1
            print(f"  FAILED  {name}: {str(exc)[:160]}")
    return 0 if not failures else 1


def register(sub: argparse._SubParsersAction) -> None:
    models_sub = sub.add_parser("models", help="model commands").add_subparsers(required=True)
    models_sub.add_parser("check", help="check that every configured model answers").set_defaults(
        handler=_cmd_models_check
    )
