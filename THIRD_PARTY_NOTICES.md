# Third-party notices

This is a community macOS distribution of **virt-viewer 11.0**, built on
**GTK 3.24.52 with the Quartz backend** and **SPICE-GTK 0.43**.
It is not an official release of the upstream projects.

The launcher and packaging code in this repository is licensed under
GPL-2.0-or-later. Upstream code retains its original copyright and license.
The upstream virt-viewer application and icon are GPL-2.0-or-later;
GTK and SPICE-GTK are LGPL licensed. Other bundled components include
GStreamer, GLib, Cairo, Pango, FreeType, HarfBuzz, OpenSSL, libxml2, and
their dependencies. Their individual license texts and package metadata
are included in `Remote Viewer.app/Contents/Resources/Licenses`.

`dependencies.json` inside the application identifies the versions and
MacPorts variants of the distributed packages. The matching release's
**corresponding-source** archive includes the exact upstream source
distributions, their checksums, MacPorts Portfiles and patches, the modified
build files, and the launcher/packaging source. This archive accompanies
the binaries in every release; it is not merely a link to an upstream website.

Bundled libraries are dynamically linked and can be replaced and relinked.
After modifying a local application, its ad-hoc signature must be regenerated;
no secret signing key is required. The packaging script demonstrates this.
Apple system frameworks are provided by macOS and are not redistributed.

Upstream projects:

- https://virt-manager.org/
- https://www.spice-space.org/
- https://www.gtk.org/
- https://gstreamer.freedesktop.org/
- https://www.macports.org/

The certificate authority bundle originates from curl's Mozilla CA extract;
its source provenance is included with the corresponding sources.

The new application artwork is generated with image_gen and included under
the project license. Its original raster and generation prompt are in `assets/`.
The unmodified upstream icon is retained separately as `assets/virt-viewer.icns`.
