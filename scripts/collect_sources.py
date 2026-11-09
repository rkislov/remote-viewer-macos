#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect exact MacPorts source distributions, patches, provenance and notices."""
import concurrent.futures
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
TREE = ROOT / 'build/corresponding-source'
NOTICES = DIST / 'stage/Remote Viewer.app/Contents/Resources/Licenses'
deps = json.loads((DIST / 'dependencies.json').read_text())
TREE.mkdir(parents=True,exist_ok=True)
NOTICES.mkdir(parents=True,exist_ok=True)

def cmd(*args): return subprocess.check_output(args,text=True)

def collect(item):
    name, version = item
    dest = TREE / 'upstream' / name
    dest.mkdir(parents=True,exist_ok=True)
    portdir = pathlib.Path(cmd('/opt/local/bin/port','dir',name).strip())
    port_dest = TREE / 'macports' / name
    shutil.copytree(portdir,port_dest,dirs_exist_ok=True,ignore=shutil.ignore_patterns('work'))
    listing = cmd('/opt/local/bin/port','distfiles',name)
    (dest/'distfiles.txt').write_text(listing.replace(str(pathlib.Path.home()),'$HOME'))
    meta = cmd('/opt/local/bin/port','info','--license','--homepage',name)
    (NOTICES / name).mkdir(exist_ok=True)
    (NOTICES / name / 'PACKAGE.txt').write_text(name+'\n'+json.dumps(version)+'\n'+meta+'\nExact upstream source and MacPorts patches are in the corresponding-source release archive.\n')
    records=[]
    for block in re.split(r'(?m)(?=^\[)',listing)[1:]:
        header=re.match(r'\[([^\]]+)\] (.+)',block)
        if not header: continue
        filename, local = header.groups()
        expected=re.search(r'(?m)^ sha256: ([0-9a-f]+)',block)
        urls=re.findall(r'(?m)^  (https?://\S+)',block)
        target=dest/filename
        localpath=pathlib.Path(local)
        if not target.exists():
            if localpath.is_file(): shutil.copy2(localpath,target)
            else:
                relative=localpath.relative_to('/opt/local/var/macports/distfiles')
                candidates=['https://distfiles.macports.org/'+str(relative)]+urls
                errors=[]
                for url in dict.fromkeys(candidates):
                    try:
                        with urllib.request.urlopen(url,timeout=90) as response: data=response.read()
                        if expected and hashlib.sha256(data).hexdigest()!=expected[1]: raise ValueError('checksum mismatch')
                        target.write_bytes(data)
                        break
                    except Exception as error: errors.append(str(error))
                else: raise RuntimeError(f'{name}/{filename}: {errors}')
        sha=hashlib.sha256(target.read_bytes()).hexdigest()
        if expected and sha!=expected[1]: raise RuntimeError(f'Bad checksum: {target}')
        records.append(dict(file=filename,sha256=sha,urls=urls))
        def keep(path):
            p=pathlib.PurePosixPath(path)
            return len(p.parts)<=4 and bool(re.match(r'(?i)^(copying|copyright|licen[cs]e|notice|authors|readme)([._-].*)?$',p.name))
        def write(path,data):
            if len(data)>2_000_000:return
            out=NOTICES/name/pathlib.Path(*pathlib.PurePosixPath(path).parts[1:])
            if out.name=='':return
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(data)
        if tarfile.is_tarfile(target):
            with tarfile.open(target) as tar:
                for member in tar:
                    if member.isfile() and keep(member.name): write(member.name,tar.extractfile(member).read())
        elif zipfile.is_zipfile(target):
            with zipfile.ZipFile(target) as archive:
                for member in archive.namelist():
                    if not member.endswith('/') and keep(member): write(member,archive.read(member))
    (dest/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
    print(f'Sources and notices: {name} ({len(records)} distfiles)',flush=True)
    return name

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    list(executor.map(collect,sorted(deps.items())))

# Include the changes used for our Quartz builds, not just unmodified upstream.
local = pathlib.Path.home() / 'Library/Application Support/RemoteViewerQuartz'
for name,subdir in [('gtk3','gtk3'),('spice-gtk','spice-gtk'),('libepoxy','libepoxy'),('virt-viewer','virt-viewer')]:
    if name in deps:
        archive=next((p for p in (TREE/'upstream'/name).glob('*') if tarfile.is_tarfile(p)),None)
        if archive:
            (TREE/'modifications'/name).mkdir(parents=True,exist_ok=True)
            for file in ['build-aux/git-version-gen','build-aux/post_install.py','meson.build','subprojects/keycodemapdb/tools/keymap-gen']:
                src=local/subdir/file
                if src.is_file():
                    out=TREE/'modifications'/name/file
                    out.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(src,out)
shutil.copy2(DIST/'dependencies.json',TREE/'dependencies.json')
print('Corresponding sources ready:',TREE)
