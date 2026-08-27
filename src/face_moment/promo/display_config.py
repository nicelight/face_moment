"""Promo-owned independent display and cooldown configuration."""

from __future__ import annotations

from dataclasses import dataclass


class InvalidDisplayConfigurationError(ValueError):
    """Deployment display configuration is missing or not a positive integer."""


@dataclass(frozen=True, slots=True)
class DisplayConfiguration:
    """The exact version-one configuration projected to the display client."""

    result_display_ms: int
    success_cooldown_ms: int

    def as_response(self) -> dict[str, int]:
        return {
            "schema_version": 1,
            "result_display_ms": self.result_display_ms,
            "success_cooldown_ms": self.success_cooldown_ms,
        }


def read_display_configuration(settings: object) -> DisplayConfiguration:
    """Read two independent positive deployment values without substitution."""

    return DisplayConfiguration(
        result_display_ms=_positive_integer(
            getattr(settings, "realtime_result_display_ms", None),
            "result_display_ms",
        ),
        success_cooldown_ms=_positive_integer(
            getattr(settings, "realtime_success_cooldown_ms", None),
            "success_cooldown_ms",
        ),
    )


def _positive_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidDisplayConfigurationError(
            f"{name} must be a positive integer"
        )
    return value


__all__ = [
    "DisplayConfiguration",
    "InvalidDisplayConfigurationError",
    "read_display_configuration",
]
