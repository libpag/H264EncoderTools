# Third-Party Software Notices

## x264 (H.264/AVC encoder)

This binary (H264EncoderTools) links statically against **x264**, a free
software library for encoding video streams into the H.264/MPEG-4 AVC format.

- **License**: GNU General Public License version 2 or later (GPL-2.0-or-later)
- **Project page**: https://www.videolan.org/developers/x264.html
- **Source repository**: https://code.videolan.org/videolan/x264

### Build configuration

The x264 library used in this project was built with the following configuration
(parameters aligned with the AE PAGExporter plugin at the parameter level;
x264 library version-level identity has not been independently verified):

- **x264 point version**: 0.165.x
- **x264 API build**: 165
- **GPL build flag**: enabled (`X264_GPL=1`)
- **Evidence**: vendored `x264_config.h` and `x264.h`
- **Exact upstream revision**: not recorded in the vendored headers and must not
  be inferred from the point version alone
- **Target platforms**: macOS x86_64, macOS arm64 (universal via lipo)
- **Notable configure flags**: `--enable-static --disable-cli --bit-depth=8`

### Corresponding source requirement

A release containing H264EncoderTools must include the complete corresponding
x264 source archive used to build the linked static library. The packaging
script treats that archive as a mandatory input and copies it beside this
notice. A generic upstream URL or a source tree from a merely similar tag is
not a substitute for the exact corresponding source.

### Interaction with the main program

The main program (PAGConvertor) does **not** link against libx264 in any form.
H264EncoderTools runs as a separate process communicating through a file-based
protocol, maintaining the Apache-2.0 / GPL license boundary.
