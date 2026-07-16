---
description: "launchctl semantics this library relies on: print as the supported per-user service-state discriminator (exit-status contract, output is not API), and bootstrap's EIO(5) behavior on an already-loaded LaunchAgent."
---

# launchctl — service-state semantics for per-user LaunchAgents

`launchctl` is macOS's interface to `launchd`. This library shells out to it
from `instrukt_ai_logging/install.py` to bootstrap the per-user rotation
LaunchAgent (`ai.instrukt.log-rotate`) and to discriminate the agent's loaded
state.

## Exit-status contract (authoritative)

The `launchctl(1)` man page (Darwin) documents, under `EXIT STATUS`:

> launchctl will exit with status 0 if the subcommand succeeded. Otherwise,
> it will exit with an error code that can be given to the error subcommand
> to be decoded into human-readable form.

The exit status — not the output text — is the supported success signal.

## `print` as the loaded-state discriminator

`launchctl print <service-target>` (service-target form: `gui/<uid>/<label>`)
prints information about the specified service and follows the exit-status
contract above:

- Service loaded in the target domain → exit `0`.
- Service not present → nonzero error code; observed `113`, which
  `launchctl error 113` decodes as `Could not find specified service`.

The man page carries an explicit caveat on `print`:

> IMPORTANT: This output is NOT API in any sense at all. Do NOT rely on the
> structure or information emitted for ANY reason. It may change from release
> to release without warning.

The caveat covers the _emitted text_ only. A consumer may rely on the exit
status (the documented success contract) and must not parse the output. This
library's already-loaded discriminator therefore uses only
`returncode == 0` from `launchctl print gui/<uid>/ai.instrukt.log-rotate`.

## `bootstrap` on an already-loaded service

`launchctl bootstrap <domain-target> <plist-path>` on a service that is
already loaded fails with returncode `5` (EIO) and stderr
`Bootstrap failed: 5: Input/output error` — with no `already bootstrapped`
token. The man page does not enumerate per-cause bootstrap errors, so EIO(5)
alone is ambiguous (other I/O-class failures share it); only a follow-up
`print` probe (exit 0) confirms the already-loaded state.

Note: the man page's zero-exit guarantee for improper-usage-only nonzero exits
applies to the legacy `load`/`unload` subcommands, not to `bootstrap`/`print`.

## Verified behavior (macOS, Darwin 25.5.0, 2026-07-16)

- `launchctl print gui/502/ai.instrukt.log-rotate` (agent loaded) → exit `0`.
- `launchctl print gui/502/ai.instrukt.nonexistent-service` → exit `113`
  (`Could not find specified service`).
- `launchctl bootstrap gui/502 ~/Library/LaunchAgents/ai.instrukt.log-rotate.plist`
  (agent already loaded) → exit `5`,
  `Bootstrap failed: 5: Input/output error`.

Provenance: all quotes are from `man launchctl` as shipped with macOS
(Darwin man page dated 1 October 2014, read on Darwin 25.5.0) — Apple ships
no more authoritative reference for `launchctl`; the mirrors below carry the
same text. The live verification was performed on the reporting host
(uid 502) on 2026-07-16 and is also recorded in the
fix-launchd-rebootstrap-eio-spurious-rotation-warning todo's `log` artifact.

## Sources

- https://ss64.com/mac/launchctl.html
- https://www.manpagez.com/man/1/launchctl/
- https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/Introduction.html
