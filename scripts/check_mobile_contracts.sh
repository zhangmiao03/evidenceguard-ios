#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
check_dir="$(mktemp -d -t evidenceguard-mobile-check)"
trap 'rm -rf "$check_dir"' EXIT
swiftc EvidenceGuard/MobileServiceConfiguration.swift EvidenceGuard/DeviceQRCode.swift Tests/MobileContracts/main.swift -o "$check_dir/check"
"$check_dir/check"
swiftc EvidenceGuard/AppModels.swift Tests/ChatPersistence/main.swift -o "$check_dir/chat-check"
"$check_dir/chat-check"
swiftc -parse-as-library EvidenceGuard/AppModels.swift EvidenceGuard/ReminderSettings.swift Tests/ReminderSettings/main.swift -o "$check_dir/reminder-check"
"$check_dir/reminder-check"
swiftc EvidenceGuard/AppModels.swift Tests/WorkspaceRouting/main.swift -o "$check_dir/workspace-check"
"$check_dir/workspace-check"
