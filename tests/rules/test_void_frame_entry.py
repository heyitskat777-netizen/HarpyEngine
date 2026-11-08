"""One real entry/Heat Dive/additive Void normal; authored, deferred final P1."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_bonded import pause_tick
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, state, tick
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter import m2_ui
from girlframe.discord_adapter import m3_void_frame_entry as native
from girlframe.engine import m3_void_frame_entry as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_void_frame_entry import VoidFrameEntryService, prove_modifier
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


class First:
    def __init__(self):
        self.calls = 0

    def choose(self, size):
        assert size == 2
        self.calls += 1
        return 0


def test_original_random_girl_real_entry_required_heat_dive_adds_void_then_real_consequence(
    ledger, tmp_path, monkeypatch
):
    strain, game = ready(ledger, face=1)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "subsystems": approval.subsystems | {"world"},
                }
            ),
        }
    )
    strain.missions.access.registry = load_registry()  # Actual fixture approval, no stale cache.
    with ledger.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(place(actual, 2, mode="outside_frame"), 3, mode="outside_frame")
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        actual.sheets["2"].heat = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_entry_baseline", actual)
    period = prepared(strain, game)
    request = next(value for value in state(game).strain.requests if value.track == "void")
    strain.roll(ADMIN, "actual-void-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "actual-void-column", request.id, 2, state(game).revision, 2)
    assert (
        next(value for value in state(game).strain.events if value.id == request.id).rule_id
        == rules.RULE
    )
    # Current Void can change after actual Strain review; half-with-Void at review
    # would correctly select High Void instead of the Low source under test.
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].assets[0].void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_void_before_entry", actual)
    rng = First()
    source = VoidFrameEntryService(strain, selector=rng)
    arm = (
        ADMIN,
        "actual-source-arm",
        request.id + ":effect",
        1,
        state(game).revision,
        "The actual Low Void effect awaits this original Girl's next Frame entry",
    )
    saved = source.arm(*arm)
    assert source.arm(*arm) == saved and rng.calls == 1
    selection = rules.records(state(game), rules.Selection)[0]
    actor = ActorRef.model_validate(saved["actor"])
    assert actor == current_ref(state(game), 2) and selection.period == period
    with pytest.raises(WorkflowError):
        source.view(OTHER, saved["id"])
    physical = PhysicalService(ledger)

    def enter(viewer, ref):
        with ledger.engine.connect() as c:
            actual = resolve(state(game), ref, profiles(c, ledger.campaign_id))
        return physical.operate(
            viewer,
            str(uuid4()),
            state(game).revision,
            CockpitAction(
                actor=ref,
                operation="sit",
                expected_position=actual.position_sha256,
                account="I actually enter my own co-located Frame",
                confirmed=True,
            ),
            channel=900,
        )

    enter(OTHER, current_ref(state(game), 3))
    assert not rules.records(state(game), rules.Entry) and rng.calls == 1
    enter(PLAYER, actor)
    entry = rules.records(state(game), rules.Entry)[0]
    assert entry.actor == actor and entry.selection == selection.id and entry.ready_event
    gateway, worker = Gateway(), GameWorker(game)
    pause_tick(game, gateway)
    captured = []
    monkeypatch.setattr(native, "viewer_from_interaction", lambda current: PLAYER)

    async def reply(interaction, text, view=None):
        captured.append(view)

    async def open_play(interaction, actual_game, *, parent, _pilot):
        assert actual_game.store is game.store and _pilot
        captured.append(parent)

    monkeypatch.setattr(native, "reply", reply)
    monkeypatch.setattr(m2_ui, "open_play", open_play)
    interaction = SimpleNamespace(id=90127, user=SimpleNamespace(id=2), channel_id=900)
    asyncio.run(native.open_void_frame_entry(interaction, source, entry.id))
    form = captured[-1]
    asyncio.run(form.submit_action(interaction, dict(operation=("dive",))))
    assert captured[-1]["kind"] == "void_frame_entry_child"
    assert captured[-1]["body"]["source_work"] == entry.id
    game.dice.faces = (3, 3)
    action = game.begin(
        PLAYER,
        "actual-required-dive",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            context="The real Frame entry requires this immediate Dive",
            heat=1,
            source_work=entry.id,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for viewer in (PLAYER, OTHER, ADMIN):
        for row in game.choices(viewer):
            if row["kind"] == "tag_window":
                game.respond(
                    viewer,
                    str(uuid4()),
                    row["id"],
                    row["revision"],
                    ChoiceAnswer(options=("pass",)),
                )
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["pre_total"] == 8  # Real 3+3, ordinary Heat1, EXTRA Void1.
    assert [item for item in receipt["pre_modifiers"] if item["source"] == rules.MODIFIER] == [
        dict(source=rules.MODIFIER, amount=1)
    ]
    assert state(game).sheets["2"].heat == 1 and game.dice.calls == 1
    answer(
        game, PLAYER, "dive_select", options=("void_and_unmark_all",), text="My actual Dive outcome"
    )
    asset = next(value for value in state(game).sheets["2"].assets if not value.void)
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": asset.id},
        text="Actual newly Void-woven component",
    )
    tick(worker, gateway, 2)
    pause_tick(game, gateway)
    assert next(value for value in state(game).sheets["2"].assets if value.id == asset.id).void
    assert rules.get(state(game), rules.Entry, entry.id).completed_event
    assert rng.calls == 1 and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove_modifier(game, c, state(game), game.action(c, action)) == 1
    interaction.channel_id = 999
    asyncio.run(native.open_void_frame_entry(interaction, source, entry.id))
    assert "State: complete" in "".join(page.body for page in captured[-1].pages)
