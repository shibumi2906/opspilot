import argparse
import asyncio
import json
from uuid import UUID

from opspilot.agent.service import RunConflict, run_investigation
from opspilot.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpsPilot: investigate, pause and resume a saved decision"
    )
    parser.add_argument("request", nargs="?")
    parser.add_argument("--run-id", type=UUID)
    parser.add_argument("--action-id", type=UUID)
    parser.add_argument("--decision", choices=("approve", "reject"))
    parser.add_argument("--mode", choices=("scripted", "real"), default=None)
    parser.add_argument("--client-request-id", type=UUID, default=None)
    args = parser.parse_args()
    if args.decision:
        if not args.run_id or not args.action_id:
            parser.error("--decision requires --run-id and --action-id")
        from opspilot.contracts.api import Decision
        from opspilot.runtime.run_service import RunService

        async def decide() -> dict[str, object]:
            service = RunService(Settings())
            try:
                await service.decide(
                    args.run_id, Decision(action_id=args.action_id, decision=args.decision)
                )
                if service.tasks:
                    await asyncio.gather(*service.tasks)
                return await service.snapshot(args.run_id)
            finally:
                await service.close()

        print(json.dumps(asyncio.run(decide()), ensure_ascii=False, indent=2))
        return
    if not args.request:
        parser.error("request is required")
    try:
        result = asyncio.run(
            run_investigation(
                Settings(), args.request, mode=args.mode, client_request_id=args.client_request_id
            )
        )
    except (ValueError, RunConflict, RuntimeError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
