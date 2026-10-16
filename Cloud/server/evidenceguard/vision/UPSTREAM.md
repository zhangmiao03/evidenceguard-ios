# SeedLite endpoint-analysis provenance

Source: team handoff `SeedLite_Vision_Kit_20261016_v3_handoff.zip`.
ZIP SHA-256: `5a71fc5ef9c6e5ac1bb07885eb7b22fc5f44fcb0e54e18eac9f73a1b2aa113a4`.
All 219 entries in its manifest matched after extraction on 2026-10-17.

Read: HANDOFF.md, README, common prompt, schemas and evidence validators, runner,
test cases, and both HUMAN-REVIEW reports. Reproduced 28 offline tests with Python
UTF-8 mode; validate-only found 1 ready sample and 28 pending business cases.
Sample prepare-only ran DepthART preprocessing without a cloud model request.

`prompts/common.md` and the three scenario prompts are copied from that archive.
Only common.md is used by the endpoint adapter; scenario prompts remain reference
material. `validation.py` extracts its schema/evidence checks and constant sets.
The adapter adds a versioned read-only instruction and an optional CPU worker.

`endpoints.py` is a product adapter, not the offline CLI. It performs one B-condition
call using a confirmed guard's immutable reference/current images, each with a full
view and the same ROI crop. It validates device/channel/view/time/ownership/revision,
retains source-clock meanings, budgets calls, and caches by the exact input context.
It neither imports local file paths from a model nor downloads arbitrary model URLs.

The handoff's synthetic RGB and depth results contain incorrect image directions
and invalid cross-frame depth interpretations. A JSON/constraint pass does not prove
semantic correctness. This result never supplies motor directions, an alarm, a task
state transition, continuous tracking, metric distance, or an identity claim.
On 2026-10-17, `processing.py` / `worker.py` adapt the handoff's DepthART448
normalization, DIS forward/backward checks and sparse SIFT cross-check. The worker
is optional, single-concurrency, separately killable and uses pinned weight SHA-256.
It does not run the experiment's nine repeated calls. Flow requires same-device,
same-session, same-view challenged samples within one second, and is skipped on
repeated pixels, shape mismatch or insufficient source evidence. It does not infer
decoder progression from upload sequences. Independent dual-lens geometry remains
unavailable. Relative inverse depth does not become metric distance or motor input.

`control.py` is product orchestration, not a hardware-validated part of the handoff.
It locates a selected target, derives a single image-axis centering step in code,
uses the unchanged v0.3 native proof/validation/confirmation gates, and observes
again after SDK acknowledgement. It never automatically chains a second movement.
The existing iOS manifest still reports camera_observe.ready=false: backend work
cannot manufacture a native decoder callback. See Docs/BACKEND-VISION-ROLLOUT-2026-10-17.md.

Default model example: `doubao-seed-2-1-lite-260915`, requiring explicit endpoint
configuration. `EG_ENDPOINT_PROFILE=video` explicitly selects the currently
configured video provider and current private credential, with no old-key retry.
Model credentials and private experiment images are not vendored. The optional
deployment downloads the pinned author ONNX export; its existing DepthART license
and third-party notices accompany the release under vision-model-licenses/.
