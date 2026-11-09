# Remote Viewer for macOS

<img src="assets/icon.png" width="160" alt="Remote Viewer icon">

A community **virt-viewer 11.0** package using **native GTK Quartz**, with
SPICE-GTK 0.43. No X11/XQuartz server, MacPorts, or Homebrew is needed to run it.

**First release: Apple Silicon, macOS 27.2 or newer only.** Intel Macs and
older macOS versions are not supported by these binaries. The current
MacPorts dependency binaries set this deployment floor; changing an Info.plist
does not make them compatible with older systems.

## Download and install

Download the `.pkg`, `.dmg`, or `.zip` from
[Releases](https://github.com/rkislov/remote-viewer-macos/releases).
The PKG installs `Remote Viewer.app` in `/Applications`. The DMG supports
dragging the app to Applications. SHA256 checksums accompany each release.

The app is **ad-hoc signed, not Developer ID signed or notarized**. macOS may
require **System Settings → Privacy & Security → Open Anyway** on first use.
Verify the source and checksum before making that decision. No global
Gatekeeper changes or quarantine-removal commands are needed.

Right-click a **fresh `.vv` file → Open With → Remote Viewer**.
For the default association, use **Get Info → Open with → Remote Viewer →
Change All**. Installation does not forcibly replace another viewer's defaults.

## Features and limits

- Native macOS window and SPICE console connections, including Proxmox `.vv` files.
- Text clipboard sharing, with the guest SPICE agent installed and running.
- Finder-to-guest file drag and drop; Linux guests normally receive files in
  the desktop user's Downloads folder. Archive folders before transferring.
- Audio auto-detection and CoreAudio modules are bundled. Actual playback,
  microphone capture and USB forwarding have not been validated against a guest.
- A private temporary copy of each `.vv` is opened. After the viewer process
  starts, the original is moved to Trash. Launch failures or a changed source
  leave it in place; connection/authentication failures after launch do not
  restore it. You can recover a file from Trash.
- Logs in `~/Library/Logs/RemoteViewer/`, with connection passwords and Proxmox
  tickets removed. Treat logs as potentially containing hostnames and diagnostics.

Text clipboard and Finder-to-guest file transfer were verified with an ALT Linux
guest. Guest-to-host file drag and drop is not implemented by this package.
This is a SPICE-focused build; VNC, libvirt management, oVirt integration and
the serial/VTE console are disabled.

## Build and package

Requires an Apple Silicon Mac, an appropriate Xcode/Command Line Tools SDK,
Python 3 with venv support, and MacPorts build dependencies. The current
release was built on macOS 27.2. Build dependencies may include X11 libraries;
the resulting app uses Quartz and requires no X11 display server.

```sh
sudo port install gtk3 spice-gtk virt-viewer libepoxy meson ninja pkgconfig \
  gstreamer1-gst-plugins-base py314-parsing
python3 scripts/build-quartz-local.py
python3 scripts/package.py --sdk build/sdk/install
python3 scripts/collect_sources.py
python3 scripts/test_cleanup.py
python3 scripts/finalize.py
python3 scripts/verify_bundle.py
```

`build-quartz-local.py` downloads checksum-pinned sources and builds libepoxy,
GTK Quartz, SPICE-GTK, virt-viewer and the native audio modules into a private
SDK. MacPorts supplies the other dynamically linked dependencies. Set
`RV_BUILD_ROOT` to choose another build directory. Build paths without spaces
are recommended because some upstream scripts assume that convention.

`package.py` recursively copies all non-system Mach-O dependencies, relocates
load paths inside the app, includes dynamic GTK/GStreamer loaders and data,
and records package provenance. It does not modify installed MacPorts libraries.
Source collection fetches the exact dependency distributions and includes their
MacPorts Portfiles, patches, and license notices. `finalize.py` creates PKG,
DMG, ZIP and a corresponding-source archive, and generates `SHA256SUMS`.

`verify_bundle.py` audits architecture, deployment versions, dependency closure,
code signatures and dynamic loader caches. Run it with a copied app path to
verify relocation outside the build tree. Runtime testing on an additional
clean Mac is still recommended before broader deployment.

## Licensing and provenance

The original Swift launcher, packaging scripts, project documentation, and
generated application artwork are licensed under **Apache License 2.0**.
See [LICENSE](LICENSE) and [NOTICE](NOTICE).

This is a distribution of independently licensed components, not an
Apache-only application. Upstream **virt-viewer remains GPL-2.0-or-later**;
GTK, SPICE-GTK and other bundled libraries retain their respective licenses.
The original upstream icon and vendored MacPorts files are also excluded
from the Apache-2.0 grant. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), the application's `Licenses`
directory, and the **corresponding-source archive** in the matching release.

This repository is not affiliated with or endorsed by the virt-viewer,
SPICE, GTK, or MacPorts projects.
