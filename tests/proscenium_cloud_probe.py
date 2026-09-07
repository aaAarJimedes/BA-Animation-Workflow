from __future__ import annotations

import json
from urllib.parse import urlsplit

import bpy

from proscenium_blender import mmcp_client


preferences = bpy.context.preferences.addons["proscenium_blender"].preferences
if bool(getattr(preferences, "self_hosted", False)):
    raise RuntimeError("refusing cloud probe because self-hosted mode is enabled")
if bool(getattr(preferences, "access_token", "")):
    raise RuntimeError("refusing unauthenticated probe because an account token already exists")

base_url = mmcp_client.get_mmcp_url()
parts = urlsplit(base_url)
if parts.scheme != "https" or parts.hostname != "api.animatica.ai" or parts.path.rstrip("/") != "/mmcp":
    raise RuntimeError(f"unexpected hosted endpoint: {base_url}")

status = None
error_code = None
models: list[str] = []
reachable = False
try:
    capabilities = mmcp_client.MmcpClient(base_url, timeout=20).capabilities(refresh=True)
    models = [str(item.get("id", "")) for item in capabilities.get("models", [])]
    reachable = True
    status = 200
except mmcp_client.MmcpError as exc:
    status = exc.status
    error_code = exc.code
    # An authentication response proves DNS, TLS and the hosted HTTP route are
    # reachable without sending credentials. Other statuses are failures.
    reachable = status in {401, 403}

result = {
    "status": "PASS" if reachable else "FAIL",
    "endpoint": base_url,
    "http_status": status,
    "error_code": error_code,
    "public_model_ids": models,
    "signed_in": False,
}
print("PROSCENIUM_CLOUD_PROBE=" + json.dumps(result, ensure_ascii=False))

if not reachable:
    raise RuntimeError(f"hosted endpoint probe failed: HTTP {status}, code={error_code}")
