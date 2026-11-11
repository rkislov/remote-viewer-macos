#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bundle a locally built Quartz SDK and its complete dylib dependency closure."""
import argparse
import hashlib
import json
import os
import pathlib
import plistlib
import re
import shutil
import sqlite3
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = '11.0.4'
TAG = '11.0-macos.4'
parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=pathlib.Path, default=pathlib.Path.home() / 'Library/Application Support/RemoteViewerQuartz/install')
args = parser.parse_args()
SDK = args.sdk.resolve()
DIST = ROOT / 'dist'
STAGE = DIST / 'stage'
APP = STAGE / 'Remote Viewer.app'
C = APP / 'Contents'
R = C / 'Resources'
H = C / 'Helpers'
F = C / 'Frameworks'
N = H / 'Remote Viewer Native.app/Contents'
if STAGE.exists(): shutil.rmtree(STAGE)
for folder in [R, H, F, N / 'MacOS', C / 'MacOS']:
    folder.mkdir(parents=True, exist_ok=True)

def run(*cmd, **kwargs):
    return subprocess.check_output([str(c) for c in cmd], text=True, **kwargs)

def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst

def tree(src, dst):
    shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)

icon = ROOT / 'assets/RemoteViewer.icns'
copy(icon, R / 'RemoteViewer.icns')
copy(icon, N / 'Resources/RemoteViewer.icns')
doc_type = 'io.github.rkislov.remote-viewer-macos.vv'
info = dict(CFBundleExecutable='RemoteViewerLauncher', CFBundleIdentifier='io.github.rkislov.remote-viewer-macos',
    CFBundleName='Remote Viewer', CFBundleDisplayName='Remote Viewer', CFBundlePackageType='APPL',
    CFBundleVersion=VERSION, CFBundleShortVersionString=VERSION, CFBundleIconFile='RemoteViewer.icns',
    LSMinimumSystemVersion='27.2', LSUIElement=True, NSHighResolutionCapable=True,
    CFBundleDocumentTypes=[dict(CFBundleTypeName='Virt Viewer Connection File', CFBundleTypeRole='Viewer',
        LSHandlerRank='Owner', LSItemContentTypes=[doc_type, 'org.macports.remote-viewer.vv'])],
    UTExportedTypeDeclarations=[dict(UTTypeIdentifier=doc_type, UTTypeDescription='Virt Viewer Connection File',
        UTTypeConformsTo=['public.data'], UTTypeTagSpecification={'public.filename-extension':['vv'],
        'public.mime-type':['application/x-virt-viewer']})])
(C / 'Info.plist').write_bytes(plistlib.dumps(info))
(N / 'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleExecutable='remote-viewer',
    CFBundleIdentifier='io.github.rkislov.remote-viewer-macos.ui', CFBundleName='Remote Viewer Native',
    CFBundlePackageType='APPL', CFBundleVersion=VERSION, CFBundleIconFile='RemoteViewer.icns', LSMinimumSystemVersion='27.2', NSHighResolutionCapable=True,
    NSMicrophoneUsageDescription='Forward microphone audio to your connected virtual machine.')))
run('xcrun', 'swiftc', ROOT / 'src/Launcher.swift', '-target', 'arm64-apple-macos27.2', '-o', C / 'MacOS/RemoteViewerLauncher')
images = {}
def image(src, dst):
    src = pathlib.Path(src).resolve()
    if dst.suffix in {'.so', '.dylib'} and dst.parent != F:
        link = dst
        dst = F / dst.name
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(os.path.relpath(dst, link.parent))
    images[dst] = src
    copy(src, dst)

image(SDK / 'bin/remote-viewer', N / 'MacOS/remote-viewer')
for name, source in {
    'gdk-pixbuf-query-loaders': '/opt/local/bin/gdk-pixbuf-query-loaders',
    'gtk-query-immodules-3.0': SDK / 'bin/gtk-query-immodules-3.0',
    'gst-plugin-scanner': '/opt/local/libexec/gstreamer-1.0/gst-plugin-scanner',
}.items(): image(source, H / name)
for source in (SDK / 'lib/gtk-3.0/3.0.0/immodules').glob('*.so'):
    image(source, R / 'immodules' / source.name)
for source in pathlib.Path('/opt/local/lib/gdk-pixbuf-2.0/2.10.0/loaders').glob('*.so'):
    # Keep common image types and SVG icons; skip optional HEIF/TIFF codec trees.
    if source.stem.removeprefix('libpixbufloader-') in {'svg','icns','ico','bmp','gif'}:
        image(source, R / 'pixbuf-loaders' / source.name)
for directory in [pathlib.Path('/opt/local/lib/gstreamer-1.0'), SDK / 'lib/gstreamer-1.0']:
    for source in directory.glob('*.dylib'):
        if source.name not in {'libgstximagesink.dylib','libgstxvimagesink.dylib','libgstcoretracers.dylib','libgstbasedebug.dylib'}:
            image(source, R / 'gstreamer-1.0' / source.name)
