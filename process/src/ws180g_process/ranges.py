# SPDX-License-Identifier: Apache-2.0
"""Value ranges and grid arithmetic, exact in Decimal."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator


class Range(BaseModel):
    """A toleranced quantity: `min <= nominal <= max`, all in `unit`."""

    model_config = ConfigDict(extra="forbid")

    min: Decimal
    nominal: Decimal
    max: Decimal
    unit: str

    @model_validator(mode="after")
    def _ordered(self) -> "Range":
        if not self.min <= self.nominal <= self.max:
            raise ValueError(f"needs min <= nominal <= max, got {self.min}, {self.nominal}, {self.max}")
        return self


def on_grid(value: Decimal, grid: Decimal) -> bool:
    """True when `value` is a whole multiple of `grid` (exact Decimal arithmetic)."""
    if grid <= 0:
        raise ValueError(f"grid must be positive, got {grid}")
    return value % grid == 0
