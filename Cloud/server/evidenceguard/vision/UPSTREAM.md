# SeedLite endpoint-analysis provenance

Source: team handoff `SeedLite_Vision_Kit_20261016_v3_handoff.zip`.
ZIP SHA-256: `5a71fc5ef9c6e5ac1bb07885eb7b22fc5f44fcb0e54e18eac9f73a1b2aa113a4`.
All 219 entries in its manifest matched after extraction on 2026-10-17.

Read: HANDOFF.md, README, common prompt, schemas and evidence validators, runner,
test cases, and both HUMAN-REVIEW reports. Reproduced 28 offline tests with Python
UTF-8 mode; validate-only found 1 ready sample and 28 pending business cases.
Sample prepare-only ran DepthART preprocessing without a cloud model request.

`prompts/common.md` and the three scenario prompts are copied from that archive.
Only common.md is used by the product adapter; scenario prompts remain reference
material. `validation.py` extracts its schema/evidence checks and constant sets;
it has no runtime OpenCV, ONNX or weights dependency. The product adds an explicit
RGB-only/read-only adapter instruction and a SHA-256 version of the combined prompt.

`endpoints.py` is a product adapter, not the offline CLI. It performs one B-condition
call using a confirmed guard's immutable reference/current images, each with a full
view and the same ROI crop. It validates device/channel/view/time/ownership/revision,
retains source-clock meanings, budgets calls, and caches by the exact input context.
It neither imports local file paths from a model nor downloads arbitrary model URLs.

The handoff's synthetic RGB and depth results contain incorrect image directions
and invalid cross-frame depth interpretations. A JSON/constraint pass does not prove
semantic correctness. This result never supplies motor directions, an alarm, a task
state transition, continuous tracking, metric distance, or an identity claim.
DepthART, DIS flow, dual-lens analysis, experiment A/B/C repetition, weights and
unshared real-scene data are deliberately not enabled in the production request path.

Default model example: `doubao-seed-2-1-lite-260915`, requiring explicit endpoint
configuration. Model credentials and private experiment images are not vendored.
