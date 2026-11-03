# Live Captions RU 1.0.3

Real-time Russian captions for Windows, fully offline. This release fixes the way the
tail of a phrase was cut off and moves phrase boundaries onto the model itself.

## What is new

**Fixed: the ends of phrases were being cut off.** The acoustic model needs a little
silence after the last word to emit its final characters. When recognition stopped —
capture stopped, the user paused it, or the audio device changed — the stream was
dropped with no trailing silence, so the last word or the last few letters vanished.
On isolated short phrases this cost a lot: the word «привет» came back empty, «сто
двести» came back as «сто». The measured word error rate on short isolated replies was
47.06%, and 21.49% once 0.6 s of silence was appended. The app now feeds 0.6 s of
silence through the model before dropping, pausing or recreating the stream, and
publishes the completed text to the caption box.

**Added: phrase boundaries come from the model.** A port of the reference T-one
log-probability splitter watches the summed probability of the space and blank tokens
and closes a caption phrase after 0.6 s of silence. Chunks that the energy gate drops
are fed to the splitter as silence, so the timeline has no holes. Caption history now
splits where speech actually stops instead of where loudness drops.

**Added: `LCRU_DEBUG=1`** in the environment raises the log to DEBUG, so phrase
boundaries and gate decisions can be inspected on any machine without a rebuild.

## Measurements

All numbers come from the repository's own test tracks built from OpenSTT telephone
audio, 8 kHz, greedy decoding, one thread per run.

- Phrase boundaries: 8 tracks of real audio with 0.8 s pauses, 6165 reference words.
  Word error rate 7.30% with the splitter and 7.30% without — the splitter changes where
  phrases break, not what is recognised. 426 phrase boundaries were found.
- Resetting the recurrent state on every phrase boundary was measured and rejected:
  word error rate rises to 19.32%, nearly three times worse. The state stays
  continuous, exactly as in the reference pipeline.
- A CTC beam search decoder without any language model was measured and rejected:
  8.89% against 6.60% for plain greedy decoding.
- Logit adjustments (blank penalty, space boost) were measured and rejected: every
  variant was worse than the 6.60% baseline, from 6.64% to 7.24%.
- The resampler was compared against soxr from ffmpeg: 7.31% against 7.38%, so the
  built-in filter stays.

## Install

Take `LiveCaptionsRU-1.0.3-setup.exe` for a normal installation, or
`LiveCaptionsRU-1.0.3-portable.zip` and unpack it anywhere — the 71 M parameter model
is included, nothing is downloaded at runtime.

Requirements: Windows 10 build 17763 or newer, 64-bit; Windows 10 build 19041 or newer
to keep the captions out of screen sharing and screenshots. 2 GB RAM minimum, 4 GB
recommended. The app holds 310-380 MB of working set.

Verify the download against `SHA256SUMS.txt`.

## Known limits

The model alphabet is 33 Russian letters and a space, so numbers arrive as words and
Latin names arrive phonetically. The model is trained on telephone audio; on clean
wideband recordings it is not the best available model, and on heavy background noise
it degrades. A language model would help, but the reference one weighs 5.46 GB and
needs 5.2 GB of RAM, which does not fit the point of this app.
