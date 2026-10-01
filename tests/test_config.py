import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gas_price_tracker.config import load_eia_api_key


class ConfigTests(unittest.TestCase):
    def test_loads_key_from_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("# local API configuration\nOTHER=value\nEIA_API_KEY=\"test-key\"\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_eia_api_key(env_file), "test-key")

    def test_process_environment_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("EIA_API_KEY=file-key\n", encoding="utf-8")
            with patch.dict(os.environ, {"EIA_API_KEY": "process-key"}):
                self.assertEqual(load_eia_api_key(env_file), "process-key")

    def test_missing_file_returns_empty_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_eia_api_key(Path("missing.env")), "")


if __name__ == "__main__":
    unittest.main()