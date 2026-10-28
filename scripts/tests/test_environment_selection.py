"""Local parameter selection must not provision resources or create access."""
from __future__ import annotations

import contextlib
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
sys.path.insert(0, str(ROOT / "content" / "assets"))
sys.path.insert(0, str(ROOT / "demos"))
import azrest
import wsconfig
from common import livewell_common as lw
import portal

spec = importlib.util.spec_from_file_location("select_params", ROOT / "scripts" / "select-params.py")
select_params = importlib.util.module_from_spec(spec)
spec.loader.exec_module(select_params)


class EnvironmentSelectionTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(select_params, "guard_target", return_value=None)
        principal = patch.object(select_params, "principal_from_token", return_value=None)
        self.guard_target = guard.start()
        self.principal_from_token = principal.start()
        self.addCleanup(guard.stop)
        self.addCleanup(principal.stop)

    def test_parameters_only_does_not_call_azure_or_create_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            infra = Path(directory).resolve()
            (infra / "env").mkdir()
            source = "using '../main.bicep'\nparam environmentName = 'mcaps'\n"
            (infra / "env" / "mcaps.bicepparam").write_text(source, encoding="utf-8")
            with patch.object(select_params, "INFRA", infra), patch.dict(os.environ, {"AZURE_ENV_NAME": "mcaps"}, clear=True):
                with patch.object(sys, "argv", ["select-params.py", "--parameters-only"]):
                    with patch.object(select_params, "run", side_effect=AssertionError("no external commands allowed")):
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(select_params.main(), 0)
                            self.assertEqual(select_params.main(), 0)
                self.assertNotIn("LIVEWELL_DEVUI_TOKEN", os.environ)
                self.assertNotIn("AZURE_PRINCIPAL_ID", os.environ)
            generated = (infra / "main.bicepparam").read_text(encoding="utf-8")
            self.assertIn("from infra/env/mcaps.bicepparam", generated)
            self.assertIn("using 'main.bicep'", generated)
            self.assertEqual((infra / "env" / "mcaps.bicepparam").read_text(encoding="utf-8"), source)
        self.guard_target.assert_not_called()
        self.principal_from_token.assert_not_called()

    def test_preprovision_hook_still_rejects_a_stale_parameter_file(self):
        with tempfile.TemporaryDirectory() as directory:
            infra = Path(directory).resolve()
            (infra / "env").mkdir()
            (infra / "env" / "mcaps.bicepparam").write_text("using '../main.bicep'\n", encoding="utf-8")
            with patch.object(select_params, "INFRA", infra), patch.dict(os.environ, {"AZURE_ENV_NAME": "mcaps"}, clear=True):
                with patch.object(sys, "argv", ["select-params.py", "--hook"]):
                    with patch.object(select_params, "run", side_effect=AssertionError("must stop before Azure calls")):
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(select_params.main(), 1)

    def test_missing_subscription_cannot_use_cli_default(self):
        with tempfile.TemporaryDirectory() as directory:
            infra = Path(directory).resolve()
            (infra / "env").mkdir()
            (infra / "env" / "mcaps.bicepparam").write_text("using '../main.bicep'\n", encoding="utf-8")
            with patch.object(select_params, "INFRA", infra), patch.dict(os.environ, {"AZURE_ENV_NAME": "mcaps"}, clear=True):
                with patch.object(sys, "argv", ["select-params.py"]), patch.object(select_params, "run") as run:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(select_params.main(), 1)
                    run.assert_not_called()
                    self.assertIn("refusing to use the CLI's unrelated default", output.getvalue())

    def test_principal_lookup_is_scoped_and_restored_devui_token_is_not_rotated(self):
        for kind in ("user", "servicePrincipal"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                infra = Path(directory).resolve()
                (infra / "env").mkdir()
                (infra / "env" / "mcaps.bicepparam").write_text("using '../main.bicep'\n", encoding="utf-8")
                env = {"AZURE_ENV_NAME": "mcaps", "AZURE_SUBSCRIPTION_ID": "selected-subscription",
                       "LAB4_DEVUI_APP_NAME": "existing-devui"}

                def run(cmd):
                    if cmd[:3] == ["az", "account", "show"]:
                        return json.dumps({"user": {"type": kind, "name": "selected-app"}})
                    if cmd[:3] == ["azd", "env", "set"]:
                        return ""
                    self.fail(f"Unexpected command: {cmd}")

                with patch.object(select_params, "INFRA", infra), patch.dict(os.environ, env, clear=True):
                    with patch.object(sys, "argv", ["select-params.py"]):
                        with (patch.object(select_params, "run", side_effect=run) as calls,
                              patch.object(select_params.azrest, "Api") as api):
                            api.return_value.get.return_value = {"id": "selected-principal"}
                            with patch.object(select_params.secrets, "token_urlsafe") as token:
                                with contextlib.redirect_stdout(io.StringIO()) as output:
                                    self.assertEqual(select_params.main(), 1)
                                token.assert_not_called()
                                self.assertIn("Restore its token privately", output.getvalue())
                            api.assert_called_once_with("graph", subscription="selected-subscription")
                            expected_path = ("/v1.0/servicePrincipals(appId='selected-app')?$select=id"
                                             if kind == "servicePrincipal" else "/v1.0/me?$select=id")
                            api.return_value.get.assert_called_once_with(expected_path)
                            commands = [call.args[0] for call in calls.call_args_list]
                            for cmd in (cmd for cmd in commands if cmd[0] == "az"):
                                self.assertEqual(cmd[cmd.index("--subscription") + 1], env["AZURE_SUBSCRIPTION_ID"])
                            self.assertIn(["azd", "env", "set", "AZURE_PRINCIPAL_ID", "selected-principal"], commands)
                            self.assertFalse(any("LIVEWELL_DEVUI_TOKEN" in cmd for cmd in commands))

    def test_missing_graph_identity_stops_before_writing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            infra = Path(directory).resolve()
            (infra / "env").mkdir()
            (infra / "env" / "mcaps.bicepparam").write_text("using '../main.bicep'\n", encoding="utf-8")
            env = {"AZURE_ENV_NAME": "mcaps", "AZURE_SUBSCRIPTION_ID": "selected-subscription"}
            with patch.object(select_params, "INFRA", infra), patch.dict(os.environ, env, clear=True):
                with patch.object(sys, "argv", ["select-params.py"]):
                    with (patch.object(select_params, "run", return_value='{"user":{"type":"user"}}') as run,
                          patch.object(select_params.azrest, "Api") as api):
                        api.return_value.get.return_value = {}
                        with contextlib.redirect_stdout(io.StringIO()) as output:
                            self.assertEqual(select_params.main(), 1)
                        self.assertIn("returned no principal ID", output.getvalue())
                        self.assertEqual(run.call_count, 1)
                        self.assertNotIn("AZURE_PRINCIPAL_ID", os.environ)

    def test_fabric_check_uses_selected_subscription_and_surfaces_failure(self):
        with patch.dict(os.environ, {"FABRIC_BRIDGE": "true"}, clear=True):
            with patch.object(select_params, "run", return_value="capacity\tActive") as run:
                self.assertTrue(select_params.fabric_capacity_updatable("workshop", "selected-subscription", "mcaps"))
                cmd = run.call_args.args[0]
                self.assertEqual(cmd[cmd.index("--subscription") + 1], "selected-subscription")
                self.assertNotIn("check", run.call_args.kwargs)
            with patch.object(select_params, "run", side_effect=SystemExit("authorization failed")):
                with self.assertRaisesRegex(SystemExit, "authorization failed"):
                    select_params.fabric_capacity_updatable("workshop", "selected-subscription", "mcaps")


class EnvironmentNamesTests(unittest.TestCase):
    def test_mcaps_names_override_only_three_defaults(self):
        base = wsconfig.load()["names"]
        expected = wsconfig.subst(base, "mcaps")
        expected.update(foundry_account="aif-hpb-livewell-mcaps", search_service="srch-hpb-livewell-mcaps",
                        fabric_capacity="fabhpblivewellmcaps")
        self.assertEqual(wsconfig.load("mcaps")["names"], expected)
        self.assertEqual(wsconfig.load()["names"], base)

    def test_sponsor_names_and_unselected_templates_are_unchanged(self):
        base = wsconfig.load()["names"]
        self.assertIn("<env>", base["foundry_account"])
        self.assertEqual(wsconfig.load("sponsor")["names"], wsconfig.subst(base, "sponsor"))

    def test_cli_and_builder_read_effective_names(self):
        with patch.object(sys, "argv", ["wsconfig.py", "get", "names.foundry_account", "--env", "mcaps"]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(wsconfig.main(), 0)
            self.assertEqual(output.getvalue().strip(), "aif-hpb-livewell-mcaps")
        with patch.object(lw, "_azd_env_name", return_value="mcaps"):
            self.assertEqual(lw.config.__wrapped__()["names"], wsconfig.load("mcaps")["names"])

    def test_invalid_name_overrides_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            for overrides in ([], {"typo": "name"}, {"foundry_account": None}, {"foundry_account": ""}):
                with self.subTest(overrides=overrides):
                    path.write_text(json.dumps({"names": {"foundry_account": "base"},
                                                "environments": {"mcaps": {"names": overrides}}}), encoding="utf-8")
                    with patch.object(wsconfig, "CONFIG", path), self.assertRaises(ValueError):
                        wsconfig.load("mcaps")

    def test_devui_build_context_includes_config_loader(self):
        module_spec = importlib.util.spec_from_file_location("stage_devui", ROOT / "scripts" / "stage-devui.py")
        stage = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(stage)
        self.assertIn("scripts/lib/wsconfig.py", stage.FILES)

    def test_values_sheet_pins_tenant_and_never_exposes_a_backend_token(self):
        module_spec = importlib.util.spec_from_file_location("render_values", ROOT / "scripts" / "render-values.py")
        render = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(render)
        values = {"AZURE_AI_PROJECT_ID": "selected-project", "AZURE_TENANT_ID": "selected-tenant",
                  "LAB4_DEVUI_APP_NAME": "existing-devui"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content" / "config").mkdir(parents=True)
            with patch.object(render, "ROOT", root), patch.object(render, "read_env", return_value=values):
                with patch.object(sys, "argv", ["render-values.py", "mcaps"]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(render.main(), 0)
            text = (root / "content" / "config" / "values.md").read_text(encoding="utf-8")
            self.assertIn("wsid=selected-project&tid=selected-tenant", text)
            self.assertIn("| Lab 4 private launch link (no token entry) | (not yet provisioned) |", text)
            self.assertNotIn("| Lab 4 DevUI token", text)
            self.assertNotIn("containerapp secret", text)


class CredentialScopeTests(unittest.TestCase):
    @staticmethod
    def token_for(tenant):
        payload = base64.urlsafe_b64encode(json.dumps({"tid": tenant}).encode()).decode().rstrip("=")
        return f"header.{payload}.signature"

    def test_cli_credentials_use_subscription_and_managed_identity_still_wins(self):
        identity = types.ModuleType("azure.identity")
        for name in ("AzureCliCredential", "AzureDeveloperCliCredential", "ChainedTokenCredential",
                     "ManagedIdentityCredential"):
            setattr(identity, name, Mock())
        try:
            with patch.dict(sys.modules, {"azure": types.ModuleType("azure"), "azure.identity": identity}):
                env = {"AZURE_SUBSCRIPTION_ID": "selected-subscription", "AZURE_TENANT_ID": "selected-tenant"}
                with patch.dict(os.environ, env, clear=True):
                    lw.credential.cache_clear()
                    lw.credential()
                    identity.AzureCliCredential.assert_called_once_with(subscription="selected-subscription")
                    identity.AzureDeveloperCliCredential.assert_called_once_with(tenant_id="selected-tenant")
                identity.AzureCliCredential.reset_mock()
                with patch.dict(os.environ, {"AZURE_TENANT_ID": "selected-tenant"}, clear=True):
                    lw.credential.cache_clear()
                    lw.credential()
                    identity.AzureCliCredential.assert_called_once_with(tenant_id="selected-tenant")
                identity.AzureCliCredential.reset_mock()
                with patch.dict(os.environ, {**env, "IDENTITY_ENDPOINT": "local-identity", "AZURE_CLIENT_ID": "devui"}, clear=True):
                    lw.credential.cache_clear()
                    lw.credential()
                    identity.ManagedIdentityCredential.assert_called_once_with(client_id="devui")
                    identity.AzureCliCredential.assert_not_called()
        finally:
            lw.credential.cache_clear()

    def test_rest_tokens_use_selected_subscription(self):
        token = self.token_for("selected-tenant")
        result = types.SimpleNamespace(returncode=0, stdout=token + "\n")
        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": "selected-subscription"}, clear=True):
            with patch.object(azrest, "run_az", return_value=result) as run:
                self.assertEqual(azrest.az_token("fabric", "selected-tenant"), token)
                cmd = run.call_args.args[0]
                self.assertEqual(cmd[cmd.index("--subscription") + 1], "selected-subscription")
                self.assertNotIn("--tenant", cmd)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(azrest, "run_az", return_value=result) as run:
                azrest.az_token("fabric", "selected-tenant")
                cmd = run.call_args.args[0]
                self.assertEqual(cmd[cmd.index("--tenant") + 1], "selected-tenant")
                self.assertNotIn("--subscription", cmd)

    def test_explicit_api_subscription_overrides_process_default(self):
        result = types.SimpleNamespace(returncode=0, stdout=self.token_for("selected-tenant") + "\n")
        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": "unrelated-subscription",
                                    "AZURE_TENANT_ID": "unrelated-tenant"}, clear=True):
            with patch.object(azrest, "run_az", return_value=result) as run:
                azrest.Api("arm", tenant="selected-tenant", subscription="selected-subscription")
                cmd = run.call_args.args[0]
                self.assertEqual(cmd[cmd.index("--subscription") + 1], "selected-subscription")
                self.assertNotIn("--tenant", cmd)

    def test_wrong_tenant_claim_still_blocks_an_explicit_subscription(self):
        result = types.SimpleNamespace(returncode=0, stdout=self.token_for("other-tenant") + "\n")
        with patch.dict(os.environ, {}, clear=True), patch.object(azrest, "run_az", return_value=result):
            with self.assertRaisesRegex(SystemExit, "refusing to call"):
                azrest.Api("arm", tenant="selected-tenant", subscription="selected-subscription")

    def test_knowledge_cli_wrapper_requires_and_passes_subscription(self):
        module_spec = importlib.util.spec_from_file_location("build_kb", ROOT / "scripts" / "build-kb.py")
        build = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(build)
        with patch.object(build.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout="name")) as run:
            self.assertEqual(build.az("storage", "account", "show", subscription="selected-subscription"), "name")
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[cmd.index("--subscription") + 1], "selected-subscription")
            with self.assertRaises(TypeError):
                build.az("storage", "account", "show")

    def test_portal_account_uses_selected_subscription(self):
        result = types.SimpleNamespace(returncode=0, stdout="selected-user\n")
        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": "selected-subscription"}, clear=True):
            with patch.object(portal, "_ACCOUNT", None), patch("shutil.which", return_value="az"):
                with patch("subprocess.run", return_value=result) as run:
                    self.assertEqual(portal.portal_account(), "selected-user")
                    cmd = run.call_args.args[0]
                    self.assertEqual(cmd[cmd.index("--subscription") + 1], "selected-subscription")

    def test_explicit_portal_account_needs_no_cli_lookup(self):
        with patch.dict(os.environ, {"LIVEWELL_PORTAL_ACCOUNT": "chosen-user"}, clear=True):
            with patch.object(portal, "_ACCOUNT", None), patch("subprocess.run") as run:
                self.assertEqual(portal.portal_account(), "chosen-user")
                run.assert_not_called()

    def test_portal_links_pin_tenant_without_losing_agent_version(self):
        with patch.object(portal, "project_segment", return_value="selected-project"):
            with patch.dict(os.environ, {"AZURE_TENANT_ID": "selected-tenant"}, clear=True):
                for route in ("home", "project", "agents", "/build/tools", "agent:demo@2"):
                    with self.subTest(route=route):
                        query = parse_qs(urlsplit(portal.url(route)).query)
                        self.assertEqual(query["tid"], ["selected-tenant"])
                        if route.startswith("agent:"):
                            self.assertEqual(query["version"], ["2"])
            with patch.dict(os.environ, {}, clear=True):
                self.assertNotIn("tid=", portal.url("project"))

    def test_failed_portal_lookup_is_not_silently_cached(self):
        results = [types.SimpleNamespace(returncode=1, stdout="", stderr="account unavailable"),
                   types.SimpleNamespace(returncode=0, stdout="selected-user")]
        with patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": "selected-subscription"}, clear=True):
            with patch.object(portal, "_ACCOUNT", None), patch("shutil.which", return_value="az"):
                with patch("subprocess.run", side_effect=results) as run:
                    with self.assertRaisesRegex(SystemExit, "account unavailable"):
                        portal.portal_account()
                    self.assertEqual(portal.portal_account(), "selected-user")
                    self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
