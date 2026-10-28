"""Offline checks for the Navigator's facilitator-prepared OpenAPI connection."""
from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("connect_tools", ROOT / "scripts" / "connect-tools.py")
connect_tools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(connect_tools)


class ProfileConnectionTests(unittest.TestCase):
    target = "https://activities.example.invalid"
    project = "/projects/workshop"
    name = "livewell-profile-openapi"

    def setUp(self):
        self.connection = {"properties": {
            "category": "OpenAPI", "authType": "None", "target": self.target,
            "metadata": {"type": "openapi"}, "isSharedToAll": False,
        }}

    def check(self, connection):
        arm = Mock(spec=["get"])
        arm.get.return_value = connection
        result = connect_tools.check_profile_connection(arm, self.project, self.name, self.target)
        arm.get.assert_called_once_with(
            f"{self.project}/connections/{self.name}?api-version={connect_tools.CONN_API}", ok_404=True)
        return result

    def test_existing_portal_connection_passes_without_changing_sharing(self):
        original = copy.deepcopy(self.connection)
        self.assertEqual(self.check(self.connection), "in sync")
        self.assertEqual(self.connection, original)

    def test_equivalent_trailing_slash_passes(self):
        self.connection["properties"]["target"] += "/"
        self.assertEqual(self.check(self.connection), "in sync")

    def test_missing_connection_requires_manual_preparation(self):
        self.assertIn("missing; facilitator: prepare the Anonymous connection in the portal", self.check(None))

    def test_each_contract_mismatch_fails_readiness(self):
        for key, value in (("category", "RemoteTool"), ("authType", "ProjectManagedIdentity"),
                           ("target", "https://another-environment.example.invalid"),
                           ("metadata", {"type": "custom_MCP"}), ("metadata", None)):
            with self.subTest(key=key, value=value):
                current = copy.deepcopy(self.connection)
                current["properties"][key] = value
                result = self.check(current)
                self.assertIn("drift", result)
                self.assertIn(key, result)
                self.assertIn("facilitator:", result)

    def test_missing_or_malformed_properties_fail_readiness(self):
        for connection in ({}, {"properties": {}}, {"properties": "invalid"}):
            with self.subTest(connection=connection):
                self.assertIn("drift", self.check(connection))

    def test_transport_failure_is_not_reported_as_a_missing_connection(self):
        arm = Mock(spec=["get"])
        arm.get.side_effect = RuntimeError("request failed")
        with self.assertRaisesRegex(RuntimeError, "request failed"):
            connect_tools.check_profile_connection(arm, self.project, self.name, self.target)


if __name__ == "__main__":
    unittest.main()
