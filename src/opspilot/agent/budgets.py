import time
from collections.abc import Callable
from typing import Any

from pydantic import Field

from opspilot.contracts.common import StrictModel


class BudgetExceeded(Exception):
    pass


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

    def remaining(self) -> float:
        return self.limits.active_seconds - (self.clock() - self.started)

    def check(self) -> None:
        if self.remaining() <= 0 or self.input_tokens + self.output_tokens >= self.limits.tokens:
            raise BudgetExceeded("Active time or token limit reached")

    def begin_read(self) -> None:
        self.check()
        # One reserved verification read is unavailable during pre-approval investigation.
        if self.read_attempts >= self.limits.reads - 1:
            raise BudgetExceeded("Read limit reached; verification reserve preserved")
        self.read_attempts += 1

    def begin_llm(self) -> None:
        self.check()
        if self.llm_attempts >= self.limits.llm_attempts:
            raise BudgetExceeded("LLM attempt limit reached")
        self.llm_attempts += 1

    def begin_round(self) -> None:
        self.check()
        if self.rounds >= self.limits.rounds:
            raise BudgetExceeded("Investigation round limit reached")
        self.rounds += 1

    def usage(self, input_tokens: int | None, output_tokens: int | None) -> None:
        if input_tokens is None or output_tokens is None:
            self.unknown_usage_count += 1
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0

    def snapshot(self) -> dict[str, Any]:
        return {
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
