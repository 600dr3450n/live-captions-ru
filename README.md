# Live Captions RU

Real-time Russian captions for Windows. Works fully offline: the audio never leaves
the machine, and no internet connection is used at runtime.

Built for people who find it hard to follow speech — for example when working in a
support queue where the voice comes through a headset all day.

## What it does

- Captures whatever your computer plays on the default output device (loopback) and
  shows it as text in a floating subtitle box.
- Recognises Russian speech locally with the [T-one](https://github.com/voicekit-team/T-one)
  CTC model (71 M parameters, Apache 2.0) running on ONNX Runtime.
- Keeps three text levels: previous phrase, current phrase (with the active word
  highlighted), and the not-yet-confirmed tail — each with its own transparency.
- The caption box is invisible to screen sharing and screenshots
  (`SetWindowDisplayAffinity`), never takes focus, and stays on top.
- Settings are in Russian, apply live, and show the real overlay as a preview.

## Requirements

- Windows 10, version 1809 (build 17763) or newer, or Windows 11, 64-bit. Older
  systems (Windows 8.1, 7, XP) are not supported: the bundled Qt 6 build does not
  start there.
- Windows 10, version 2004 (build 19041) or newer to keep the captions out of
  screenshots and screen sharing; on older builds that protection is unavailable.
- 2 GB RAM minimum, 4 GB recommended. The app itself holds 310-380 MB of working set
  and ~590 MB of private commit, measured over a 9 minute run with the fp32 model,
  so it fits a 2 GB machine next to Windows. The 1024 MB emergency valve only fires
  if the process runs away, roughly 2.7x above the observed peak.
- Any output device; the app follows the system default and reconnects on changes.

## Download

Take the archive from [Releases](../../releases), unpack it anywhere and run
`LiveCaptionsRU.exe`. The model is included, so the first run needs no downloads.

The executable is not code-signed, so Windows SmartScreen may warn on first launch:
choose **More info → Run anyway**.

## Build from source

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # PyInstaller, Pillow, pytest, ruff
python tools/fetch_model.py           # downloads the reference model and verifies SHA-256
python app/main.py                    # run from sources
python tools/build.py --clean         # build dist/LiveCaptionsRU (onedir)

# the installer needs Inno Setup 6.3 or newer:
iscc installer\LiveCaptionsRU.iss     # dist-installer\LiveCaptionsRU-<version>-setup.exe
```

`tools/build.py --onefile` produces a single executable instead; it starts slower
because the bundle is unpacked to a temporary folder on every launch.

The model in `models/t-one/` is the fp32 export described in
[`models/README.md`](models/README.md); `tools/fetch_model.py` downloads the
upstream quantized file, which is smaller and useful for tests but is not the one
the release ships.

`tools/make_icons.py` is not needed for a normal build: `app/icon.ico` and
`app/icon_off.ico` are already in the repository. Run it only to re-render them
after a design change (it needs Pillow).

## How it works

```
output device -> loopback capture -> 300 ms chunks -> T-one ONNX -> CTC decoder -> overlay
```

- **Capture** uses `soundcard` in loopback mode, follows the default device and
  reopens the stream when the device changes.
- **Recognition** feeds 300 ms chunks (8 kHz) into the model together with its
  recurrent state, then decodes CTC log-probabilities with a small custom decoder.
  The decoder is ours on purpose: the sherpa-onnx Python runtime leaked about
  3–4 KB per text read in its `get_result` path (~210 MB/h).
- **Phrase history** keeps the last completed phrases for the top line.
- **Rendering** wraps words, trims the beginning of an overlong line (the end of a
  phrase matters more), and paints outline and backdrop.

Measured on a laptop CPU (2 threads): real-time factor ~0.08, i.e. about ten times
faster than real time; the working set stays at 310-380 MB with the model loaded and
the private commit at ~590 MB, flat over a long run.

## Control

Everything lives in the tray icon menu: **Включить/Выключить субтитры**, **Настройки**
and **Выход**. Global hotkeys are deliberately not used — the program must not take
system key combinations away from other applications.

Three sections: **General** (autostart, device and monitor, service actions),
**Appearance** (position and width, animation, text, transparency, outline, backdrop),
**About**. Changes are previewed immediately; **OK** applies and saves them,
**Cancel** restores the previous values.

## Project layout

```
app/                application code
  main.py           entry point, tray, pipeline wiring
  asr.py            T-one inference and the CTC decoder
  capture.py        loopback capture with reconnect
  overlay.py        caption window, layout and edit mode
  settings_dialog.py, widgets_ui.py, color_dialog.py, theme in main.py
  settings.py       settings model, validation and migrations
  paths.py          folders, autostart, logging setup
tests/              verification scripts (Qt based, run on a real desktop)
tools/              build and model download helpers
assets/             icon
docs/               Russian manual and architecture notes
```

## Tests

The scripts under `tests/` are end-to-end checks: they create real Qt widgets, render
the overlay, start the worker and compare output. Run them one by one on a desktop
session:

```powershell
python tests/verify_v5.py      # appearance, transparency, backdrop
python tests/verify_v7.py      # preview text and segments
python tests/verify_v10.py     # decoder, endpointing, memory (needs the model)
pytest tests/test_mutex.py     # single-instance guard
```

`verify_v10.py` needs `models/t-one/model.onnx`; the rest work without it.

The offline gates take their paths from the environment, so they work outside this
checkout: `LCRU_MODEL_DIR` (default `models/t-one`), `LCRU_GATE_SET` (default
`%TEMP%\gate_set`), `LCRU_GATE_SRC` (a clean 8 kHz mono recording for
`make_gate_set.py`), `LCRU_MAX_CER` (default 0.35). `tests/gate_eval.py` exits with
code 1 when a speech file decodes worse than that threshold and code 2 when the model
or the set is missing, so it can be wired into a check instead of being read by eye.

## Quality

Measured on a laptop CPU with the bundled fp32 model, two threads:

- real-time factor 0.075, i.e. about 13 times faster than real time;
- process memory 359 → 362 MB over a 254-second continuous run, no growth;
- no glued words, no double spaces, no stray characters in the decoded text;
- idle CPU 10-11 % of one core on a silent input, down from 74.7 % before the energy
  gate. Chunks that cannot carry speech never reach the model; the leftover is audio
  capture and resampling. With the gate switched off the decoded text is identical on
  6 of the 8 speech files of the gate set (clean, -12/-20/-28 dB, SNR 15/8/3 dB, 1.5x
  speed, quiet); on the two quietest ones, -34 dB and -40 dB, where the gate drops
  3.4 % and 4.4 % of chunks, 4 and 7 characters out of ~1600 differ, which is a CER of
  0.0025 and 0.0046 against the run without the gate;
- the model itself, not the gate, is what suffers at 2x speed: CER 0.78 against the
  clean reference on `speech_fast_2x.wav`. 1.5x stays at 0.12;
- word error rate 16.4 % on 200 clips from Golos crowd (read speech, many clips are
  one or two words); 13.7 % on phrases from five words; 18.4 % when the same clips go
  through a 300–3400 Hz telephone band with 20 dB of noise. Greedy decoding without a
  language model is the main reason we do not reach the published 6–8 %.

## Privacy

- No network access at runtime, no telemetry, no crash reporting.
- Settings and logs stay on the machine: `%LOCALAPPDATA%\LiveCaptionsRU\`
  (`settings.json`, `app.log`, rotated at 1 MB).
- The log records starts, stops, device changes, settings changes and errors only.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Third-party components and their licenses are listed in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

The T-one model is distributed under Apache 2.0 by T-Bank / T-Software DC and was
converted to ONNX by the sherpa-onnx project. Roboto is distributed under Apache 2.0
by Google. This project is not affiliated with either of them.

## Support

The app is free and stays free. If it is useful to you, you can leave a tip:

[pay.cloudtips.ru/p/318e1bac](https://pay.cloudtips.ru/p/318e1bac)

Author: **600D R3450N** — [github.com/600dr3450n](https://github.com/600dr3450n)
