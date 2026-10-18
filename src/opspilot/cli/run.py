import argparse
import asyncio
import json
from uuid import UUID

from opspilot.agent.service import RunConflict, run_investigation
from opspilot.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpsPilot stage 3: checkpointed read-only investigation"
    )
    parser.add_argument("request")
    parser.add_argument("--mode", choices=("scripted", "real"), default=None)
    parser.add_argument("--client-request-id", type=UUID, default=None)
    args = parser.parse_args()
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
