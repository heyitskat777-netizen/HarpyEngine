"""Break Down uses printed roll ownership and actual native effect work."""

import asyncio

import pytest
from test_handler_creation import agree, complete, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state
from test_mission_ui import current
from test_off_duty_cycle import activate, prepared
from test_punishment_service import submit

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_frantic_breakdown import records
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("faces", ((1, 2), (3, 3), (4, 4)))
def test_break_down_keeps_roll_roles_and_actual_consequences(ledger, faces):
    def create(_):
        creation = HandlerCreationService(ledger)
        approval, rulings = ledger.policy.m3_approval, ledger.policy.owner_m3_rulings
        ledger.policy = ledger.policy.model_copy(
            update=dict(
                m3_approval=approval.model_copy(
                    update=dict(subsystems=approval.subsystems | {"plays", "playbooks"})
                ),
                owner_m3_rulings=rulings.model_copy(
                    update=dict(handler_creation="owned_shared_choices_preserve_existing")
                ),
            )
        )
        save(creation, complete(creation, "Frantic"))
        agree(creation)
        preview = creation.view(ADMIN)
        creation.activate(
            ADMIN, "activate-frantic", preview["revision"], preview["game_revision"], True
        )

    cycle, game, period = prepared(ledger, before_period=create)
    activate(cycle, game, period)
    game.dice = Dice(faces)
    native = HandlerPlayService(ledger)
    native.game = game
    service, inbox = FranticBreakdownService(ledger, game), InboxService(ledger)
    expected = state(game).revision
    fake_account = "PRIVATE_BREAKDOWN_ACCOUNT"

    async def start():
        click = current(1, 47500)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, native)
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, "frantic_breakdown")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(account=fake_account)
        sent = current(1, 47501)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(start())
    original = service.start(ADMIN, "47501", expected, 900, fake_account)
    identity = original["id"]
    (saved,) = records(state(game))
    assert original["total"] == sum(faces) + 3 and saved.faces == faces
    assert set(saved.bases) == {"base0", "base1", "base2"} and game.dice.calls == 1
    owner = OTHER if faces == (1, 2) else ADMIN
    wrong = PLAYER if owner == ADMIN else ADMIN
    options = (
        ("office", "moderate_one", "minor_all")
        if owner == OTHER
        else ("office", "moderate_one")
        if faces == (3, 3)
        else ("minor_all",)
    )
    target = current_ref(state(game), 3)
    with pytest.raises(WorkflowError, match="saved original owner"):
        service.select(wrong, "wrong-breakdown-owner", identity, state(game).revision, options)
    assert identity not in {x.identity for x in inbox.items(PLAYER)}
    with pytest.raises(WorkflowError):
        service.get(PLAYER, identity)
    ledger.engine.dispose()

    async def choose(viewer, sequence, **values):
        click = current(viewer.user_id, sequence)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(viewer) if x.identity == identity)
        await InboxView(inbox, viewer.user_id).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        sent = current(viewer.user_id, sequence + 1)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    selection = dict(options=options)
    if "office" in options:
        selection["office"] = (target.token,)
    if "moderate_one" in options:
        selection["moderate"] = (target.token,)
    ledger.safety(OTHER, "pause-breakdown", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.select(owner, "paused-breakdown", identity, state(game).revision, options)
    ledger.safety(OTHER, "resume-breakdown", ledger.status(OTHER)["revision"], pause=False)
    awaiting = state(game).revision
    asyncio.run(choose(owner, 47510, **selection))
    replay = service.select(
        owner,
        "47511",
        identity,
        awaiting,
        options,
        office=target if "office" in options else None,
        moderate=target if "moderate_one" in options else None,
    )
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.select(owner, "stale-breakdown", identity, awaiting, options)
    if faces == (4, 4):
        assert replay["state"] == "choice"
        assert service.get(PLAYER, identity)["choose"] == 1
        asyncio.run(choose(PLAYER, 47520, options=("office",), office=(target.token,)))
    assert service.get(ADMIN, identity)["phase"] == "effects"
    with pytest.raises(WorkflowError, match="original Girl"):
        service.discover(ADMIN, "fake-office-discovery", identity, state(game).revision, "Fake.")
    asyncio.run(choose(OTHER, 47530, account="PRIVATE_ACTUAL_OFFICE_DISCOVERY"))
    assert service.get(ADMIN, identity)["phase"] == "effects"

    discipline = PunishmentService(ledger)
    work = [x for x in cycle.periods.get(ADMIN, period)["work"] if x["kind"] == "punishment"]
    assert len(work) == sum(
        2 if value == "minor_all" else 1 for value in options if value != "office"
    )
    for row in work:
        work_id = row["id"]
        detail = discipline.get(ADMIN, work_id)
        severity = detail["required_severity"]
        subject = PLAYER if detail["subject_id"] == "2" else OTHER
        choice = Details(kind="stimulant_injection")
        if severity == "moderate":
            with pytest.raises(WorkflowError, match="actual severity"):
                submit(discipline, ADMIN, work_id, choice, "wrong-severity")
            asset_id = next(
                x.id for x in state(game).sheets[str(subject.user_id)].assets if x.family == "frame"
            )
            choice = Details(kind="frame_disassembly", asset=asset_id)
        discipline.propose_scene(
            ADMIN,
            "scene:" + work_id,
            work_id,
            detail["revision"],
            detail["game_revision"],
            "A private synthetic discipline scene.",
        )
        for performer in (ADMIN, subject):
            step = discipline.get(performer, work_id)
            discipline.attest_scene(
                performer,
                f"attest:{performer.user_id}:{work_id}",
                work_id,
                step["revision"],
                step["game_revision"],
            )
        submit(discipline, ADMIN, work_id, choice, "perform:" + work_id)
        assert discipline.get(subject, work_id)["state"] == "resolved"
    assert service.get(ADMIN, identity)["phase"] == "complete"
    assert game.dice.calls == 1
