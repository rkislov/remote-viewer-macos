import os, pathlib, subprocess, urllib.request, tarfile, hashlib, shutil, sys

repo = pathlib.Path(__file__).resolve().parents[1]
root = pathlib.Path(os.environ.get('RV_BUILD_ROOT', repo / 'build/sdk')).resolve()
root.mkdir(parents=True, exist_ok=True)
prefix = root / 'install'
alias = pathlib.Path.home() / '.local' / ('remote-viewer-sdk-' + hashlib.sha256(str(root).encode()).hexdigest()[:10])
alias.parent.mkdir(exist_ok=True)
if not alias.is_symlink(): alias.symlink_to(prefix, target_is_directory=True)
assert alias.resolve(strict=False) == prefix
ports = repo / 'patches/macports'
if not (root / 'tooling/bin/python').exists():
    subprocess.run([sys.executable, '-m', 'venv', root / 'tooling'], check=True)
    subprocess.run([root / 'tooling/bin/python', '-m', 'pip', 'install', 'pyparsing==3.3.3'], check=True)
env = os.environ.copy()
env.update(PATH=f'{root}/tooling/bin:/opt/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
           PKG_CONFIG_PATH=f'{prefix}/lib/pkgconfig:/opt/local/lib/pkgconfig:/opt/local/share/pkgconfig',
           CC='/usr/bin/clang', CXX='/usr/bin/clang++')

def run(args, cwd=None):
    print('RUN:', ' '.join(str(a) for a in args), flush=True)
    with (root / 'build.log').open('a') as log:
        result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join((root / 'build.log').read_text(errors='replace').splitlines()[-70:]), flush=True)
        raise SystemExit(result.returncode)

def source(name, url, sha):
    archive = root / url.rsplit('/', 1)[-1]
    if not archive.exists():
        print('Downloading', name, flush=True)
        try:
            urllib.request.urlretrieve(url, archive)
        except Exception:
            if name != 'virt-viewer': raise
            urllib.request.urlretrieve('https://distfiles.macports.org/virt-viewer/virt-viewer-11.0.tar.xz', archive)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == sha, f'Checksum mismatch: {name}'
    dest = root / name
    if not dest.exists():
        dest.mkdir()
        with tarfile.open(archive) as tar:
            top = tar.getnames()[0].split('/')[0]
            tar.extractall(dest, filter='data')
        extracted = dest / top
        for child in extracted.iterdir(): shutil.move(str(child), dest / child.name)
        extracted.rmdir()
    return dest

def patches(src, port, names):
    marker = src / '.macports-patched'
    if marker.exists(): return
    for name in names:
        run(['/usr/bin/patch', '-p0', '-i', ports / port / 'files' / name], cwd=src)
    marker.touch()

def build(src, opts):
    b = src / '_quartz_build'
    if not (b / 'build.ninja').exists():
        run(['meson', 'setup', b, src, '--prefix', prefix, '--libdir', 'lib', '--buildtype=release', '--wrap-mode=nodownload', *opts])
    run(['ninja', '-C', b, '-j6'])
    run(['ninja', '-C', b, 'install'])
    # Some upstream build scripts split pkg-config arguments at spaces.
    for pc in (prefix / 'lib/pkgconfig').glob('*.pc'):
        pc.write_text(pc.read_text().replace(str(prefix), str(alias)))

epoxy = source('libepoxy', 'https://distfiles.macports.org/libepoxy/libepoxy-1.5.10.tar.gz', 'b3e076c5bea209ffa7789cb460d76718be206ccad65a8c915757957c76318376')
build(epoxy, ['-Dx11=false', '-Dglx=no', '-Degl=no', '-Dtests=false', '-Ddocs=false'])

gtk = source('gtk3', 'https://download.gnome.org/sources/gtk/3.24/gtk-3.24.52.tar.xz', '80931fa472a77b9a164f6740e3c0b444fac6770054632d35a7ff9d679e5e7b9f')
patches(gtk, 'gnome/gtk3', ['patch-quartz-calayer-contentsformat.diff', 'patch-quartz-meson-appleframeworks.diff', 'patch-tests-gdkgears.diff', 'patch-sincos.diff', 'patch-focus.patch', 'patch-focus-2.patch'])
build(gtk, ['-Dx11_backend=false', '-Dquartz_backend=true', '-Dwayland_backend=false', '-Dbroadway_backend=false', '-Dxinerama=no', '-Dtests=false', '-Dgtk_doc=false', '-Dman=false', '-Dintrospection=false', '-Ddemos=false', '-Dexamples=false', '-Dprofiler=false'])

spice = source('spice-gtk', 'https://www.spice-space.org/download/gtk/spice-gtk-0.43.tar.xz', 'cee26e5b2d22909f35b40a94398d1e863ca3962ee46494ca97aab206abc3203b')
patches(spice, 'gnome/spice-gtk', ['patch-keymap-gen.diff', 'patch-src-channel-display.diff'])
version_script = spice / 'build-aux/git-version-gen'
version_script.write_text(version_script.read_text().replace('test -f $tarball_version_file', 'test -f "$tarball_version_file"').replace('cat $tarball_version_file', 'cat "$tarball_version_file"'))
keymap = spice / 'subprojects/keycodemapdb/tools/keymap-gen'
keymap.write_text(keymap.read_text().replace('@PYTHON@', '/opt/local/bin/python3.14'))
env['CFLAGS'] = '-D_XOPEN_SOURCE'
build(spice, ['-Dgtk_doc=disabled', '-Dpolkit=disabled', '-Dsasl=disabled', '-Dsmartcard=disabled', '-Dusbredir=enabled', '-Dwebdav=disabled', '-Dintrospection=disabled', '-Dvapi=disabled'])
env.pop('CFLAGS', None)

viewer = source('virt-viewer', 'https://releases.pagure.org/virt-viewer/virt-viewer-11.0.tar.xz', 'a43fa2325c4c1c77a5c8c98065ac30ef0511a21ac98e590f22340869bad9abd0')
patches(viewer, 'emulators/virt-viewer', ['patch-data-meson-build.diff'])
meson = viewer / 'meson.build'
meson.write_text(meson.read_text().replace("'python3', '-c'", "python3, '-c'"))
post_install = viewer / 'build-aux/post_install.py'
post_install.write_text(post_install.read_text().replace('prefix = os.environ["MESON_INSTALL_PREFIX"]', 'prefix = ' + repr(str(alias))))
build(viewer, ['-Dlibvirt=disabled', '-Dvnc=disabled', '-Dspice=enabled', '-Dovirt=disabled', '-Dvte=disabled', '-Dbash_completion=disabled'])
print('BUILD COMPLETE:', prefix / 'bin/remote-viewer', flush=True)
audio = source('gst-plugins-good', 'https://gstreamer.freedesktop.org/src/gst-plugins-good/gst-plugins-good-1.28.8.tar.xz', 'a7670ed900d3d03be744d25c1873b239896e9a82ce6d17f8febc6fffbaee9521')
build(audio, ['-Dauto_features=disabled', '-Dosxaudio=enabled', '-Dautodetect=enabled'])
