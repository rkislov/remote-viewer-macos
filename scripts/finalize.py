#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Sign locally, create distribution artifacts, and archive corresponding sources."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
APP = DIST / 'stage/Remote Viewer.app'
VERSION = '11.0-macos.3'
def run(*args): subprocess.run([str(a) for a in args],check=True)

license_dir = APP / 'Contents/Resources/Licenses'
license_dir.mkdir(exist_ok=True)
for name in ['LICENSE','NOTICE','THIRD_PARTY_NOTICES.md']:
    shutil.copy2(ROOT / name, license_dir / name)
for path in json.loads((DIST / 'macho-manifest.json').read_text()):
    run('/usr/bin/codesign','--force','--sign','-','--timestamp=none',APP / path)
run('/usr/bin/codesign','--force','--sign','-','--timestamp=none',APP / 'Contents/Helpers/Remote Viewer Native.app')
run('/usr/bin/codesign','--force','--sign','-','--timestamp=none',APP)
run('/usr/bin/codesign','--verify','--deep','--strict',APP)
base = 'Remote-Viewer-' + VERSION + '-macOS-arm64'
run('/usr/bin/pkgbuild','--root',DIST / 'stage','--identifier','io.github.rkislov.remote-viewer-macos',
    '--version','11.0.3','--install-location','/Applications',DIST / (base + '.pkg'))
dmgroot = DIST / 'dmg-root'
if dmgroot.exists(): shutil.rmtree(dmgroot)
dmgroot.mkdir()
run('/usr/bin/ditto',APP,dmgroot / APP.name)
(dmgroot / 'Applications').symlink_to('/Applications')
shutil.copy2(ROOT / 'INSTALL.txt',dmgroot / 'INSTALL.txt')
dmg = DIST / (base + '.dmg')
if dmg.exists(): dmg.unlink()
run('/usr/bin/hdiutil','create','-volname','Remote Viewer','-srcfolder',dmgroot,'-format','UDZO','-ov',dmg)
run('/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',APP,DIST / (base + '.zip'))
source_name = 'Remote-Viewer-' + VERSION + '-corresponding-source'
source_tree = ROOT / 'build/corresponding-source'
for name in ['src','scripts','patches','assets','licenses']:
    shutil.copytree(ROOT / name,source_tree / 'packaging' / name,dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
for name in ['README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','INSTALL.txt']:
    shutil.copy2(ROOT / name,source_tree / 'packaging' / name)
source_asset = DIST / (source_name + '.tar.gz')
with tarfile.open(source_asset,'w:gz',compresslevel=6) as archive:
    archive.add(source_tree,arcname=source_name)
assets = [DIST / (base+ext) for ext in ['.pkg','.dmg','.zip']] + [source_asset]
(DIST / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in assets))
print('Release assets ready:')
for path in assets: print(path.name, path.stat().st_size)
