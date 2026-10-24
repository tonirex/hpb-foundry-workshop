"""The guarded hosted-agent version must also be the version shown by azd."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

path = Path(__file__).resolve().parents[1] / "scripts" / "hosted-postdeploy.py"
spec = importlib.util.spec_from_file_location("hosted_postdeploy", path)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class VersionTracking(unittest.TestCase):
    def test_records_the_guarded_version_under_the_service_key(self):
        with patch.object(hook.shutil, "which", return_value="azd"), \
                patch.object(hook.subprocess, "run", return_value=Mock(returncode=0)) as run:
            hook.record_version("livewell-workshop-hosted", "2")
        self.assertEqual(run.call_args.args[0],
                         ["azd", "env", "set", "AGENT_LIVEWELL_WORKSHOP_HOSTED_VERSION", "2"])
        self.assertEqual(run.call_args.kwargs["env"]["AZURE_DEV_USER_AGENT"], "microsoft_foundry_skill")

    def test_a_failed_local_update_is_not_silent(self):
        with patch.object(hook.subprocess, "run", return_value=Mock(returncode=1, stderr="cannot write environment")):
            with self.assertRaisesRegex(SystemExit, "could not record guarded agent version"):
                hook.record_version("livewell-workshop-hosted", "2")


if __name__ == "__main__":
    unittest.main()
