# Lab 4 shared DevUI: private launch links establish expiring sessions; backend bearer stays server-side.
# Built remotely in ACR by `azd deploy lab4-devui`. The azd prepackage hook (scripts/stage-devui.py) first copies
# the script and the files it reads into ./app with the repo layout, so the same code runs here and on a laptop.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY app/ ./

EXPOSE 80
# DEVUI_AUTH_TOKEN, FOUNDRY_PROJECT_ENDPOINT, AZURE_CLIENT_ID and LIVEWELL_DEVUI_SEATS come from the Container App
# (infra/modules/devui.bicep). A non-loopback host makes the script refuse to start without the token.
CMD ["python", "demos/lab4-devui.py", "--host", "0.0.0.0", "--port", "80", "--no-browser"]
