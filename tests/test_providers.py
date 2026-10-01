import unittest
from unittest.mock import patch

from gas_price_tracker.providers import EIAProvider, FREDProvider, PricePoint


class ProviderTests(unittest.TestCase):
    def test_eia_history_builds_weekly_prices(self):
        provider = EIAProvider()
        payload = {"response": {"data": [{"period": "2025-01-06", "value": "3.129", "value-units": "dollars per gallon"}]}}
        with patch.object(provider, "_get_json", return_value=payload) as request:
            points = provider.fetch_history(api_key="key", product="EPMR", region="NUS")

        self.assertEqual(points, [PricePoint("EIA", "EPMR", "NUS", "2025-01-06", 3.129, "dollars per gallon")])
        self.assertEqual(request.call_args.args[0], "data/")
        self.assertEqual(request.call_args.args[1]["frequency"], "weekly")
        self.assertEqual(request.call_args.args[1]["facets[duoarea][0]"], "NUS")

    def test_fred_csv_parser_skips_missing_values(self):
        provider = FREDProvider()
        response = b"observation_date,GASREGW\n2025-01-06,3.129\n2025-01-13,.\n"

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return response

        with patch("gas_price_tracker.providers.urlopen", return_value=FakeResponse()):
            points = provider.fetch_history()

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].price, 3.129)
        self.assertEqual(points[0].source, "FRED")


if __name__ == "__main__":
    unittest.main()