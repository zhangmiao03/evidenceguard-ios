"""Download pinned public ONNX artifacts; no remote Python code is executed."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parent
SPECS = {
    "depthart224": {
        "repo": "Fengxue93/DepthART",
        "revision": "9e154201cd8fb3453c9def581997aaf1b4da3c22",
        "file": "onnx/relative_mnv4m_slim_spf_224_default.onnx",
        "origin": "author ONNX export; MobileNetV4-M-slim-SPF",
    },
    "depthart448": {
        "repo": "Fengxue93/DepthART",
        "revision": "9e154201cd8fb3453c9def581997aaf1b4da3c22",
        "file": "onnx/relative_mnv4m_slim_spf_448_default.onnx",
        "origin": "author ONNX export; MobileNetV4-M-slim-SPF",
    },
    "dav2small": {
        "repo": "onnx-community/depth-anything-v2-small",
        "revision": "4472b7362082ad9968fee890ca0f1e5aca36b93d",
        "file": "onnx/model.onnx",
        "origin": "community ONNX conversion, not official Depth Anything ONNX",
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, dest):
    if dest.exists():
        return
    partial = dest.with_suffix(dest.suffix + ".partial")
    with urllib.request.urlopen(url, timeout=180) as response, partial.open("wb") as out:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            out.write(chunk)
    partial.replace(dest)


def main():
    folder = ROOT / "models"
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    known = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest = {}
    for name, spec in SPECS.items():
        url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{spec['file']}"
        target = folder / f"{name}.onnx"
        print(f"Preparing {name} ...", flush=True)
        recorded = known.get(name, {})
        if target.exists() and all(recorded.get(key) == spec[key] for key in ("repo", "revision", "file")):
            if target.stat().st_size == recorded.get("bytes") and sha256(target) == recorded.get("sha256"):
                manifest[name] = recorded
                print(f"  verified local / Git LFS file, no model network request: {target.name}", flush=True)
                continue
            raise RuntimeError(f"{target.name} does not match manifest; run git lfs pull, or restore the pinned artifact")
        download(url, target)
        # LFS SHA comes from the pinned upstream tree, not from a local guess.
        tree_url = f"https://huggingface.co/api/models/{spec['repo']}/tree/{spec['revision']}/onnx"
        with urllib.request.urlopen(tree_url, timeout=60) as response:
            listing = json.load(response)
        entry = next(row for row in listing if row['path'] == spec['file'])
        expected = entry.get("lfs", {}).get("oid")
        actual = sha256(target)
        if expected and actual != expected:
            raise RuntimeError(f"Upstream SHA256 mismatch: {target.name}")
        manifest[name] = {**spec, "url": url, "sha256": actual,
                          "verified_upstream_sha256": bool(expected),
                          "bytes": target.stat().st_size}
        print(f"  {target.stat().st_size / 1e6:.1f} MB; sha256={actual}", flush=True)
    spec = SPECS['dav2small']
    for filename in ["preprocessor_config.json", "config.json"]:
        download(f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{filename}",
                 folder / f"dav2small-{filename}")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
