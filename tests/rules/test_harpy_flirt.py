"""Synthetic native normal Harpy/Core ↔ Girl Flirt, without live rule approval."""

import asyncio
from uuid import uuid4

import pytest
from test_harpy_actor_plays import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current
from test_physical_operations import place

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_harpy_flirt import open_flirt, open_followthrough
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref, depth, is_helpless
from girlframe.engine.m3_actor_plays import embrace
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.engine.m3_harpy_flirt import assert_can_refuse, clear_tag_debt
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_handler_plays import HandlerPlayService

CANARY = "SYNTHETIC_PRIVATE_HARPY_FLIRT_REPLY"


def prepared(store, *, faces=(4, 5)):
    source, game, cast, ref = ready(store, faces=faces, heat=2)
    with store.transaction() as c:
        canon = place(place(state(game), 2), 3)
        value = harpy(canon, ref)
        canon = update(
            canon,
            ref,
            identities=tuple(x.model_copy(update={"marked": True}) for x in value.identities),
        )
        canon.sheets["3"].identities[0].marked = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_flirt_marks", canon)
    return source, game, cast, ref, GameWorker(game), Gateway()


def interaction(viewer, number):
    result = current(viewer.user_id, number)
    result.channel_id = 900
    return result


async def submit_form(viewer, callback, values, number, *, wrong_owner=False):
    origin = interaction(viewer, number)
    await origin.response.defer(ephemeral=True)
    await callback(origin)
    form = origin.edit_original_response.call_args.kwargs["view"]
    assert isinstance(form, NativeForm)
    if wrong_owner:
        assert not await form.interaction_check(interaction(ADMIN, number + 1))
    form.values.update(values)
    confirmation = interaction(viewer, number + 2)
    await form.confirm.callback(confirmation)
    assert form.completed, confirmation.edit_original_response.call_args_list
    return str(confirmation.id)


def native_answer(game, viewer, kind, values, number):
    row = next(x for x in game.choices(viewer) if x["kind"] == kind)
    key = asyncio.run(
        submit_form(
            viewer, lambda i: open_choice(i, game, row["id"]), values, number, wrong_owner=True
        )
    )
    return row, key


def pass_tags(game):
    for viewer in (ADMIN, PLAYER, OTHER):
        if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))


def start_native(game, ref, worker, gateway):
    target = current_ref(state(game), 3)
    asyncio.run(
        submit_form(
            PLAYER,
            lambda i: open_flirt(i, game, ref),
            dict(
                context="Original Harpy/Girl interaction",
                target=(target.token,),
                heat=("1",),
                gain=("1",),
            ),
            987000,
        )
    )
    with game.store.engine.connect() as c:
        action = game.lock(c, 900)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return action


def questions(game, *, high=None):
    answer(
        game,
        PLAYER,
        "harpy_flirt_actor",
        options=("name",),
        fields={"extra": high} if high else {},
        text="I go too far" if high else "",
    )
    answer(game, OTHER, "harpy_flirt_target", options=("fears",), text=CANARY)
    answer(game, PLAYER, "harpy_flirt_answer", text="I genuinely answer her own question")


