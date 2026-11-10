"""Eval-only cumulative token reservations; never implies billing eligibility.

The ledger is single-process and single-run, created exclusively. Unknown usage
retains its full reservation and stops dispatch. Do not reuse it for a resume.
"""

import asyncio
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from opspilot.llm.base import Completion, Operation, ProviderFailure, Usage
from opspilot.llm.real import RealProvider


class TokenGuard:
    def __init__(self, path: Path, limit: int, model: str) -> None:
        if not 0 < limit <= 200000:
            raise ValueError("F22 total limit must be between 1 and 200000 tokens")
        self.path, self.limit, self.model = path, limit, model
        self.charged = 0
        self.stop_reason: str | None = None
        self.entries: list[dict[str, Any]] = []
        self.lock = asyncio.Lock()
        # Existing reports/unknown in-flight requests cannot silently receive a new budget.
        with path.open("x", encoding="utf-8") as target:
            json.dump(self.snapshot(), target)
            target.flush()
            os.fsync(target.fileno())

    def snapshot(self) -> dict[str, Any]:
        return dict(
            limit=self.limit,
            charged_or_reserved=self.charged,
            provider_attempts=len(self.entries),
            stop_reason=self.stop_reason,
            known_input_tokens=sum(e.get("input_tokens") or 0 for e in self.entries),
            known_output_tokens=sum(e.get("output_tokens") or 0 for e in self.entries),
            unknown_usage=sum(e["status"] in {"reserved", "unknown"} for e in self.entries),
            entries=self.entries,
            billing_eligibility_verified=False,
            actual_billed_usd=None,
        )

    def save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as target:
            json.dump(self.snapshot(), target, indent=2)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(self.path)

    async def reserve(self, provider: RealProvider, operation: Any, context: dict[str, Any]) -> int:
        async with self.lock:
            if provider.model != self.model:
                self.stop_reason = "MODEL_CONFIG_CHANGED"
            # Existing provider bound includes UTF8 request bytes, max output and overhead.
            amount = provider.reservation_tokens(operation, context)
            if self.stop_reason or self.charged + amount > self.limit:
                self.stop_reason = self.stop_reason or "GLOBAL_TOKEN_LIMIT"
                self.save()
                raise ProviderFailure("EVAL_" + self.stop_reason, dispatched=False)
            self.charged += amount
            self.entries.append(dict(operation=operation, reservation=amount, status="reserved"))
            self.save()  # Durable before any network dispatch.
            return len(self.entries) - 1

    async def settle(self, index: int, usage: Usage) -> None:
        async with self.lock:
            row = self.entries[index]
            row.update(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
            if usage.input_tokens is None or usage.output_tokens is None:
                row["status"] = "unknown"
                self.stop_reason = "UNKNOWN_PROVIDER_USAGE"
            else:
                actual = usage.input_tokens + usage.output_tokens
                self.charged += actual - row["reservation"]
                row["status"] = "known"
                if actual > row["reservation"]:
                    self.stop_reason = "RESERVATION_BOUND_EXCEEDED"
            self.save()

    @contextmanager
    def installed(self) -> Iterator[None]:
        original = RealProvider.complete
        guard = self

        async def bounded(
            provider: RealProvider, operation: Operation, context: dict[str, Any]
        ) -> Completion:
            index = await guard.reserve(provider, operation, context)
            usage = Usage()
            try:
                result = await original(provider, operation, context)
                usage = result.usage
                return result
            except ProviderFailure as exc:
                usage = exc.usage
                raise
            finally:
                await guard.settle(index, usage)

        with patch.object(RealProvider, "complete", bounded):
            yield
