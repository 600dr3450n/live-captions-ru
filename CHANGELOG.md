# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-03

First public release. Numbering starts over: pre-public builds were numbered 1.0.1
through 1.0.8, never published as separate releases, and are all folded into this one.
The version below is the first one that counts, and every later change gets its own
entry from here on.

### Changed

- The tray tooltip always shows the program name. It used to report the state
  ("Live Captions RU: Слушаю", "Запускаюсь…") and changed on every status tick;
  the state is carried by the icon and by the menu item instead.
- The built exe carries a version resource, so the Details tab in the file
  properties shows the version, company and description instead of blank fields.

### Fixed

- A pinned output device no longer reopens the capture stream on every poll. The
  device-change check compared the recorded device with the *system default*, which
  they are by definition unequal when a device is pinned in the settings, so the
  recorder was reopened every two seconds and dropped a slice of audio each time.
  A pinned device is now watched for disappearing, and the default is compared with
  the previously observed default.
- Dragging inside the colour picker no longer freezes when the cursor leaves the
  field. Coordinates outside the widget are normal during a drag, and the previous
  code ignored them, so the colour stopped at the last point inside the boundary.
- Long words are broken to the box width instead of running off the plate. A long
  URL, a Latin run or a hyphenated compound used to become a line wider than the
  window, and the part outside was clipped and unreadable.
- The watchdog sees an audio stream that is quiet but not silent. Two different
  thresholds (1e-6 for "silent", 0.01 for "loud") left a band where neither the
  silence timer nor the loud timestamp moved, so a device that delivers sound at a
  low level looked healthy forever and neither the dead-device rule nor the stall
  rule could fire. Both now use one threshold.
- The watchdog baselines are reset with the pipeline. Fresh threads start their
  counters at zero while the stored baselines kept the old values, so every later
  recognition error and dropped block was invisible.
- `0.0` in the statistics is no longer read as "never". `float(x or -1.0)` turned
  "just now" into "never", which made the stall rule see no sound during continuous
  audio and the dead-device rule see a fresh emit as stale.
- A gap in the audio is reported to the worker in more cases: after a reconnect, after
  a device change and after a recovered stream. The state was left set by a previous
  gap, which is why words were still glued occasionally.
- The resampler keeps the filter history between blocks. Filtering each 300 ms block
  on its own pretended the signal started from zero at every boundary; the anti-alias
  kernel also grew from 33 to 129 taps, because 33 taps attenuated 4-5 kHz by only
  9-21 dB and let sibilants fold back into the speech band.
- The plate does not clear in the middle of a phrase when the model stream is reset
  at 4000 characters. The empty text is no longer published; the previous line stays
  on screen until the next real text replaces it.
- An unwritable `LOCALAPPDATA` no longer kills the windowed build before it can show
  a message: the log falls back to the temp directory and then to no file at all.
- A failed `Popen` during the memory-watchdog relaunch keeps the app alive and
  restarts the pipeline instead of leaving a process without a tray icon.
- A failed model load is retried (15 s, 30 s, up to 5 minutes) and the tray reports
  "модель не загрузилась" instead of "Запускаюсь…" forever.
- The pipeline restart runs on a helper thread. Joining a stuck capture thread used to
  freeze the interface for up to six seconds every time the watchdog fired.
- Dragging the plate to a second monitor keeps it there: the geometry is stored
  against the monitor it sits on, that monitor is remembered, and the position is
  clamped to the screen under the pointer instead of the configured one.
- Horizontal padding is part of the box width, the plate is never narrower than the
  two edit buttons need, and the height is clamped to the screen, not only the
  position. "OK" can no longer be drawn outside the window.
- `user32` is loaded with `use_last_error=True`, so the logged `api_error` code is the
  real one instead of 0.
- "Сброс настроек" asks for confirmation and refreshes the device and monitor lists;
  after a reset the dialog used to show the old device while the model had already
  gone back to the system default.
- The installer removes `_internal`, `*.py`, `*.pyc` and `__pycache__` of a previous
  version before copying: a stale module next to the exe is imported first.

### Changed

- `models/README.md` documents both model files honestly: the shipped fp32 export
  (287 475 849 bytes, SHA-256 `4a3827b0…82249e`) and the upstream quantized file
  (`5ded080e…b4dabc`, 144 193 702 bytes) that `tools/fetch_model.py` downloads. The
  old text promised the shipped model *is* the upstream file, which it is not.
