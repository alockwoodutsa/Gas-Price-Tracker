"""Local SQLite storage for fetched price history."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .providers import PricePoint


class PriceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS prices (
                    source TEXT NOT NULL,
                    product TEXT NOT NULL,
                    region TEXT NOT NULL,
                    period TEXT NOT NULL,
                    price REAL NOT NULL,
                    unit TEXT NOT NULL,
                    PRIMARY KEY (source, product, region, period)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(self, points: list[PricePoint]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO prices (source, product, region, period, price, unit)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, product, region, period) DO UPDATE SET
                    price = excluded.price,
                    unit = excluded.unit
                """,
                [(point.source, point.product, point.region, point.period, point.price, point.unit) for point in points],
            )

    def history(self, source: str, product: str, region: str) -> list[PricePoint]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT source, product, region, period, price, unit
                FROM prices
                WHERE source = ? AND product = ? AND region = ?
                ORDER BY period
                """,
                (source, product, region),
            ).fetchall()
        return [PricePoint(*row) for row in rows]