tree(SDK / 'share/glib-2.0/schemas', R / 'share/glib-2.0/schemas')
tree(SDK / 'share/locale', R / 'share/locale')
tree(SDK / 'share/icons', R / 'share/icons')
for theme in ['Adwaita','hicolor']:
    source = pathlib.Path('/opt/local/share/icons') / theme
    if source.exists(): tree(source, R / 'share/icons' / theme)
copy('/opt/local/share/curl/curl-ca-bundle.crt', R / 'cert.pem')
(R / 'gio/modules').mkdir(parents=True)
(R / 'fonts.conf').write_text('''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
 <dir>/System/Library/Fonts</dir><dir>/Library/Fonts</dir><dir prefix="xdg">fonts</dir>
 <dir>~/Library/Fonts</dir><cachedir prefix="xdg">fontconfig</cachedir>
 <match target="pattern"><test name="family" qual="any"><string>sans-serif</string></test>
 <edit name="family" mode="prepend"><string>Helvetica</string></edit></match>
</fontconfig>
''')

def deps(path):
    return [line.strip().split(' (compatibility version', 1)[0] for line in run('/usr/bin/otool','-L',path).splitlines()[1:] if line.strip()]

def external(dep): return dep.startswith(('/opt/local/', str(SDK), str(pathlib.Path.home() / '.local/remote-viewer-quartz')))

library_sources = {}
queue = list(images)
for dest in queue:
    source = images[dest]
    for dep in deps(source):
        if not external(dep):
            if dep.startswith('@'):
                raise RuntimeError(f'Unresolved input dependency {dep}: {source}')
            continue
        lib_source = pathlib.Path(dep).resolve()
        lib_dest = F / pathlib.Path(dep).name
        if lib_dest in images:
            if images[lib_dest] != lib_source: raise RuntimeError(f'Conflicting library name {lib_dest.name}')
            continue
        image(lib_source, lib_dest)
        library_sources[lib_dest.name] = lib_source
        queue.append(lib_dest)

for dest, source in images.items():
    subprocess.run(['/usr/bin/codesign','--remove-signature',str(dest)], capture_output=True)
    changes = []
    for dep in deps(source):
        if external(dep):
            relative = os.path.relpath(F / pathlib.Path(dep).name, dest.parent)
            changes += ['-change', dep, '@loader_path/' + relative]
    ids = run('/usr/bin/otool','-D',source).splitlines()
    if len(ids) > 1: changes += ['-id', '@rpath/' + dest.name]
    if changes: run('/usr/bin/install_name_tool', *changes, dest)
    # Absolute build-time rpaths must not leak into the shipped application.
    load = run('/usr/bin/otool','-l',dest)
    for rpath in re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', load):
        if rpath.startswith(('/opt/local/', '/Users/')):
            run('/usr/bin/install_name_tool','-delete_rpath',rpath,dest)

registry = sqlite3.connect('file:/opt/local/var/macports/registry/registry.db?mode=ro', uri=True)
owners = {}
for source in images.values():
    if str(source).startswith('/opt/local/'):
        row = registry.execute('SELECT p.name,p.version,p.revision,p.variants FROM files f JOIN ports p ON p.id=f.id WHERE (f.actual_path=? OR f.path=?) AND f.active=1 LIMIT 1',(str(source),str(source))).fetchone()
        if not row: raise RuntimeError(f'Missing source provenance for {source}')
        owners[row[0]] = dict(version=row[1], revision=row[2], variants=row[3])
for name in ['adwaita-icon-theme','hicolor-icon-theme','curl-ca-bundle']:
    row = registry.execute('SELECT version,revision,variants FROM ports WHERE name=? AND state="installed"',(name,)).fetchone()
    if row: owners[name] = dict(version=row[0], revision=row[1], variants=row[2])
owners.update({name: dict(version=version, revision=0, variants='quartz-local') for name,version in {
    'gtk3':'3.24.52','spice-gtk':'0.43','libepoxy':'1.5.10','virt-viewer':'11.0','gstreamer1-gst-plugins-good':'1.28.8'}.items()})
(DIST / 'dependencies.json').write_text(json.dumps(owners,indent=2)+'\n')
(R / 'dependencies.json').write_text(json.dumps(owners,indent=2)+'\n')
manifest = []
for dest in images:
    for dep in deps(dest):
        if external(dep): raise RuntimeError(f'Unbundled dependency: {dest}: {dep}')
        if dep.startswith('@loader_path/') and not (dest.parent / dep.removeprefix('@loader_path/')).resolve().is_file():
            raise RuntimeError(f'Missing relocated dependency: {dep}')
    manifest.append(str(dest.relative_to(APP)))
(DIST / 'macho-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f'Bundled {len(images)} Mach-O images from {len(owners)} source packages.')
print('Stage:', APP)
print('Next: collect_sources.py, finalize.py')
