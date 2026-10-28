"""Search region offerings: an empty SKU list blocks new service creation, regardless of quota."""
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
import searchcheck
from searchcheck import advertised_skus


class SearchOfferings(unittest.TestCase):
    def test_actual_and_documented_sku_shapes(self):
        payload = {"regions": [{"regionName": "France Central", "skus": [
            {"name": "basic"}, {"sku": {"name": "standard"}}]}]}
        self.assertEqual(advertised_skus(payload, "francecentral"), {"basic", "standard"})

    def test_capacity_constrained_region_is_empty_not_unknown(self):
        payload = {"regions": [{"regionName": "swedencentral", "skus": []}]}
        self.assertEqual(advertised_skus(payload, "swedencentral"), set())

    def test_existing_search_accepts_arm_display_name_for_location(self):
        cfg = {"environments": {"test": {"search_location": "francecentral", "tenant_id": "tenant",
                                         "subscription_id": "subscription"}},
               "names": {"resource_group": "group", "search_service": "search"}}
        with patch.object(searchcheck.wsconfig, "load", return_value=cfg), patch.object(searchcheck, "Api") as api, \
                patch.object(sys, "argv", ["searchcheck", "--env", "test"]), redirect_stdout(StringIO()):
            api.return_value.get.return_value = {"location": "France Central", "sku": {"name": "basic"}}
            self.assertEqual(searchcheck.main(), 0)
            api.return_value.call.assert_not_called()

    def test_missing_or_ambiguous_data_is_not_mistaken_for_capacity(self):
        for payload in (None, {}, {"regions": []},
                        {"regions": [{"regionName": "francecentral"}]},
                        {"regions": [{"regionName": "francecentral", "skus": [{"unexpected": "shape"}]}]},
                        {"regions": [{"regionName": "francecentral", "skus": []}] * 2}):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "could not verify"):
                advertised_skus(payload, "francecentral")


if __name__ == "__main__":
    unittest.main()
