"""One explicit confirmation freezes its choices until the submission finishes."""

import asyncio
import threading
from unittest.mock import AsyncMock

import pytest
from test_m2_ui import interaction

from girlframe.discord_adapter.m2_forms import Field, NarrativeModal, NativeForm
from girlframe.services.onboarding import WorkflowError


def form_with(submit):
    return NativeForm(
        2,
        "Confirm an actual choice",
        "Review the original choices before confirming.",
        [Field("account", "Describe")],
        submit,
        values={"account": "Original confirmed account"},
    )


def test_confirmation_snapshots_values_before_deferred_acknowledgment():
    async def run():
        acknowledged = asyncio.Event()
        resume = asyncio.Event()

        async def defer(**kwargs):
            acknowledged.set()
            await resume.wait()

        submit = AsyncMock(return_value="Saved")
        form = form_with(submit)
        original = interaction()
        original.response.defer.side_effect = defer
        pending = asyncio.create_task(form.confirm.callback(original))
        try:
            await asyncio.wait_for(acknowledged.wait(), 5)
            # A callback already admitted before confirmation must not change its payload.
            form.values["account"] = "A later unconfirmed account"
        finally:
            resume.set()
            await pending

        submit.assert_awaited_once_with(original, {"account": "Original confirmed account"})
        assert submit.await_args.args[1] is not form.values
        assert form.completed

    asyncio.run(run())


def test_inflight_confirmation_rejects_duplicate_submit_and_open_modal():
    async def run():
        started = asyncio.Event()
        finish = asyncio.Event()

        async def save(current, values):
            started.set()
            await finish.wait()
            return "Saved"

        submit = AsyncMock(side_effect=save)
        form = form_with(submit)
        modal = NarrativeModal(form, form.fields[0])
        modal.input._value = "Late modal account"
        pending = asyncio.create_task(form.confirm.callback(interaction()))
        try:
            await asyncio.wait_for(started.wait(), 5)
            assert not await form.interaction_check(interaction())
            await asyncio.wait_for(form.confirm.callback(interaction()), 5)
            await modal.on_submit(interaction())
            assert submit.await_count == 1
            assert form.values == {"account": "Original confirmed account"}
        finally:
            finish.set()
            await pending

        await form.confirm.callback(interaction())
        assert submit.await_count == 1 and form.completed

    asyncio.run(run())


@pytest.mark.parametrize("error", [WorkflowError("Reopen"), ValueError("Invalid"), KeyError("key")])
def test_failed_confirmation_reopens_for_explicit_corrected_retry(error):
    async def run():
        submit = AsyncMock(side_effect=[error, "Saved"])
        form = form_with(submit)
        await form.confirm.callback(interaction())
        assert not form.completed
        assert await form.interaction_check(interaction())

        modal = NarrativeModal(form, form.fields[0])
        modal.input._value = "Corrected account"
        await modal.on_submit(interaction())
        await form.confirm.callback(interaction())
        assert form.completed and submit.await_count == 2
        assert submit.await_args.args[1] == {"account": "Corrected account"}

    asyncio.run(run())


def test_cancelled_confirmation_stays_closed_while_backend_thread_finishes():
    async def run():
        started = threading.Event()
        finish = threading.Event()
        finished = threading.Event()
        saved = []

        def save():
            started.set()
            try:
                if not finish.wait(5):
                    raise TimeoutError("Test did not release the actual backend thread")
                saved.append("committed")
                return "Saved"
            finally:
                finished.set()

        async def submit_action(current, values):
            return await asyncio.to_thread(save)

        submit = AsyncMock(side_effect=submit_action)
        form = form_with(submit)
        pending = asyncio.create_task(form.confirm.callback(interaction()))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert not saved and not form.completed
            assert not await form.interaction_check(interaction())
            await form.confirm.callback(interaction())
            assert submit.await_count == 1
        finally:
            finish.set()
            assert await asyncio.to_thread(finished.wait, 5)

        # The thread's eventual commit does not establish a result for the cancelled form.
        assert saved == ["committed"] and not form.completed
        assert not await form.interaction_check(interaction())

    asyncio.run(run())


def test_unknown_submission_failure_requires_saved_progress_review():
    async def run():
        saved = []

        async def submit_action(current, values):
            saved.append("committed")
            raise RuntimeError("Result unavailable after the operation")

        submit = AsyncMock(side_effect=submit_action)
        form = form_with(submit)
        with pytest.raises(RuntimeError, match="Result unavailable"):
            await form.confirm.callback(interaction())
        assert saved == ["committed"] and not form.completed
        check = interaction()
        assert not await form.interaction_check(check)
        assert "outcome is unknown" in check.response.send_message.call_args.args[0]
        await form.confirm.callback(interaction())
        assert submit.await_count == 1

    asyncio.run(run())


def test_cancelled_acknowledgment_does_not_lock_an_unstarted_submission():
    async def run():
        submit = AsyncMock(return_value="Saved")
        form = form_with(submit)
        original = interaction()
        original.response.defer.side_effect = asyncio.CancelledError
        with pytest.raises(asyncio.CancelledError):
            await form.confirm.callback(original)
        submit.assert_not_awaited()
        assert not form.completed
        assert await form.interaction_check(interaction())

    asyncio.run(run())
