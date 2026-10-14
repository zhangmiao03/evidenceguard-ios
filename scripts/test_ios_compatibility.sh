#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/check_mobile_contracts.sh
ruby scripts/configure_ui_tests.rb
runtime="$(xcrun simctl list runtimes -j | python3 -c 'import json,sys; r=[x for x in json.load(sys.stdin)["runtimes"] if x.get("isAvailable") and ".iOS-" in x["identifier"]]; r.sort(key=lambda x: tuple(map(int,x["version"].split(".")))); print(r[-1]["identifier"] if r else "")')"
if [[ -z "$runtime" ]]; then echo 'No available iOS Simulator runtime.' >&2; exit 1; fi
simulator="$(xcrun simctl create EvidenceGuardReview com.apple.CoreSimulator.SimDeviceType.iPhone-16 "$runtime")"
trap 'xcrun simctl delete "$simulator" >/dev/null 2>&1 || true' EXIT
xcodebuild -project EvidenceGuard.xcodeproj -scheme EvidenceGuardReview \
  -configuration Debug -destination "platform=iOS Simulator,id=$simulator" \
  -parallel-testing-enabled NO -resultBundlePath CompatibilityResults.xcresult \
  CODE_SIGNING_ALLOWED=NO test