- `THIRD-PARTY-NOTICES.md` says the bundled model is a derived work (ONNX export with
  137 of 242 tensors widened from fp16), not the unchanged upstream artifact.
- Tests take their paths from the environment instead of a hardcoded home path;
  `tests/test_mutex.py` actually asserts under pytest, and
  `tests/gate_eval.py` returns an exit code and enforces a CER threshold;
  `gate_features.py` moved to `tools/`: it prints statistics and checks nothing, so it
  does not belong in `tests/`, and it takes the file set from `LCRU_GATE_SET`.
- `tools/make_icons.py` renders into a temporary directory instead of a hardcoded
  user temp path; `requirements-dev.txt` lists Pillow, which
  the icon script needs.
- README no longer promises an unchanged character error rate at 2x speed. Measured
  on the gate set it is 0.78 against the clean reference (1.5x stays at 0.12), and the
  gate itself is documented with the A/B numbers: identical text on 6 of the 8 speech
  files, 4 and 7 characters out of ~1600 differ on the two quietest.
- The resampler now carries the filter history *and* the fractional position of the
  next output sample, so a block-wise run is numerically the same as the one-shot
  reference (max difference 0.0 for 48 kHz and 16 kHz input, 7e-9 for 44.1 kHz;
  the previous per-block filtering differed by 4.9e-2). Verified with a script that
  compares four input rates and checks `reset()` and silence.

## [1.0.7] - 2026-11-02

### Fixed

- Clearing captions on a pause no longer flickers. The `clear_requested` branch reset
  only local variables while the model stream kept its accumulated text, so the whole
  previous line came back 20-40 ms later. Clearing now resets the recognition state,
  and the box really empties once "Задержка очистки субтитров при паузе" elapses
  (verified by a live run: the text does not return).
- No empty backdrop is left behind when the settings dialog is closed after captions
  were switched off from the tray menu. The preview kept the box on screen and turning
  the preview off only cleared the text without hiding the window.
- The watchdog sees recognition failures again. The error counter was never read and
  the handled-block counter did not grow on failures, so a pipeline failing on every
  block looked exactly like a healthy idle one and was never restarted. Errors are now
  counted, restart the pipeline, and dropped capture blocks are logged.
- Recognition no longer glues words across a dropped-audio gap: the first block after
  an overflow is flagged, the model state is reset and `audio_gap` is logged.
- The recognition thread can no longer die silently: the loop body is wrapped in a
  general handler that logs `recognition_worker_crashed`.
- A clear request is honoured with an empty queue: the check moved before the blocking
  audio read, so it no longer waits for the next block or forever when capture stopped.
- Worker statistics are honest: `_publish` no longer increments the block counter.
- Removed the dead `feed_no_read` branch (the method does not exist) and the dead
  phrase-flag handling.
- The capture block size respects the device minimum period: a 20 ms block failed to
  open on some Bluetooth/HDMI/USB endpoints and capture gave up after twenty retries.
- "Сбросить настройки по умолчанию" reloads every control, including font, output
  device and screen: the dialog used to keep the old values while the model held the
  defaults, and OK then restarted the pipeline for nothing.
- A pending preview is no longer applied after Esc or the close button.
- A stored monitor index that does not exist is no longer kept: the list showed the
  first screen while settings kept the old number.
- Field ranges match settings validation: idle clear up to 600 s, highlight from 0.5 s,
  width in pixels from 0 (follow percent) to 4000.
- A half-typed font size no longer disagrees with the field: model and field get the
  same value.
- The preset card loses its selection on a manual edit instead of claiming a style the
  values no longer match.
- Width in pixels in the dialog is computed from the same screen area the box paints
  on, taskbar included in the calculation.
- The colour dialog no longer closes silently with the previous colour on invalid
  input: it explains the format and highlights the field. A click in the gap between
  the saturation square and the hue strip no longer picks black.
- "Открыть журнал событий" in settings reports a missing log and survives a failure to
  open it.
- The recognition status is visible in the tray icon, not only in the tooltip: warn and
  danger states get a coloured dot.
- The Roboto availability check works: the registration result is used, otherwise the
  app honestly falls back to the system font and logs it.

## [1.0.6] — 2026-11-02

### Fixed

