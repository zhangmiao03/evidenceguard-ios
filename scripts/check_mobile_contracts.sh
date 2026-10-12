#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
check_dir="$(mktemp -d -t evidenceguard-mobile-check)"
trap 'rm -rf "$check_dir"' EXIT
swiftc EvidenceGuard/MobileServiceConfiguration.swift EvidenceGuard/DeviceQRCode.swift Tests/MobileContracts/main.swift -o "$check_dir/check"
"$check_dir/check"
swiftc EvidenceGuard/AppModels.swift Tests/ChatPersistence/main.swift -o "$check_dir/chat-check"
"$check_dir/chat-check"
