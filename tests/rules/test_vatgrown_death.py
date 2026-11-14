"""Deferred P1 normal: actual death, distinct reviewed replacement, real supply and own noticing."""

import asyncio
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from test_creation import selected
from test_facilitator_native import interaction
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_vatgrown_plays import ready

from girlframe.discord_adapter.m3_careers import open_replacement
from girlframe.discord_adapter.m3_vatgrown_death import open_vatgrown_death
from girlframe.discord_adapter.p1_shelving import register_shelving
from girlframe.engine import m3_vatgrown_death as rules
from girlframe.engine.bonds import BondProposal
from girlframe.engine.creation_details import DesireChoice, GirlDetails, NpcInvestor
from girlframe.engine.drafts import DraftInput
from girlframe.engine.handler_setup import PilotRef
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.bonds import BondService
from girlframe.services.creation import CreationService
from girlframe.services.creation_coordination import CoordinationService
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m3_careers import CareerService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_vatgrown_death import VatgrownDeathService, prove
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService
from girlframe.services.p1_shelving import ShelvingService
from girlframe.services.p1_shelving_review import ShelvingReviewService


def _native_source(service, viewer, identity, **values):
    async def perform():
        opened = current(viewer.user_id, uuid4().int % 1000000000)
        opened.channel_id = 999
        await opened.response.defer(ephemeral=True)
        await open_vatgrown_death(opened, service, identity)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        submitted = current(viewer.user_id, uuid4().int % 1000000000)
        submitted.channel_id = 998
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(service.game)
        await form.confirm.callback(submitted)
        assert state(service.game) == saved

    asyncio.run(perform())