- The ready-made minimal style puts the box back on the taskbar. The clamp added in
  1.0.5 used `availableGeometry()`, so a custom position next to the Start button was
  pulled above the taskbar: the style sets `y` from the full screen height on purpose.
  Clamping, snapping while dragging and saving a dragged geometry now all use the full
  screen rectangle; only the automatic positions (top, center, bottom) still respect
  `avoid_taskbar`. While the box overlaps the taskbar the topmost flag is reasserted
  every 0.7 s instead of 5 s, otherwise a click on the taskbar covers the captions.
- With "Включать субтитры при запуске" off the box no longer appears at startup.
  `set_ready()` called `show()` unconditionally once the model was loaded, so the
  backdrop was drawn on an empty, disabled overlay while the tray icon correctly
  showed the off state. Visibility now follows the captions state; the settings
  dialog still shows the box as a preview.
- The log no longer opens on entries from a previous version: `setup_logging()` drops
  `app.log` and its rotated copies when the version in the file differs from the
  running one. The build strips `*.log` and `settings.json` from the package and now
  fails when `app/paths.py` and the installer disagree about the version, so a release
  can neither ship the state of the build machine nor a mismatched version. The
  uninstaller removes the log as well; settings survive on purpose.
- A second copy can no longer start alongside the first one. The self relaunch slept six
  seconds and then skipped the instance check, so a slow shutdown left two pipelines,
  two tray icons and two overlays. The relaunched copy now waits for the single-instance
  mutex for up to 20 s and exits with an explanation if the previous copy is hung.
- A failed pipeline restart had no retry at all: it was scheduled five seconds later and
  the interval check then refused it. Retries follow the same growing delay as the
  restart itself, which now doubles from a minute to ten minutes and is counted afresh
  after half an hour of quiet instead of reloading the model every minute forever.
- The memory watchdog relaunches the process at most twice in a row and then stays with
  a tray notification, so a threshold below the real footprint cannot turn the app into
  a restart loop that never shows a caption.
- Ready-made styles and the percent-to-pixels value in the settings use the monitor the
  box is configured for instead of the primary screen, which put the minimal style on
  the wrong display.
- The autostart checkbox reflects the Run key after the write. A refused write used to
  leave the setting promising autostart until the next start.
- The tray tooltip shows the pipeline status ("Слушаю", "Переподключаю звук", "Ошибка")
  instead of the app name, a dead pipeline forces the off icon, and the icon is rebuilt
  only when its state changes rather than every two seconds.
- "Открыть журнал событий" creates the log when it is missing and logs the failure when
  the viewer cannot be started, instead of silently doing nothing.
- The instance check runs before logging is opened, so a second copy cannot delete the
  log of the running one. The capture thread writes its state under the same lock that
  `stats()` reads it under.

## [1.0.5] — 2026-10-30

### Fixed

- A soft restart can no longer leave two pipelines running. `_restart_pipeline` called
  `join(timeout=3.0)` and never checked `is_alive`, then started a fresh capture and
  worker on the same queue: every chunk would have been decoded twice. A thread that
  does not stop now blocks the restart, and a second blocked attempt escalates to a
  full relaunch, because a thread stuck in native code cannot be joined or killed.
- Exiting the app waits for both threads. `shutdown` only called `stop()` and then
  `QApplication.quit()`, so a worker could emit into an overlay that Qt had already
  destroyed — the random crash on exit. Both threads are joined with a 2 s timeout.
- Self-restart on the memory limit stops the recognition worker too, not only capture,
  so the old process releases the model and the queue before the new one starts.
- Watchdog and status counters are read under a lock in both `capture.stats()` and
  `worker.stats()`. They were read from the GUI thread while the owning thread wrote
  them, which could report "распознавание остановлено" or a stall on a healthy pipeline
  and trigger a restart for nothing.
- Capture no longer retries a dead device forever in silence: after 20 consecutive
  failures (about 20 s) the thread finishes with `state="failed"`, the watchdog sees a
  dead thread and reports it instead of the app hanging with a frozen picture.
- `settings.json` can no longer be lost because of one bad number. `_clamp` swallowed
  `TypeError` and `ValueError` but not `OverflowError`, so a value like `1e400` (which
  json reads as `inf`) raised on `int(inf)` and sent the whole file to quarantine.
