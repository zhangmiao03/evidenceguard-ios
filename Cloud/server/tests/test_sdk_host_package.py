import importlib.util
import plistlib
from pathlib import Path

import pytest


_spec = importlib.util.spec_from_file_location(
    "sdk_host_check", Path(__file__).resolve().parents[3] / "scripts/check_sdk_host.py")
host = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(host)


def device_app(tmp_path):
    app = tmp_path / "SDK.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps({"CADisableMinimumFrameDurationOnPhone": True}))
    for relative in ("Frameworks/SampleCore.framework/SampleCore",
                     "Frameworks/AnkerWebRTC.framework/AnkerWebRTC",
                     "compose-resources/composeResources/com.anker.esiotkit.demo.generated.resources/values/strings.cvr"):
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test fixture")
    return app


@pytest.mark.parametrize("flag", [None, False, "YES", 1])
def test_host_rejects_missing_or_non_boolean_compose_flag(flag):
    with pytest.raises(ValueError, match="CADisableMinimumFrameDuration"):
        host.validate_sdk_host({"CADisableMinimumFrameDurationOnPhone": flag})


def test_valid_package_and_missing_framework_or_resources(tmp_path):
    app = device_app(tmp_path)
    host.validate_sdk_app(app)
    resource = next((app / "compose-resources").rglob("*.cvr"))
    resource.unlink()
    with pytest.raises(ValueError, match="resources"):
        host.validate_sdk_app(app)
    resource.write_bytes(b"restored fixture")
    (app / "Frameworks/SampleCore.framework/SampleCore").unlink()
    with pytest.raises(ValueError, match="framework missing"):
        host.validate_sdk_app(app)


@pytest.mark.parametrize("key", ["EGSDKUserID", "EGSDKAuthToken", "EGSDKEnvironment"])
def test_invalid_managed_config_does_not_expose_credential(key):
    info = {"CADisableMinimumFrameDurationOnPhone": True, "EGSDKManagedAccount": "YES",
            "EGSDKUserID": "test-account", "EGSDKAuthToken": "private-test-value", "EGSDKEnvironment": "PR"}
    host.validate_sdk_host(info)
    info[key] = "$(UNRESOLVED)"
    with pytest.raises(ValueError) as error:
        host.validate_sdk_host(info)
    assert "private-test-value" not in str(error.value)
    assert "test-account" not in str(error.value)
