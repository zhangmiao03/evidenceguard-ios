# Tool package provenance

Updated from the team's `EvidenceGuard_AgentTools_Source_v0.3.0.zip` on 2026-10-17.
ZIP SHA-256: `b8ead6aaae62082b32a6b5d46458b6c76b0666ab0bcb328fb59e09a97f02d3e4`.

Source: `EvidenceGuard/output/EvidenceGuard_AgentTools_Source_v0.3.0.zip` in the local workspace.
The package documents 29 tools, 45 capability-matrix entries, and an official
Android-demo baseline. Those baseline records are not product iOS validation.

Imported definitions: `contracts/camera-tools/{tools,capabilities,official-demo-baseline,result-evidence.schema}.json`
and `vendor/camera_tools/{catalog,verification}.py`. The runtime comes from the
same package, retaining product patches for stop-first dispatch, independent
execution/stop receipt races, field fingerprints, and explicit per-field validation.
The standalone server and its provisioning credentials are not mounted.

`gateway.py` / `routes.py` adapt this runtime to the existing team authorization,
installation identities, current visual scenes, legacy task leases, and live captures.
`SDK/Bridge/Tools` imports the bounded PTZ implementation and SDK mappings, preserving
the product's rejection of an unverified preset-stop entry point.

Single-step and continuous PTZ validation are separate. Continuous requests have
a 100–1100 ms application window and a 2500 ms stop-call timeout; neither measures
motor displacement or physical stopping time. Settings are validated per field.
SDK acknowledgement, observed effect, artifact validation, and human review are
separate result fields. A review does not release an unknown lease or authorize
future commands.

The current native player bridge exposes activity callbacks, not verified decoded
frame progression. Consequently it advertises `camera_observe.ready=false`; it
does not synthesize a `decoded_live_frame` proof from bitrate, callback counts, or
`cutImage()`. Ordinary challenged snapshots remain available for observation.
Only a validated decoder-frame envelope can become a v0.3 control reference.

No SDK binary, SDK source, real device credential, or model weight is included here.
