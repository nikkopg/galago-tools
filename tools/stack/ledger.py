"""The step-key ledger of the STACK adapter: one durable record per Transfer.

A Transfer must never send a second ``execute_transfer`` for the same step key,
even across a crash or a restart of this tool server. This module is the
adapter-side bookkeeping that makes that so. It records which step key reached
which stage; it holds no instrument rule and never decides anything about
STACK (the core classifies, the adapter records).

It is stdlib only and never imports ``stack_automation_layer`` or the generated
protobuf modules, so it can be unit tested without the core.

File layout (binding contract, 05-SPIKE.md section 6):

    <ledger dir>/stack-ledger.json        {"version": 1, "records": {<step key>: <record>}}
    <ledger dir>/stack-ledger.json.lock   sibling flock file

A record is ``{fingerprint, state, instance, handle, result, [latchGuid],
createdAt, updatedAt}`` with ``state`` one of ``submitting`` (written before
``execute_transfer`` is sent, the write-ahead), ``started`` (the core returned
a task handle), ``done`` (a terminal outcome was observed) or
``outcomeUnknown``.

Loading is strict and fail closed, like the core's own state store: a missing
file is a clean start, anything unreadable, corrupt or of an unknown version
refuses the whole ledger. It is never treated as empty, deleted or rewritten
(a mutation loads strictly first). Every mutation takes an ``fcntl.flock`` on
the lock file, re-loads under the lock, applies one change and saves
atomically (temp file in the same directory, fsync, ``os.replace``, directory
fsync). The directory is created 0700, the ledger and lock files are 0600.
The environment is read at call time, never at import time.
"""
import contextlib
import dataclasses
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypeVar

LEDGER_VERSION = 1
LEDGER_FILENAME = "stack-ledger.json"
LOCK_FILENAME = "stack-ledger.json.lock"
STATES = ("submitting", "started", "done", "outcomeUnknown")

# How long a mutation waits for the sibling flock before it fails closed.
LOCK_TIMEOUT_S = 5.0
_LOCK_POLL_S = 0.01

# D-07 as amended by 05-SPIKE.md section 6b: a recorded ``ran`` is replayed
# only while 0 <= age < REPLAY_WINDOW_S.
REPLAY_WINDOW_S = 600.0

# 7 days: a write prunes ``done`` records older than this (never any other state).
RETENTION_DONE_S = 604800.0

# What decide() can answer, one per row of the repeat-key table.
FRESH = "fresh"
MISMATCH = "mismatch"
REFUSE_SUBMITTING = "refuseSubmitting"
REFUSE_OUTCOME_UNKNOWN = "refuseOutcomeUnknown"
REATTACH = "reattach"
REPLAY = "replay"
REFUSE_COMPLETED = "refuseCompleted"
REFUSE_FAILED = "refuseFailed"

# Results of a wait that end a task for the core's own bookkeeping (A-1).
_TERMINAL_KINDS = frozenset({"ran", "failed", "aborted"})

_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")

_T = TypeVar("_T")


class LedgerError(Exception):
    """The ledger cannot be trusted or cannot be written. ``reason`` is one of
    ``unreadable``, ``corrupt``, ``unknownVersion``, ``unwritable``, ``busy``,
    ``unsupported`` or ``missing``; ``path`` is the ledger file (or directory)
    concerned."""

    def __init__(self, reason: str, path: str) -> None:
        super().__init__(f"{reason}: {path}")
        self.reason = reason
        self.path = path


def resolve_ledger_dir(configured: str, environ: Optional[Mapping[str, str]] = None) -> Path:
    """D-03: an explicit absolute ``configured`` directory wins; else
    ``$XDG_STATE_HOME/galago-tools/stack`` when that is set and absolute; else
    ``~/.local/state/galago-tools/stack``. A non-blank relative ``configured``
    value raises ValueError. Reads the environment at call time and creates
    nothing."""
    env = os.environ if environ is None else environ
    value = configured.strip()
    if value:
        if not os.path.isabs(value):
            raise ValueError(
                f"stack: Config.ledger_dir must be an absolute path, got {configured!r}")
        return Path(value)
    xdg = env.get("XDG_STATE_HOME")
    if xdg and os.path.isabs(xdg):
        return Path(xdg) / "galago-tools" / "stack"
    return Path.home() / ".local" / "state" / "galago-tools" / "stack"


