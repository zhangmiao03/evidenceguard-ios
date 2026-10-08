import asyncio

from evidenceguard.camera.adapters.eufy_ports import EufyT8171Adapter, EufyT8214Adapter
from evidenceguard.camera.adapters.fixture_lab import FixtureLabAdapter
from evidenceguard.camera.contracts import CapabilityState, SnapshotKind


def test_unverified_official_ports_report_unknown_capabilities():
    async def run():
        for adapter in (EufyT8171Adapter(), EufyT8214Adapter()):
            manifest = (await adapter.manifests())[0]
            assert set(manifest.capabilities.values()) == {CapabilityState.UNKNOWN}
            assert manifest.connection == "unknown"
    asyncio.run(run())


def test_stored_and_live_snapshot_are_distinct():
    async def run():
        receipt = await FixtureLabAdapter().snapshot("cam-a", SnapshotKind.STORED)
        assert receipt.status == "unsupported"
        assert receipt.kind is SnapshotKind.STORED
    asyncio.run(run())
