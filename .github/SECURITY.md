# Security policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | Yes       |

Fixes go into the latest release only. There is no maintenance branch for older builds.

## Reporting a vulnerability

Report privately through GitHub: open the **Security** tab of the repository and use
**Report a vulnerability**, which creates a draft security advisory visible only to you
and the maintainer. Please do not open a public issue for a security problem.

Include what you can:

- the version from the settings dialog and the Windows build;
- what an attacker gains and what they need in order to do it (local access, a file in a
  specific folder, a crafted audio device, and so on);
- steps to reproduce, or a proof of concept;
- any log excerpt from `%LOCALAPPDATA%\LiveCaptionsRU\app.log`.

You can expect an acknowledgement within 7 days and an assessment within 30 days. If the
report is valid, the fix is prepared privately and published with the next release, and
the advisory credits you unless you prefer otherwise.

## Scope

In scope:

- the application code under `app/`, `tools/` and the installer script;
- the update-free model loading path, including a model folder placed next to the
  executable;
- the single-instance mutex, the relaunch path and the log file handling;
- anything that breaks the offline promise: a network request, telemetry or a hidden
  download.

Out of scope:

- the release binaries not being code-signed, and SmartScreen or antivirus warnings that
  follow from it;
- the checksum files proving download integrity but not authorship;
- recognition accuracy, and anything that only requires the attacker to already run code
  as the same user;
- vulnerabilities in third-party components that are already published upstream, unless
  this project's use of them makes the impact worse;
- findings that need a modified Windows installation, a patched Qt or a debugger
  attached.

## What the app already does

- No network access at runtime, no telemetry, no crash reporting.
- `model.onnx` and `tokens.txt` are checked against published SHA-256 values on every
  start; a mismatch is written to the log as `model_verify_mismatch`.
- The tray action that opens the log re-checks the target path and refuses anything
  outside `%LOCALAPPDATA%\LiveCaptionsRU\` or anything that is not a `.log` file.
- Release assets are published with `SHA256SUMS.txt`.
