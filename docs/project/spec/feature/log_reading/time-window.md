---
id: "project/spec/feature/log_reading/time-window"
type: "spec"
scope: "project"
description: "Feature: instrukt-ai-logs --since time-window retrieval returns in-window lines merged across the live segment and its rotated archives, including gzip-compressed ones."
delivered_by: ["fix-instrukt-ai-logs-since-silently-omits-ro"]
---

# Time-Window Log Retrieval — Spec

## What it is

The `instrukt-ai-logs <app> --since <window>` retrieval path returns every log
line whose timestamp falls within the window, merged in timestamp order across
the app's log files — the live segment and its rotated archives alike, whether
or not an archive has been gzip-compressed by rotation.

## Canonical fields

`--since N` means "everything in the last N": compression of an already-rotated
segment never removes its in-window lines from the result. Rotated `.gz`
archives are read transparently; an archive whose entire content predates the
window is skipped (its modification time precedes the cutoff), so window latency
scales with the window, not with rotation depth.

### Use cases

<!-- planned:fix-instrukt-ai-logs-since-silently-omits-ro -->

#### UC-TW1: --since returns in-window lines from a rotated, gzipped archive

```gherkin
Given an app log directory holding a live uncompressed segment and a rotated
  gzip-compressed archive
And the gzipped archive contains a log line whose timestamp falls inside the
  --since window
And a further gzip-compressed archive whose every line predates the window
When instrukt-ai-logs reads that app with the --since window
Then the in-window line from the gzipped archive appears in the output
And it is ordered by timestamp among the lines read from the live segment
And no line from the wholly-older archive appears in the output
```

<!-- /planned:fix-instrukt-ai-logs-since-silently-omits-ro -->