def test_native_harpy_mid_both_owned_questions_unmark_actual_resources_and_confirm_followthrough(
    ledger,
):
    source, game, _, ref, worker, gateway = prepared(ledger)
    before = state(game)
    action = start_native(game, ref, worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["faces"] == [4, 5] and receipt["heat"] == 1
    own_identity = harpy(before, ref).identities[0].id
    target = current_ref(before, 3)
    pilot_identity = before.sheets["3"].identities[0].id
    native_answer(
        game, PLAYER, "harpy_flirt_actor", dict(options=("name",), denied=(own_identity,)), 987100
    )
    native_answer(
        game,
        OTHER,
        "harpy_flirt_target",
        dict(options=("fears",), denied=(pilot_identity,), text=CANARY),
        987110,
    )
    row, key = native_answer(
        game, PLAYER, "harpy_flirt_answer", dict(text="My actual answer"), 987120
    )
    completed = state(game)
    game.respond(PLAYER, key, row["id"], row["revision"], ChoiceAnswer(text="My actual answer"))
    assert state(game) == completed and game.dice.calls == 1
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert not harpy(completed, ref).identities[0].marked
    assert not completed.sheets["3"].identities[0].marked
    assert completed.sheets["2"] == before.sheets["2"]
    assert harpy(completed, ref).heat == harpy(before, ref).heat - 1
    assert depth(completed, ref, target) == 0
    owed = [x for x in completed.obligations if x.kind == "harpy_flirt_followthrough"]
    assert len(owed) == 2 and {ActorRef.model_validate_json(x.details["actor"]) for x in owed} == {
        ref,
        target,
    }
    tick(worker, gateway, 5)
    follow = next(x for x in owed if ActorRef.model_validate_json(x.details["actor"]) == ref)
    asyncio.run(
        submit_form(
            PLAYER,
            lambda i: open_followthrough(i, game, follow.model_dump(mode="json")),
            dict(account="I actually use her requested name"),
            987130,
        )
    )
    tick(worker, gateway, 3)
    native_answer(
        game,
        OTHER,
        "harpy_flirt_followthrough_confirm",
        dict(flag=("yes",), text="She actually followed through"),
        987140,
    )
    assert depth(state(game), ref, target) == 1 and game.dice.calls == 1
    assert GameService(ledger).inspect(PLAYER, action)["receipt"] == receipt
    tick(worker, gateway, 5)
    assert CANARY not in str(gateway.messages)


def test_harpy_low_weakens_only_actual_edge_target_unmarks_and_actor_answers_return_question(
    ledger,
):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(1, 1))
    target = current_ref(state(game), 3)
    with ledger.transaction() as c:
        canon = change(state(game), ref, target, 1, "synthetic-prior-personal-bond")
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_flirt_bond", canon)
    before = state(game)
    action = start_native(game, ref, worker, gateway)
    answer(
        game,
        OTHER,
        "harpy_flirt_target",
        options=("hide",),
        denied=(before.sheets["3"].identities[0].id,),
        text="What pushes me away",
    )
    answer(game, PLAYER, "harpy_flirt_answer", text="My actual return answer")
    actual = state(game)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert depth(actual, ref, target) == 0 and harpy(actual, ref).identities[0].marked
    assert not actual.sheets["3"].identities[0].marked
    assert not any(x.kind == "harpy_flirt_followthrough" for x in actual.obligations)
    assert actual.sheets["2"] == before.sheets["2"] and game.dice.calls == 1


