"""Actual Casualty NPC low/mid answers and high pending prerequisite fallback."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_casualty import ready, tags
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick

from girlframe.engine import m3_casualty as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_casualty import prove_sex
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_low_mid_and_pending_high(ledger, tmp_path, monkeypatch):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch, marked=True)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="original-casualty-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            detail="PRIVATE_CASUALTY_NPC_DETAIL",
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
    same_owner = ActorRef(kind="npc", entity="same-controller-npc")
    roles = NpcRoleService(WorldService(missions))
    offered = roles.offer(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=same_owner.entity,
            name="Other Pat",
            jobs=("guard",),
            controller=2,
            detail="Actual independently introduced NPC",
            revealed=True,
            cell=(0, 0),
        ),
    )["id"]
    roles.respond(PLAYER, str(uuid4()), offered, state(game).revision, "accept")
    cast_change(CastService(ActorService(missions)), PLAYER, "join", same_owner)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        same_owner,
        "human_npc",
        "Actual original second human NPC body and brain",
    )
    before_same = state(game)
    with pytest.raises(WorkflowError, match="independently controlled"):
        service.invite(
            PLAYER,
            str(uuid4()),
            900,
            same_owner,
            before_same.revision,
            "Same human cannot stand for both source choice roles",
        )
    assert state(game) == before_same
    assert not any(
        x["ref"] == same_owner.model_dump(mode="json")
        for x in service.menu(PLAYER, 900)["sex_targets"]
    )
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in service.menu(PLAYER, 900)["sex_targets"]
    )
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_CASUALTY_NPC_SOURCE Actual voluntary original encounter",
    )["id"]

    async def inspect_original_consent():
        from test_mission_ui import current

        from girlframe.discord_adapter.m3_casualty import open_casualty

        interaction = current(ADMIN.user_id, 92001)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_casualty(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        text = form.text()
        assert "NPC high results need human adjudication" in text
        assert "entire result remains pending" in text
        assert "NPC Identity unmark is unsupported" in text
        assert "explicit decline" in text

    asyncio.run(inspect_original_consent())
    before = state(game)
    with pytest.raises(WorkflowError):
        service.confirm(OTHER, str(uuid4()), identity, before.revision, True, "Not my NPC")
    assert state(game) == before
    with pytest.raises(WorkflowError, match="Attest actual physical contact"):
        service.confirm(
            ADMIN,
            str(uuid4()),
            identity,
            before.revision,
            True,
            "Consent alone is not spatial evidence",
        )
    assert state(game) == before
    service.confirm(
        ADMIN,
        str(uuid4()),
        identity,
        before.revision,
        True,
        "Actual original NPC controller confirms voluntary interaction",
        npc_contact_account="Actual original body contact here, outside all enclosures and rides",
    )

    def perform(identity, faces):
        game.dice = Dice(faces)
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=rules.PLAY,
                source_work=identity,
                target_actor=npc,
                heat=0,
                context="Actual confirmed original NPC interaction",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        tags(game)
        return action

    def session(identity):
        return next(x for x in rules.records(state(game), rules.SexSession) if x.id == identity)

    def next_source(faces):
        tick(worker, gateway, 8)
        identity = service.invite(
            PLAYER,
            str(uuid4()),
            900,
            npc,
            state(game).revision,
            "Actual new source; high NPC result requires adjudication",
        )["id"]
        service.confirm(
            ADMIN,
            str(uuid4()),
            identity,
            state(game).revision,
            True,
            "Actual original NPC voluntary confirmation with known high limitation",
            npc_contact_account="Actual original bodies in contact outside enclosures here",
        )
        return identity, perform(identity, faces)

    action = perform(identity, (1, 1))
    answer(game, PLAYER, "casualty_unsatisfied", text="Actual own report of dissatisfaction")
    answer(game, ADMIN, "casualty_agree", options=("disagree",), text="Actual NPC disagrees")
    answer(
        game,
        PLAYER,
        "casualty_low_both",
        options=("give",),
        fields={"self": "Actual own impression", "other": "Actual counterpart impression"},
    )
    assert session(identity).phase == "complete"
    assert any(
        x.label == "Actual counterpart impression"
        and x.giver_entity == current_ref(state(game), 2).model_dump_json()
        for x in actor_tags(state(game), npc)
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"

    middle, action = next_source((4, 4))
    answer(
        game, PLAYER, "casualty_present", options=("legs", "hands"), text="Actual original parts"
    )
    answer(
        game,
        ADMIN,
        "casualty_focus",
        fields={"legs": "focus", "hands": "hesitate"},
        text="Actual NPC reactions",
    )
    before = state(game)
    with pytest.raises(WorkflowError, match="NPC Identity unmark needs human adjudication"):
        answer(game, ADMIN, "casualty_unmark", options=("unmark",))
    assert state(game) == before
    answer(game, ADMIN, "casualty_unmark", options=("skip",))
    answer(game, PLAYER, "casualty_unmark", options=("unmark",), denied=("identity:0",))
    answer(game, ADMIN, "casualty_mutual_tag", text="Actual NPC hesitation impression")
    answer(game, PLAYER, "casualty_mutual_tag", text="Actual Casualty hesitation impression")
    assert session(middle).phase == "complete"
    assert not next(x for x in state(game).sheets["2"].identities if x.id == "identity:0").marked
    assert any(
        x.label == "Actual Casualty hesitation impression" for x in actor_tags(state(game), npc)
    )
    with ledger.engine.connect() as c:
        assert prove_sex(game, c, state(game), middle) == session(middle)

    high, action = next_source((6, 6))
    before = state(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "casualty_high_heat")
    detail = game.decision(PLAYER, row["id"])["detail"]
    assert detail["unsupported_npc"] and "pending" in detail["guidance"]
    with pytest.raises(WorkflowError, match="entire high result remains pending"):
        game.respond(PLAYER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(number=3))
    assert state(game) == before
    assert session(high).phase == "results" and session(high).completed_event is None
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert "PRIVATE_CASUALTY_NPC_DETAIL" not in repr(gateway.messages)
