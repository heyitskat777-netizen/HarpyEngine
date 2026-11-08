"""Birth-time authority, actual forced Identity replacement and NPC deprogramming."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_disposable_psyche import real_period
from test_dose_up import contact, dose, native_choice
from test_dose_up import ready as dose_ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import call

from girlframe.database import tables as t
from girlframe.engine import m3_dose_up as drugs
from girlframe.engine import m3_malleable as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_off_duty import HandlerContext
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_malleable import MalleableService, prove_birth
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def prepared(store, tmp_path, monkeypatch):
    game, worker, gateway, dosing = dose_ready(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(drugs.RULE, rules.RULE))
    store.policy = store.policy.model_copy(
        update={
            "owner_m3_rulings": store.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    return game, worker, gateway, dosing, MalleableService(store, game)


def ordinary_tag(game, worker, gateway):
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            context="Actual confrontation in the shared scene",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "status"),
        fields={"tag": "PRIVATE_AUTHORED_ORDINARY_TAG"},
        text="Actual confrontation",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 5)
    return state(game).sheets["3"].tags[-1].id


def recipient_keep(game, worker, gateway, *, tag=None, resolution=False):
    game.dice.faces = (3, 4) if tag else (4, 4)
    action = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual subsequent danger",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    for human in (PLAYER, OTHER, ADMIN):
        if tag and human == PLAYER:
            answer(
                game,
                human,
                "tag_window",
                options=("tag",),
                denied=(tag,),
                number=1,
                text="The actual established Tag affects this reaction",
            )
        else:
            answer(game, human, "tag_window", options=("pass",))
    if resolution:
        return action
    finish_keep(game, worker, gateway, action)
    return action


def finish_keep(game, worker, gateway, action):
    answer(game, OTHER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual danger adjudication")
    assert game.inspect(OTHER, action)["state"] == "complete"
    tick(worker, gateway, 5)


def npc_sources(store, tmp_path, monkeypatch):
    game, worker, gateway, _, controls = prepared(store, tmp_path, monkeypatch)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "strain", "playbooks"}}
            )
        }
    )
    protected = ActorRef(kind="npc", entity="actual-altered-worker")
    ordinary = ActorRef(kind="npc", entity="actual-ordinary-worker")
    with store.transaction() as c:
        actual = state(game)
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        actual.world = actual.world.model_copy(
            update={
                "npcs": tuple(
                    Npc(
                        id=x.entity,
                        name="Actual worker",
                        jobs=("civilian",),
                        detail="PRIVATE_ACTUAL_NPC_DETAIL",
                        controller=3,
                        cell=(0, 0),
                        employment="foundation",
                    )
                    for x in (protected, ordinary)
                )
            }
        )
        game.event(c, 1, str(uuid4()), "synthetic.original_existing_Foundation_workers", actual)
    casts = CastService(ActorService(MissionService(store)))
    for subject in (protected, ordinary):
        view = casts.view(OTHER, 900)
        casts.change(
            OTHER, str(uuid4()), 900, view["game_revision"], view["cast_revision"], "join", subject
        )
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.record_npc_alteration(
            PLAYER,
            str(uuid4()),
            900,
            protected,
            before.revision,
            "Cannot invent another controller's actual NPC state",
        )
    assert state(game) == before
    account = "PRIVATE_ACTUAL_ALTERATION The existing worker is actually disoriented after exposure"
    source = controls.record_npc_alteration(
        OTHER, "npc-actual-alteration", 900, protected, before.revision, account
    )
    assert (
        controls.record_npc_alteration(
            OTHER, "npc-actual-alteration", 900, protected, before.revision, account
        )
        == source
    )
    tag = controls.give_npc_tag(
        PLAYER, str(uuid4()), 900, protected, "Actual ingrained work Tag", state(game).revision
    )
    assert tag["eligible"]
    controls.end_npc_alteration(
        OTHER,
        str(uuid4()),
        900,
        protected,
        source["id"],
        state(game).revision,
        "The original exposure actually ended",
    )
    # Whole-person protection also blocks removal of another, later ordinary Tag.
    later = controls.give_npc_tag(
        PLAYER, str(uuid4()), 900, protected, "Later work-affecting Tag", state(game).revision
    )
    baseline = controls.give_npc_tag(
        PLAYER, str(uuid4()), 900, ordinary, "Ordinary work-affecting Tag", state(game).revision
    )
    assert not later["eligible"] and not baseline["eligible"]
    assert rules.protected_npc(state(game), protected) and not rules.protected_npc(
        state(game), ordinary
    )
    assert set(state(game).sheets) == {"2", "3"}
    with store.engine.connect() as c:
        assert prove_birth(game, c, state(game), tag["id"]).recipient == protected
        assert "PRIVATE_ACTUAL_ALTERATION" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    return game, controls, protected, ordinary, later["id"], baseline["id"]


def test_genuine_dose_ordinary_tag_expiry_forced_native_embrace_and_pending_resolution(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, dosing, controls = prepared(ledger, tmp_path, monkeypatch)
    reach = contact(dosing, game)
    action = dose(game, worker, gateway, faces=(3, 4), heat=1, source=reach)
    native_choice(game, PLAYER, ("quick", "strong"))
    tick(worker, gateway, 5)
    assert not rules.records(
        state(game), rules.Birth
    )  # Temporary physiology is not a permanent Identity.
    tag = ordinary_tag(game, worker, gateway)
    value = rules.records(state(game), rules.Birth)[-1]
    assert value.id == tag and value.giver == current_ref(state(game), 2)
    assert value.recipient == current_ref(state(game), 3) and value.altered_kind == "dose"
    with ledger.engine.connect() as c:
        assert prove_birth(game, c, state(game), tag) == value
    recipient_keep(game, worker, gateway, tag=tag)
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for human in (PLAYER, OTHER, ADMIN):
        game.join_scene(human, str(uuid4()), 900)
    recipient_keep(game, worker, gateway)
    game.close_scene(ADMIN, str(uuid4()), 900)
    assert drugs.expired(state(game), action)
    assert not any(x.id.startswith("dose-up:") for x in state(game).sheets["3"].tags)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for human in (PLAYER, OTHER, ADMIN):
        game.join_scene(human, str(uuid4()), 900)
    pending = recipient_keep(game, worker, gateway, tag=tag, resolution=True)
    row = next(x for x in game.choices(OTHER) if x["kind"] == "tag_resolution")
    before = state(game)
    selected = controls.view(PLAYER, tag)["replacements"][0]["id"]
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, tag)
    with pytest.raises(WorkflowError):
        controls.force(OTHER, str(uuid4()), tag, selected, before.revision)
    with pytest.raises(WorkflowError):
        controls.force(PLAYER, str(uuid4()), tag, selected, before.revision - 1)
    assert state(game) == before
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        controls.force(PLAYER, "force-retry", tag, selected, before.revision)
    assert state(game) == before
    monkeypatch.setattr(game, "event", original)

    async def native_force():
        from girlframe.discord_adapter.m3_malleable import open_malleable

        interaction = current(2, 99401)
        await interaction.response.defer(ephemeral=True)
        await open_malleable(interaction, controls, tag)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values["replacement"] = (selected,)
        await form.confirm.callback(current(2, 99402))
        assert form.completed

    asyncio.run(native_force())
    after = state(game)
    assert not any(x.id == tag for x in after.sheets["3"].tags)
    assert next(
        x for x in after.sheets["3"].identities if x.name == "PRIVATE_AUTHORED_ORDINARY_TAG"
    ).slot == next(x.slot for x in before.sheets["3"].identities if x.id == selected)
    assert len(after.sheets["3"].identities) == len(before.sheets["3"].identities)
    assert not any(x["kind"] == "tag_resolution" for x in game.choices(OTHER))
    with ledger.engine.connect() as c:
        actual = (
            c.execute(sa.select(t.m2["m2_choices"]).where(t.m2["m2_choices"].c.id == row["id"]))
            .mappings()
            .one()
        )
        assert actual["actor_id"] == "3"
        assert "PRIVATE_AUTHORED_ORDINARY_TAG" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    assert "notes" not in str(controls.view(PLAYER, tag))
    replay = MalleableService(ledger).force(PLAYER, "99402", tag, selected, before.revision)
    assert replay["id"] == tag and state(game) == after
    finish_keep(game, worker, gateway, pending)
    assert game.dice.calls == 5


def test_no_retroactive_eligibility_and_identity_constraints(ledger, tmp_path, monkeypatch):
    game, worker, gateway, dosing, controls = prepared(ledger, tmp_path, monkeypatch)
    old = ordinary_tag(game, worker, gateway)
    reach = contact(dosing, game)
    dose(game, worker, gateway, faces=(3, 4), heat=1, source=reach)
    native_choice(game, PLAYER, ("quick", "strong"))
    tick(worker, gateway, 5)
    assert not any(x.id == old for x in rules.records(state(game), rules.Birth))
    with pytest.raises(WorkflowError):
        controls.view(PLAYER, old)
    quick = next(x.id for x in state(game).sheets["3"].tags if x.id.endswith(":quick"))
    recipient_keep(game, worker, gateway, tag=quick)
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for human in (PLAYER, OTHER, ADMIN):
        game.join_scene(human, str(uuid4()), 900)
    embracing = recipient_keep(game, worker, gateway, tag=quick, resolution=True)
    answer(game, OTHER, "tag_resolution", options=("embrace",), denied=("identity:0",))
    finish_keep(game, worker, gateway, embracing)
    assert not any(x.id == quick for x in state(game).sheets["3"].tags)
    tag = ordinary_tag(game, worker, gateway)
    actual = state(game)
    value = rules.records(actual, rules.Birth)[-1]
    assert value.altered_id == quick  # Genuine consumed presentation, original active drug clock.
    selected = rules.legal_replacements(actual, value, duplicates=True)[0]
    actual.sheets["3"].sedation_locked = (selected.id,)
    changed = rules.force(
        actual, value, selected.id, "new-identity", "source-force", duplicates=True
    )
    replacement = next(x for x in changed.sheets["3"].identities if x.id == "new-identity")
    assert replacement.marked and changed.sheets["3"].sedation_locked == ("new-identity",)
    for updates in (
        {"protected": True},
        {"paired": True},
        {"obsession_sources": ("source",)},
        {"am_limiter": "source", "protected": True, "slot": 0},
    ):
        blocked = actual.model_copy(deep=True)
        blocked.sheets["3"].identities = [
            x.model_copy(update=updates) if x.id == selected.id else x
            for x in blocked.sheets["3"].identities
        ]
        with pytest.raises(ValueError):
            rules.force(blocked, value, selected.id, "new", "force", duplicates=True)
    assert tag != old


@pytest.mark.parametrize("protected", (True, False))
def test_actual_npc_alteration_tag_and_foundation_off_duty_procedure(
    ledger, tmp_path, monkeypatch, protected
):
    game, controls, immune, ordinary, later, baseline = npc_sources(ledger, tmp_path, monkeypatch)
    cycle, period = real_period(MissionService(ledger), game)
    subject, tag = (immune, later) if protected else (ordinary, baseline)
    before = state(game)
    npcs = {x.id: x for x in before.world.npcs}
    context = HandlerContext(
        entity="npc:" + subject.entity, operation="deprogram", deprogram_tags=(tag,)
    )
    review = cycle.review(ADMIN, period)
    with pytest.raises(WorkflowError):
        cycle.handler_scene(
            OTHER,
            str(uuid4()),
            period,
            review["revision"],
            before.revision,
            "npc_employment",
            (1, 2),
            "Cannot author another original Handler's procedure",
            context=context,
        )
    assert state(game) == before
    cycle.handler_scene(
        ADMIN,
        str(uuid4()),
        period,
        review["revision"],
        before.revision,
        "npc_employment",
        (1, 2),
        "PRIVATE_ACTUAL_PROCEDURE These selected Tags noticeably impair the worker's duties; "
        "Foundation staff actually perform the deprogramming procedure",
        context=context,
    )
    for viewer in (ADMIN, PLAYER, OTHER):
        call(cycle, game, viewer, period, "acknowledge", None)
    after = state(game)
    receipt = rules.records(after, rules.Deprogramming)[-1]
    assert receipt.subject == subject and receipt.tags == (tag,) and receipt.blocked is protected
    changed = next(x for x in after.world.npcs if x.id == subject.entity)
    if protected:
        assert changed == npcs[subject.entity]
    else:
        assert not any(x.id == tag for x in changed.tags)
        assert changed.model_dump(exclude={"tags"}) == npcs[subject.entity].model_dump(
            exclude={"tags"}
        )
    untouched = ordinary if protected else immune
    assert next(x for x in after.world.npcs if x.id == untouched.entity) == npcs[untouched.entity]
    assert set(after.sheets) == set(before.sheets)
    assert (
        controls.view(PLAYER, rules.records(after, rules.Birth)[-1].id)["phase"] == "npc_protected"
    )
