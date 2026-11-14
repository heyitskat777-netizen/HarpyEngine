"""One actual low Alpha NPC Conversation, saved native performance and owned wake."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_alpha_brutalize import ready
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_alpha_sex import open_alpha, open_alpha_choice, open_consent
from girlframe.engine import m3_alpha_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_npc import NARRATIVE
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_alpha_npc import prove_performance
from girlframe.services.m3_alpha_sex import SexService, prove
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_low_npc_job_play_native_readback_and_original_wake(ledger, tmp_path, monkeypatch):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (4, 4))
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE, "npc.npc.journalist"))
    service = SexService(game)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="original-alpha-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("journalist",),
            controller=1,
            detail="PRIVATE_ALPHA_NPC_DETAIL",
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
        "PRIVATE_ALPHA_NPC_SOURCE Actual voluntary original encounter",
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
        pass_tags(game)
        return action

    action = perform(identity, (1, 1))
    before = state(game)
    value = rules.get(before, identity)
    receipt = game.inspect(PLAYER, action)["receipt"]
    original_bond = depth(before, value.actor, npc)
    original_sheets = before.sheets.copy()
    original_world = before.world
    assert value.phase == "sleeping" and rules.asleep(before, value.actor)

    def counts():
        with ledger.engine.connect() as c:
            return tuple(
                c.scalar(sa.select(sa.func.count()).select_from(t.m2[name]))
                for name in ("m2_actions", "m2_receipts")
            )

    original_counts = counts()

    def interaction(viewer):
        opened = current(viewer.user_id, uuid4().int % 1000000000)
        opened.channel_id = 900
        return opened

    async def native_choice(viewer, row, values):
        opened = interaction(viewer)
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and form.owner == viewer.user_id
        form.values.update(values)
        submitted = interaction(viewer)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        return form

    low = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_sex_low")
    asyncio.run(native_choice(ADMIN, low, dict(opportunity=("play",))))
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_sex_npc_play")
    pending = state(game)
    assert not any(x["kind"] == "alpha_sex_wake" for x in game.choices(PLAYER))
    assert rules.get(pending, identity).npc_performance is None
    rendition = "PRIVATE_ALPHA_NPC_RENDITION Pat takes a candid picture of the sleeping Alpha."
    response = ChoiceAnswer(
        options=("journalist",), fields={"move": NARRATIVE["journalist"][0]}, text=rendition
    )
    with pytest.raises(WorkflowError):
        game.respond(OTHER, str(uuid4()), row["id"], row["revision"], response)
    assert state(game) == pending
    with pytest.raises(WorkflowError, match="supported actual NPC job move"):
        game.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=("journalist",), fields={"move": "Inflict damage"}, text=rendition
            ),
        )
    assert state(game) == pending
    form = asyncio.run(native_choice(ADMIN, row, dict(job=("journalist",), account=rendition)))
    after = state(game)
    performed = rules.get(after, identity).npc_performance
    assert performed is not None
    assert performed.actor == npc and performed.controller == ADMIN.user_id
    assert performed.job == "journalist" and performed.move == NARRATIVE["journalist"][0]
    assert performed.rendition == rendition and performed.action == action
    assert performed.session == identity and performed.choice == row["id"]
    assert performed.selection_choice == low["id"]
    assert performed.cast == value.cast
    assert performed.recipients == tuple(x for x in value.cast.roles if x.actor == value.actor)
    with ledger.engine.connect() as c:
        assert prove_performance(game, c, after, rules.get(after, identity)) == performed
        assert prove(game, c, after, identity) == rules.get(after, identity)
    assert counts() == original_counts and game.dice.calls == 1
    assert after.sheets == original_sheets and after.world == original_world
    assert npc.entity not in after.sheets
    assert depth(after, value.actor, npc) == original_bond
    assert rules.asleep(after, value.actor) and rules.get(after, identity).phase == "waking"
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt

    async def reopen_and_replay():
        # The independent NPC controller has no fabricated Girl sheet.
        opened = interaction(ADMIN)
        await opened.response.defer(ephemeral=True)
        await open_alpha(opened, SexService(game))
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = ("source:" + identity,)
        selected = interaction(ADMIN)
        await menu.confirm.callback(selected)
        text = selected.edit_original_response.call_args.kwargs["content"]
        assert rendition in text and NARRATIVE["journalist"][0] in text
        # A completed form cannot repeat the performance or advance the wake.
        await form.confirm.callback(interaction(ADMIN))
        observer = interaction(OTHER)
        with pytest.raises(WorkflowError):
            await open_consent(observer, SexService(game), identity)
        observer.edit_original_response.assert_not_awaited()
        assert observer.response.events == []

    asyncio.run(reopen_and_replay())
    assert state(game) == after
    with pytest.raises(WorkflowError):
        game.respond(ADMIN, str(uuid4()), row["id"], row["revision"], response)
    assert state(game) == after
    wake = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_sex_wake")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            wake["id"],
            wake["revision"],
            ChoiceAnswer(options=("wake",), text="Not the original Alpha's own wake"),
        )
    assert state(game) == after
    asyncio.run(native_choice(PLAYER, wake, dict(account="The original Alpha actually wakes")))
    final = state(game)
    assert not rules.asleep(final, value.actor)
    assert rules.get(final, identity).npc_performance == performed
    assert rules.get(final, identity).phase == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert counts() == original_counts and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove(game, c, final, identity) == rules.get(final, identity)
    assert "PRIVATE_ALPHA_NPC_DETAIL" not in repr(gateway.messages)
    assert rendition not in repr(gateway.messages)
