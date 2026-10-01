"""Adapters for public fuel-price data sources."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PricePoint:
    source: str
    product: str
    region: str
    period: str
    price: float
    unit: str


@dataclass(frozen=True)
class Facet:
    id: str
    label: str


class PriceProvider(Protocol):
    def fetch_history(self, **options: str) -> list[PricePoint]: ...


class ProviderError(Exception):
    """An upstream price provider could not return usable data."""


class EIAProvider:
    BASE_URL = "https://api.eia.gov/v2/petroleum/pri/gnd"
    PRODUCTS = {
        "Regular gasoline": "EPMR",
        "Midgrade gasoline": "EPMM",
        "Premium gasoline": "EPMP",
        "Diesel": "EPD2",
    }

    def _get_json(self, path: str, params: dict[str, str]) -> dict:
        query = urlencode(params)
        request = Request(f"{self.BASE_URL}/{path}?{query}", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=25) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ProviderError(f"EIA returned HTTP {error.code}: {detail[:240]}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderError(f"Could not reach EIA: {error}") from error

    def list_regions(self, api_key: str) -> list[Facet]:
        result = self._get_json("facet/duoarea/", {"api_key": api_key, "length": "5000"})
        values = result.get("response", {}).get("facets", [])
        facets = [Facet(value["id"], value.get("alias") or value.get("name") or value["id"]) for value in values]
        return sorted(facets, key=lambda item: (item.id != "NUS", item.label.casefold()))

    def fetch_history(self, *, api_key: str, product: str, region: str) -> list[PricePoint]:
        result = self._get_json(
            "data/",
            {
                "api_key": api_key,
                "frequency": "weekly",
                "data[0]": "value",
                "facets[duoarea][0]": region,
                "facets[product][0]": product,
                "facets[process][0]": "R20",
                "sort[0][column]": "period",
                "sort[0][direction]": "asc",
                "length": "5000",
            },
        )
        rows = result.get("response", {}).get("data", [])
        points = []
        for row in rows:
            try:
                points.append(
                    PricePoint(
                        "EIA",
                        product,
                        region,
                        row["period"],
                        float(row["value"]),
                        row.get("value-units", "dollars per gallon"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not points:
            raise ProviderError("EIA returned no prices for that fuel and region.")
        return points


class FREDProvider:
    URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GASREGW"

    def fetch_history(self, **options: str) -> list[PricePoint]:
        request = Request(self.URL, headers={"Accept": "text/csv"})
        try:
            with urlopen(request, timeout=25) as response:
                content = response.read().decode("utf-8-sig")
        except (HTTPError, URLError, TimeoutError) as error:
            raise ProviderError(f"Could not reach FRED: {error}") from error

        reader = csv.DictReader(io.StringIO(content))
        value_column = next((name for name in (reader.fieldnames or []) if name != "observation_date"), None)
        if value_column is None:
            raise ProviderError("FRED returned an unexpected CSV format.")

        points = []
        for row in reader:
            try:
                points.append(
                    PricePoint("FRED", "EPMR", "NUS", row["observation_date"], float(row[value_column]), "dollars per gallon")
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not points:
            raise ProviderError("FRED returned no regular gasoline prices.")
        return points