- Settings are written atomically: a temp file in the same directory, `fsync`, then
  `os.replace`, and the temp file is removed if anything fails. A crash mid-write used
  to leave a half-written `settings.json` that the loader would quarantine on next start.
- The single-instance mutex handle is kept for the process lifetime instead of being
  dropped on the floor, and a handle belonging to another process is closed rather than
  leaked on every check.
- `app_data_dir()` falls back to the home directory when `LOCALAPPDATA` points somewhere
  unwritable, instead of raising on `mkdir` during startup.
- The overlay cannot park itself off screen any more: custom `x`/`y` saved on another
  monitor or at a different DPI are clamped into the screen rectangle. A session with no
  screens at all gets a virtual 1920x1080 rect instead of `None.availableGeometry()`.
- `user32` is cached with explicit `argtypes`/`restype` and the results of
  `SetWindowPos` and `SetWindowDisplayAffinity` are checked with `GetLastError`, so a
  failed always-on-top or capture-exclusion call is visible in the log instead of silent.
- `text_ready` is connected with an explicit `Qt.QueuedConnection`: the worker thread
  must never call into the overlay directly, and that no longer depends on Qt inferring
  the connection type.
- A zero or negative layout width no longer glues every word onto one endless line:
  `wrap_words` and `wrap_flagged` fall back to one word per line.
- The deferred restart retry does nothing while the app is shutting down, instead of
  waking up after `quit()` and touching destroyed objects.

## [1.0.4] — 2026-10-30

### Fixed

- Phrases no longer jump between the active line and the history line: a boundary
  reported by the model is now confirmed after 0.5 s, and if new text arrives inside
  that window the phrase stays whole instead of splitting. The boundary is also
  published when audio stalls, so a phrase cannot hang half-finished.
- The phrase threshold moved from 0.6 s to 0.9 s of silence. On 11.7 min of real
  conversation 0.6 s produced 122 phrases with 18% shorter than 2 s; 0.9 s produces 78
  phrases with the same recognised text, so the short fragments that looked like a
  stray third of a line are mostly gone. The reference pipeline splits at 0.6 s because
  it cuts audio for batch decoding, which is not the same job as live captions.
- The tray icon was empty in the 1.0.3 build: `tools/build.py` copied the model, the
  fonts and the licence texts but not `icon.ico` / `icon_off.ico`, and the tray loads
  them from disk, so `QIcon` pointed at a missing file and Windows showed a blank slot.
  The build script now ships both files and stops if either is missing, and
  `icons.make_icon` draws the bubble in memory when the files are absent, so a missing
  resource can no longer leave an invisible tray. Covered by tests/verify_tray_icon.py.

## [1.0.3] — 2026-10-29

### Fixed

- The last word is no longer cut off when capture stops, the device changes or the
  user pauses. The streaming model needs right context to emit the final frames of a
  word: fed audio that ends mid-word, it drops the tail. Measured on OpenSTT
  asr_calls_2_val (648 real telephone utterances): 47.06% WER without trailing
  silence, 21.49% with 0.6 s of it. Now 0.6 s of silence is fed through the model
  before the stream is dropped, paused or recreated, and the completed text is
  published to the overlay. Covered by tests/verify_v14.py.

### Added

- Phrase boundaries now come from the model itself. A port of the reference T-one
  log-probability splitter reads the summed probability of the space and blank tokens
  and closes a phrase after 0.6 s of silence, so the caption history splits where
  speech actually stops instead of where loudness drops. Gated-out chunks are fed to
  the splitter as silence, so the timeline stays continuous. Measured on 8 tracks of
  real telephone audio with 0.8 s pauses (6165 reference words): WER 7.30% with the
  splitter, 7.30% without, 426 phrase boundaries found. Resetting the recurrent state
  on each boundary was also measured and rejected: WER jumps to 19.32%, so the state
  stays continuous, as in the reference pipeline. Covered by tests/verify_v15.py.
- `LCRU_DEBUG=1` in the environment raises the log to DEBUG, which is how phrase
  boundaries and gate decisions can be inspected on a user machine without a rebuild.

## [1.0.2] — 2026-10-29

### Changed

- Silence no longer reaches the model. Each 300 ms chunk is decoded only when it can
  carry speech, judged by modulation (cv of 20 ms frame energy) instead of loudness:
  hum, hiss, a tone and digital silence stay flat at cv 0.00-0.05, while speech swings
  at 0.31-0.84 even at RMS 0.0009. Idle CPU on a silent input fell from 74.7% of one
  core to 10.5%, and the garbage text that used to appear in quiet rooms is gone.
