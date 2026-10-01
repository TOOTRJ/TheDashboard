"""Offline, independent acceptance tests for command ownership and uncertainty.

Only an injected transport and clock are used. No application configuration,
network client, database environment, or legacy persistence path is required.
"""

from __future__ import annotations

import asyncio
from collections import deque
from copy import deepcopy
import unittest
from unittest.mock import patch
from uuid import uuid4

from tests.security_support import deny_network
from vonneumann.core.decimal_execution import DecimalExecutionConfig
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.economic_operations import run_configuration
from vonneumann.db.command_repository import (
    CommandAdmissionError,
    CommandBusy,
    CommandRepository,
    UncertainCommand,
)


def identity():
    return str(uuid4())


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class Transport:
    def __init__(self):
        self.calls = []
        self.results = deque()

    def add(self, result):
        self.results.append(result)

    async def rpc(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if not self.results:
            raise AssertionError("No fake response was explicitly supplied")
        result = self.results.popleft()
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            return await result(name, arguments)
        return deepcopy(result)


class Gate:
    def __init__(self, result):
        self.result = result
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.task = None

    async def __call__(self, _name, _arguments):
        self.task = asyncio.current_task()
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if isinstance(self.result, BaseException):
            raise self.result
        return deepcopy(self.result)


class CommandRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.network_guard = deny_network()
        self.network_guard.__enter__()
        self.addCleanup(self.network_guard.__exit__, None, None, None)
        self.owner, self.run, self.worker = identity(), identity(), identity()
        self.clock, self.transport = Clock(), Transport()
        self.repo = CommandRepository(self.transport, self.owner, self.run, self.worker,
                                      monotonic=self.clock, lease_margin=.25)
        self.tasks, self.gates = [], []

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 1)
        await self.settled()

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task

    async def entered(self, gate):
        await asyncio.wait_for(gate.entered.wait(), 1)

    async def settled(self):
        for _ in range(30):
            if not self.repo.busy:
                return
            await asyncio.sleep(0)
        self.fail("Owned fake transport operation did not settle")

    def gate(self, result):
        gate = Gate(result)
        self.gates.append(gate)
        self.transport.add(gate)
        return gate

    def creation(self, **overrides):
        options = dict(owner_id=self.owner, run_id=self.run, worker_id=self.worker,
                       config={"strategy": "fixture", "nested": [1, 2]}, initial_cash="1000")
        options.update(overrides)
        return PreparedCommand.create(**options)

    def batch(self, operations=None, **overrides):
        options = dict(owner_id=self.owner, run_id=self.run, worker_id=self.worker,
                       fence=1, expected_revision=self.repo.revision,
                       operations=operations or [{"kind": "birth", "id": identity(),
                                                  "cash": "100", "parent_ids": []}])
        options.update(overrides)
        return PreparedCommand.batch(**options)

    def interruption(self, **overrides):
        options = dict(owner_id=self.owner, run_id=self.run,
                       expected_revision=self.repo.revision)
        options.update(overrides)
        return PreparedCommand.interrupt(**options)

    def reply(self, command, **overrides):
        if command.kind == "create":
            response = dict(run_id=self.run, revision=1, fence=1, status="starting")
        elif command.kind == "batch":
            status = self.repo.status
            for operation in command.expected_request["payload"]["operations"]:
                if operation["kind"] == "lifecycle":
                    status = operation["status"]
            response = dict(run_id=self.run, revision=command.expected_revision + 1,
                            fence=1, status=status, reserve="900")
        else:
            response = dict(run_id=self.run, revision=command.expected_revision + 1,
                            fence=self.repo.fence + 1, status="failed",
                            code="worker_interrupted", requires_reconciliation=True)
        response.update(overrides)
        return response

    def journal(self, command, response=None, **overrides):
        result = dict(request=command.expected_request, request_hash="ab" * 32,
                      response=self.reply(command) if response is None else response)
        result.update(overrides)
        return result

    async def created(self):
        command = self.creation()
        self.transport.add(self.reply(command))
        receipt = await self.repo.submit(command)
        self.assertEqual(receipt.revision, 1)
        return command

    def heartbeat_reply(self, **overrides):
        result = dict(run_id=self.run, revision=self.repo.revision, fence=self.repo.fence)
        result.update(overrides)
        return result

    async def leased(self, *, seconds=30):
        await self.created()
        self.transport.add(self.heartbeat_reply())
        await self.repo.heartbeat(lease_seconds=seconds)
        self.assertTrue(self.repo.lease_valid)
        self.assertTrue(self.repo.accepting)

    async def make_uncertain(self, command):
        self.transport.add(RuntimeError("fixture private token=DO_NOT_LEAK"))
        with self.assertRaises(UncertainCommand) as caught:
            await self.repo.submit(command)
        self.assertNotIn("DO_NOT_LEAK", str(caught.exception))
        self.assertEqual(self.repo.pending, command)
        self.assertTrue(self.repo.uncertain)
        self.assertFalse(self.repo.accepting)

    async def test_creation_ack_is_not_a_lease_and_receipt_is_defensive(self):
        self.assertEqual(self.repo.revision, 0)
        self.assertIsNone(self.repo.fence)
        self.assertIsNone(self.repo.status)
        self.assertIsNone(self.repo.pending)
        self.assertFalse(self.repo.accepting)
        self.assertFalse(self.repo.lease_valid)
        command = await self.created()
        self.assertEqual(self.repo.status, "starting")
        self.assertEqual(self.repo.fence, 1)
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.repo.accepting)
        receipt = self.repo.last_receipt
        self.assertEqual(receipt.command, command)
        response = receipt.response
        response["revision"] = 999
        self.assertEqual(receipt.response["revision"], 1)
        with self.assertRaises((AttributeError, TypeError)):
            receipt.revision = 99
        before = len(self.transport.calls)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(self.batch())
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(command)
        self.assertEqual(len(self.transport.calls), before)

    async def test_legacy_run_rejects_version_two_before_transport(self):
        self.assertIsNone(self.repo.command_version)
        await self.leased()
        self.assertEqual(self.repo.command_version, 1)
        operation = {"kind": "lifecycle", "status": "running"}
        command = self.batch([operation], version=2)
        before = len(self.transport.calls)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(command)
        self.assertEqual(len(self.transport.calls), before)
        self.assertIsNone(self.repo.pending)
        self.assertEqual(self.repo.revision, 1)
        legacy = self.batch([operation], version=1)
        self.transport.add(self.reply(legacy))
        await self.repo.submit(legacy)
        self.assertEqual(self.repo.command_version, 1)
        self.assertEqual(self.repo.revision, 2)

    async def test_decimal_run_rejects_legacy_batch_without_changing_binding(self):
        command = self.creation(config=run_configuration(DecimalExecutionConfig(fee_bps="1")))
        self.transport.add(self.reply(command))
        await self.repo.submit(command)
        self.assertEqual(self.repo.command_version, 2)
        self.assertFalse(self.repo.lease_valid)
        self.transport.add(self.heartbeat_reply())
        await self.repo.heartbeat()
        operation = {"kind": "lifecycle", "status": "running"}
        before = len(self.transport.calls)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(self.batch([operation], version=1))
        self.assertEqual(len(self.transport.calls), before)
        self.assertIsNone(self.repo.pending)
        exact = self.batch([operation], version=2)
        self.transport.add(self.reply(exact))
        await self.repo.submit(exact)
        self.assertEqual(self.repo.command_version, 2)
        self.assertEqual(self.repo.revision, 2)

    async def test_resolved_lost_creation_ack_adopts_its_original_version_only(self):
        config = run_configuration(DecimalExecutionConfig(fee_bps="2"))
        command = self.creation(config=config)
        config["durability_contract_version"] = 1
        await self.make_uncertain(command)
        self.assertIsNone(self.repo.command_version)
        self.transport.add(None)
        self.assertIsNone(await self.repo.resolve_pending())
        self.assertIsNone(self.repo.command_version)
        self.assertEqual(self.repo.pending, command)
        self.transport.add(self.journal(command))
        receipt = await self.repo.resolve_pending()
        self.assertEqual(receipt.command, command)
        self.assertEqual(self.repo.command_version, 2)
        self.assertFalse(self.repo.lease_valid)
        self.transport.add(self.heartbeat_reply())
        await self.repo.heartbeat()
        before = len(self.transport.calls)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(self.batch([{"kind": "lifecycle", "status": "running"}], version=1))
        self.assertEqual(len(self.transport.calls), before)
        self.assertEqual(self.repo.command_version, 2)

    async def test_command_version_binding_is_read_only(self):
        with self.assertRaises((AttributeError, TypeError)):
            self.repo.command_version = 2
        await self.created()
        with self.assertRaises((AttributeError, TypeError)):
            self.repo.command_version = 2
        self.assertEqual(self.repo.command_version, 1)

    async def test_heartbeat_deadline_uses_request_start_and_margin(self):
        await self.leased(seconds=2)
        self.clock.value = 101.749
        self.assertTrue(self.repo.lease_valid)
        self.clock.value = 101.75
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.repo.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(self.batch())

    async def test_valid_batch_advances_revision_only_after_matching_ack(self):
        await self.leased()
        command = self.batch()
        gate = self.gate(self.reply(command))
        caller = self.spawn(self.repo.submit(command))
        await self.entered(gate)
        self.assertEqual(self.repo.pending, command)
        self.assertEqual(self.repo.revision, 1)
        self.assertTrue(self.repo.busy)
        self.assertFalse(self.repo.accepting)
        self.assertIsNot(gate.task, caller)
        gate.release.set()
        receipt = await caller
        self.assertEqual(receipt.revision, 2)
        self.assertEqual(receipt.fence, 1)
        self.assertEqual(self.repo.revision, 2)
        self.assertIsNone(self.repo.pending)
        self.assertFalse(self.repo.uncertain)
        self.assertEqual(self.transport.calls[-1], (command.rpc_name, command.rpc_args))

    async def test_ack_after_local_deadline_is_recorded_but_does_not_restore_admission(self):
        await self.leased(seconds=2)
        command = self.batch()
        gate = self.gate(self.reply(command))
        caller = self.spawn(self.repo.submit(command))
        await self.entered(gate)
        self.clock.value = 105
        gate.release.set()
        receipt = await caller
        # The server may have committed before the response was delayed.
        self.assertEqual(receipt.revision, 2)
        self.assertEqual(self.repo.revision, 2)
        self.assertIsNone(self.repo.pending)
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.repo.accepting)

    async def test_pending_is_owned_before_transport_first_executes(self):
        command = self.creation()

        async def inspect(name, arguments):
            self.assertEqual(self.repo.pending, command)
            self.assertTrue(self.repo.busy)
            self.assertFalse(self.repo.accepting)
            self.assertEqual(name, "create_run")
            self.assertEqual(arguments, command.rpc_args)
            return self.reply(command)

        self.transport.add(inspect)
        await self.repo.submit(command)

    async def test_concurrent_submit_and_resolve_and_heartbeat_cannot_overlap(self):
        command = self.creation()
        gate = self.gate(self.reply(command))
        caller = self.spawn(self.repo.submit(command))
        await self.entered(gate)
        for coroutine in (self.repo.submit(self.creation()), self.repo.resolve_pending(), self.repo.heartbeat()):
            with self.assertRaises(CommandBusy):
                await coroutine
        self.assertEqual(len(self.transport.calls), 1)
        gate.release.set()
        await caller

    async def test_caller_cancellation_retains_owned_write_and_adopts_late_ack(self):
        command = self.creation()
        gate = self.gate(self.reply(command))
        caller = self.spawn(self.repo.submit(command))
        await self.entered(gate)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertFalse(gate.cancelled)
        self.assertEqual(self.repo.pending, command)
        self.assertTrue(self.repo.busy)
        self.assertFalse(self.repo.accepting)
        with self.assertRaises(CommandBusy):
            await self.repo.resolve_pending()
        gate.release.set()
        await self.settled()
        self.assertEqual(self.repo.revision, 1)
        self.assertIsNone(self.repo.pending)
        self.assertEqual(self.repo.last_receipt.command, command)
        self.assertFalse(self.repo.lease_valid)
        self.assertIsNone(await self.repo.resolve_pending())
        self.assertEqual([name for name, _ in self.transport.calls], ["create_run"])

    async def test_canceled_caller_late_failure_is_consumed_and_remains_uncertain(self):
        command = self.creation()
        gate = self.gate(RuntimeError("private fixture endpoint DO_NOT_LEAK"))
        caller = self.spawn(self.repo.submit(command))
        await self.entered(gate)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        gate.release.set()
        await self.settled()
        self.assertEqual(self.repo.pending, command)
        self.assertTrue(self.repo.uncertain)
        self.assertEqual(self.repo.revision, 0)
        self.transport.add(None)
        self.assertIsNone(await self.repo.resolve_pending())
        self.assertTrue(self.repo.uncertain)

    async def test_owned_transport_cancellation_retains_uncertainty(self):
        command = self.creation()
        gate = self.gate(self.reply(command))
        caller = self.spawn(self.repo.submit(command))
        await self.entered(gate)
        gate.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(gate.cancelled)
        self.assertFalse(self.repo.busy)
        self.assertEqual(self.repo.pending, command)
        self.assertTrue(self.repo.uncertain)
        self.assertEqual(self.repo.revision, 0)

    async def test_scheduler_failure_retains_command_without_sending_rpc(self):
        command = self.creation()
        with patch("vonneumann.db.command_repository.asyncio.create_task",
                   side_effect=RuntimeError("private scheduler DO_NOT_LEAK")):
            with self.assertRaises(CommandAdmissionError) as caught:
                await self.repo.submit(command)
        self.assertNotIn("DO_NOT_LEAK", str(caught.exception))
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.repo.pending, command)
        self.assertTrue(self.repo.uncertain)
        self.assertFalse(self.repo.busy)

    @unittest.skipUnless(hasattr(asyncio, "eager_task_factory"), "Python 3.12 eager task factory")
    async def test_eager_task_factory_cannot_finish_before_ownership_is_recorded(self):
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            command = self.creation()

            async def inspect(_name, _arguments):
                self.assertTrue(self.repo.busy)
                self.assertEqual(self.repo.pending, command)
                return self.reply(command)

            self.transport.add(inspect)
            receipt = await self.repo.submit(command)
            self.assertEqual(receipt.revision, 1)
            self.assertFalse(self.repo.busy)
            self.assertIsNone(self.repo.pending)
        finally:
            loop.set_task_factory(previous)

    async def test_owned_wrapper_cancelled_before_start_cleans_ownership(self):
        command = self.creation()
        create_task = asyncio.create_task

        def cancel_immediately(coroutine):
            task = create_task(coroutine)
            task.cancel()
            return task

        with patch("vonneumann.db.command_repository.asyncio.create_task", side_effect=cancel_immediately):
            with self.assertRaises(asyncio.CancelledError):
                await self.repo.submit(command)
        await self.settled()
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.repo.pending, command)
        self.assertTrue(self.repo.uncertain)
        self.assertFalse(self.repo.busy)

    async def test_unknown_transport_failure_never_retries_or_discards_command(self):
        await self.leased()
        command = self.batch()
        await self.make_uncertain(command)
        calls = list(self.transport.calls)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(self.batch())
        with self.assertRaises(CommandAdmissionError):
            await self.repo.heartbeat()
        self.assertEqual(calls, self.transport.calls)
        self.assertFalse(self.repo.lease_valid)

    async def test_null_resolution_is_inconclusive_and_retains_exact_command(self):
        command = self.creation()
        await self.make_uncertain(command)
        self.transport.add(None)
        self.assertIsNone(await self.repo.resolve_pending())
        self.assertEqual(self.repo.pending, command)
        self.assertTrue(self.repo.uncertain)
        self.assertEqual(self.repo.revision, 0)
        self.assertEqual(self.transport.calls[-1], ("get_command", {
            "owner_id": self.owner, "run": self.run, "command_id": command.command_id}))

    async def test_valid_resolution_after_lease_expiry_adopts_original_receipt(self):
        await self.leased()
        command = self.batch()
        await self.make_uncertain(command)
        self.clock.value = 1000
        self.transport.add(self.journal(command))
        receipt = await self.repo.resolve_pending()
        self.assertEqual(receipt.command, command)
        self.assertEqual(receipt.revision, 2)
        self.assertEqual(self.repo.revision, 2)
        self.assertIsNone(self.repo.pending)
        self.assertFalse(self.repo.uncertain)
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.repo.accepting)
        self.transport.add(self.heartbeat_reply())
        await self.repo.heartbeat()
        self.assertTrue(self.repo.accepting)

    async def test_resolution_failure_is_sanitized_and_does_not_change_pending(self):
        command = self.creation()
        await self.make_uncertain(command)
        self.transport.add(RuntimeError("secret DO_NOT_LEAK"))
        with self.assertRaises(UncertainCommand) as caught:
            await self.repo.resolve_pending()
        self.assertNotIn("DO_NOT_LEAK", str(caught.exception))
        self.assertEqual(self.repo.pending, command)
        self.assertEqual(self.repo.revision, 0)
        self.assertFalse(self.repo.busy)

    async def test_resolver_must_match_request_including_identity_and_decimal_spelling(self):
        await self.leased()
        command = self.batch()
        await self.make_uncertain(command)
        variants = []
        for name, value in (("owner_id", identity()), ("run_id", identity()),
                            ("command_id", identity()), ("worker", identity()),
                            ("expected_revision", 2), ("fence", 2)):
            changed = command.expected_request
            changed[name] = value
            variants.append(changed)
        changed = command.expected_request
        changed["payload"]["operations"][0]["cash"] = "100.0"
        variants.append(changed)
        changed = command.expected_request
        changed["payload"]["operations"].append({"kind": "lifecycle", "status": "running"})
        variants.append(changed)
        for request in variants:
            with self.subTest(request=request):
                self.transport.add(self.journal(command, request=request))
                with self.assertRaises(UncertainCommand):
                    await self.repo.resolve_pending()
                self.assertEqual(self.repo.revision, 1)
                self.assertEqual(self.repo.pending, command)
        self.transport.add(self.journal(command))
        self.assertEqual((await self.repo.resolve_pending()).revision, 2)

    async def test_resolver_rejects_invalid_hash_shape_and_extra_fields(self):
        command = self.creation()
        await self.make_uncertain(command)
        for invalid in (None, {}, [], "", "ab" * 31, "gg" * 32, 1, True):
            with self.subTest(hash=invalid):
                self.transport.add(self.journal(command, request_hash=invalid))
                with self.assertRaises(UncertainCommand):
                    await self.repo.resolve_pending()
                self.assertEqual(self.repo.pending, command)
        value = self.journal(command)
        value["unexpected"] = "provider detail"
        self.transport.add(value)
        with self.assertRaises(UncertainCommand):
            await self.repo.resolve_pending()
        self.assertEqual(self.repo.revision, 0)

    async def test_resolver_rejects_non_json_config_coercions(self):
        command = self.creation(config={"1": [1, 2]})
        await self.make_uncertain(command)
        for configuration in ({"1": (1, 2)}, {1: [1, 2]}):
            with self.subTest(configuration=configuration):
                changed = command.expected_request
                changed["config"] = configuration
                self.transport.add(self.journal(command, request=changed))
                with self.assertRaises(UncertainCommand):
                    await self.repo.resolve_pending()
                self.assertEqual(self.repo.pending, command)
                self.assertEqual(self.repo.revision, 0)

    async def test_resolver_rejects_tuple_operations_instead_of_json_array(self):
        await self.leased()
        command = self.batch()
        await self.make_uncertain(command)
        changed = command.expected_request
        changed["payload"]["operations"] = tuple(changed["payload"]["operations"])
        self.transport.add(self.journal(command, request=changed))
        with self.assertRaises(UncertainCommand):
            await self.repo.resolve_pending()
        self.assertEqual(self.repo.pending, command)
        self.assertEqual(self.repo.revision, 1)

    async def test_malformed_create_responses_never_establish_ownership(self):
        changes = [dict(run_id=identity()), dict(revision=2), dict(revision=True),
                   dict(fence=2), dict(fence=True), dict(status="running"),
                   dict(unexpected="secret detail")]
        for overrides in changes:
            with self.subTest(overrides=overrides):
                transport = Transport()
                repo = CommandRepository(transport, self.owner, self.run, self.worker, monotonic=self.clock)
                command = self.creation()
                transport.add(self.reply(command, **overrides))
                with self.assertRaises(UncertainCommand):
                    await repo.submit(command)
                self.assertEqual(repo.revision, 0)
                self.assertIsNone(repo.fence)
                self.assertEqual(repo.pending, command)
                self.assertFalse(repo.lease_valid)

    async def test_malformed_batch_response_is_uncertain_without_local_revision_advance(self):
        await self.leased()
        command = self.batch()
        self.transport.add(self.reply(command, reserve=900.0))
        with self.assertRaises(UncertainCommand):
            await self.repo.submit(command)
        self.assertEqual(self.repo.revision, 1)
        self.assertEqual(self.repo.pending, command)
        for overrides in (dict(run_id=identity()), dict(revision=3), dict(revision=True),
                          dict(fence=2), dict(status="unknown"), dict(reserve="NaN"),
                          dict(reserve="-1"), dict(extra=True)):
            with self.subTest(overrides=overrides):
                self.transport.add(self.journal(command, response=self.reply(command, **overrides)))
                with self.assertRaises(UncertainCommand):
                    await self.repo.resolve_pending()
                self.assertEqual(self.repo.revision, 1)
                self.assertEqual(self.repo.pending, command)

    async def test_mismatched_prepared_identities_are_rejected_before_transport(self):
        for overrides in (dict(owner_id=identity()), dict(run_id=identity()), dict(worker_id=identity())):
            with self.subTest(overrides=overrides), self.assertRaises(CommandAdmissionError):
                await self.repo.submit(self.creation(**overrides))
        self.assertEqual(self.transport.calls, [])
        self.assertIsNone(self.repo.pending)
        await self.leased()
        before = list(self.transport.calls)
        for overrides in (dict(owner_id=identity()), dict(run_id=identity()), dict(worker_id=identity()),
                          dict(fence=2), dict(expected_revision=2)):
            with self.subTest(overrides=overrides), self.assertRaises(CommandAdmissionError):
                await self.repo.submit(self.batch(**overrides))
        self.assertEqual(self.transport.calls, before)
        self.assertIsNone(self.repo.pending)
        self.assertTrue(self.repo.lease_valid)

    def test_repository_identity_properties_cannot_be_reassigned(self):
        for name in ("owner_id", "run_id", "worker_id"):
            with self.subTest(name=name), self.assertRaises(AttributeError):
                setattr(self.repo, name, identity())
        self.assertEqual(self.repo.owner_id, self.owner)
        self.assertEqual(self.repo.run_id, self.run)
        self.assertEqual(self.repo.worker_id, self.worker)

    async def test_transport_cannot_mutate_retained_command_snapshot(self):
        config = {"nested": {"original": [1, 2]}}
        command = self.creation(config=config)
        before = command.request
        config["nested"]["original"].append(3)

        async def malicious(_name, arguments):
            arguments["configuration"]["nested"]["original"].append(999)
            arguments["owner_id"] = identity()
            raise RuntimeError("No acknowledgement")

        self.transport.add(malicious)
        with self.assertRaises(UncertainCommand):
            await self.repo.submit(command)
        self.assertEqual(command.request, before)
        self.assertEqual(self.repo.pending.request, before)
        self.transport.add(self.journal(command))
        receipt = await self.repo.resolve_pending()
        self.assertEqual(receipt.command.expected_request["config"], {"nested": {"original": [1, 2]}})

    async def test_heartbeat_serializes_and_expired_delayed_ack_cannot_renew_from_receipt(self):
        await self.created()
        gate = self.gate(self.heartbeat_reply())
        caller = self.spawn(self.repo.heartbeat(lease_seconds=2))
        await self.entered(gate)
        self.assertTrue(self.repo.busy)
        self.assertFalse(self.repo.accepting)
        with self.assertRaises(CommandBusy):
            await self.repo.heartbeat()
        with self.assertRaises(CommandBusy):
            await self.repo.submit(self.batch())
        self.clock.value = 102
        gate.release.set()
        # A valid but already expired ACK does not confer a usable lease.
        try:
            await caller
        except (UncertainCommand, CommandAdmissionError):
            pass
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.repo.accepting)
        self.assertIsNone(self.repo.pending)
        self.transport.add(self.heartbeat_reply())
        await self.repo.heartbeat(lease_seconds=2)
        self.assertTrue(self.repo.lease_valid)

    async def test_failed_heartbeat_invalidates_previous_lease_and_sanitizes_error(self):
        await self.leased()
        self.transport.add(RuntimeError("private provider DO_NOT_LEAK"))
        with self.assertRaises((UncertainCommand, CommandAdmissionError)) as caught:
            await self.repo.heartbeat()
        self.assertNotIn("DO_NOT_LEAK", str(caught.exception))
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.repo.accepting)
        self.assertIsNone(self.repo.pending)
        self.assertEqual(self.repo.revision, 1)
        self.transport.add(self.heartbeat_reply())
        await self.repo.heartbeat()
        self.assertTrue(self.repo.lease_valid)

    async def test_heartbeat_validates_exact_identity_revision_fence_and_shape(self):
        await self.created()
        for changes in (dict(run_id=identity()), dict(revision=2), dict(revision=True),
                        dict(fence=2), dict(fence=True), dict(unexpected=True)):
            with self.subTest(changes=changes):
                self.transport.add(self.heartbeat_reply(**changes))
                with self.assertRaises((UncertainCommand, CommandAdmissionError)):
                    await self.repo.heartbeat()
                self.assertFalse(self.repo.lease_valid)
                self.assertEqual(self.repo.revision, 1)
                self.assertEqual(self.repo.fence, 1)
        self.transport.add(self.heartbeat_reply())
        await self.repo.heartbeat()
        self.assertTrue(self.repo.lease_valid)

    async def test_invalid_lease_durations_never_reach_transport(self):
        await self.created()
        before = list(self.transport.calls)
        for value in (None, False, True, 0, -1, 121, 30.0, "30"):
            with self.subTest(value=value), self.assertRaises(CommandAdmissionError):
                await self.repo.heartbeat(lease_seconds=value)
        self.assertEqual(self.transport.calls, before)
        self.assertFalse(self.repo.lease_valid)

    async def test_backward_or_nonfinite_clock_invalidates_known_lease(self):
        await self.leased()
        self.clock.value = 99
        with self.assertRaises(CommandAdmissionError):
            _ = self.repo.lease_valid
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.repo.accepting)
        for value in (float("nan"), float("inf"), True):
            with self.subTest(value=value):
                self.clock.value = value
                before = list(self.transport.calls)
                with self.assertRaises(CommandAdmissionError):
                    await self.repo.heartbeat()
                self.assertEqual(self.transport.calls, before)
                self.assertFalse(self.repo.lease_valid)
        self.clock.value = 101
        self.transport.add(self.heartbeat_reply())
        await self.repo.heartbeat()
        self.assertTrue(self.repo.lease_valid)

    async def test_canceled_heartbeat_retains_owned_transport_until_ack(self):
        await self.created()
        gate = self.gate(self.heartbeat_reply())
        caller = self.spawn(self.repo.heartbeat())
        await self.entered(gate)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.repo.busy)
        self.assertFalse(self.repo.accepting)
        self.clock.value = 101
        gate.release.set()
        await self.settled()
        self.assertTrue(self.repo.lease_valid)
        self.assertEqual(len(self.transport.calls), 2)

    async def test_close_admission_is_permanent_but_pending_resolution_remains_available(self):
        command = self.creation()
        await self.make_uncertain(command)
        self.repo.close_admission()
        self.transport.add(self.journal(command))
        receipt = await self.repo.resolve_pending()
        self.assertEqual(receipt.revision, 1)
        self.assertFalse(self.repo.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.heartbeat()
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(self.batch())
        self.repo.close_admission()
        self.assertFalse(self.repo.accepting)

    async def test_close_admission_during_owned_submission_cannot_be_undone_by_ack(self):
        await self.leased()
        command = self.batch()
        gate = self.gate(self.reply(command))
        caller = self.spawn(self.repo.submit(command))
        await self.entered(gate)
        self.repo.close_admission()
        gate.release.set()
        receipt = await caller
        self.assertEqual(receipt.revision, 2)
        self.assertEqual(self.repo.revision, 2)
        self.assertFalse(self.repo.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.heartbeat()

    async def test_close_admission_during_renewal_cannot_be_undone_by_ack(self):
        await self.created()
        gate = self.gate(self.heartbeat_reply())
        caller = self.spawn(self.repo.heartbeat())
        await self.entered(gate)
        self.repo.close_admission()
        gate.release.set()
        await caller
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.repo.accepting)

    async def test_repository_cannot_move_to_another_event_loop(self):
        await self.created()

        def other_loop():
            return asyncio.run(self.repo.resolve_pending())

        with self.assertRaises(CommandAdmissionError):
            await asyncio.to_thread(other_loop)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.repo.revision, 1)

    async def test_terminal_ack_cannot_resume_or_renew_and_preserves_receipt(self):
        await self.leased()
        command = self.batch([{"kind": "lifecycle", "status": "stopped"}])
        self.transport.add(self.reply(command))
        receipt = await self.repo.submit(command)
        self.assertEqual(receipt.status, "stopped")
        self.assertFalse(self.repo.accepting)
        before = list(self.transport.calls)
        with self.assertRaises(CommandAdmissionError):
            await self.repo.submit(self.batch([{"kind": "lifecycle", "status": "running"}]))
        with self.assertRaises(CommandAdmissionError):
            await self.repo.heartbeat()
        self.assertEqual(self.repo.last_receipt, receipt)
        self.assertEqual(self.transport.calls, before)

    async def test_interruption_can_be_submitted_without_a_locally_valid_lease(self):
        await self.created()
        self.assertFalse(self.repo.lease_valid)
        command = self.interruption()
        self.transport.add(self.reply(command))
        receipt = await self.repo.submit(command)
        self.assertEqual(receipt.revision, 2)
        self.assertEqual(receipt.fence, 2)
        self.assertEqual(receipt.status, "failed")
        self.assertTrue(receipt.response["requires_reconciliation"])
        self.assertFalse(self.repo.accepting)
        self.assertFalse(self.repo.lease_valid)
        self.assertEqual(self.transport.calls[-1], ("interrupt_expired", command.rpc_args))

    async def test_interrupt_failure_is_uncertain_and_resolution_validates_fence_increment(self):
        await self.created()
        command = self.interruption()
        await self.make_uncertain(command)
        for changes in (dict(fence=1), dict(fence=3), dict(revision=3), dict(status="running"),
                        dict(code="other"), dict(requires_reconciliation=False),
                        dict(requires_reconciliation=1)):
            with self.subTest(changes=changes):
                self.transport.add(self.journal(command, response=self.reply(command, **changes)))
                with self.assertRaises(UncertainCommand):
                    await self.repo.resolve_pending()
                self.assertEqual(self.repo.revision, 1)
                self.assertEqual(self.repo.pending, command)
        self.transport.add(self.journal(command))
        self.assertEqual((await self.repo.resolve_pending()).fence, 2)

    async def test_resolver_cancellation_retains_owned_read_and_adopts_matching_result(self):
        command = self.creation()
        await self.make_uncertain(command)
        gate = self.gate(self.journal(command))
        caller = self.spawn(self.repo.resolve_pending())
        await self.entered(gate)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(self.repo.busy)
        self.assertFalse(gate.cancelled)
        gate.release.set()
        await self.settled()
        self.assertEqual(self.repo.revision, 1)
        self.assertIsNone(self.repo.pending)
        self.assertEqual(self.repo.last_receipt.command, command)

    async def test_resolve_with_no_pending_does_not_contact_transport(self):
        self.assertIsNone(await self.repo.resolve_pending())
        self.assertEqual(self.transport.calls, [])
        await self.created()
        before = list(self.transport.calls)
        self.assertIsNone(await self.repo.resolve_pending())
        self.assertEqual(self.transport.calls, before)
