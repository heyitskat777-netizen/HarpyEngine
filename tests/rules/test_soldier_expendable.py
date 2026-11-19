"""An approved Soldier takes a real original low Defeat only with the controller's consent."""

import asyncio

import pytest
from test_ancillary_creation import enable
from test_cast_service import change
from test_gorgon_runtime import candidate_source_gate as candidate_source_gate
from test_gorgon_runtime import gorgon_source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine import m3_ancillary as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services import m3_soldier_expendable as expendable
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_defeat import start_work
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("accept", [True, False])
def test_native_original_soldier_owns_fatal_defeat_choice(ledger, tmp_path, monkeypatch, accept):
    game, worker, gateway, _, attack = gorgon_source(ledger, begin=False)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"playbooks"})
            ),
        )
    )
    enable(ledger, game, tmp_path, monkeypatch, extra=(expendable.RULE,))
    missions = MissionService(ledger)
    adjunct = AncillaryService(missions)
    invite = adjunct.invite(ADMIN, "soldier-source", state(game).revision, 3, "base0")["id"]
    selection = rules.Draft(
        name="Original reserve Soldier",
        book="SOLDIER",
        frame_catalogue="SOLDIER_3",
        bond=current_ref(state(game), 2),
        girl_assets=(
            rules.NamedAsset(name="Nice Jacket", description="Jacket"),
            rules.NamedAsset(name="Taser", description="Trainer gear"),
        ),
        frame_assets=(
            rules.NamedAsset(name="Laser Sword", description="Blade"),
            rules.NamedAsset(name="Armour Plating", description="Plate"),
        ),
    )
    owner = adjunct.respond(OTHER, "own-soldier", invite, state(game).revision, selection)
    soldier = ActorRef.model_validate(owner["actor"])
    change(CastService(ActorService(missions)), OTHER, "join", soldier)

    with ledger.transaction() as connection:
        canon = state(game)
        sheet = canon.sheets["2"]
        frames = [x for x in sheet.assets if x.family == "frame"]
        for extra in frames[1:]:
            extra.damaged = True
        game.event(connection, 2, "actual-prior-loss", "synthetic.pre_existing_damage", canon)
    service = GorgonPlayService(game)
    preview = service.preview(ADMIN, 900)
    actual = {x["ref"]["entity"]: x for x in preview["actors"]}
    attack = attack.model_copy(
        update=dict(
            actor_sha256=actual[attack.actor.entity]["source_sha256"],
            target_sha256=actual["2"]["source_sha256"],
        )
    )
    parent = service.begin(ADMIN, "native-real-blow", 900, preview["revision"], attack)["action_id"]
    tick(worker, gateway, 3)
    with ledger.engine.connect() as c:
        started = game.action(c, parent)["data"]["gorgon_play"]["started"]
    if not started:
        game.roll(ADMIN, "resolve-blow", parent)
    answer(
        game, PLAYER, "gorgon_defend", options=("damage",), text="My actual Frame takes the hit."
    )
    answer(game, PLAYER, "gorgon_damage_asset", options=(frames[0].id,), text="It breaks.")
    pending = missions.owned_work(PLAYER)
    work = next((x for x in pending if x["kind"] == "defeat"), None)
    assert work is not None, pending
    game.dice.faces = (1, 1)
    action = start_work(game, PLAYER, "original-low", work["id"], 900, "The Frame is defeated.")[
        "action_id"
    ]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))

    def body_now():
        return next(x for x in state(game).world.pilots if x.id == soldier.entity)

    before = state(game)
    choosing = next(x for x in game.choices(PLAYER) if x["kind"] == "defeat_select")
    assert game.decision(PLAYER, choosing["id"])["defeat"]["soldiers"] == (
        (soldier.token, "Original reserve Soldier"),
    )
    with pytest.raises(WorkflowError, match="one actual Soldier"):
        answer(
            game,
            PLAYER,
            "defeat_select",
            options=(expendable.OPTION, "death"),
            fields={"soldier": soldier.token},
            text="Cannot combine these effects.",
        )
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=(expendable.OPTION,),
        fields={"soldier": soldier.token},
        text="I ask the Soldier to shield me.",
    )
    prompt = next(x for x in game.choices(OTHER) if x["kind"] == expendable.REQUEST)
    assert body_now().alive and state(game).sheets == before.sheets
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            "not-your-decision",
            prompt["id"],
            prompt["revision"],
            ChoiceAnswer(flag=True, text="Fake"),
        )
    with pytest.raises(WorkflowError, match="STALE"):
        game.respond(
            OTHER,
            "stale-soldier",
            prompt["id"],
            prompt["revision"] + 1,
            ChoiceAnswer(flag=accept, text="Actual"),
        )
    account = "I take the actual hit." if accept else ""
    ledger.safety(OTHER, "pause-sacrifice", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        game.respond(
            OTHER,
            "paused",
            prompt["id"],
            prompt["revision"],
            ChoiceAnswer(flag=accept, text=account),
        )
    ledger.safety(OTHER, "resume-sacrifice", ledger.status(OTHER)["revision"], pause=False)
    ledger.engine.dispose()

    async def native_consent():
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(OTHER) if x.identity == prompt["id"])
        click = current(3, 94100)
        await click.response.defer(ephemeral=True)
        await InboxView(inbox, 3).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update({"accept": ("yes" if accept else "no",), "account": account})
        sent = current(3, 94101)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(native_consent())
    game.respond(
        OTHER, "94101", prompt["id"], prompt["revision"], ChoiceAnswer(flag=accept, text=account)
    )
    assert body_now().alive is (not accept)
    final = state(game)
    assert final.sheets == before.sheets
    if accept:
        (saved,) = tuple(x for x in final.facts if x.get("kind") == "soldier_expendable")
        assert saved["action"] == action and saved["actor"] == soldier.model_dump_json()
        with ledger.engine.connect() as c:
            assert game.action(c, action)["state"] == "complete"
            assert game.action(c, parent)["state"] == "complete"
    else:
        replacement = next(x for x in game.choices(PLAYER) if x["kind"] == "defeat_select")
        assert not game.decision(PLAYER, replacement["id"])["defeat"]["soldiers"]
        assert game.inspect(PLAYER, action)["state"] != "complete"
        assert not any(x.get("kind") == "soldier_expendable" for x in final.facts)
    assert game.dice.calls == 1
