"""Verify modern Fabric ontology-context bindings without any cloud calls."""
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "fabric"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("fabric_data_agent_setup", SCRIPTS / "40-data-agent.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class OntologyContext(unittest.TestCase):
    def part(self, stage="published", workspace="ws", ontology="onto"):
        return {f"Files/Config/{stage}/ontologies/resident_ontology/ontology.json":
                {"artifactId": ontology, "workspaceId": workspace, "displayName": "resident_ontology"}}

    def test_matching_published_binding_is_verified(self):
        self.assertTrue(setup.has_ontology_context(self.part(), "published", "ws", "onto"))

    def test_draft_does_not_prove_publication(self):
        self.assertFalse(setup.has_ontology_context(self.part(stage="draft"), "published", "ws", "onto"))

    def test_wrong_workspace_or_ontology_is_not_accepted(self):
        for part in (self.part(workspace="other"), self.part(ontology="other")):
            self.assertFalse(setup.has_ontology_context(part, "published", "ws", "onto"))

    def test_unrelated_or_unstructured_reference_does_not_pass(self):
        for definition in ({}, {"unrelated.json": {"artifactId": "onto", "workspaceId": "ws"}},
                           {"Files/Config/published/ontologies/x/ontology.json": "onto"}):
            self.assertFalse(setup.has_ontology_context(definition, "published", "ws", "onto"))


if __name__ == "__main__":
    unittest.main()
