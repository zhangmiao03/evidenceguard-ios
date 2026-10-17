#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/check_sdk_host.py
check_dir="$(mktemp -d -t evidenceguard-mobile-check)"
trap 'rm -rf "$check_dir"' EXIT
swiftc EvidenceGuard/MobileServiceConfiguration.swift EvidenceGuard/DeviceQRCode.swift Tests/MobileContracts/main.swift -o "$check_dir/check"
"$check_dir/check"
swiftc EvidenceGuard/SDKConfiguration.swift Tests/SDKConfiguration/main.swift -o "$check_dir/sdk-check"
"$check_dir/sdk-check"
swiftc EvidenceGuard/AppModels.swift Tests/ChatPersistence/main.swift -o "$check_dir/chat-check"
"$check_dir/chat-check"
swiftc -parse-as-library EvidenceGuard/AppModels.swift EvidenceGuard/ReminderSettings.swift Tests/ReminderSettings/main.swift -o "$check_dir/reminder-check"
"$check_dir/reminder-check"
swiftc EvidenceGuard/AppModels.swift Tests/WorkspaceRouting/main.swift -o "$check_dir/workspace-check"
"$check_dir/workspace-check"
swiftc EvidenceGuard/AppModels.swift Tests/AssistantTimeline/main.swift -o "$check_dir/timeline-check"
"$check_dir/timeline-check"
swiftc -parse-as-library EvidenceGuard/AppModels.swift EvidenceGuard/MobileServiceConfiguration.swift EvidenceGuard/ReminderSettings.swift EvidenceGuard/AppStore.swift Tests/AssistantStore/Stubs.swift Tests/AssistantStore/main.swift -o "$check_dir/store-check"
"$check_dir/store-check"

swiftc EvidenceGuard/AppModels.swift Tests/ChatPresentation/main.swift -o "$check_dir/presentation-check"
"$check_dir/presentation-check"

swiftc EvidenceGuard/AppModels.swift Tests/VideoSearch/main.swift -o "$check_dir/video-search-check"
"$check_dir/video-search-check"

swiftc EvidenceGuard/AppModels.swift Tests/EndpointAnalysis/main.swift -o "$check_dir/endpoint-analysis-check"
"$check_dir/endpoint-analysis-check"
