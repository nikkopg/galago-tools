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
    LEDGER_FILENAME,
    LOCK_FILENAME,
    Ledger,
    LedgerError,
    fingerprint,
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


if __name__ == "__main__":
    unittest.main()
