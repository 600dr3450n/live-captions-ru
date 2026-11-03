# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-03

First public release.

### Added

- Live Russian captions for the sound the computer plays on its default output device:
  WASAPI loopback capture that follows the default device and reconnects when it changes.
- Local recognition with the T-one CTC model (71 M parameters) on ONNX Runtime, fed with
  300 ms chunks and its own CTC decoder instead of the sherpa-onnx Python runtime.
- Three text levels in the overlay, each with its own transparency: the previous phrase,
  the current phrase with the active word highlighted, and the not yet confirmed tail.
- Caption window that stays on top, never takes focus and is excluded from screen capture
  and screenshots.
- Settings dialog in Russian with a live preview on the real overlay: position, width,
  line count, font, spacing, alignment, colour, transparency, outline and backdrop.
- Energy gate in front of the model. Chunks that cannot carry speech never reach it,
  which brought idle CPU from 74.7 to 10 to 11 percent of one core.
- Self-monitoring: the pipeline restarts after 60 seconds of sound without text, and the
  process relaunches itself above 1024 MB of working set. Both events are logged.
- Offline operation: no network access at runtime, no telemetry, no crash reporting.
- Model checksum verification on every start, and a log that records events but never the
  recognised text.
- Installer that runs without administrator rights, and a portable archive. Both ship the
  speech model inside the package.

[1.0.0]: https://github.com/600dr3450n/live-captions-ru/releases/tag/v1.0.0