def fingerprint(endpoint: str, request: Any) -> str:
    """D-06: sha256 hex of the canonical JSON of the ledger version, the STACK
    endpoint and the transfer request. It excludes the step key and the wait
    budget, so the same request against a different STACK does not match."""
    canonical = json.dumps(
        {"v": LEDGER_VERSION, "endpoint": endpoint, "request": dataclasses.asdict(request)},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_terminal(result: Mapping[str, Any]) -> bool:
    """A-1: a wait result is recorded ``done`` only when it is ``ran``,
    ``failed`` or ``aborted``, or ``lost`` with reason ``taskNotFound`` -- the
    core's own ``_task_ended`` set. ``timedOut``, ``lost(pollFailed)``,
    ``cancelled`` and anything else leave the record ``started``."""
    if not isinstance(result, Mapping):
        return False
    kind = result.get("kind")
    if not isinstance(kind, str):
        return False
    if kind in _TERMINAL_KINDS:
        return True
    return kind == "lost" and result.get("reason") == "taskNotFound"


@dataclasses.dataclass(frozen=True)
class Decision:
    """What to do with a repeated step key. ``restarted`` is True exactly when
    the record was written by a different tool-server instance than the
    caller's; ``record`` is the record decided on (None for ``fresh``)."""

    action: str
    restarted: bool
    record: Optional[dict[str, Any]]


def _age_s(record: Mapping[str, Any], now: datetime) -> Optional[float]:
    """Seconds from the record's ``updatedAt`` to ``now``, or None when
    ``updatedAt`` is missing, unparseable or naive (the caller fails closed)."""
    value = record.get("updatedAt")
    if not isinstance(value, str):
        return None
    try:
        updated = datetime.fromisoformat(value)
    except ValueError:
        return None
    if updated.tzinfo is None:
        return None
    return (now - updated).total_seconds()


def decide(
    record: Optional[Mapping[str, Any]], *, fingerprint: str, instance: str, now: datetime
) -> Decision:
    """The pure repeat-key state machine (05-SPIKE.md section 6b). It reads no
    file, calls no core and never mutates ``record``. The fingerprint check
    runs first, for every state; then the state decides. A replay needs a
    ``done`` ``ran`` record with ``0 <= age < REPLAY_WINDOW_S``: an age of
    exactly the window, a negative age (clock skew) or an unreadable
    ``updatedAt`` all refuse, so replay fails closed."""
    if now.tzinfo is None:
        raise ValueError("decide needs a timezone-aware now")
    if record is None:
        return Decision(FRESH, False, None)
    held = dict(record) if not isinstance(record, dict) else record
    restarted = held.get("instance") != instance
    if held.get("fingerprint") != fingerprint:
        return Decision(MISMATCH, restarted, held)
    state = held.get("state")
    if state == "submitting":
        return Decision(REFUSE_SUBMITTING, restarted, held)
    if state == "started":
        return Decision(REATTACH, restarted, held)
    if state == "done":
        result = held.get("result")
        kind = result.get("kind") if isinstance(result, Mapping) else None
        if kind != "ran":
            return Decision(REFUSE_FAILED, restarted, held)
        age = _age_s(held, now)
        if age is not None and 0.0 <= age < REPLAY_WINDOW_S:
            return Decision(REPLAY, restarted, held)
        return Decision(REFUSE_COMPLETED, restarted, held)
    # outcomeUnknown, and any state this version does not know: never re-send.
    return Decision(REFUSE_OUTCOME_UNKNOWN, restarted, held)


def _prune(records: dict[str, dict[str, Any]], now: datetime) -> bool:
    """Drop ``done`` records whose ``updatedAt`` is more than RETENTION_DONE_S
    old. Every other state is kept whatever its age, and so is a ``done``
    record whose age cannot be computed. Returns True when anything was
    dropped."""
    expired = [
        key for key, record in records.items()
        if record.get("state") == "done"
        and (_age_s(record, now) or 0.0) > RETENTION_DONE_S
    ]
    for key in expired:
        del records[key]
    return bool(expired)


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of the directory so the rename itself is durable."""
    if os.name == "nt":
        return
    with contextlib.suppress(OSError):
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _stamp(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("ledger timestamps must be timezone-aware")
    return now.astimezone(timezone.utc).isoformat()


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _aware_stamp(value: Any) -> bool:
    """True when ``value`` is an ISO-8601 string that parses to an aware datetime."""
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_record(key: str, record: Any, path: str) -> None:
    """Raise LedgerError("corrupt") unless ``record`` is a well-formed record."""
    if not isinstance(record, dict):
        raise LedgerError("corrupt", path)
    state = record.get("state")
    if state not in STATES:
        raise LedgerError("corrupt", path)
    fingerprint_value = record.get("fingerprint")
    if not (isinstance(fingerprint_value, str) and _FINGERPRINT_RE.fullmatch(fingerprint_value)):
        raise LedgerError("corrupt", path)
    if not isinstance(record.get("instance"), str):
        raise LedgerError("corrupt", path)
    for stamp in ("createdAt", "updatedAt"):
        if not _aware_stamp(record.get(stamp)):
            raise LedgerError("corrupt", path)
    handle = record.get("handle")
    if handle is not None and not isinstance(handle, dict):
        raise LedgerError("corrupt", path)
    result = record.get("result")
    if result is not None and not isinstance(result, dict):
        raise LedgerError("corrupt", path)
    latch_guid = record.get("latchGuid")
    if latch_guid is not None and not isinstance(latch_guid, str):
        raise LedgerError("corrupt", path)
    if state == "started" and not (isinstance(handle, dict) and _non_empty_str(handle.get("guid"))):
        raise LedgerError("corrupt", path)
    if state == "done" and not (isinstance(result, dict) and isinstance(result.get("kind"), str)):
        raise LedgerError("corrupt", path)


class Ledger:
    """The step-key ledger in one directory."""

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)

    @property
    def path(self) -> Path:
        return self._directory / LEDGER_FILENAME

    @property
    def _lock_path(self) -> Path:
        return self._directory / LOCK_FILENAME

    # -- reading ---------------------------------------------------------

    def load(self) -> dict[str, dict[str, Any]]:
        """Every record, strictly parsed. A missing file is ``{}``; any other
        problem raises LedgerError. Never creates anything."""
        return self._parse(self._read())

    def get(self, key: str) -> Optional[dict[str, Any]]:
        """The record for ``key``, or None."""
        return self.load().get(key)

    def _read(self) -> Optional[bytes]:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            raise LedgerError("unreadable", str(self.path)) from None

    def _parse(self, raw: Optional[bytes]) -> dict[str, dict[str, Any]]:
        path = str(self.path)
        if raw is None:
            return {}
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise LedgerError("corrupt", path) from None
        if not isinstance(document, dict):
            raise LedgerError("corrupt", path)
        version = document.get("version")
        if type(version) is not int or version != LEDGER_VERSION:
            raise LedgerError("unknownVersion", path)
        records = document.get("records")
        if not isinstance(records, dict):
            raise LedgerError("corrupt", path)
        for key, record in records.items():
            if not isinstance(key, str):
                raise LedgerError("corrupt", path)
            _validate_record(key, record, path)
        return records

    # -- mutations -------------------------------------------------------

    def claim(self, key: str, *, fingerprint: str, instance: str, now: datetime) -> bool:
        """D-05: write the write-ahead ``submitting`` record. Create-if-absent,
        re-checked under the flock; returns False when the key already
        exists (nothing is written then)."""
        stamp = _stamp(now)

        def change(records: dict[str, dict[str, Any]]) -> tuple[bool, bool]:
            if key in records:
                return False, False
            records[key] = {
                "fingerprint": fingerprint,
                "state": "submitting",
                "instance": instance,
                "handle": None,
                "result": None,
                "createdAt": stamp,
                "updatedAt": stamp,
            }
            return True, True

        return self._mutate(change, now)

    def mark_started(self, key: str, *, handle: dict[str, Any], now: datetime) -> None:
        """Record the task handle the core returned. The record must exist."""
        stamp = _stamp(now)

        def change(records: dict[str, dict[str, Any]]) -> tuple[None, bool]:
            record = self._existing(records, key)
            record["state"] = "started"
            record["handle"] = handle
            record["updatedAt"] = stamp
            return None, True

        self._mutate(change, now)

    def mark_done(self, key: str, *, result: dict[str, Any], now: datetime) -> None:
        """Record the terminal outcome. The record must exist. A-1: a result
        that is not terminal (``is_terminal``) raises ValueError and changes
        nothing, so the record stays ``started``."""
        if not is_terminal(result):
            raise ValueError("ledger: only a terminal result may be recorded as done")
        stamp = _stamp(now)

        def change(records: dict[str, dict[str, Any]]) -> tuple[None, bool]:
            record = self._existing(records, key)
            record["state"] = "done"
            record["result"] = result
            record["updatedAt"] = stamp
            return None, True

        self._mutate(change, now)

    def mark_outcome_unknown(
        self, key: str, *, latch_guid: Optional[str], now: datetime
    ) -> None:
        """A-5: the submit outcome is unknown. The record is never deleted
        after this. ``latch_guid`` is what ``latch_status()`` named at that
        moment (a string), or None when the core was not latched."""
        stamp = _stamp(now)

        def change(records: dict[str, dict[str, Any]]) -> tuple[None, bool]:
            record = self._existing(records, key)
            record["state"] = "outcomeUnknown"
            record["latchGuid"] = latch_guid
            record["updatedAt"] = stamp
            return None, True

        self._mutate(change, now)

    def release(self, key: str, *, now: datetime) -> None:
        """XFR-04: delete ``key`` because nothing was sent. Only that key is
        touched, and an absent key is a no-op that writes nothing."""
        _stamp(now)

        def change(records: dict[str, dict[str, Any]]) -> tuple[None, bool]:
            if key not in records:
                return None, False
            del records[key]
            return None, True

        self._mutate(change, now)

    def find_by_guid(self, guid: str) -> Optional[str]:
        """The step key whose recorded task handle has this guid, else None.
        A read-only strict load (it never writes, prunes or creates)."""
        if not guid:
            return None
        for key, record in sorted(self.load().items()):
            handle = record.get("handle")
            if isinstance(handle, dict) and handle.get("guid") == guid:
                return key
        return None

    def _existing(self, records: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
        record = records.get(key)
        if record is None:
            raise LedgerError("missing", str(self.path))
        return record

    def _mutate(
        self, change: Callable[[dict[str, dict[str, Any]]], tuple[_T, bool]], now: datetime
    ) -> _T:
        """One read-modify-write under the flock. ``change`` edits the records
        in place and returns ``(value, changed)``; the file is saved only when
        ``changed``, and a save first prunes expired ``done`` records (D-08
        retention: a write only, never a load). The flock is held only around
        this, never across a transfer."""
        try:
            import fcntl
        except ImportError:
            raise LedgerError("unsupported", str(self.path)) from None
        try:
            self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(
                self._lock_path,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError:
            raise LedgerError("unwritable", str(self._directory)) from None
        try:
            deadline = time.monotonic() + LOCK_TIMEOUT_S
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LedgerError("busy", str(self.path)) from None
                    time.sleep(_LOCK_POLL_S)
                except OSError:
                    raise LedgerError("unwritable", str(self._lock_path)) from None
            try:
                records = self._parse(self._read())
                value, changed = change(records)
                if changed:
                    _prune(records, now)
                    self._save(records)
                return value
            finally:
                with contextlib.suppress(OSError):
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        """Atomically replace the ledger file. A crash leaves the previous file
        intact: the temp file is fsynced before ``os.replace``, and the
        directory is fsynced after."""
        path = str(self.path)
        try:
            text = json.dumps(
                {"version": LEDGER_VERSION, "records": records}, sort_keys=True, indent=2)
        except (TypeError, ValueError):
            raise LedgerError("unwritable", path) from None
        try:
            fd, tmp = tempfile.mkstemp(
                dir=self._directory, prefix=LEDGER_FILENAME + ".", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, self.path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
        except OSError:
            raise LedgerError("unwritable", path) from None
        _fsync_dir(self._directory)
