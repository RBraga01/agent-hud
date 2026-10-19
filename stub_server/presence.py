"""Independent link evidence for one server-selected pair of glasses.

This is an internal observation boundary, not an HTTP heartbeat endpoint. A
paired token proves which credential spoke, but not that the physical glasses
or their display are working. Only a trusted link checker supplied by the
gateway may call ``observe`` through the server.
"""

from __future__ import annotations

from dataclasses import dataclass

PRESENCE_LEASE_SECONDS = 10.0
MIN_ABSENCE_SECONDS = 60.0


@dataclass
class PresenceMonitor:
    device_id: str | None = None
    last_verified_at: float | None = None
    presence_valid_until: float | None = None
    absence_started_at: float | None = None
    failed_observations: int = 0
    last_failure_at: float | None = None

    def observe(self, device_id: str, linked: bool, *, at: float) -> None:
        """Record one independent physical-link check for the selected ID."""
        if self.device_id != device_id:
            self.device_id = device_id
            self.last_verified_at = None
            self.presence_valid_until = None
            self.absence_started_at = None
            self.failed_observations = 0
            self.last_failure_at = None
        if linked:
            self.last_verified_at = at
            self.presence_valid_until = at + PRESENCE_LEASE_SECONDS
            self.absence_started_at = None
            self.failed_observations = 0
            self.last_failure_at = None
        elif self.last_verified_at is not None and at > self.last_verified_at:
            if self.last_failure_at is None or at > self.last_failure_at:
                if self.absence_started_at is None:
                    self.absence_started_at = at
                self.failed_observations += 1
                self.last_failure_at = at

    def state(self, device_id: str, *, at: float) -> dict:
        """Describe existing proof without performing or scheduling a check."""
        if self.device_id != device_id:
            return {
                "health": "unknown", "evidence": "none",
                "last_verified_link_at": None, "presence_valid_until": None,
                "absence_started_at": None, "failed_observations": 0,
            }
        healthy = (
            self.last_verified_at is not None
            and self.failed_observations == 0
            and self.presence_valid_until is not None
            and self.last_verified_at <= at <= self.presence_valid_until
        )
        unavailable = (
            self.last_verified_at is not None
            and self.absence_started_at is not None
            and self.failed_observations >= 2
            and self.last_failure_at is not None
            and self.last_failure_at - self.absence_started_at >= MIN_ABSENCE_SECONDS
            and self.presence_valid_until is not None
            and at > self.presence_valid_until
        )
        health = "healthy" if healthy else "unavailable" if unavailable else "unknown"
        evidence = "verified_link" if self.last_verified_at is not None else "none"
        return {
            "health": health,
            "evidence": evidence,
            "last_verified_link_at": self.last_verified_at,
            "presence_valid_until": self.presence_valid_until,
            "absence_started_at": self.absence_started_at,
            "failed_observations": self.failed_observations,
        }
