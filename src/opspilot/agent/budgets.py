import time
from collections.abc import Callable
from typing import Any

from pydantic import Field

from opspilot.contracts.common import StrictModel


class BudgetExceeded(Exception):
    def __init__(
        self,
        message: str,
        *,
        kind: str | None = None,
        used: int | float | None = None,
        requested: int | float | None = None,
        available: int | float | None = None,
    ) -> None:
        super().__init__(message)
        self.details = {
            key: value
            for key, value in dict(
                kind=kind, used=used, requested=requested, available=available
            ).items()
            if value is not None
        }


class BudgetLimits(StrictModel):
    rounds: int = Field(default=6, ge=1, le=6)
    reads: int = Field(default=15, ge=1, le=15)
    llm_attempts: int = Field(default=10, ge=1, le=10)
    tokens: int = Field(default=30000, ge=1, le=30000)
    active_seconds: float = Field(default=120, gt=0, le=120)
    recursion_limit: int = Field(default=60, ge=10, le=60)


class Budget:
    def __init__(self, limits: BudgetLimits, clock: Callable[[], float] = time.monotonic) -> None:
        self.limits = limits
        self.clock = clock
        self.started = clock()
        self.read_attempts = 0
        self.llm_attempts = 0
        self.rounds = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.unknown_usage_count = 0
        self.reserved_tokens = 0
        self.durable: dict[str, Any] = {}

    def remaining(self) -> float:
        return self.limits.active_seconds - (self.clock() - self.started)

    def check(self) -> None:
        remaining = self.remaining()
        if remaining <= 0:
            raise BudgetExceeded(
                "Active time limit reached",
                kind="active_seconds",
                used=self.limits.active_seconds - remaining,
                available=0,
            )
        tokens = self.input_tokens + self.output_tokens + self.reserved_tokens
        if tokens >= self.limits.tokens:
            raise BudgetExceeded("Token limit reached", kind="tokens", used=tokens, available=0)

    def begin_read(self, *, verification: bool = False) -> None:
        self.check()
        # F15: research reads have their own durable cap; verification has a per-action reserve.
        if self.read_attempts >= self.limits.reads:
            raise BudgetExceeded(
                "Read limit reached; verification reserve preserved",
                kind="reads",
                used=self.read_attempts,
                requested=1,
                available=0,
            )
        self.read_attempts += 1

    def begin_llm(self) -> None:
        self.check()
        if self.llm_attempts >= self.limits.llm_attempts:
            raise BudgetExceeded(
                "LLM attempt limit reached",
                kind="llm_attempts",
                used=self.llm_attempts,
                requested=1,
                available=0,
            )
        self.llm_attempts += 1

    def begin_round(self) -> None:
        self.check()
        if self.rounds >= self.limits.rounds:
            raise BudgetExceeded(
                "Investigation round limit reached",
                kind="rounds",
                used=self.rounds,
                requested=1,
                available=0,
            )
        self.rounds += 1

    def usage(self, input_tokens: int | None, output_tokens: int | None) -> None:
        if input_tokens is None or output_tokens is None:
            self.unknown_usage_count += 1
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.durable,
            "reserved_tokens": self.reserved_tokens,
            "limits": self.limits.model_dump(),
            "rounds": self.rounds,
            "read_attempts": self.read_attempts,
            "llm_attempts": self.llm_attempts,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "unknown_usage_count": self.unknown_usage_count,
            "active_seconds": max(0, self.clock() - self.started),
            "reserved_verify_reads": 1,
        }
