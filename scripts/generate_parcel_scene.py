#!/usr/bin/env python3
"""Generate owned, visibly synthetic fixtures with FFmpeg. No downloaded footage."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
output = root/'Cloud/server/evidenceguard/fixtures/parcel'
output.mkdir(parents=True,exist_ok=True)
font = next(p for p in [Path('/System/Library/Fonts/Supplemental/Arial.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.is_file())
base = [
    'drawbox=x=0:y=330:w=960:h=210:color=0xb3b8b3:t=fill',
    'drawbox=x=650:y=70:w=245:h=280:color=0x38453e:t=fill',
    'drawbox=x=673:y=90:w=200:h=242:color=0x556258:t=fill',
    'drawbox=x=827:y=218:w=12:h=28:color=0xddd6c6:t=fill',
    'drawbox=x=95:y=85:w=265:h=175:color=0x576c69:t=fill',
    'drawbox=x=108:y=98:w=239:h=149:color=0x95b5b8:t=fill',
    'drawbox=x=210:y=355:w=335:h=145:color=0x268bff:t=4',
]
parcel = [
    'drawbox=x=285:y=349:w=125:h=110:color=0xbe8b53:t=fill',
    'drawbox=x=300:y=365:w=95:h=85:color=0xd2a16b:t=fill',
    'drawbox=x=338:y=349:w=18:h=110:color=0xe8d0a0:t=fill',
    'drawbox=x=310:y=390:w=22:h=28:color=0xf7f5ed:t=fill',
]
for state in ('present','absent','occluded'):
    filters = base + (parcel if state=='present' else [])
    if state=='occluded': filters += ['drawbox=x=175:y=235:w=405:h=290:color=0x465467:t=fill']
    filters += [
        'drawbox=x=0:y=0:w=960:h=52:color=0x152b26:t=fill',
        f"drawtext=fontfile={font}:text='SYNTHETIC TEST - NOT A REAL CAMERA':x=24:y=16:fontsize=24:fontcolor=white",
        f"drawtext=fontfile={font}:text='Discrete samples / no continuous action':x=24:y=511:fontsize=18:fontcolor=0x152b26",
    ]
    subprocess.run(['ffmpeg','-nostdin','-y','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0xd7ded6:s=960x540',
                    '-vf',','.join(filters),'-frames:v','1','-q:v','2',str(output/(state+'.jpg'))],check=True)
print('Generated three owned synthetic images:',output)
