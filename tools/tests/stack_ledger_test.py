"""Core-free tests of the STACK step-key ledger (tools/stack/ledger.py).

This file imports only the standard library and ``tools.stack.ledger``: no
``stack_automation_layer``, no generated gRPC module, no ``tools.stack.server``.
It therefore runs, and never skips, on a machine without the private core.

Every test works in a temporary directory and patches the environment, so none
can ever read or write the real ``~/.local/state/galago-tools`` ledger.
"""
import copy
import dataclasses
import fcntl
import json
import os
import shutil
import stat
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

from tools.stack import ledger as ledger_module
from tools.stack.ledger import (
    FRESH,
    LEDGER_FILENAME,
    LOCK_FILENAME,
    MISMATCH,
    REATTACH,
    REFUSE_COMPLETED,
    REFUSE_FAILED,
    REFUSE_OUTCOME_UNKNOWN,
    REFUSE_SUBMITTING,
    REPLAY,
    REPLAY_WINDOW_S,
    RETENTION_DONE_S,
    Decision,
    Ledger,
    LedgerError,
    decide,
    fingerprint,
    is_terminal,
    resolve_ledger_dir,
)

_NOW = datetime(2026, 10, 29, 12, 0, 0, 123456, tzinfo=timezone.utc)
_FP = "a" * 64
_FP2 = "b" * 64
_INSTANCE = "0123456789abcdef0123456789abcdef"
_GUID = "11111111-2222-3333-4444-555555555555"


@dataclasses.dataclass(frozen=True)
class _Location:
    device: Optional[str] = None
    deck: Optional[str] = None
    nest: Optional[str] = None
    transfer_profile: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class _Request:
    robot: Optional[str] = None
    labware_profile: Optional[str] = None
    source: Optional[_Location] = None
    destination: Optional[_Location] = None


def _record(
    state: str = "submitting",
    *,
    fp: str = _FP,
    instance: str = _INSTANCE,
    when: datetime = _NOW,
    handle: Optional[dict[str, Any]] = None,
    result: Optional[dict[str, Any]] = None,
    latch_guid: Optional[str] = None,
) -> dict[str, Any]:
    """A well-formed record in ``state`` (handle / result are filled in as the
    state requires unless given)."""
    if state in ("started", "done") and handle is None:
        handle = {"kind": "transfer", "guid": _GUID, "robot": "r1", "estimatedS": 12.0}
    if state == "done" and result is None:
        result = {"kind": "ran"}
    stamp = when.astimezone(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "fingerprint": fp,
        "state": state,
        "instance": instance,
        "handle": handle,
        "result": result,
        "createdAt": stamp,
        "updatedAt": stamp,
    }
    if state == "outcomeUnknown":
        record["latchGuid"] = latch_guid
    return record


