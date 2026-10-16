"""Exercise the actual release archive without production config or media."""
import importlib.util
import json
from pathlib import Path
import tarfile


def test_release_contains_runtime_prompts_but_not_local_reports(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('endpoint_release_package',Path(__file__).with_name('package.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    root=tmp_path/'repository'
    files={
        'Cloud/server/evidenceguard/vision/endpoints.py':'# runtime source',
        'Cloud/server/evidenceguard/vision/prompts/common.md':'fixed prompt fixture',
        'Cloud/server/evidenceguard/vision/UPSTREAM.md':'not a runtime dependency',
        'Cloud/server/evidenceguard/vision/private-report.md':'private-report-canary',
        'Cloud/server/evidenceguard/vision/.env':'private-env-canary',
        'Cloud/server/requirements.txt':'',
        'scripts/run_dashboard.py':'', 'scripts/import_official_web_demo.py':'',
        'Web/dist/index.html':'<main>fixture</main>', 'Web/dist/sdk/index.js':'',
        'Web/dist/sdk/manifest.local.json':'{}', 'Web/dist/official-demo/index.html':'fixture',
        'Web/dist/official-demo/manifest.json':'{}'}
    for name,body in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')
    monkeypatch.setattr(module,'ROOT',root)
    def git(args,**kwargs):
        return 'fixture-revision\n' if kwargs.get('text') else b''
    monkeypatch.setattr(module.subprocess,'check_output',git)
    baseline=tmp_path/'audit.json';baseline.write_text(json.dumps({'remote':{'demo':{},'team':{}}}))
    output=tmp_path/'release.tar.gz';module.package(output,baseline)
    with tarfile.open(output,'r:gz') as archive:
        names=archive.getnames()
        assert 'Cloud/server/evidenceguard/vision/prompts/common.md' in names
        assert not any(name.endswith(('.env','private-report.md','UPSTREAM.md')) for name in names)
        manifest=json.load(archive.extractfile('manifest.json'))
        assert 'Cloud/server/evidenceguard/vision/prompts/common.md' in manifest['files']
        assert archive.extractfile('Cloud/server/evidenceguard/vision/prompts/common.md').read()==b'fixed prompt fixture'
