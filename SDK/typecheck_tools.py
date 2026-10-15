"""Typecheck the shared tool facade against the supplied Android AAR.

This does not certify iOS linking or any physical device. SDK/prepare.py and the
Mac verification handoff remain required for the actual iPhone SDK target.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import urllib.request
import zipfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--sdk-root',type=Path,required=True)
parser.add_argument('--kotlin-home',type=Path,default=Path('C:/Program Files/Android/Android Studio/plugins/Kotlin/kotlinc'))
parser.add_argument('--java',default='C:/Program Files/Android/Android Studio/jbr/bin/java.exe')
parser.add_argument('--android-sdk',type=Path,default=Path.home()/'AppData/Local/Android/Sdk')
args=parser.parse_args()
out=root/'SDK/.tools-local/typecheck'; out.mkdir(parents=True,exist_ok=True)
aar=args.sdk_root/'ESIotKit-DemoApp-Android/libs/ESIotKit-2.2.7.aar'
jars=[]
with zipfile.ZipFile(aar) as archive:
    for member in archive.namelist():
        if member.endswith('.jar'):
            target=out/Path(member).name; target.write_bytes(archive.read(member)); jars.append(target)
# These are the official demo's pinned versions, used only by the local checker.
for module,version in [('kotlinx-serialization-json-jvm','1.9.0'),('kotlinx-serialization-core-jvm','1.9.0'),('kotlinx-coroutines-core-jvm','1.9.0')]:
    target=out/f'{module}-{version}.jar'
    if not target.exists():
        with urllib.request.urlopen(f'https://repo.maven.apache.org/maven2/org/jetbrains/kotlinx/{module}/{version}/{target.name}',timeout=45) as response:
            target.write_bytes(response.read())
    jars.append(target)
jars+=list((args.kotlin_home/'lib').glob('kotlin-stdlib*.jar'))
jars += [args.kotlin_home/'lib/annotations-13.0.jar',args.android_sdk/'platforms/android-36/android.jar']
sources=sorted((root/'SDK/Bridge/Tools').glob('*.kt'))
command=[args.java,'-cp',str(args.kotlin_home/'lib/*'),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
    '-no-stdlib','-no-reflect','-jvm-target','17','-classpath',os.pathsep.join(map(str,jars)),'-d',str(out/'tools.jar'),*map(str,sources)]
result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
print(result.stdout+result.stderr)
report=dict(check='shared Kotlin facade vs delivered Android AAR',exitCode=result.returncode,
    sdkSha256=hashlib.sha256(aar.read_bytes()).hexdigest(),sources=[p.relative_to(root).as_posix() for p in sources],
    iosLinked=False,hardwareTested=False)
(out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(result.returncode)