class _LedgerCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.directory = self.root / "ledger"
        self.ledger = Ledger(self.directory)
        fake_home = self.root / "home"
        fake_home.mkdir()
        patcher = patch.dict(os.environ, {
            "HOME": str(fake_home),
            "XDG_STATE_HOME": str(self.root / "xdg"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_document(self, document: Any) -> bytes:
        """Write ``document`` (JSON-encoded) as the ledger file; returns the bytes."""
        self.directory.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(document).encode("utf-8")
        self.ledger.path.write_bytes(raw)
        return raw

    def write_records(self, records: dict[str, Any]) -> bytes:
        return self.write_document({"version": 1, "records": records})

    def claim(self, key: str = "k", *, fp: str = _FP, instance: str = _INSTANCE,
              now: datetime = _NOW) -> bool:
        return self.ledger.claim(key, fingerprint=fp, instance=instance, now=now)

    def stray_temp_files(self) -> list[str]:
        return sorted(name for name in os.listdir(self.directory) if name.endswith(".tmp"))


class TestLedgerStorage(_LedgerCase):
    def test_a_missing_file_loads_as_empty_and_creates_nothing(self) -> None:
        self.assertEqual(self.ledger.load(), {})
        self.assertIsNone(self.ledger.get("k"))
        self.assertFalse(self.directory.exists())

    def test_a_missing_file_inside_an_existing_directory_stays_missing(self) -> None:
        self.directory.mkdir()
        self.assertEqual(self.ledger.load(), {})
        self.assertEqual(os.listdir(self.directory), [])

    def test_every_malformed_ledger_fails_closed_and_is_never_modified(self) -> None:
        good = _record("submitting")
        started = _record("started")
        done = _record("done")

        def with_field(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
            record = copy.deepcopy(base)
            record.update(changes)
            return record

        def without_field(base: dict[str, Any], name: str) -> dict[str, Any]:
            record = copy.deepcopy(base)
            del record[name]
            return record

        raw_cases: dict[str, bytes] = {
            "non-UTF-8 bytes": b"\xff\xfe\x00{not utf8",
            "invalid JSON": b'{"version": 1, "records": ',
            "empty file": b"",
            "top-level list": b"[]",
            "top-level string": b'"records"',
        }
        document_cases: dict[str, Any] = {
            "version missing": {"records": {}},
            "version 2": {"version": 2, "records": {}},
            "version true": {"version": True, "records": {}},
            "version '1'": {"version": "1", "records": {}},
            "version 1.0": {"version": 1.0, "records": {}},
            "records missing": {"version": 1},
            "records a list": {"version": 1, "records": []},
            "record a list": {"version": 1, "records": {"k": []}},
            "record null": {"version": 1, "records": {"k": None}},
            "record unknown state": {
                "version": 1, "records": {"k": with_field(good, state="pending")}},
            "record state missing": {
                "version": 1, "records": {"k": without_field(good, "state")}},
            "fingerprint not 64 hex (short)": {
                "version": 1, "records": {"k": with_field(good, fingerprint="abc")}},
            "fingerprint not hex": {
                "version": 1, "records": {"k": with_field(good, fingerprint="z" * 64)}},
            "fingerprint upper case": {
                "version": 1, "records": {"k": with_field(good, fingerprint="A" * 64)}},
            "fingerprint not a string": {
                "version": 1, "records": {"k": with_field(good, fingerprint=7)}},
            "instance missing": {
                "version": 1, "records": {"k": without_field(good, "instance")}},
            "createdAt unparseable": {
                "version": 1, "records": {"k": with_field(good, createdAt="yesterday")}},
            "updatedAt unparseable": {
                "version": 1, "records": {"k": with_field(good, updatedAt="not-a-time")}},
            "updatedAt naive": {
                "version": 1,
                "records": {"k": with_field(good, updatedAt="2026-10-29T12:00:00")}},
            "createdAt naive": {
                "version": 1,
                "records": {"k": with_field(good, createdAt="2026-10-29T12:00:00")}},
            "updatedAt missing": {
                "version": 1, "records": {"k": without_field(good, "updatedAt")}},
            "started without handle": {
                "version": 1, "records": {"k": with_field(started, handle=None)}},
            "started handle without guid": {
                "version": 1,
                "records": {"k": with_field(started, handle={"kind": "transfer"})}},
            "started handle with empty guid": {
                "version": 1,
                "records": {"k": with_field(started, handle={"guid": ""})}},
            "done without result": {
                "version": 1, "records": {"k": with_field(done, result=None)}},
            "done result without kind": {
                "version": 1, "records": {"k": with_field(done, result={"reason": "x"})}},
            "done result kind not a string": {
                "version": 1, "records": {"k": with_field(done, result={"kind": 3})}},
            "handle not an object": {
                "version": 1, "records": {"k": with_field(good, handle="guid")}},
            "latchGuid not a string": {
                "version": 1, "records": {"k": with_field(good, latchGuid=5)}},
            "a good record next to a bad one": {
                "version": 1,
                "records": {"ok": good, "bad": with_field(good, state="nope")}},
        }
        cases: dict[str, bytes] = dict(raw_cases)
        for name, document in document_cases.items():
            cases[name] = json.dumps(document).encode("utf-8")
        self.assertGreaterEqual(len(cases), 14)

        self.directory.mkdir(parents=True, exist_ok=True)
        for name, raw in cases.items():
            with self.subTest(shape=name):
                self.ledger.path.write_bytes(raw)
                with self.assertRaises(LedgerError) as caught:
                    self.ledger.load()
                self.assertIn(caught.exception.reason, ("corrupt", "unknownVersion"))
                self.assertEqual(caught.exception.path, str(self.ledger.path))
                with self.assertRaises(LedgerError):
                    self.ledger.get("k")
                # A mutation must refuse too, never repair.
                with self.assertRaises(LedgerError):
                    self.claim("fresh-key")
                self.assertEqual(self.ledger.path.read_bytes(), raw)
                self.assertEqual(self.stray_temp_files(), [])

    def test_unknown_version_is_reported_as_unknown_version(self) -> None:
        for name, version in (("two", 2), ("true", True), ("string", "1"), ("missing", None)):
            with self.subTest(version=name):
                document: dict[str, Any] = {"records": {}}
                if version is not None:
                    document["version"] = version
                self.write_document(document)
                with self.assertRaises(LedgerError) as caught:
                    self.ledger.load()
                self.assertEqual(caught.exception.reason, "unknownVersion")

    def test_a_directory_at_the_ledger_path_is_unreadable_and_untouched(self) -> None:
        self.ledger.path.parent.mkdir(parents=True)
        self.ledger.path.mkdir()
        with self.assertRaises(LedgerError) as caught:
            self.ledger.load()
        self.assertEqual(caught.exception.reason, "unreadable")
        with self.assertRaises(LedgerError):
            self.claim()
        self.assertTrue(self.ledger.path.is_dir())
        self.assertEqual(os.listdir(self.ledger.path), [])

    def test_a_well_formed_ledger_round_trips(self) -> None:
        records = {
            "a": _record("submitting"),
            "b": _record("started"),
            "c": _record("done"),
            "d": _record("outcomeUnknown", latch_guid="submit-0123456789abcdef"),
            "e": _record("outcomeUnknown", latch_guid=None),
        }
        self.write_records(records)
        self.assertEqual(self.ledger.load(), records)
        self.assertEqual(self.ledger.get("b"), records["b"])

    def test_claim_writes_a_submitting_record_and_refuses_a_repeat(self) -> None:
        self.assertTrue(self.claim("k"))
        record = self.ledger.get("k")
        assert record is not None
        self.assertEqual(record["state"], "submitting")
        self.assertEqual(record["fingerprint"], _FP)
        self.assertEqual(record["instance"], _INSTANCE)
        self.assertIsNone(record["handle"])
        self.assertIsNone(record["result"])
        self.assertEqual(record["createdAt"], _NOW.isoformat())
        self.assertEqual(record["updatedAt"], _NOW.isoformat())
        before = self.ledger.path.read_bytes()
        self.assertFalse(self.claim("k", fp=_FP2, now=_NOW + timedelta(seconds=5)))
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_a_step_key_is_used_byte_exact(self) -> None:
        self.assertTrue(self.claim("run-1:stack-1"))
        self.assertTrue(self.claim("run-1:stack-1 "))
        self.assertTrue(self.claim("Run-1:stack-1"))
        self.assertEqual(
            sorted(self.ledger.load()), ["Run-1:stack-1", "run-1:stack-1", "run-1:stack-1 "])

    def test_a_naive_timestamp_is_refused_before_anything_is_written(self) -> None:
        with self.assertRaises(ValueError):
            self.claim(now=datetime(2026, 10, 29, 12, 0, 0))
        self.assertFalse(self.directory.exists())

    def test_started_and_done_transitions_refresh_updated_at(self) -> None:
        self.claim("k")
        later = _NOW + timedelta(seconds=30)
        handle = {"kind": "transfer", "guid": _GUID, "robot": "r1", "estimatedS": 3.0}
        self.ledger.mark_started("k", handle=handle, now=later)
        record = self.ledger.get("k")
        assert record is not None
        self.assertEqual(record["state"], "started")
        self.assertEqual(record["handle"], handle)
        self.assertEqual(record["updatedAt"], later.isoformat())
        self.assertEqual(record["createdAt"], _NOW.isoformat())
        result = {"kind": "ran"}
        self.ledger.mark_done("k", result=result, now=later + timedelta(seconds=1))
        record = self.ledger.get("k")
        assert record is not None
        self.assertEqual(record["state"], "done")
        self.assertEqual(record["result"], result)
        self.assertEqual(record["handle"], handle)

    def test_a_transition_on_an_absent_key_is_a_missing_error(self) -> None:
        with self.assertRaises(LedgerError) as caught:
            self.ledger.mark_started("nope", handle={"guid": _GUID}, now=_NOW)
        self.assertEqual(caught.exception.reason, "missing")
        with self.assertRaises(LedgerError):
            self.ledger.mark_done("nope", result={"kind": "ran"}, now=_NOW)

    def test_directory_is_0700_and_files_are_0600(self) -> None:
        self.claim("k")
        self.assertEqual(stat.S_IMODE(os.stat(self.directory).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.ledger.path).st_mode), 0o600)
        self.assertEqual(
            stat.S_IMODE(os.stat(self.directory / LOCK_FILENAME).st_mode), 0o600)

    def test_modes_hold_after_a_second_write(self) -> None:
        self.claim("k")
        self.claim("k2")
        self.assertEqual(stat.S_IMODE(os.stat(self.ledger.path).st_mode), 0o600)

    def test_the_file_is_a_versioned_document(self) -> None:
        self.claim("k")
        document = json.loads(self.ledger.path.read_text(encoding="utf-8"))
        self.assertEqual(document["version"], 1)
        self.assertEqual(sorted(document["records"]), ["k"])
        self.assertEqual(self.ledger.path.name, LEDGER_FILENAME)

    def test_a_failed_replace_keeps_the_previous_bytes_and_leaves_no_temp_file(self) -> None:
        self.claim("first")
        before = self.ledger.path.read_bytes()
        with patch("tools.stack.ledger.os.replace", side_effect=OSError("disk gone")):
            with self.assertRaises(LedgerError) as caught:
                self.claim("second")
        self.assertEqual(caught.exception.reason, "unwritable")
        self.assertEqual(self.ledger.path.read_bytes(), before)
        self.assertEqual(self.stray_temp_files(), [])
        self.assertIsNone(self.ledger.get("second"))
        # The ledger is still usable afterwards.
        self.assertTrue(self.claim("second"))

    def test_a_non_serialisable_value_is_a_ledger_error_not_a_raw_exception(self) -> None:
        self.claim("k")
        before = self.ledger.path.read_bytes()
        with self.assertRaises(LedgerError) as caught:
            self.ledger.mark_started("k", handle={"guid": _GUID, "bad": object()}, now=_NOW)
        self.assertEqual(caught.exception.reason, "unwritable")
        self.assertEqual(self.ledger.path.read_bytes(), before)
        self.assertEqual(self.stray_temp_files(), [])

    def test_two_threads_claiming_one_key_exactly_one_wins(self) -> None:
        for round_number in range(5):
            with self.subTest(round=round_number):
                key = f"contested-{round_number}"
                barrier = threading.Barrier(2)
                outcomes: list[Optional[bool]] = [None, None]
                errors: list[BaseException] = []

                def worker(index: int, ledger: Ledger) -> None:
                    try:
                        barrier.wait(timeout=5)
                        outcomes[index] = ledger.claim(
                            key, fingerprint=_FP, instance=f"inst-{index}", now=_NOW)
                    except BaseException as exc:  # noqa: BLE001 - surfaced below
                        errors.append(exc)

                threads = [
                    threading.Thread(target=worker, args=(i, Ledger(self.directory)))
                    for i in range(2)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=10)
                self.assertEqual(errors, [])
                self.assertEqual(sorted(str(o) for o in outcomes), ["False", "True"])
                document = json.loads(self.ledger.path.read_text(encoding="utf-8"))
                self.assertEqual(
                    [k for k in document["records"] if k == key], [key])

    def test_a_held_lock_makes_claim_report_busy_after_the_deadline(self) -> None:
        self.directory.mkdir(mode=0o700)
        lock_fd = os.open(self.directory / LOCK_FILENAME, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, lock_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        started = time.monotonic()
        with patch.object(ledger_module, "LOCK_TIMEOUT_S", 0.2):
            with self.assertRaises(LedgerError) as caught:
                self.claim()
        elapsed = time.monotonic() - started
        self.assertEqual(caught.exception.reason, "busy")
        self.assertGreaterEqual(elapsed, 0.2)
        self.assertLess(elapsed, 2.0)
        self.assertFalse(self.ledger.path.exists())

    def test_the_lock_is_released_after_every_mutation(self) -> None:
        self.claim("k")
        fd = os.open(self.directory / LOCK_FILENAME, os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_a_symlink_at_the_lock_path_is_refused(self) -> None:
        self.directory.mkdir(mode=0o700)
        target = self.root / "elsewhere"
        target.write_text("untouched")
        (self.directory / LOCK_FILENAME).symlink_to(target)
        with self.assertRaises(LedgerError):
            self.claim()
        self.assertEqual(target.read_text(), "untouched")
        self.assertFalse(self.ledger.path.exists())

    def test_load_never_creates_the_lock_file_or_directory(self) -> None:
        self.ledger.load()
        self.assertFalse(self.directory.exists())

    def test_a_directory_that_cannot_be_created_is_unwritable(self) -> None:
        blocker = self.root / "blocker"
        blocker.write_text("a file, not a directory")
        with self.assertRaises(LedgerError) as caught:
            Ledger(blocker / "ledger").claim("k", fingerprint=_FP, instance="i", now=_NOW)
        self.assertEqual(caught.exception.reason, "unwritable")
        self.assertEqual(blocker.read_text(), "a file, not a directory")


class TestResolveLedgerDir(unittest.TestCase):
    def test_an_absolute_configured_value_wins_over_everything(self) -> None:
        env = {"XDG_STATE_HOME": "/var/xdg"}
        self.assertEqual(resolve_ledger_dir("/srv/ledger", env), Path("/srv/ledger"))
        self.assertEqual(resolve_ledger_dir("  /srv/ledger  ", env), Path("/srv/ledger"))

    def test_an_absolute_configured_value_may_sit_under_tmp(self) -> None:
        self.assertEqual(resolve_ledger_dir("/tmp/x/ledger", {}), Path("/tmp/x/ledger"))

    def test_blank_uses_an_absolute_xdg_state_home(self) -> None:
        env = {"XDG_STATE_HOME": "/var/xdg"}
        for blank in ("", "   ", "\t\n"):
            with self.subTest(blank=blank):
                self.assertEqual(
                    resolve_ledger_dir(blank, env), Path("/var/xdg/galago-tools/stack"))

    def test_a_relative_or_empty_xdg_state_home_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home}):
                expected = Path(home) / ".local" / "state" / "galago-tools" / "stack"
                for xdg in ("relative/state", "", "~/state"):
                    with self.subTest(xdg=xdg):
                        self.assertEqual(resolve_ledger_dir("", {"XDG_STATE_HOME": xdg}), expected)

    def test_an_absent_xdg_state_home_falls_back_to_home(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home}):
                self.assertEqual(
                    resolve_ledger_dir("", {}),
                    Path(home) / ".local" / "state" / "galago-tools" / "stack")

    def test_a_relative_configured_value_raises_value_error(self) -> None:
        for value in ("ledger", "./ledger", "../ledger", "a/b", "~/ledger"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    resolve_ledger_dir(value, {"XDG_STATE_HOME": "/var/xdg"})

    def test_the_environment_is_read_at_call_time_when_not_given(self) -> None:
        with patch.dict(os.environ, {"XDG_STATE_HOME": "/first"}):
            self.assertEqual(resolve_ledger_dir(""), Path("/first/galago-tools/stack"))
        with patch.dict(os.environ, {"XDG_STATE_HOME": "/second"}):
            self.assertEqual(resolve_ledger_dir(""), Path("/second/galago-tools/stack"))

    def test_the_default_never_resolves_under_tmp_when_home_is_not_under_tmp(self) -> None:
        with patch.dict(os.environ, {"HOME": "/home/operator"}):
            for env in ({}, {"XDG_STATE_HOME": "relative"}):
                with self.subTest(env=env):
                    resolved = resolve_ledger_dir("", env)
                    self.assertFalse(str(resolved).startswith("/tmp"))
                    self.assertEqual(
                        resolved,
                        Path("/home/operator/.local/state/galago-tools/stack"))

    def test_resolving_creates_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {"HOME": home}):
                resolve_ledger_dir("", {})
                self.assertEqual(os.listdir(home), [])


class TestFingerprint(unittest.TestCase):
    def _request(self) -> _Request:
        return _Request(
            robot="robot-1",
            labware_profile="plate-96",
            source=_Location("dev-a", "deck-1", "nest-1", "prof-s"),
            destination=_Location("dev-b", "deck-2", "nest-2", "prof-d"),
        )

    def test_it_is_64_lowercase_hex(self) -> None:
        value = fingerprint("10.0.0.5:80", self._request())
        self.assertEqual(len(value), 64)
        self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_equal_inputs_give_equal_fingerprints(self) -> None:
        self.assertEqual(
            fingerprint("host:80", self._request()), fingerprint("host:80", self._request()))

    def test_construction_order_does_not_matter(self) -> None:
        first = _Request(
            robot="r", labware_profile="p",
            source=_Location(device="d", deck="k", nest="n", transfer_profile="t"),
            destination=_Location(nest="n2", deck="k2", device="d2", transfer_profile="t2"))
        second = _Request(
            destination=_Location(transfer_profile="t2", device="d2", deck="k2", nest="n2"),
            source=_Location(transfer_profile="t", nest="n", deck="k", device="d"),
            labware_profile="p", robot="r")
        self.assertEqual(fingerprint("e", first), fingerprint("e", second))

    def test_a_different_endpoint_differs(self) -> None:
        request = self._request()
        self.assertNotEqual(fingerprint("host-a:80", request), fingerprint("host-b:80", request))
        self.assertNotEqual(fingerprint("host:80", request), fingerprint("host:81", request))

    def test_every_request_field_changes_the_fingerprint(self) -> None:
        base = self._request()
        reference = fingerprint("host:80", base)
        source = base.source
        destination = base.destination
        assert source is not None and destination is not None
        variants: dict[str, _Request] = {
            "robot": dataclasses.replace(base, robot="robot-2"),
            "labware_profile": dataclasses.replace(base, labware_profile="plate-384"),
            "source.device": dataclasses.replace(
                base, source=dataclasses.replace(source, device="dev-x")),
            "source.deck": dataclasses.replace(
                base, source=dataclasses.replace(source, deck="deck-x")),
            "source.nest": dataclasses.replace(
                base, source=dataclasses.replace(source, nest="nest-x")),
            "source.transfer_profile": dataclasses.replace(
                base, source=dataclasses.replace(source, transfer_profile="prof-x")),
            "destination.device": dataclasses.replace(
                base, destination=dataclasses.replace(destination, device="dev-x")),
            "destination.deck": dataclasses.replace(
                base, destination=dataclasses.replace(destination, deck="deck-x")),
            "destination.nest": dataclasses.replace(
                base, destination=dataclasses.replace(destination, nest="nest-x")),
            "destination.transfer_profile": dataclasses.replace(
                base, destination=dataclasses.replace(destination, transfer_profile="prof-x")),
            "source None": dataclasses.replace(base, source=None),
            "destination None": dataclasses.replace(base, destination=None),
            "source.transfer_profile None": dataclasses.replace(
                base, source=dataclasses.replace(source, transfer_profile=None)),
            "robot None": dataclasses.replace(base, robot=None),
            "source and destination swapped": dataclasses.replace(
                base, source=destination, destination=source),
        }
        seen = {reference}
        for name, variant in variants.items():
            with self.subTest(field=name):
                value = fingerprint("host:80", variant)
                self.assertNotEqual(value, reference)
                seen.add(value)
        self.assertEqual(len(seen), len(variants) + 1)

    def test_none_and_the_empty_string_are_different(self) -> None:
        none_request = _Request(robot=None)
        empty_request = _Request(robot="")
        self.assertNotEqual(fingerprint("e", none_request), fingerprint("e", empty_request))

    def test_the_fingerprint_does_not_mutate_the_request(self) -> None:
        request = self._request()
        snapshot = dataclasses.asdict(request)
        fingerprint("host:80", request)
        self.assertEqual(dataclasses.asdict(request), snapshot)


class TestDecide(unittest.TestCase):
    """The D-07 repeat-key table as amended by 05-SPIKE.md section 6b."""

    def decide(self, record: Optional[dict[str, Any]], *, fp: str = _FP,
               instance: str = _INSTANCE, now: datetime = _NOW) -> Decision:
        return decide(record, fingerprint=fp, instance=instance, now=now)

    def done_ran(self, age_s: float, **kwargs: Any) -> dict[str, Any]:
        return _record("done", when=_NOW - timedelta(seconds=age_s), **kwargs)

    def test_the_window_is_600_seconds(self) -> None:
        self.assertEqual(REPLAY_WINDOW_S, 600.0)

    def test_no_record_is_fresh(self) -> None:
        self.assertEqual(self.decide(None), Decision(FRESH, False, None))

    def test_a_different_fingerprint_is_a_mismatch_in_every_state(self) -> None:
        records = {
            "submitting": _record("submitting", fp=_FP2),
            "started": _record("started", fp=_FP2),
            "done ran": _record("done", fp=_FP2),
            "done failed": _record("done", fp=_FP2, result={"kind": "failed"}),
            "outcomeUnknown": _record("outcomeUnknown", fp=_FP2, latch_guid="submit-0123456789abcdef"),
        }
        for name, record in records.items():
            with self.subTest(state=name):
                decision = self.decide(record)
                self.assertEqual(decision.action, MISMATCH)
                self.assertEqual(decision.record, record)

    def test_a_mismatch_is_checked_before_the_age_and_restart(self) -> None:
        old = self.done_ran(10_000, fp=_FP2, instance="another-instance")
        self.assertEqual(self.decide(old).action, MISMATCH)

    def test_submitting_is_refused(self) -> None:
        decision = self.decide(_record("submitting"))
        self.assertEqual(decision.action, REFUSE_SUBMITTING)
        self.assertFalse(decision.restarted)

    def test_submitting_from_another_instance_reports_the_restart(self) -> None:
        decision = self.decide(_record("submitting", instance="older-instance"))
        self.assertEqual(decision.action, REFUSE_SUBMITTING)
        self.assertTrue(decision.restarted)

    def test_outcome_unknown_is_refused(self) -> None:
        record = _record("outcomeUnknown", latch_guid="submit-0123456789abcdef")
        decision = self.decide(record)
        self.assertEqual(decision.action, REFUSE_OUTCOME_UNKNOWN)
        self.assertFalse(decision.restarted)
        self.assertEqual(decision.record, record)

    def test_outcome_unknown_reports_the_restart(self) -> None:
        decision = self.decide(_record("outcomeUnknown", instance="older-instance"))
        self.assertEqual(decision.action, REFUSE_OUTCOME_UNKNOWN)
        self.assertTrue(decision.restarted)

    def test_started_in_the_same_instance_reattaches(self) -> None:
        decision = self.decide(_record("started"))
        self.assertEqual(decision.action, REATTACH)
        self.assertFalse(decision.restarted)

    def test_started_from_another_instance_reattaches_and_reports_the_restart(self) -> None:
        decision = self.decide(_record("started", instance="older-instance"))
        self.assertEqual(decision.action, REATTACH)
        self.assertTrue(decision.restarted)

    def test_a_ran_record_inside_the_window_is_replayed(self) -> None:
        for age in (0.0, 1.0, 599.999):
            with self.subTest(age=age):
                record = self.done_ran(age)
                decision = self.decide(record)
                self.assertEqual(decision.action, REPLAY)
                self.assertEqual(decision.record, record)
                self.assertFalse(decision.restarted)

    def test_a_replay_from_another_instance_still_replays(self) -> None:
        decision = self.decide(self.done_ran(5.0, instance="older-instance"))
        self.assertEqual(decision.action, REPLAY)
        self.assertTrue(decision.restarted)

    def test_a_ran_record_at_exactly_600_seconds_is_refused_as_completed(self) -> None:
        decision = self.decide(self.done_ran(600.0))
        self.assertEqual(decision.action, REFUSE_COMPLETED)

    def test_an_old_ran_record_is_refused_as_completed(self) -> None:
        for age in (600.001, 601.0, 86_400.0):
            with self.subTest(age=age):
                self.assertEqual(self.decide(self.done_ran(age)).action, REFUSE_COMPLETED)

    def test_a_future_dated_ran_record_is_refused_as_completed(self) -> None:
        # The clock moved back, or the record was written with a skewed clock.
        for age in (-5.0, -0.001, -86_400.0):
            with self.subTest(age=age):
                self.assertEqual(self.decide(self.done_ran(age)).action, REFUSE_COMPLETED)

    def test_a_ran_record_with_an_unparseable_updated_at_is_refused_as_completed(self) -> None:
        for stamp in ("not-a-time", "2026-10-29T12:00:00", ""):
            with self.subTest(stamp=stamp):
                record = _record("done")
                record["updatedAt"] = stamp
                self.assertEqual(self.decide(record).action, REFUSE_COMPLETED)

    def test_any_other_done_result_is_refused_as_failed(self) -> None:
        results = {
            "failed": {"kind": "failed"},
            "aborted": {"kind": "aborted"},
            "lost taskNotFound": {"kind": "lost", "reason": "taskNotFound"},
            "cancelled": {"kind": "cancelled"},
            "unexpected": {"kind": "somethingNew"},
        }
        for name, result in results.items():
            for age in (0.0, 30.0, 10_000.0):
                with self.subTest(result=name, age=age):
                    decision = self.decide(self.done_ran(age, result=result))
                    self.assertEqual(decision.action, REFUSE_FAILED)

    def test_a_ran_kind_check_is_exact(self) -> None:
        record = self.done_ran(1.0, result={"kind": "Ran"})
        self.assertEqual(self.decide(record).action, REFUSE_FAILED)

    def test_decide_does_not_mutate_its_input(self) -> None:
        records = [
            _record("submitting"), _record("started"), self.done_ran(1.0),
            self.done_ran(900.0), _record("outcomeUnknown"),
            _record("done", result={"kind": "failed"}), _record("submitting", fp=_FP2),
        ]
        for record in records:
            with self.subTest(state=record["state"], updated=record["updatedAt"]):
                snapshot = copy.deepcopy(record)
                self.decide(record)
                self.assertEqual(record, snapshot)

    def test_equal_inputs_give_equal_decisions(self) -> None:
        record = self.done_ran(12.0)
        self.assertEqual(self.decide(record), self.decide(copy.deepcopy(record)))
        self.assertEqual(self.decide(None), self.decide(None))

    def test_decision_is_frozen(self) -> None:
        decision = self.decide(None)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decision.action = REPLAY  # type: ignore[misc]

    def test_decide_needs_an_aware_now(self) -> None:
        with self.assertRaises(ValueError):
            self.decide(self.done_ran(1.0), now=datetime(2026, 10, 29, 12, 0, 0))

    def test_decide_reads_no_file_and_makes_no_core_call(self) -> None:
        with patch("builtins.open", side_effect=AssertionError("decide touched a file")), \
                patch("os.open", side_effect=AssertionError("decide touched a file")):
            self.assertEqual(self.decide(self.done_ran(1.0)).action, REPLAY)
            self.assertEqual(self.decide(None).action, FRESH)


class TestTransitions(_LedgerCase):
    def test_release_deletes_only_its_key(self) -> None:
        self.claim("k")
        self.claim("k2", fp=_FP2, now=_NOW + timedelta(seconds=1))
        kept = self.ledger.get("k2")
        self.ledger.release("k", now=_NOW + timedelta(seconds=2))
        self.assertEqual(sorted(self.ledger.load()), ["k2"])
        self.assertEqual(self.ledger.get("k2"), kept)

    def test_release_of_an_absent_key_writes_nothing_new(self) -> None:
        self.claim("k")
        before = self.ledger.path.read_bytes()
        mtime = os.stat(self.ledger.path).st_mtime_ns
        self.ledger.release("absent", now=_NOW + timedelta(seconds=5))
        self.assertEqual(self.ledger.path.read_bytes(), before)
        self.assertEqual(os.stat(self.ledger.path).st_mtime_ns, mtime)
        self.assertEqual(self.stray_temp_files(), [])

    def test_release_on_a_missing_ledger_creates_no_ledger_file(self) -> None:
        self.ledger.release("absent", now=_NOW)
        self.assertFalse(self.ledger.path.exists())

    def test_release_refuses_a_corrupt_ledger_and_leaves_it(self) -> None:
        self.directory.mkdir()
        self.ledger.path.write_bytes(b"{broken")
        with self.assertRaises(LedgerError):
            self.ledger.release("k", now=_NOW)
        self.assertEqual(self.ledger.path.read_bytes(), b"{broken")

    def test_release_needs_an_aware_now(self) -> None:
        self.claim("k")
        with self.assertRaises(ValueError):
            self.ledger.release("k", now=datetime(2026, 10, 29, 12, 0, 0))
        self.assertIsNotNone(self.ledger.get("k"))

    def test_mark_outcome_unknown_records_the_latch_guid(self) -> None:
        self.claim("k")
        later = _NOW + timedelta(seconds=3)
        self.ledger.mark_outcome_unknown("k", latch_guid="submit-0123456789abcdef", now=later)
        record = self.ledger.get("k")
        assert record is not None
        self.assertEqual(record["state"], "outcomeUnknown")
        self.assertEqual(record["latchGuid"], "submit-0123456789abcdef")
        self.assertEqual(record["updatedAt"], later.isoformat())
        self.assertEqual(record["createdAt"], _NOW.isoformat())
        self.assertEqual(record["fingerprint"], _FP)
        self.assertEqual(record["instance"], _INSTANCE)

    def test_mark_outcome_unknown_with_no_latch_guid_stores_none(self) -> None:
        self.claim("k")
        self.ledger.mark_outcome_unknown("k", latch_guid=None, now=_NOW)
        record = self.ledger.get("k")
        assert record is not None
        self.assertEqual(record["state"], "outcomeUnknown")
        self.assertIn("latchGuid", record)
        self.assertIsNone(record["latchGuid"])

    def test_the_outcome_unknown_file_still_loads_strictly(self) -> None:
        self.claim("k")
        self.ledger.mark_outcome_unknown("k", latch_guid="submit-0123456789abcdef", now=_NOW)
        self.assertEqual(Ledger(self.directory).get("k"), self.ledger.get("k"))

    def test_mark_outcome_unknown_on_an_absent_key_is_a_missing_error(self) -> None:
        with self.assertRaises(LedgerError) as caught:
            self.ledger.mark_outcome_unknown("nope", latch_guid=None, now=_NOW)
        self.assertEqual(caught.exception.reason, "missing")

    def _put(self, key: str, state: str) -> None:
        """Bring ``key`` to ``state`` through the ledger's own legal writes."""
        self.claim(key)
        if state == "submitting":
            return
        if state == "outcomeUnknown":
            self.ledger.mark_outcome_unknown(key, latch_guid="submit-0123456789abcdef", now=_NOW)
            return
        self.ledger.mark_started(key, handle={"kind": "transfer", "guid": _GUID}, now=_NOW)
        if state == "done":
            self.ledger.mark_done(key, result={"kind": "ran"}, now=_NOW)

    def test_a_transition_the_write_order_never_makes_is_refused_and_changes_nothing(
            self) -> None:
        """WR-04: the ledger is the one guard against a second send, so it does
        not rely on its callers: only a submitting record is released, only a
        submitting record starts or becomes outcomeUnknown, and a done or
        outcomeUnknown record is never overwritten."""
        later = _NOW + timedelta(seconds=9)
        operations = {
            "release": (
                ("started", "done", "outcomeUnknown"),
                lambda: self.ledger.release("k", now=later)),
            "mark_started": (
                ("started", "done", "outcomeUnknown"),
                lambda: self.ledger.mark_started("k", handle={"guid": _GUID}, now=later)),
            "mark_done": (
                ("done", "outcomeUnknown"),
                lambda: self.ledger.mark_done("k", result={"kind": "failed"}, now=later)),
            "mark_outcome_unknown": (
                ("started", "done", "outcomeUnknown"),
                lambda: self.ledger.mark_outcome_unknown("k", latch_guid=None, now=later)),
        }
        for name, (refused_from, operation) in operations.items():
            for state in refused_from:
                with self.subTest(operation=name, state=state):
                    shutil.rmtree(self.directory, ignore_errors=True)
                    self._put("k", state)
                    before = self.ledger.path.read_bytes()
                    with self.assertRaises(LedgerError) as caught:
                        operation()
                    self.assertEqual(caught.exception.reason, "state")
                    self.assertEqual(self.ledger.path.read_bytes(), before)
                    self.assertEqual(self.stray_temp_files(), [])

    def test_release_deletes_a_submitting_record_and_only_that_state(self) -> None:
        self._put("k", "submitting")
        self.ledger.release("k", now=_NOW)
        self.assertIsNone(self.ledger.get("k"))

    def test_mark_done_is_allowed_from_started_and_from_submitting(self) -> None:
        for state in ("started", "submitting"):
            with self.subTest(state=state):
                shutil.rmtree(self.directory, ignore_errors=True)
                self._put("k", state)
                self.ledger.mark_done("k", result={"kind": "ran"}, now=_NOW)
                record = self.ledger.get("k")
                assert record is not None
                self.assertEqual(record["state"], "done")

    def test_other_transitions_leave_no_latch_guid(self) -> None:
        self.claim("k")
        self.ledger.mark_started("k", handle={"guid": _GUID}, now=_NOW)
        self.ledger.mark_done("k", result={"kind": "ran"}, now=_NOW)
        record = self.ledger.get("k")
        assert record is not None
        self.assertIsNone(record.get("latchGuid"))

    def test_find_by_guid_returns_the_owning_step_key(self) -> None:
        other = "99999999-8888-7777-6666-555555555555"
        self.claim("k")
        self.claim("k2")
        self.claim("k3")
        self.ledger.mark_started("k", handle={"kind": "transfer", "guid": _GUID}, now=_NOW)
        self.ledger.mark_started("k2", handle={"kind": "transfer", "guid": other}, now=_NOW)
        self.assertEqual(self.ledger.find_by_guid(_GUID), "k")
        self.assertEqual(self.ledger.find_by_guid(other), "k2")
        self.assertIsNone(self.ledger.find_by_guid("11111111-0000-0000-0000-000000000000"))
        self.assertIsNone(self.ledger.find_by_guid(""))

    def test_find_by_guid_ignores_records_without_a_handle(self) -> None:
        self.claim("k")
        self.assertIsNone(self.ledger.find_by_guid(_GUID))

    def test_find_by_guid_is_read_only(self) -> None:
        self.assertIsNone(self.ledger.find_by_guid(_GUID))
        self.assertFalse(self.directory.exists())
        self.claim("k")
        before = self.ledger.path.read_bytes()
        self.ledger.find_by_guid(_GUID)
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_find_by_guid_fails_closed_on_a_corrupt_ledger(self) -> None:
        self.directory.mkdir()
        self.ledger.path.write_bytes(b"[]")
        with self.assertRaises(LedgerError):
            self.ledger.find_by_guid(_GUID)

    def test_mark_done_refuses_a_non_terminal_result_and_changes_nothing(self) -> None:
        self.claim("k")
        self.ledger.mark_started("k", handle={"guid": _GUID}, now=_NOW)
        before = self.ledger.path.read_bytes()
        for result in (
            {"kind": "timedOut"},
            {"kind": "lost", "reason": "pollFailed"},
            {"kind": "lost", "reason": "submitOutcomeUnknown"},
            {"kind": "cancelled"},
            {"kind": "needsInput"},
            {},
        ):
            with self.subTest(result=result):
                with self.assertRaises(ValueError):
                    self.ledger.mark_done("k", result=result, now=_NOW)
                self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_mark_done_accepts_each_terminal_result(self) -> None:
        for number, result in enumerate((
            {"kind": "ran"},
            {"kind": "failed"},
            {"kind": "aborted"},
            {"kind": "lost", "reason": "taskNotFound"},
        )):
            with self.subTest(result=result):
                key = f"k{number}"
                self.claim(key)
                self.ledger.mark_done(key, result=result, now=_NOW)
                record = self.ledger.get(key)
                assert record is not None
                self.assertEqual(record["state"], "done")
                self.assertEqual(record["result"], result)


class TestIsTerminal(unittest.TestCase):
    def test_terminal_results(self) -> None:
        for result in (
            {"kind": "ran"},
            {"kind": "failed"},
            {"kind": "aborted"},
            {"kind": "lost", "reason": "taskNotFound"},
        ):
            with self.subTest(result=result):
                self.assertTrue(is_terminal(result))

    def test_non_terminal_results(self) -> None:
        for result in (
            {"kind": "timedOut"},
            {"kind": "cancelled"},
            {"kind": "lost", "reason": "pollFailed"},
            {"kind": "lost", "reason": "submitOutcomeUnknown"},
            {"kind": "lost"},
            {"kind": "lost", "reason": "TaskNotFound"},
            {"kind": "needsInput"},
            {"kind": "readFailed"},
            {"kind": "refused"},
            {"kind": "Ran"},
            {"kind": "RAN"},
            {"kind": "ran "},
            {"kind": "unknown"},
            {"kind": None},
            {"kind": ["ran"]},
            {"kind": {"x": 1}},
            {"reason": "taskNotFound"},
            {},
        ):
            with self.subTest(result=result):
                self.assertFalse(is_terminal(result))

    def test_non_dict_input_is_not_terminal(self) -> None:
        for value in ([], ["ran"], "ran", None, 3, ("kind", "ran")):
            with self.subTest(value=value):
                self.assertFalse(is_terminal(value))  # type: ignore[arg-type]


class TestRetention(_LedgerCase):
    def seed(self, **ages_s: Any) -> None:
        """Write a ledger whose records are of the given (state, age in seconds)."""
        records: dict[str, Any] = {}
        for key, (state, age) in ages_s.items():
            records[key] = _record(state, when=_NOW - timedelta(seconds=age))
        self.write_records(records)

    def test_the_retention_is_seven_days(self) -> None:
        self.assertEqual(RETENTION_DONE_S, 604_800.0)

    def test_a_write_prunes_an_expired_done_record(self) -> None:
        self.seed(old=("done", RETENTION_DONE_S + 1.0))
        self.assertTrue(self.claim("new"))
        self.assertEqual(sorted(self.ledger.load()), ["new"])

    def test_a_done_record_at_exactly_the_retention_is_kept(self) -> None:
        self.seed(edge=("done", RETENTION_DONE_S))
        self.claim("new")
        self.assertEqual(sorted(self.ledger.load()), ["edge", "new"])

    def test_a_done_record_younger_than_the_retention_is_kept(self) -> None:
        self.seed(young=("done", 6 * 86_400.0), fresh=("done", 5.0))
        self.claim("new")
        self.assertEqual(sorted(self.ledger.load()), ["fresh", "new", "young"])

    def test_unfinished_records_of_any_age_are_kept(self) -> None:
        thirty_days = 30 * 86_400.0
        self.seed(
            sub=("submitting", thirty_days),
            start=("started", thirty_days),
            unknown=("outcomeUnknown", thirty_days),
            ancient=("submitting", 3650 * 86_400.0),
        )
        self.claim("new")
        self.assertEqual(
            sorted(self.ledger.load()), ["ancient", "new", "start", "sub", "unknown"])

    def test_load_alone_never_prunes(self) -> None:
        self.seed(old=("done", RETENTION_DONE_S + 100.0))
        before = self.ledger.path.read_bytes()
        self.assertEqual(sorted(self.ledger.load()), ["old"])
        self.assertIsNotNone(self.ledger.get("old"))
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_a_write_that_changes_nothing_does_not_prune(self) -> None:
        self.seed(old=("done", RETENTION_DONE_S + 100.0), live=("submitting", 10.0))
        before = self.ledger.path.read_bytes()
        self.assertFalse(self.claim("live"))
        self.ledger.release("absent", now=_NOW)
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_every_mutator_prunes(self) -> None:
        old = ("done", RETENTION_DONE_S + 100.0)
        with self.subTest(mutator="mark_started"):
            self.seed(old=old, live=("submitting", 1.0))
            self.ledger.mark_started("live", handle={"guid": _GUID}, now=_NOW)
            self.assertEqual(sorted(self.ledger.load()), ["live"])
        with self.subTest(mutator="mark_outcome_unknown"):
            self.seed(old=old, live=("submitting", 1.0))
            self.ledger.mark_outcome_unknown("live", latch_guid=None, now=_NOW)
            self.assertEqual(sorted(self.ledger.load()), ["live"])
        with self.subTest(mutator="release"):
            self.seed(old=old, live=("submitting", 1.0))
            self.ledger.release("live", now=_NOW)
            self.assertEqual(sorted(self.ledger.load()), [])
        with self.subTest(mutator="mark_done"):
            self.seed(old=old, live=("started", 1.0))
            self.ledger.mark_done("live", result={"kind": "ran"}, now=_NOW)
            self.assertEqual(sorted(self.ledger.load()), ["live"])

    def test_a_corrupt_ledger_is_never_pruned_or_treated_as_empty(self) -> None:
        self.directory.mkdir()
        raw = b'{"version": 1, "records": {"old": {"state": "done"}}}'
        self.ledger.path.write_bytes(raw)
        with self.assertRaises(LedgerError):
            self.claim("new")
        self.assertEqual(self.ledger.path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
