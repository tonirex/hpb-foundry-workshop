"""Builder rail setup check. Run it once after filling content/assets/.env, before Lab 1:

    python content/assets/check_setup.py

Read-only: it signs in, reads the project's tool connections and model deployments, and creates nothing.
Each line prints OK, WARN or FIX (with what to do); the exit code is 1 while anything needs a FIX.
"""
import base64
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
problems = 0


def line(status: str, text: str) -> None:
    global problems
    problems += status == "FIX"
    print(f"  {status:<4} {text}")


print("LiveWell Builder setup check")
v = sys.version_info
line("OK" if v >= (3, 10) else "FIX", f"Python {v.major}.{v.minor} at {sys.executable}"
     + ("" if v >= (3, 10) else " (needs 3.10 or newer)"))

missing = []
for module in ("yaml", "azure.identity", "azure.ai.projects", "openai", "agent_framework"):
    try:
        __import__(module)
    except ImportError:
        missing.append(module)
if missing:
    line("FIX", f"missing packages {', '.join(missing)}: run  pip install -r requirements.txt  from the repo root"
         " (in a Codespace, check that `which python` ends in .venv/bin/python)")
    sys.exit(1)
line("OK", "packages from requirements.txt")
try:
    __import__("ipykernel")
    line("OK", "ipykernel (Run Cell in VS Code)")
except ImportError:
    line("WARN", "ipykernel missing: Run Cell will ask to install it; or run  pip install ipykernel")

sys.path.insert(0, str(HERE))
from common import livewell_common as lw  # noqa: E402

env_file = HERE / ".env"
if env_file.is_file():
    line("OK", "content/assets/.env found")
elif os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or os.environ.get("AZURE_AI_PROJECT_ENDPOINT"):
    line("OK", "no content/assets/.env; using settings from the shell or the azd environment")
else:
    line("FIX", "no content/assets/.env: run  cp content/assets/.env.sample content/assets/.env  and fill it in")

try:
    initials = lw.initials()
    if initials == "abc":
        line("WARN", "INITIALS=abc is the example value; use your own initials so your agents do not clash")
    else:
        line("OK", f"INITIALS={initials}: your agents are livewell-{initials}-<role>")
except SystemExit as e:
    line("FIX", str(e))

try:
    ep = lw.endpoint()
    if re.fullmatch(r"https://[a-z0-9-]+\.services\.ai\.azure\.com/api/projects/[A-Za-z0-9_.-]+", ep):
        line("OK", f"FOUNDRY_PROJECT_ENDPOINT points at project '{ep.rsplit('/', 1)[1]}'")
    else:
        line("FIX", "FOUNDRY_PROJECT_ENDPOINT should look like https://<account>.services.ai.azure.com/api/projects/"
             "<project>: copy the whole 'Project endpoint' row from the values sheet")
except SystemExit as e:
    line("FIX", str(e))

if problems:
    print(f"\n{problems} thing(s) to fix in content/assets/.env first.")
    sys.exit(1)

try:
    token = lw.credential().get_token("https://ai.azure.com/.default").token
    body = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    who = claims.get("upn") or claims.get("preferred_username") or claims.get("unique_name") or "an Azure identity"
    line("OK", f"signed in as {who}")
    # A workshop account lives in one of the workshop tenants (workshop.yaml environments); a work account does not.
    tenants = {str(e.get("tenant_id", "")).lower() for e in lw.config().get("environments", {}).values()} - {"", "todo"}
    if tenants and str(claims.get("tid", "")).lower() not in tenants:
        line("WARN", "not a workshop account: run az logout, then sign in with the workshop account on your sign-in card")
except Exception as e:  # noqa: BLE001
    line("FIX", "not signed in to Azure: run  az login --use-device-code --allow-no-subscriptions  and sign in with "
         f"your workshop account ({type(e).__name__})")
    sys.exit(1)

checks = [("knowledge base", lw.NAMES["kb_mcp_connection"]), ("activities MCP", lw.NAMES["mcp_connection"])]
if lw.fabric_enabled():
    checks.append(("Fabric IQ", lw.NAMES["fabric_connection"]))
for label, name in checks:
    try:
        lw.connection(name)
        line("OK", f"project connection {name} ({label})")
    except Exception as e:  # noqa: BLE001
        status = getattr(e, "status_code", None)
        if status in (401, 403):
            line("FIX", "your account cannot open this project: check the endpoint, or ask a facilitator to add "
                 "you as Foundry User")
            break
        line("FIX", f"project connection {name} ({label}) not found: tell a facilitator ({status or type(e).__name__})")

for model in dict.fromkeys((lw.DEFAULT_MODEL, lw.TOOLS_MODEL)):
    try:
        lw.project().deployments.get(model)
        line("OK", f"model deployment {model}")
    except Exception as e:  # noqa: BLE001
        line("WARN", f"could not read model deployment {model} ({getattr(e, 'status_code', None) or type(e).__name__});"
             " the labs will say if it is really missing")

print("\nAll set: start Lab 1." if not problems else f"\n{problems} thing(s) to fix before Lab 1.")
sys.exit(1 if problems else 0)
