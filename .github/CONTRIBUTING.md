# Contributing

Thanks for taking a look at the project. It is a small, focused program: Russian
captions, offline, Windows only. Patches that keep it that way are welcome.

## Before you start

- Open an issue for anything bigger than a typo or a one-line fix, so the approach can be
  agreed before you write code.
- For a security problem use [SECURITY.md](SECURITY.md) instead. Do not open a public
  issue for it.

## Ground rules

- **Comments in the code are minimal and in English.** They explain why, not what. A
  comment that restates the next line gets removed in review.
- **The interface is Russian.** Menu items, dialog labels and messages stay Russian; the
  sources and the documentation are English.
- **No network.** The app must work with the network cable unplugged, so no update
  checks, no telemetry, no crash reporting, no remote fonts or icons.
- **No new runtime dependencies without a reason.** The bundle size and the start time
  are part of the product.
- **Windows only is fine.** The capture path and the screenshot protection are Win32
  APIs, a cross-platform port is not planned.

## Running from sources

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python tools\verify_model.py     # needs the model in models\t-one, see models\README.md
python app\main.py
```

The model is not in the repository because GitHub rejects files above 100 MB. Without it
the app starts and shows nothing; put the file described in
[`models/README.md`](../models/README.md) into `models\t-one` first.

## Checks

The scripts under `tests/` are end-to-end checks that need a real desktop session, so
they cannot run headless in CI. Run the ones that cover your change:

```powershell
python tests\verify_v5.py       # appearance, transparency, backdrop
python tests\verify_v7.py       # preview text and segments
python tests\verify_v10.py      # decoder, endpointing, memory (needs the model)
pytest tests\test_mutex.py      # single-instance guard
ruff check app tests tools
```

Also add a line to [CHANGELOG.md](../CHANGELOG.md) under `Unreleased` for anything a user
can notice.

## Pull requests

- One topic per pull request, with a short description of the behaviour before and after.
- Mention the numbers if the change touches performance, memory or accuracy: the README
  claims are measured, so a change that invalidates them has to update them.
- Say what you ran and what it printed. "Looks fine" is not a test result.
- By submitting a pull request you agree to license your work under Apache 2.0, the same
  terms as the rest of the project.