def test_actual_vatgrown_death_fresh_native_activation_and_original_other_owned_notice(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    old = state(game)
    original = current_ref(old, 2)
    FacilitatorService(game).configure(
        ADMIN, "replacement-shelving-reviewer", "user", ADMIN.user_id
    )
    shelving = ShelvingService(game)
    old_request = shelving.request(PLAYER, "original-before-real-death")
    old_frame = next(x.frame_instance for x in old.placements if x.actor == original)
    with ledger.transaction() as c:
        prior = state(game)
        frames = [x for x in prior.sheets["2"].assets if x.family == "frame"]
        for component in frames[1:]:
            component.damaged = True
        last = frames[0].id
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_vatgrown_Frame_damage", prior)
    physical = PhysicalService(ledger)
    own = physical.preview(PLAYER)
    physical.operate(
        PLAYER,
        str(uuid4()),
        own["game_revision"],
        CockpitAction(
            actor=original,
            operation="pilot",
            expected_position=own["position_sha256"],
            account="I actually enter and pilot my original Frame",
            confirmed=True,
        ),
    )
    game.dice.faces = (1, 1)
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            piloting=True,
            trigger_confirmed=True,
            context="Actual confrontation while piloting my original Frame",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, parent)["receipt"] is not None
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="My actual counterattack")
    answer(game, PLAYER, "beneath_details", denied=(last,))
    death = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            parent=parent,
            heat=0,
            piloting=True,
            trigger_confirmed=True,
            context="Actual required Defeat after the last working Frame Asset is damaged",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, death)["receipt"] is not None
    pass_tags(game)
    death_receipt = game.inspect(PLAYER, death)["receipt"]
    answer(
        game, PLAYER, "defeat_select", options=("death",), text="I choose the actual printed death"
    )
    tick(worker, gateway, 8)
    ended = state(game)
    archive = next(x for x in ended.career_archives if x.actor == original)
    assert archive.ending == "death" and "2" not in ended.sheets
    careers = CareerService(ledger)
    detail = careers.get(PLAYER, archive.id)
    assert detail["vatgrown_death_required"]
    with pytest.raises(WorkflowError):
        careers.begin_replacement(
            PLAYER,
            str(uuid4()),
            archive.id,
            ended.revision,
            DraftInput(
                callsign="Not a Vatgrown", girl_playbook="ALPHA", frame_playbook="THE ENFORCER"
            ),
        )
    assert state(game) == ended

    async def begin_native():
        opened = current(2, uuid4().int % 1000000000)
        await opened.response.defer(ephemeral=True)
        await open_replacement(opened, careers, archive.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert set(dict(next(x for x in form.fields if x.key == "girl").options)) == {"VATGROWN"}
        form.values.update(
            callsign="ANOTHER_ACTUAL_VATGROWN",
            girl=("VATGROWN",),
            frame=("THE ENFORCER",),
            notes="NEW_PERSON_PRIVATE_NOTE",
        )
        reply = current(2, uuid4().int % 1000000000)
        await form.confirm.callback(reply)
        assert form.completed, reply.edit_original_response.call_args_list

    asyncio.run(begin_native())
    fresh = rules.records(state(game), rules.Replacement)[-1]
    assert fresh.new_actor != original and fresh.original == original
    controls = VatgrownDeathService(game)
    # Genuine new agreements and a complete new review; old accepted relationships cannot qualify.
    draft = ledger.draft(PLAYER)
    other = ledger.draft(OTHER)
    bonds = BondService(ledger)
    proposal = bonds.propose(
        PLAYER,
        str(uuid4()),
        draft["revision"],
        other["revision"],
        BondProposal(target_id=3, prompt=0, context="My own new person's starting Personal Bond"),
    )
    bonds.decide(OTHER, str(uuid4()), proposal["id"], 1, "accept")
    creation = CreationService(ledger)
    progress = creation.get(PLAYER)
    new = selected("VATGROWN", "THE ENFORCER").model_copy(
        update={
            "frame_name": "Distinct actually supplied replacement Frame",
            "frame_appearance": "Distinct newly supplied Frame and equipment",
            "shared_tokens": progress.draft.shared_tokens,
            "girl_details": GirlDetails(
                investors=tuple(
                    NpcInvestor(npc_slot=x.slot, desires=DesireChoice(slots=(0,)))
                    for x in selected("VATGROWN", "THE ENFORCER").npc_bonds
                )
            ),
        }
    )
    coordination = CoordinationService(ledger)
    desired = coordination.propose(
        ADMIN,
        str(uuid4()),
        2,
        "vatgrown_handler",
        coordination.prepare(ADMIN, 2, "vatgrown_handler"),
        DesireChoice(slots=(2,)),
    )
    coordination.decide(PLAYER, str(uuid4()), desired["id"], 1, "accept")
    creation.save(PLAYER, str(uuid4()), progress.revision, draft["revision"], new)
    handler = HandlerService(ledger)
    handler.rank(
        ADMIN,
        str(uuid4()),
        handler.roster(ADMIN)["revision"],
        tuple(
            PilotRef(user_id=x.user_id, character_revision=ledger.draft(x)["revision"])
            for x in (OTHER, PLAYER)
        ),
    )
    careers.assign_status(
        ADMIN, str(uuid4()), 2, str(fresh.new_actor.incarnation), state(game).revision, 1
    )
    review = CreationReviewService(ledger)
    checked = review.get(PLAYER)
    assert checked.sheet.ready_for_rules_review, checked.sheet.issues
    review.save(PLAYER, str(uuid4()), checked.saved_revision, checked.fingerprint)
    with pytest.raises(WorkflowError, match="issue"):
        game.activate(PLAYER, str(uuid4()), review.get(PLAYER).fingerprint)
    assert "2" not in state(game).sheets
    _native_source(controls, PLAYER, fresh.id, operation=("request",))
    data = controls.view(ADMIN, fresh.id)
    assert data["can_issue"] and data["kit"]["frame_name"] == new.frame_name
    base = next(
        x.cell
        for x in state(game).world.locations
        if x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
    )
    _native_source(
        controls,
        ADMIN,
        fresh.id,
        operation=("issue",),
        x=str(base[0]),
        y=str(base[1]),
        account="I actually issue this distinct newly supplied reviewed body and Frame at our base",
    )
    _native_source(controls, PLAYER, fresh.id, operation=("activate",))
    active = state(game)
    source = rules.records(active, rules.Replacement)[-1]
    assert source.activated_event and current_ref(active, 2) == fresh.new_actor
    new_request = shelving.request(PLAYER, "new-original-after-real-activation")
    reviews = ShelvingReviewService(game)
    with pytest.raises(WorkflowError, match="STALE_SHELVING_ACTOR"):
        reviews.inspect(ADMIN, old_request["id"], old_request["revision"])
    reviewed = reviews.inspect(ADMIN, new_request["id"], new_request["revision"])
    assert reviewed.actor == fresh.new_actor and reviewed.availability_authority is False
    assert state(game) == active
    assert new_request["id"] != old_request["id"]
    assert new_request["original_actor"] == fresh.new_actor.model_dump(mode="json")
    assert new_request["pilot_identity_proof"]["character"] == fresh.new_actor.incarnation
    assert new_request["pilot_identity_proof"]["binding_event"]
    assert shelving.view(PLAYER, old_request["id"]) == dict(
        old_request, can_review=False, own=True, actor_context="previous actor"
    )
    assert old_request["status"] == "requested"
    with pytest.raises(WorkflowError, match="STALE_SHELVING_REQUEST"):
        shelving.request(PLAYER, "original-before-real-death")
    with pytest.raises(WorkflowError):
        shelving.view(OTHER, old_request["id"])
    with pytest.raises(WorkflowError):
        shelving.view(OTHER, new_request["id"])

    async def withdraw_previous_intake():
        tree = MagicMock()
        register_shelving(tree, PLAYER.guild_id, game)
        group = tree.add_command.call_args.args[0]
        inbox = interaction(PLAYER, "replacement-shelving-inbox")
        await group.get_command("inbox").callback(inbox)
        form = inbox.edit_original_response.call_args.kwargs["view"]
        labels = dict(form.fields[0].options)
        assert set(labels) == {old_request["id"], new_request["id"]}
        assert "previous actor" in labels[old_request["id"]]
        assert "current actor" in labels[new_request["id"]]
        visible = form.text() + "\n" + "\n".join(labels.values())
        actual_options = next(child.options for child in form.children if hasattr(child, "options"))
        assert {option.value: option.label for option in actual_options} == labels
        inbox.response.defer.assert_awaited_once_with(ephemeral=True)
        for request in (old_request, new_request):
            assert request["id"] in labels[request["id"]]
            assert len(labels[request["id"]]) <= 100
            assert request["original_actor"]["incarnation"] not in visible
            for value in request["pilot_identity_proof"].values():
                if isinstance(value, str) and len(value) > 20:
                    assert value not in visible
        # Reopening reconstructs identical labels; no ephemeral UI is the authority.
        reopened = interaction(PLAYER, "replacement-shelving-inbox-reopen")
        await group.get_command("inbox").callback(reopened)
        saved_form = reopened.edit_original_response.call_args.kwargs["view"]
        assert dict(saved_form.fields[0].options) == labels
        saved_form.values["request"] = (old_request["id"],)
        selected_request = interaction(PLAYER, "select-old-shelving-request")
        await saved_form.confirm.callback(selected_request)
        review_packet = selected_request.edit_original_response.call_args.kwargs
        review = review_packet["view"]
        assert labels[old_request["id"]] in review_packet["content"]
        assert new_request["id"] not in review_packet["content"]
        assert original.incarnation not in review_packet["content"]
        assert fresh.new_actor.incarnation not in review_packet["content"]
        assert "no player is frozen" in review_packet["content"]
        assert dict(review.fields[0].options) == {"withdraw": "Withdraw my shelving request"}
        review.values["operation"] = ("withdraw",)
        submitted = interaction(PLAYER, "withdraw-real-previous-actor-request")
        await review.confirm.callback(submitted)
        assert review.completed
        assert old_request["id"] in submitted.edit_original_response.call_args.kwargs["content"]
        assert shelving.view(PLAYER, old_request["id"])["status"] == "withdrawn"
        assert shelving.view(PLAYER, new_request["id"])["status"] == "requested"
        assert [row["id"] for row in shelving.tasks(PLAYER)] == [new_request["id"]]
        assert state(game) == active

    asyncio.run(withdraw_previous_intake())
    assert active.sheets["2"].girl == "VATGROWN" and active.sheets["2"].permissions == 0
    assert active.sheets["2"].heat == 0 and not any(x.marked for x in active.sheets["2"].identities)
    assert tuple(x.name for x in active.sheets["2"].identities) == tuple(new.identities)
    assert next(x for x in active.career_archives if x.id == archive.id) == archive
    assert active.order[-1] == 2 and game.inspect(PLAYER, death)["receipt"] == death_receipt
    pose = next(x for x in active.placements if x.actor == fresh.new_actor)
    assert pose.girl_cell == base and pose.frame_cell == base and pose.mode == "outside_frame"
    assert pose.frame_instance != old_frame
    other_view = controls.view(OTHER, fresh.id)
    assert other_view["kit"] is None and other_view["issue"] is None
    assert len(other_view["pending"]) == 1
    notice = other_view["pending"][0]
    with pytest.raises(WorkflowError):
        controls.answer(
            PLAYER, str(uuid4()), fresh.id, active.revision, notice, "yes", "Not my reply"
        )
    _native_source(
        controls,
        OTHER,
        fresh.id,
        operation=("notice:" + notice,),
        answer=("yes",),
        account="I notice she is a different actual Girl; these are my own observations",
    )
    handler_notice = controls.view(ADMIN, fresh.id)["pending"][0]
    _native_source(
        controls,
        ADMIN,
        fresh.id,
        operation=("notice:" + handler_notice,),
        answer=("uncertain",),
        account="My actual original Handler's own answer remains uncertain",
    )
    assert controls.view(PLAYER, fresh.id)["phase"] == "complete"
    assert len(controls.view(OTHER, fresh.id)["notices"]) == 1
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), fresh.id).new_actor == fresh.new_actor
    assert "NEW_PERSON_PRIVATE_NOTE" not in str(controls.view(OTHER, fresh.id))
