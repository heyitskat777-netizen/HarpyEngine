"""Actual NPC Status choice opens adjudication without inventing ranked resources."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current
from test_oldgen_sex import native_choice, setup

from girlframe.discord_adapter.m3_oldgen_sex import open_choice
from girlframe.engine import m3_oldgen_sex as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService


def test_oldgen_npc_status_opens_owned_durable_gm_request_without_partial_effects(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, service, _ = setup(ledger, tmp_path, monkeypatch)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="original-oldgen-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            detail="PRIVATE_OLDGEN_NPC_DETAIL",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(missions)), ADMIN, "join", npc)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "I witness this actual original ordinary civilian's human body and brain",
    )
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in service.menu(PLAYER, 900)["targets"]
    )
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_OLDGEN_NPC_SOURCE Actual voluntary original encounter",
    )["id"]
    before = state(game)
    with pytest.raises(WorkflowError):
        service.respond(OTHER, str(uuid4()), identity, before.revision, True, "Not my NPC")
    assert state(game) == before
    with pytest.raises(WorkflowError, match="Attest actual physical contact"):
        service.respond(
            ADMIN,
            str(uuid4()),
            identity,
            before.revision,
            True,
            "Consent alone is not spatial evidence",
        )
    assert state(game) == before
    service.respond(
        ADMIN,
        str(uuid4()),
        identity,
        before.revision,
        True,
        "Actual original NPC controller confirms voluntary interaction",
        npc_contact_account="Actual original body contact here, outside all enclosures and rides",
    )
    game.dice.faces = (6, 6)
    before = state(game)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            source_work=identity,
            target_actor=npc,
            heat=1,
            context="Actual original NPC encounter",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "oldgen_sex_effects")
    detail = game.decision(PLAYER, row["id"])["detail"]
    assert detail["unsupported_status"]
    assert "status" not in {key for key, _ in detail["options"]}
    assert "no Cadre rank" in detail["status_scope"]
    facilitator = FacilitatorService(game)
    facilitator.configure(ADMIN, str(uuid4()), "user", OTHER.user_id)
    before_request = state(game)
    receipt = game.inspect(PLAYER, action)["receipt"]

    async def request(key):
        opening = current(PLAYER.user_id, key)
        opening.channel_id = 900
        await opening.response.defer(ephemeral=True)
        await open_choice(opening, game, game.decision(PLAYER, row["id"]))
        form = opening.edit_original_response.call_args.kwargs["view"]
        assert next(x for x in form.fields if x.key == "effects").required
        form.values.update(effects=("tag", "status"), tag="PRIVATE_UNAPPLIED_TAG")
        denied = current(OTHER.user_id, key + 1)
        denied.channel_id = 900
        await form.confirm.callback(denied)
        assert not form.completed and facilitator.tasks(PLAYER) == []
        confirmation = current(PLAYER.user_id, key + 2)
        confirmation.channel_id = 900
        await form.confirm.callback(confirmation)
        assert form.completed
        assert (
            "Human adjudication" in confirmation.edit_original_response.call_args.kwargs["content"]
        )

    asyncio.run(request(891001))
    tasks = facilitator.tasks(PLAYER)
    assert len(tasks) == 1
    identity = tasks[0]["id"]
    packet = facilitator.view(PLAYER, identity)
    assert packet["request"]["source"] == action
    assert packet["request"]["rule"] == "choice:oldgen_sex_effects"
    assert packet["request"]["mandatory"]
    assert facilitator.view(OTHER, identity)["request"]["source"] != action
    facilitator.change(
        PLAYER, str(uuid4()), identity, packet["revision"], state(game).revision, "share"
    )
    packet = facilitator.view(OTHER, identity)
    facilitator.change(
        OTHER,
        str(uuid4()),
        identity,
        packet["revision"],
        state(game).revision,
        "rule",
        "GM must determine actual NPC status semantics; mechanical effects remain pending.",
        adapter="blocked",
    )
    packet = facilitator.view(PLAYER, identity)
    with pytest.raises(WorkflowError):
        facilitator.change(
            PLAYER, str(uuid4()), identity, packet["revision"], state(game).revision, "resume"
        )
    assert "NPC status" in packet["request"]["ruling"]
    assert state(game).order == before_request.order
    assert not actor_tags(state(game), npc)
    assert rules.records(state(game), rules.Effect) == rules.records(before_request, rules.Effect)
    assert state(game).sheets == before_request.sheets
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert any(x["id"] == row["id"] for x in game.choices(PLAYER))
    assert game.dice.calls == 1
    assert "PRIVATE_UNAPPLIED_TAG" not in str(gateway.messages)

    # The unsupported proposal applied nothing. The original player may choose a
    # different supported pair; the facilitator does not choose on their behalf.
    facilitator.change(
        OTHER,
        str(uuid4()),
        identity,
        packet["revision"],
        state(game).revision,
        "rule",
        "NPC rank remains unsupported. The owner may select supported alternatives; "
        "the original action must actually finish before this request can close.",
        adapter="existing_source",
    )
    packet = facilitator.view(PLAYER, identity)
    with pytest.raises(WorkflowError, match="Complete the actual original action"):
        facilitator.change(
            PLAYER, str(uuid4()), identity, packet["revision"], state(game).revision, "resume"
        )
    native_choice(
        game,
        PLAYER,
        "oldgen_sex_effects",
        ("tag", "bond"),
        fields={"tag": "PRIVATE_SUPPORTED_ALTERNATIVE_TAG"},
    )
    # High keeps its independently controlled counterpart question and optional
    # reciprocal effect. Neither is answered by the facilitator's ruling.
    native_choice(game, ADMIN, "oldgen_sex_creep", ("yes",))

    async def decline_reciprocal():
        choice = next(x for x in game.choices(ADMIN) if x["kind"] == "oldgen_sex_effects")
        opening = current(ADMIN.user_id, 891010)
        await opening.response.defer(ephemeral=True)
        await open_choice(opening, game, game.decision(ADMIN, choice["id"]))
        form = opening.edit_original_response.call_args.kwargs["view"]
        assert not next(x for x in form.fields if x.key == "effects").required
        # Confirm without touching the optional selector, not a direct service answer.
        confirmation = current(ADMIN.user_id, 891011)
        await form.confirm.callback(confirmation)
        assert form.completed

    asyncio.run(decline_reciprocal())
    final = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert final.order == before_request.order
    assert depth(final, current_ref(final, 2), npc) == 1
    assert [x.label for x in actor_tags(final, npc)] == ["PRIVATE_SUPPORTED_ALTERNATIVE_TAG"]
    assert {x.kind for x in rules.records(final, rules.Effect)} == {"tag", "bond"}
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.dice.calls == 1
    packet = facilitator.view(PLAYER, identity)
    key = str(uuid4())
    facilitator.change(PLAYER, key, identity, packet["revision"], final.revision, "resume")
    assert facilitator.view(PLAYER, identity)["request"]["status"] == "resolved"
    assert facilitator.tasks(PLAYER) == []
    completed = state(game)
    facilitator.change(PLAYER, key, identity, packet["revision"], final.revision, "resume")
    assert state(game) == completed
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.dice.calls == 1
    tick(worker, gateway, 8)
    assert "PRIVATE_SUPPORTED_ALTERNATIVE_TAG" not in str(gateway.messages)
