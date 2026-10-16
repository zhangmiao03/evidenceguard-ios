# Tool package provenance

Imported from the team's `EvidenceGuard_AgentTools_Source_v0.2.0.zip`.
ZIP SHA-256: `818175fe2f43b8ea8f67751d45e51ca3ea1dd2b69a581629b747645f1bd7b434`.

`contracts/camera-tools/{tools,capabilities}.json` and `vendor/camera_tools/catalog.py`
retain the package definitions. `vendor/camera_tools/runtime.py` retains the runtime,
with product patches for field-schema fingerprinting, stop-first claim gating, and
independent execution/stop receipt races. The original standalone HTTP server and
its provisioning tokens are deliberately not mounted in the product.

`gateway.py` and `routes.py` adapt this runtime to the existing FastAPI team access,
installation identities, device registry, Agent runs, and validated live captures.
Only implemented host routes can register. A catalog entry is not an enabled feature.
No official SDK binary or actual credential is included here.
