# ADR-006 — Workspace Persistence and Snapshot Recovery

## Status

Proposed

## Context

TermForge functions as an engineering workbench rather than a temporary command dialog.

Engineers may arrange the main window and multiple supporting tool windows to match their workflow. Reconstructing that workspace after every restart, reboot, or unexpected shutdown creates unnecessary interruption and cognitive load.

TermForge should allow an engineer to resume work with the same workspace arrangement that existed before the application closed.

The application must also distinguish between workspace state that can be safely preserved and runtime state that cannot be recreated after termination.

## Decision

TermForge shall preserve the engineer’s workspace between application sessions.
Following an unexpected shutdown, TermForge shall offer to restore the most recent preserved workspace snapshot.

## Restoration Principle

Workspace restoration shall restore the engineer's environment, not recreate execution.

Persistent workspace state defines the engineer's workbench and may be restored automatically.

Transient runtime state represents live execution and shall never be recreated automatically.

## Persistent Workspace State

Persistent workspace state may include:

### Main Window

- Geometry (position and size)
- Window state
- Active tab
- Selected profile

### Tool Windows

- Open/closed state
- Geometry
- Window state

### User Interface

- Splitter positions
- Tree expansion state
- Column widths
- Scroll position
- Selected items

### User Context

- Search text
- Active filters
- Current selections

The exact set of persisted workspace attributes may evolve as TermForge grows.

Transient runtime state shall not be restored.

## Transient Runtime State

Transient runtime state shall not be restored.

Examples include:

- Running commands
- Active subprocesses
- SSH sessions
- Temporary dialogs
- Progress operations
- Operating-system resources

After a clean shutdown, TermForge shall restore the most recently saved workspace automatically on the next launch.

If the previous session ended unexpectedly, TermForge shall inform the engineer and offer a choice:

```text
Welcome back to the Forge

The previous session ended unexpectedly.

A preserved snapshot of your workbench is available.

Running commands and external processes will not be restored.

[ Restore Workspace ]    [ Start Fresh ]
```

Workspace snapshots shall be written safely and retained in multiple generations so that TermForge can recover from an incomplete write, corrupted state file, or failed restoration attempt.

If the latest workspace cannot be restored, TermForge should offer the newest valid preserved snapshot before requiring the engineer to start fresh.


## State Separation

TermForge shall keep configuration and workspace state separate.

Suggested locations:

```text
~/.config/termforge/
    config.json
```

```text
~/.local/state/termforge/
    workspace-current.json
    workspace-previous-1.json
    workspace-previous-2.json
```

Configuration records deliberate user preferences.

Workspace state records what TermForge remembers about the engineer’s workbench.


## Consequences

### Positive

* Engineers can resume work quickly after restarting TermForge.
* Reboots and unexpected shutdowns cause less disruption.
* Window placement and workflow continuity become backend-independent.
* Workspace recovery becomes predictable and testable.
* TermForge behaves consistently with its identity as an engineering workbench.


### Negative

* Window and workspace state require versioned persistence formats.
* Multi-monitor changes may require geometry validation and repositioning.
* Corrupted or obsolete state must be handled safely.
* Restoration behavior requires careful testing across desktop environments.


## Guiding Principle

> **A craftsman’s bench should greet its owner exactly as it was left.**



## Related Principle

> **Good engineering tools preserve continuity.**



