from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import maxminddb
except ImportError:  # pragma: no cover - dependency is installed in packaged deployments
    maxminddb = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GeoLocation:
    country_code: str | None = None
    country_name: str | None = None


class GeoIPCityResolver:
    """Resolve a public IP locally and retain only country-level fields."""

    def __init__(self, database: str | Path = ""):
        self.database = Path(database) if database else None
        self._reader: Any = None

    @property
    def ready(self) -> bool:
        return self._reader is not None

    def initialize(self) -> bool:
        self.close()
        if self.database is None or not self.database.is_file():
            return False
        if maxminddb is None:
            logger.warning("maxminddb is unavailable; city geolocation is disabled")
            return False
        try:
            self._reader = maxminddb.open_database(str(self.database))
        except (OSError, ValueError):
            logger.exception("Unable to open the configured GeoIP city database")
            self._reader = None
        return self.ready

    def lookup(self, address: str | None) -> GeoLocation | None:
        if self._reader is None or not address:
            return None
        try:
            parsed = ipaddress.ip_address(address.strip())
        except ValueError:
            return None
        if not parsed.is_global:
            return None
        try:
            record = self._reader.get(str(parsed))
        except (KeyError, OSError, ValueError):
            logger.debug("GeoIP lookup failed", exc_info=True)
            return None
        return self._from_record(record)

    def close(self) -> None:
        if self._reader is not None:
            try:
                self._reader.close()
            except (AttributeError, OSError):
                logger.debug("GeoIP reader close failed", exc_info=True)
            finally:
                self._reader = None

    @classmethod
    def _from_record(cls, record: object) -> GeoLocation | None:
        if not isinstance(record, dict):
            return None
        country = record.get("country")
        country_map = country if isinstance(country, dict) else {}

        country_code = cls._text(country_map.get("iso_code"), 2, upper=True)
        country_name = cls._localized_name(country_map)
        if not any((country_code, country_name)):
            return None
        return GeoLocation(
            country_code=country_code,
            country_name=country_name,
        )

    @classmethod
    def _localized_name(cls, value: dict[str, object]) -> str | None:
        names = value.get("names")
        if not isinstance(names, dict):
            return None
        for language in ("zh-CN", "zh", "en"):
            name = cls._text(names.get(language), 96)
            if name:
                return name
        return None

    @staticmethod
    def _text(value: object, maximum: int, *, upper: bool = False) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.split())[:maximum]
        if not normalized:
            return None
        return normalized.upper() if upper else normalized
