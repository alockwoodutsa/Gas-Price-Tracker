# Fuel Price Ledger

A small Windows desktop app for exploring and storing U.S. weekly gasoline price history. It uses Python's built-in Tkinter interface and SQLite database.

## Run

```powershell
py -m gas_price_tracker
```

To use EIA data, register for a free API key at [EIA Open Data](https://www.eia.gov/opendata/register.php). Copy `.env.example` to `.env` and replace the placeholder with your key, or set `EIA_API_KEY` in your environment. The app loads `.env` from the project root; a process environment variable takes precedence. You can also enter a key in the app for the current run. The `.env` file is ignored by Git.

## Sources

- **EIA** provides weekly U.S. gasoline prices by fuel grade and geography. The app discovers available regions from the API. An API key is required.
- **FRED** provides a second source for weekly U.S. regular gasoline prices. It does not require a key; this series is national regular gasoline only.

Fetched observations are upserted into `%APPDATA%\GasPriceTracker\prices.db` (or `~/.local/share/GasPriceTracker/prices.db` outside Windows). Repeated refreshes update existing weeks rather than duplicating them.

## Tests

```powershell
py -m unittest discover -s tests -v
```