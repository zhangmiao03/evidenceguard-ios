#!/usr/bin/env python3
"""Prepare the organizer's iPhone SDK without connecting a phone or logging in."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess

sdk = Path(__file__).resolve().parent
root = sdk.parent
parser = argparse.ArgumentParser()
parser.add_argument('--tools', type=Path, default=sdk.parents[2] / 'work/anker-sdk-tools')
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
tools = args.tools.resolve()
vendor = sdk / 'Vendor'
ios = vendor / 'ESIotKit-DemoApp-iOS'
common = vendor / 'ESIotKit-DemoApp-Common/sample-core'
java = os.environ.get('JAVA_HOME')
if not java:
    java = next((str(p) for p in tools.glob('zulu*/Contents/Home')), None)
gem_home = tools / 'gems'
bundle = gem_home / 'bin/bundle'
pod = shutil.which('pod')
system_bundle = shutil.which('bundle')
env = dict(os.environ)
if java:
    env.update(JAVA_HOME=java, PATH=str(Path(java) / 'bin') + ':' + os.environ['PATH'])
if bundle.exists():
    env.update(GEM_HOME=str(gem_home), GEM_PATH=str(gem_home), BUNDLE_GEMFILE=str(tools / 'Gemfile'))
    env['RUBYOPT'] = '-rlogger ' + env.get('RUBYOPT', '')
if bundle.exists():
    pod_command = ['ruby', str(bundle), 'exec', 'pod']
    ruby_command = ['ruby', str(bundle), 'exec', 'ruby']
elif system_bundle:
    env['BUNDLE_GEMFILE'] = str(sdk/'Gemfile')
    pod_command = [system_bundle, 'exec', 'pod']
    ruby_command = [system_bundle, 'exec', 'ruby']
else:
    pod_command = [pod] if pod else []
    ruby_command = ['ruby']
pod_ready = bool(pod_command) and subprocess.run(pod_command + ['--version'], cwd=root, env=env,
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
checks = {'Xcode': shutil.which('xcodebuild') is not None,
          'JDK 17': java is not None and (Path(java) / 'bin/java').exists(),
          'CocoaPods': pod_ready,
          'SDK local libraries': (ios / 'libs/ios-kotlin-repo').exists() and (ios / 'libs/ios-frameworks').exists()}
for label, ready in checks.items():
    print(f'{label}: {"available" if ready else "missing"}', flush=True)
if args.check:
    raise SystemExit(0 if all(checks.values()) else 1)
if not all(checks.values()):
    raise SystemExit('Prepare JDK 17 / CocoaPods and keep both vendor folders under SDK/Vendor before continuing.')
tools_local = sdk / '.tools'
tools_local.mkdir(exist_ok=True)
(tools_local / 'java.env').write_text('export JAVA_HOME=' + shlex.quote(java) + '\nexport PATH="$JAVA_HOME/bin:$PATH"\n')
bridge = common / 'src/iosArm64Main/kotlin/com/anker/esiotkit/sample/evidenceguard/EvidenceGuardSDKBridge.kt'
bridge.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(sdk / 'Bridge/EvidenceGuardSDKBridge.kt', bridge)
(ios / 'kotlin/gradlew').chmod(0o755)
subprocess.run(ruby_command + [str(sdk / 'configure_project.rb')], cwd=root, env=env, check=True)
subprocess.run([str(ios / 'kotlin/gradlew'), '-p', str(ios / 'kotlin'), ':sample-core:generateDummyFramework', '--console=plain'], cwd=ios, env=env, check=True)
subprocess.run(pod_command + ['install'], cwd=root, env=env, check=True)
print('Open EvidenceGuard.xcworkspace and select EvidenceGuardSDK for your iPhone. No SDK login was performed.')
