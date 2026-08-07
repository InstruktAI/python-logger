---
id: third-party/logrotate
scope: project
description: "logrotate semantics this library relies on: rotation triggers, and why maxage cannot bound archive age under a size-only trigger — the pruning pass runs only inside a triggered rotation."
---

# logrotate — rotation and archive-expiry semantics

`logrotate` is the Linux rotation backend this library targets. It consumes the
stanza `instrukt_ai_logging/install.py` writes to
`~/.config/instrukt-ai/logrotate.conf`, driven by a per-user systemd timer.

The question this document settles: can archive retention be bounded by **age**
as well as by count? The answer is no under the trigger this library uses, and
the reason is not obvious from the directive's name.

## `rotate` — the count bound

`logrotate(8)`:

> **rotate** _count_
> Log files are rotated _count_ times before being removed or mailed to the
> address specified in a **mail** directive. If _count_ is 0, old versions are
> removed rather than rotated. If _count_ is -1, old logs are not removed at
> all, except they are affected by **maxage** (use with caution, may waste
> performance and disk space). Default is 0.

## `maxage` — the age bound, and its precondition

> **maxage** _count_
> Remove rotated logs older than <count> days. **The age is only checked if the
> logfile is to be rotated.** **rotate -1** does not hinder removal. The files
> are mailed to the configured address if **maillast** and **mail** are
> configured.

The emphasized sentence is the decisive one. `maxage` is not a background sweep;
it is a pruning pass that runs _inside_ a rotation. Upstream `logrotate.c`
confirms this structurally: every `removeLogFile()` call site sits within
`prerotateSingleLog()` or `postrotateSingleLog()`, and both functions open with
an early return:

```c
if (!state->doRotate)
    return 0;
```

`doRotate` is set in `findNeedRotating()`. For a size-triggered stanza it is
purely the threshold test (`state->doRotate = (sb.st_size >= log->threshold)`),
and it is also cleared when the file is empty and `ifempty` is not set.

**Consequence for a `size`-triggered stanza:** a log that never reaches the size
threshold never rotates, so `maxage` never runs and archives are never pruned.
When such a log eventually does cross the threshold, the pass then deletes every
archive older than the limit — including ones `rotate <count>` would have kept.
An age bound therefore removes history from low-volume producers without adding
any for high-volume ones.

## Age is measured by mtime, not by filename

Both the numbered-suffix path and the `dateext` path compare
`difftime(now, st_mtime)`; the date suffix is used only for glob ordering. Since
`rename(2)` preserves mtime, default numbered suffixes (`.1`, `.2.gz`, …) age
correctly. The comparison is integer-truncated days and strictly greater, so a
file survives through its Nth day and is removed at age ≥ N+1 days.

A historical bug made `maxage` ineffective without `dateext`; it was fixed in
3.17.0 (`ChangeLog.md`: "delete old logs hit by maxage regardless of dateext
(#301)"). Builds older than 3.17.0 do not honour it with numbered suffixes.

## `size` versus `maxsize` versus `minsize`

> **maxsize** _size_
> Log files are rotated when they grow bigger than _size_ bytes even before the
> additionally specified time interval (**daily**, **weekly**, **monthly**, or
> **yearly**). The related **size** option is similar except that it is mutually
> exclusive with the time interval options, and it causes log files to be
> rotated without regard for the last rotation time, if specified after the time
> criteria (the last specified option takes the precedence).

`size` is therefore mutually exclusive with a time interval: a stanza using
`size` has no time trigger at all. Pairing a time interval with a size ceiling
requires `maxsize` (rotate on the interval, or sooner at the ceiling) or
`minsize` (rotate on the interval, but only once the floor is met).

## Not a documented pairing

`rotate <count>` combined with `maxage <days>` is legal — the two are
independent caps applied in the same pass, whichever bites first — but it is not
an idiom the documentation endorses. `maxage` appears exactly twice in the man
page, both times in the prose entries quoted above; the EXAMPLES and
CONFIGURATION FILE sections contain no `maxage` line, and neither does upstream
`examples/logrotate.conf`. The only combination the docs speak to is
`rotate -1` + `maxage`.

## Sources

- https://raw.githubusercontent.com/logrotate/logrotate/main/logrotate.8.in — upstream man page source; all quotes above.
- https://github.com/logrotate/logrotate/blob/main/logrotate.c — upstream implementation; the `doRotate` guard and the mtime comparison.
- https://raw.githubusercontent.com/logrotate/logrotate/main/ChangeLog.md — the 3.17.0 `maxage`/`dateext` fix.
- https://github.com/logrotate/logrotate/issues/301 — the `maxage` without `dateext` report.
- https://man7.org/linux/man-pages/man8/logrotate.8.html — rendered man page.

## See also

- docs/third-party/newsyslog.md — the macOS backend, which has no age bound at all.
