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
parser.add_argument('--archive-downloads', action='store_true',
                    help='Download pinned public pod sources from official GitHub archives when git transport is unavailable')
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
if args.archive_downloads:
    env['EG_POD_ARCHIVE_DOWNLOADS'] = '1'
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
runtime = ['export JAVA_HOME=' + shlex.quote(java)]
for name in ['GEM_HOME', 'GEM_PATH', 'BUNDLE_GEMFILE', 'RUBYOPT']:
    if name in env:
        runtime.append('export ' + name + '=' + shlex.quote(env[name]))
runtime.append('export PATH=' + shlex.quote(str(tools_local / 'bin')) + ':"$JAVA_HOME/bin:$PATH"')
(tools_local / 'java.env').write_text('\n'.join(runtime) + '\n')
pod_wrapper = tools_local / 'bin/pod'
pod_wrapper.parent.mkdir(exist_ok=True)
pod_loader = tools_local / 'pod-loader.rb'
loader = ["require 'bundler/setup'"] if bundle.exists() or system_bundle else []
loader.append("require 'cocoapods'")
if args.archive_downloads:
    loader.append('require ' + repr(str(sdk / 'pod_archive_downloads.rb')))
loader.append('load Gem.bin_path("cocoapods", "pod")')
pod_loader.write_text('\n'.join(loader) + '\n')
pod_wrapper.write_text('#!/bin/sh\n. ' + shlex.quote(str(tools_local / 'java.env')) + '\nexec ' +
                       shlex.join(ruby_command + [str(pod_loader)]) + ' "$@"\n')
pod_wrapper.chmod(0o755)
env['PATH'] = str(pod_wrapper.parent) + ':' + env['PATH']
# Kotlin's synthetic CocoaPods project also needs the selected runtime. Keep
# machine-specific paths inside ignored vendor files, never in team sources.
properties = ios / 'kotlin/local.properties'
existing = properties.read_text().splitlines() if properties.exists() else []
existing = [line for line in existing if not line.startswith('kotlin.apple.cocoapods.bin=')]
existing.append('kotlin.apple.cocoapods.bin=' + str(pod_wrapper).replace('\\', '\\\\').replace(' ', '\\ '))
properties.write_text('\n'.join(existing) + '\n')
build_file = common / 'build.gradle.kts'
content = build_file.read_text()
if 'pod("SSZipArchive")' in content:
    build_file.write_text(content.replace('pod("SSZipArchive")', 'pod("SSZipArchive", "2.4.3")'))
bridge = common / 'src/iosArm64Main/kotlin/com/anker/esiotkit/sample/evidenceguard/EvidenceGuardSDKBridge.kt'
bridge.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(sdk / 'Bridge/EvidenceGuardSDKBridge.kt', bridge)
(ios / 'kotlin/gradlew').chmod(0o755)
subprocess.run(ruby_command + [str(sdk / 'configure_project.rb')], cwd=root, env=env, check=True)
subprocess.run([str(ios / 'kotlin/gradlew'), '-p', str(ios / 'kotlin'), ':sample-core:generateDummyFramework', '--console=plain'], cwd=ios, env=env, check=True)
subprocess.run(pod_command + ['install'], cwd=root, env=env, check=True)
print('Open EvidenceGuard.xcworkspace and select EvidenceGuardSDK for your iPhone. No SDK login was performed.')
