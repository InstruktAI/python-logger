---
id: third-party/newsyslog
scope: project
description: "newsyslog.conf semantics this library relies on: the field layout it emits, the three rotation triggers, and the absence of any age-based archive expiry."
---

# newsyslog — conf field layout and rotation triggers

`newsyslog` is the macOS rotation backend this library targets. It consumes the
single glob line `instrukt_ai_logging/install.py` writes to
`~/.config/instrukt-ai/newsyslog.conf`, invoked by a per-user launchd
LaunchAgent.

## Field layout

`newsyslog.conf(5)` defines the line as:

`logfile_name` `owner:group` `mode` `count` `size` `when` `flags`
`path_to_pid_file` `signal_number`

This library emits the first six positionally plus flags, so field _position_ —
not substring presence — is what identifies the archive count in an emitted
line.

### `count`

> Specify the maximum number of archive files which may exist. This does not
> consider the current log file.

A count cap only. There is no companion age field.

### `when`

> The when field may consist of an interval, a specific time, or both. If the
> when field contains an asterisk ('*'), log rotation will solely depend on the
> contents of the size field. Otherwise, the when field consists of an optional
> interval in hours, usually followed by an '@'-sign and a time in restricted
> ISO 8601 format. Additionally, the format may also be constructed with a '$'
> sign along with a rotation time specification of once a day, once a week, or
> once a month.

> If a time is specified, the log file will only be trimmed if newsyslog(8) is
> run within one hour of the specified time. If an interval is specified, the
> log file will be trimmed if that many hours have passed since the last
> rotation. When both a time and an interval are specified then both conditions
> must be satisfied for the rotation to take place.

`when` schedules **when a rotation happens**. It says nothing about how long an
archive survives afterwards.

The "within one hour of the specified time" clause matters for a scheduler that
can miss its window — a `$D0`-style absolute time is skipped entirely if the
host is asleep across that hour, whereas an hours interval resumes on the next
run.

### `flags`

> **Z** indicates that newsyslog(8) should attempt to save disk space by
> compressing the rotated log file using gzip(1).

> **G** indicates that the specified _logfile_name_ is a shell pattern, and that
> newsyslog(8) should archive all filenames matching that pattern using the
> other options on this line.

The `G` flag is what lets one emitted line cover every present and future
`{app}/{source}.log` under the log root without a re-install step.

## Rotation triggers — all three rotate the live log

`newsyslog(8)`:

> A log can be archived for three reasons: 1. It is larger than the configured
> size (in kilobytes). 2. A configured number of hours have elapsed since the
> log was last archived. 3. This is the specific configured hour for rotation of
> the log.

The three are alternatives, and every one of them is a trigger for rotating the
**live** log.

## No age-based archive expiry

There is no `maxage` equivalent and no field of any kind that expires an archive
by age. An archive is discarded only by being pushed past index `count - 1`
during a rotation — which, as above, happens only when a rotation is triggered.

Retention on this backend is therefore expressible as a count and nothing else.
Any age-bounded retention would have to be emulated by this library, which is
the bespoke mechanism the project's rotation design declines to build.

Provenance: every quote above is from `man 5 newsyslog.conf` and `man 8 newsyslog`
as shipped with macOS (page dated November 27, 2006). macOS ships no online
manual for these, so the BSD lineage of the same pages is linked below as the
publicly reachable equivalent.

## Sources

- https://man.openbsd.org/newsyslog.8 — the BSD lineage of the same manual.
- https://man.openbsd.org/newsyslog.conf.5 — the conf-format manual in the same lineage.

## See also

- docs/third-party/logrotate.md — the Linux backend, whose `maxage` is bounded by the same rotate-triggered precondition.
