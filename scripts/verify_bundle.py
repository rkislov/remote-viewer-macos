#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit all bundled dependencies, deployment versions, signatures and loader caches."""
import json
import os
import pathlib
import re
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[1]
app = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else root/'dist/stage/Remote Viewer.app').resolve()
frameworks = app/'Contents/Frameworks'
images = [app/p for p in json.loads((root/'dist/macho-manifest.json').read_text())]
images.append(app/'Contents/MacOS/RemoteViewerLauncher')
for image in images:
    output = subprocess.check_output(['otool','-L',str(image)],text=True)
    for line in output.splitlines()[1:]:
        dependency = line.strip().split(' (compatibility version',1)[0]
        if dependency.startswith(('/usr/lib/','/System/Library/','@rpath/')): continue
        assert dependency.startswith('@loader_path/'), (image,dependency)
        target = (image.parent/dependency.removeprefix('@loader_path/')).resolve()
        assert target.is_relative_to(app) and target.is_file(), (image,dependency)
    load = subprocess.check_output(['otool','-l',str(image)],text=True)
    assert not re.search(r'path (/(opt/local|Users)/[^\n]+) \(offset',load), image
    info = subprocess.check_output(['xcrun','vtool','-show-build',str(image)],text=True)
    for value in re.findall(r'minos (\S+)',info):
        assert tuple(map(int,value.split('.'))) <= (27,2,0), (image,value)
    architectures = subprocess.check_output(['lipo','-archs',str(image)],text=True).strip()
    assert architectures == 'arm64', (image,architectures)
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
env = os.environ.copy()
env.pop('DISPLAY',None)
env.update(GDK_BACKEND='quartz',DYLD_PRINT_LIBRARIES='1',
    XDG_DATA_DIRS=str(app/'Contents/Resources/share'),
    GSETTINGS_SCHEMA_DIR=str(app/'Contents/Resources/share/glib-2.0/schemas'),
    FONTCONFIG_FILE=str(app/'Contents/Resources/fonts.conf'))
executables = [
    ([app/'Contents/Helpers/Remote Viewer Native.app/Contents/MacOS/remote-viewer','--version'],{}),
    ([app/'Contents/Helpers/gdk-pixbuf-query-loaders'],{'GDK_PIXBUF_MODULEDIR':str(app/'Contents/Resources/pixbuf-loaders')}),
    ([app/'Contents/Helpers/gtk-query-immodules-3.0',*sorted((app/'Contents/Resources/immodules').glob('*.so'))],{}),
]
for command, extra in executables:
    result = subprocess.run([str(a) for a in command],env=env|extra,capture_output=True,text=True,check=True)
    loaded = '\n'.join(line for line in result.stderr.splitlines() if line.startswith('dyld['))
    assert '/opt/local/' not in loaded and '/opt/homebrew/' not in loaded, loaded
    assert 'Cannot load loader' not in result.stderr and 'Unable to load' not in result.stderr, result.stderr
    print('OK:',command[0].name)
print(f'PASS: {len(images)} Mach-O images; no external MacPorts/Homebrew dependencies; arm64; macOS <=27.2.')