@pytest.mark.parametrize("escape", ["helpless", "damage", "play"])
def test_harpy_high_real_target_escape_consequences(ledger, escape):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(6, 6))
    action = start_native(game, ref, worker, gateway)
    target = current_ref(state(game), 3)
    questions(game, high="escape")
    actual_asset = next(x for x in state(game).sheets["3"].assets if not x.damaged)
    answer(
        game,
        OTHER,
        "harpy_flirt_escape",
        options=(escape,),
        denied=(actual_asset.id,) if escape == "damage" else (),
    )
    if escape == "play":
        child = game.begin(
            OTHER,
            str(uuid4()),
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="My actual escape now",
                parent=action,
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        answer(game, OTHER, "actor_keep", text="Actual escape Tag")
        answer(game, ADMIN, "handler_keep", flag=True, text="Actual escape succeeds")
        assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert is_helpless(state(game), target, ref) == (escape == "helpless")
    if escape == "damage":
        assert next(x for x in state(game).sheets["3"].assets if x.id == actual_asset.id).damaged
    assert game.dice.calls == (2 if escape == "play" else 1)


def test_harpy_high_owed_tag_binds_actual_actor_and_original_giver_until_real_embrace(ledger):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(6, 6))
    action = start_native(game, ref, worker, gateway)
    questions(game, high="owe")
    native_answer(game, OTHER, "harpy_flirt_owe", dict(text="My actual owed Tag"), 987200)
    actual = state(game)
    tag = harpy(actual, ref).tags[-1]
    target = current_ref(actual, 3)
    assert tag.giver_ref == target and not actual.sheets["2"].tags
    with pytest.raises(ValueError, match="COMPULSION"):
        assert_can_refuse(actual, ref, target)
    assert_can_refuse(actual, current_ref(actual, 2), target)
    actual = update(
        actual,
        ref,
        tags=tuple(
            x.model_copy(update={"marked": True}) if x.id == tag.id else x
            for x in harpy(actual, ref).tags
        ),
    )
    embrace(actual, ref, tag.id, ())
    clear_tag_debt(actual, ref, tag.id)
    assert_can_refuse(actual, ref, target)
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_harpy_high_handler_requires_actual_typed_handler_play(ledger):
    _, game, _, ref, worker, gateway = prepared(ledger, faces=(6, 6))
    action = start_native(game, ref, worker, gateway)
    questions(game, high="handler")
    grant = state(game).handler_plays[-1]
    assert set(grant.targets) == {ref, current_ref(state(game), 3)}
    assert game.inspect(PLAYER, action)["state"] != "complete"
    source = HandlerPlayService(ledger)
    data = source.get(ADMIN, grant.id)
    source.submit(
        ADMIN,
        str(uuid4()),
        grant.id,
        data["game_revision"],
        "brief",
        Effect(kind="brief", account="Actual Handler provides real scene intelligence"),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1


def test_actual_pilot_flirts_with_original_core_then_core_escapes_and_flirts_as_herself(
    ledger, tmp_path, monkeypatch
):
    from test_frame_control import exposed_core

    game, pilot, core = exposed_core(ledger, tmp_path, monkeypatch, caster_mode="inside_frame")
    # Actual original Core is already admitted through request/controller/GM.
    # Prior synthetic removal is source history, not a fake new Harpy or PC
    # alias. Keep the original pain/Drugged Tags and all immutable source fields.
    with ledger.transaction() as c:
        canon = state(game)
        value = harpy(canon, core)
        removed = {value.baseline_tags["restrained"], value.baseline_tags["muzzled"]}
        canon = update(canon, core, tags=tuple(x for x in value.tags if x.id not in removed))
        game.event(c, 1, str(uuid4()), "synthetic.prior_core_tag_removal", canon)
    before = state(game)
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (6, 6)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play="flirt",
            heat=0,
            context="Actual Girl speaks with her original Core",
            target_actor=core,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "harpy_flirt_actor",
        options=("name",),
        fields={"extra": "escape"},
        text="I actually go too far with this original Core",
    )
    answer(game, OTHER, "harpy_flirt_target", options=("hide",), text="The original Core's answer")
    answer(game, PLAYER, "harpy_flirt_answer", text="Her original Pilot answers her")
    answer(game, OTHER, "harpy_flirt_escape", options=("play",))
    source = ActorPlayService(game)
    view = source.preview(OTHER, 900, core)
    child = source.begin(
        OTHER,
        str(uuid4()),
        900,
        core,
        view["actor"]["source_sha256"],
        None,
        view["cast_revision"],
        PlayInput(
            play="check_sensors",
            heat=0,
            context="The original Core asks actual Sensor questions to escape now",
            parent=action,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    answer(
        game, ADMIN, "harpy_sensor_answers", text="The actual GM answers every question", flag=True
    )
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 5)
    game.dice.faces = (4, 4)
    view = source.preview(OTHER, 900, core)
    own = source.begin(
        OTHER,
        str(uuid4()),
        900,
        core,
        view["actor"]["source_sha256"],
        None,
        view["cast_revision"],
        PlayInput(
            play="flirt",
            heat=1,
            context="The original Core makes her own ordinary Flirt",
            target_actor=pilot,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    native_answer(game, OTHER, "harpy_flirt_actor", dict(options=("name",)), 987300)
    native_answer(
        game,
        PLAYER,
        "harpy_flirt_target",
        dict(options=("be",), text="Actual Pilot answer"),
        987310,
    )
    native_answer(
        game, OTHER, "harpy_flirt_answer", dict(text="Actual original Core return answer"), 987320
    )
    actual = state(game)
    assert game.inspect(OTHER, own)["state"] == "complete" and game.dice.calls == 2
    assert actual.sheets["3"] == before.sheets["3"]
    assert harpy(actual, core).heat == harpy(before, core).heat - 1
    assert harpy(actual, core).source_setup == harpy(before, core).source_setup
    assert harpy(actual, core).baseline_tags == harpy(before, core).baseline_tags
    assert actual.placements == before.placements