- Two guards keep quiet speech intact: a 0.6 s pre-roll is replayed when speech starts,
  and decoding continues for 1.2 s after the last modulated chunk, so a soft onset or
  a trailing syllable is not cut. Verified on real Russian call audio at -12, -20, -28,
  -34 and -40 dB, at SNR 15/8/3 dB, sped up 1.5x and 2x: character error rate against
  the clean transcript is unchanged or better on every variant.
- After 3 s of gated silence the recurrent state is reset, so the first word after a
  pause cannot glue itself to the last one.
- Emergency memory valve lowered from 1500 MB to 1024 MB of working set, still ~2.7x
  the measured peak. README now states 2 GB RAM minimum, 4 GB recommended.

## [1.0.1] — 2026-10-29

Fixes found by live testing on Windows 11 (build 26100) with real call audio.

### Removed

- Global hotkeys (`Ctrl+Alt+H/C/↑/↓/,`). Everything is done from the tray menu, so
  the program no longer takes system key combinations away from other applications.

### Fixed

- Memory watchdog crashed instead of restarting the process (`sys` was never imported).
- A settings.json with wrong value types stopped the app from starting at all; every
  field now falls back to its default and the broken file is kept as
  `settings.json.broken`.
- settings.json saved with a UTF-8 BOM (Notepad) silently reset all settings.
- The settings window could open behind other windows on the first call.
- The "already running" notice could appear behind maximised windows.
- A failed model load raised `NameError` instead of showing the error box.
- Missing `QMessageBox` import on the model-failure path.
- `soundcard` flooded stderr with `data discontinuity` warnings (several per second).
- Resampling to 8 kHz decimated without an anti-alias filter, folding hiss and
  sibilants into the speech band.

### Changed

- Watchdog thresholds follow measurements instead of guesses: text must be absent
  for 60 s while sound is present (was 180 s) to trigger a pipeline restart; the
  memory rule is a single emergency valve at 1500 MB (was 900/1400 MB plus a forced
  restart every 4 hours). Measured footprint: 310-380 MB working set, 592 MB private
  commit, flat over a 9 minute run.
- A soft pipeline restart blinks the tray icon the same way model loading does.
- Autostart checkbox now reflects the actual Run key, so the installer's checkbox and
  the settings cannot disagree.
- Licence texts (`LICENSE`, `NOTICE`, `THIRD-PARTY-NOTICES.md`, `licenses/`) are
  shipped with the build.
- Installer requires Windows 10 1809+ and 64-bit, and warns on builds older than
  2004 where captions cannot be hidden from screen capture.

## [1.0.0] — 2026-10-26

First public release.

### Added

- Live Russian captions for any audio playing on the default output device.
- Fully offline speech recognition on the T-one CTC model through ONNX Runtime.
- Custom CTC decoder with end-of-phrase detection, replacing the sherpa-onnx
  runtime because of a memory leak in its `get_result` path.
- Subtitle overlay excluded from screen capture (`WDA_EXCLUDEFROMCAPTURE`),
  click-through outside the edit mode, always on top.
- Settings window with three sections (General, Appearance, About), live preview
  on the real overlay, OK / Cancel semantics.
- Appearance controls: position, width, line count, font family, size, style,
  line and letter spacing, alignment, colours, three transparency levels,
  outline and backdrop with padding and corner radius.
- Animation settings: active-text highlight duration and idle clear delay.
- Tray menu with exactly three items: toggle captions, settings, quit.
- Autostart at logon, single-instance guard, global hotkeys.
- Compact colour picker with saturation/value field, hue bar and hex input.
- Roboto bundled with the application (Apache 2.0).

### Changed

- Icons are pre-rendered into `icon_on.ico` and `icon_off.ico`; the tray and window
  icons are loaded from files, so they no longer depend on font registration order.
- The model is the real fp32 export: 242 tensors taken from `model.safetensors`,
  137 widened from fp16. Loading is 1.3 s faster and peak memory is 138 MB lower.
- Settings window is 772×600, the colour dialog 232 px wide with a 208×208 field.

### Notes

- The model ships inside the application archive; no internet connection is used
  at runtime.
- Windows SmartScreen may warn about an unsigned executable.
