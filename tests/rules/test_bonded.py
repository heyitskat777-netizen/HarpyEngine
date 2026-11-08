"""Bonded ordinary normals; only the named likely smoke runs before final P1."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_intracadre_marriage import FOUR, third_draft
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_bonded import open_bonded, open_choice
from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_bonded import BondedService, original_pair, prove
from girlframe.services.onboarding import WorkflowError

PEOPLE = {2: PLAYER, 3: OTHER, 4: FOUR}


def bonded_game(store, girl="BONDED", frame="THE ENFORCER", faces=(4, 5), *, three=False):
    from test_creation import selected
    from test_creation_review import ready as creation_ready
    from test_m2_game import Dice

    from girlframe.engine.bonds import BondProposal
    from girlframe.engine.m2 import ReleaseApproval
    from girlframe.engine.m2_registry import registry_digest
    from girlframe.services.bonds import BondService
    from girlframe.services.m2_game import GameService

    review, creation, _ = creation_ready(store, girl, frame)
    store.policy = store.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic fixture only",
                reference="Not independent certification",
            ),
        }
    )
    own = creation.get(OTHER)
    creation.save(
        OTHER,
        str(uuid4()),
        own.revision,
        store.draft(OTHER)["revision"],
        selected("MOCKINGBIRD", "JANUS-B").model_copy(
            update={"shared_tokens": own.draft.shared_tokens}
        ),
    )
    third_draft(store)
    bonds = BondService(store)
    personal = bonds.propose(
        OTHER,
        str(uuid4()),
        store.draft(OTHER)["revision"],
        store.draft(FOUR)["revision"],
        BondProposal(target_id=4, prompt=0, context="My actual Personal starting Bond"),
    )
    bonds.decide(FOUR, str(uuid4()), personal["id"], 1, "accept")
    own = creation.get(OTHER)
    review.select_bond(
        OTHER, str(uuid4()), own.revision, store.draft(OTHER)["revision"], own.draft, personal["id"]
    )
    game = GameService(store, dice=Dice(faces))
    for owner in (PLAYER, OTHER, FOUR):
        value = review.get(owner)
        assert value.sheet.ready_for_rules_review, value.sheet.issues
        review.save(owner, str(uuid4()), value.saved_revision, value.fingerprint)
        game.activate(owner, str(uuid4()), review.get(owner).fingerprint)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for owner in (PLAYER, OTHER, FOUR, ADMIN) if three else (PLAYER, OTHER, ADMIN):
        game.join_scene(owner, str(uuid4()), 900)
    return game, GameWorker(game), Gateway(), game.dice


def ready(store, tmp_path, monkeypatch, *, three=False, marks=False, pair_book=None):
    import test_mission_service as fixture

    monkeypatch.setattr(
        fixture, "setup_game", lambda actual, **kwargs: bonded_game(actual, three=three, **kwargs)
    )
    _, game = service(store, girl="BONDED", frame="THE ENFORCER")
    approved(
        store,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            *rules.RULES,
            "girl.alpha.sex-play",
            "girl.am.sex-play",
            "girl.mockingbird.sex-play",
        ),
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        for owner in (2, 3, 4) if three else (2, 3):
            actual = place(actual, owner, mode="outside_frame", cell=(0, 0))
        actual.order = (3, 2, 4)
        if marks:
            for sheet in actual.sheets.values():
                for entry in sheet.identities:
                    entry.marked = True
        if pair_book:
            # Explicit synthetic prior subtype context only; this is not creation evidence.
            # All later source requests, counterpart confirmations, dice and effects are real.
            actual.sheets["3"].girl = pair_book
        game.event(
            c, 1, str(uuid4()), "synthetic.original_Pair_prior_physical_resource_context", actual
        )
    return game, GameWorker(game), Gateway(), BondedService(game)


def show(controls, viewer=PLAYER, identity=None, number=87000):
    async def run():
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_bonded(interaction, controls, identity)
        return interaction.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(run())


def submit(form, viewer, values, number):
    async def run():
        form.values.update(values)
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        await form.confirm.callback(interaction)
        assert form.completed, interaction.edit_original_response.call_args_list
        return interaction.edit_original_response.call_args.kwargs.get("view")

    return asyncio.run(run())


def native_choice(game, viewer, kind, values, number=87500):
    decision = next(x for x in game.choices(viewer) if x["kind"] == kind)

    async def run():
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, game.decision(viewer, decision["id"]))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        response = current(viewer.user_id, number + 1)
        response.channel_id = 900
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(run())


def pick(game, viewer, kind, options=(), *, identities=(), **fields):
    return answer(
        game,
        viewer,
        kind,
        options=options,
        denied=identities,
        text=json.dumps({"account": "My actual performed owned source outcome", **fields}),
    )


def pass_tags(game):
    for viewer in (PLAYER, OTHER, FOUR, ADMIN):
        if viewer != ADMIN and str(viewer.user_id) not in state(game).sheets:
            continue
        for row in game.choices(viewer):
            if row["kind"] == "tag_window":
                game.respond(
                    viewer,
                    str(uuid4()),
                    row["id"],
                    row["revision"],
                    ChoiceAnswer(options=("pass",)),
                )


def pause_tick(game, gateway):
    from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker

    asyncio.run(SourcePauseWorker(game).tick(gateway))


def propose(controls, game, kind, *, target=None, observer=None, route="pair"):
    return controls.propose(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        kind,
        "PRIVATE_BONDED_SOURCE: my actual voluntary source, with no inferred words from her",
        target=current_ref(state(game), target) if target else None,
        observer=current_ref(state(game), observer) if observer else None,
        route=route,
        apart=kind == "side",
    )["id"]


def roll(game, worker, gateway, source, faces=(4, 4)):
    value = rules.get(state(game), source)
    game.dice.faces = faces
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.SIDE_PLAY if value.kind == "side" else rules.SEX_PLAY,
            source_work=source,
            heat=state(game).sheets["2"].heat,
            context="My genuine actual original-person source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return action


def intimate(controls, game, target=3, route="pair"):
    identity = propose(controls, game, "sex", target=target, route=route)
    controls.confirm(
        PEOPLE[target],
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "My own actual voluntary participation; no other response is inferred",
    )
    return identity


def test_native_mid_side_real_paired_five_split_arrival_and_private_reopen(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    paired = next(x for x in before.sheets["2"].identities if x.paired)
    menu = show(controls)
    form = submit(menu, PLAYER, {"source": ("side",)}, 87001)
    submit(
        form,
        PLAYER,
        {
            "apart": ("yes",),
            "account": "We are in the same broad square but actually apart; I want her side",
        },
        87002,
    )
    source = rules.records(state(game), rules.Source)[-1].id
    assert game.dice.calls == 0
    actor, pair = current_ref(before, 2), current_ref(before, 3)
    saved_frame = next(x for x in before.placements if x.actor == actor)
    with ledger.engine.connect() as c:
        assert original_pair(game, c, state(game), actor)[0] == pair
    game.dice.faces = (3, 3)
    action = game.begin(
        PLAYER,
        "paired-side-real-roll",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=rules.SIDE_PLAY,
            source_work=source,
            heat=3,
            identity=paired.id,
            gain=5,
            pair_share=2,
            context="I want to be by my actual Pair",
            trigger_confirmed=True,
        ),
    )["action_id"]
    assert (
        game.dice.calls == 0
        and not next(x for x in state(game).sheets["2"].identities if x.id == paired.id).marked
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    assert actual.sheets["3"].heat == before.sheets["3"].heat + 2
    assert next(x for x in actual.sheets["2"].identities if x.id == paired.id).marked
    native_choice(
        game,
        PLAYER,
        "bonded_side",
        {"options": ("arrive",), "account": "I actually arrive close enough to touch her"},
    )
    tick(worker, gateway, 3)
    actual = state(game)
    moved = next(x for x in actual.placements if x.actor == actor)
    assert moved.vessel_id == saved_frame.vessel_id
    assert (
        moved.frame_cell == saved_frame.frame_cell
        and moved.frame_instance == saved_frame.frame_instance
    )
    from girlframe.services.m3_actors import profiles

    with ledger.engine.connect() as c:
        bindings = profiles(c, ledger.campaign_id)
        assert resolve(actual, actor, bindings).cell == resolve(actual, pair, bindings).cell
    with ledger.engine.connect() as c:
        assert game.action(c, action)["state"] == "complete"
        assert prove(game, c, actual, source).phase == "complete"
    assert rules.get(actual, source).account not in json.dumps(game.sheet(OTHER, 2))
    assert controls.view(PLAYER, source)["selections"]
    assert controls.view(OTHER, source)["selections"][0]["identities"] == ()
    assert show(controls, PLAYER, source, 87010) is None
    calls, frozen = game.dice.calls, actual.model_dump_json()
    with pytest.raises(WorkflowError):
        controls.view(FOUR, source)
    assert game.dice.calls == calls and state(game).model_dump_json() == frozen
    # Exact begin replay remains one actual receipt/charge; no second roll.
    assert (
        game.begin(
            PLAYER,
            "paired-side-real-roll",
            900,
            before.sheets["2"].revision,
            PlayInput(
                play=rules.SIDE_PLAY,
                source_work=source,
                heat=3,
                identity=paired.id,
                gain=5,
                pair_share=2,
                context="I want to be by my actual Pair",
                trigger_confirmed=True,
            ),
        )["action_id"]
        == action
    )
    assert game.dice.calls == calls


def test_high_side_actual_found_weapon_is_item_and_not_asset(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    source = propose(controls, game, "side")
    before = state(game)
    roll(game, worker, gateway, source, (6, 6))
    pick(
        game,
        PLAYER,
        "bonded_side",
        ("arrive", "weapon"),
        weapon_name="A real loose iron bar",
        weapon_description="The actual bar I needed, found and took with me",
    )
    actual = state(game)
    assert actual.sheets["2"].assets == before.sheets["2"].assets
    item = next(x for x in actual.held_items if x.source.startswith("bonded-weapon:"))
    assert item.holder == current_ref(actual, 2)
    assert controls.view(PLAYER, source)["phase"] == "complete"


@pytest.mark.parametrize("choice", ["stay", "arrive"])
def test_low_side_owned_choice_real_helpless_status_and_original_pair_help(
    ledger, tmp_path, monkeypatch, choice
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    source = propose(controls, game, "side")
    before = state(game)
    roll(game, worker, gateway, source, (1, 1))
    pick(game, PLAYER, "bonded_side", (choice,), question="When are you actually coming for me?")
    tick(worker, gateway, 3)
    actual = state(game)
    assert is_helpless(actual, current_ref(actual, 2))
    calls = game.dice.calls
    with pytest.raises(WorkflowError, match="Helpless|helpless"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            actual.sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="Actual new defensive danger",
                trigger_confirmed=True,
            ),
        )
    assert game.dice.calls == calls
    key = str(uuid4())
    first = controls.help(
        OTHER, key, source, actual.revision, "I actually come close and physically help her"
    )
    assert (
        controls.help(
            OTHER, key, source, actual.revision, "I actually come close and physically help her"
        )
        == first
    )
    assert not rules.helpless(state(game), current_ref(actual, 2))
    assert before.sheets["2"].assets == state(game).sheets["2"].assets


def test_mid_pair_sex_all_four_requests_real_pair_replies_order_and_appearance(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, marks=True)
    source = intimate(controls, game)
    roll(game, worker, gateway, source)
    actual = state(game)
    ids = tuple(x.id for x in actual.sheets["2"].identities if x.marked)[:4]
    pick(game, PLAYER, "bonded_mid", ("tag", "secret", "order", "appearance"), identities=ids)
    for request, content in (
        ("tag", "Hers and safe"),
        ("secret", "PRIVATE_PAIR_SECRET: my actual secret"),
        ("order", "Stay by my side"),
        ("appearance", "I actually braid her hair in a new style"),
    ):
        row = next(
            x
            for x in game.choices(OTHER)
            if x["kind"] == "bonded_reply"
            and game.decision(OTHER, x["id"])["detail"]["request"] == request
        )
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(
                options=("give",),
                text=json.dumps({"account": "My actual response", "content": content}),
            ),
        )
    assert controls.view(PLAYER, source)["phase"] == "results"
    order = game.issue_order(OTHER, str(uuid4()), 900, 2, "Stay by my side")
    assert order
    assert depth(state(game), current_ref(state(game), 2), current_ref(state(game), 3)) == 2
    assert all(
        not next(x for x in state(game).sheets["2"].identities if x.id == key).marked for key in ids
    )
    assert (
        rules.appearance(state(game), current_ref(state(game), 2))
        == "I actually braid her hair in a new style"
    )
    assert any(x.label == "Hers and safe" for x in state(game).sheets["2"].tags)
    assert controls.view(PLAYER, source)["phase"] == "complete"


def test_high_pair_sex_actual_promise_pair_tags_and_status_above(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    from girlframe.engine.m3_mockingbird import give_tag

    with ledger.transaction() as c:
        actual = state(game)
        event = str(uuid4())
        actual = give_tag(
            actual,
            (),
            current_ref(actual, 3),
            current_ref(actual, 2),
            "Actual original Pair Tag",
            "actual-prior-pair-tag",
            event,
            (2, 3),
        )
        game.event(c, 2, str(uuid4()), "synthetic.prior_owned_ordinary_Tag", actual, event_id=event)
    source = intimate(controls, game)
    roll(game, worker, gateway, source, (6, 6))
    pick(game, PLAYER, "bonded_promise", ("promise",))
    pick(game, OTHER, "bonded_high", identities=("actual-prior-pair-tag",))
    actual = state(game)
    assert any(
        x.label == "Actual original Pair Tag" and x.giver_actor == current_ref(actual, 3)
        for x in actual.sheets["2"].tags
    )
    assert any(x.id == "actual-prior-pair-tag" for x in actual.sheets["3"].tags)
    assert state(game).order.index(2) + 1 == state(game).order.index(3)
    assert controls.view(PLAYER, source)["phase"] == "complete"


@pytest.mark.parametrize("decision", ["continue", "stop"])
def test_low_pair_sex_actual_counterpart_owns_continuing_or_stopping(
    ledger, tmp_path, monkeypatch, decision
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, marks=True)
    source = intimate(controls, game)
    before = state(game)
    roll(game, worker, gateway, source, (1, 1))
    identity = next(x.id for x in before.sheets["3"].identities if x.marked)
    pick(
        game,
        OTHER,
        "bonded_low",
        (decision,),
        identities=(identity,) if decision == "continue" else (),
    )
    actual = state(game)
    if decision == "continue":
        assert not next(x for x in actual.sheets["3"].identities if x.id == identity).marked
    else:
        assert depth(actual, current_ref(actual, 2), current_ref(actual, 3)) == max(
            0, depth(before, current_ref(before, 2), current_ref(before, 3)) - 1
        )
    assert controls.view(PLAYER, source)["phase"] == "complete"


@pytest.mark.parametrize("outcome", ["draw_back", "pair_tag", "observer_tag", "child"])
def test_real_witnessed_affection_owned_tag_or_real_child_silence(
    ledger, tmp_path, monkeypatch, outcome
):

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, three=True)
    source = propose(controls, game, "intimacy", observer=4)
    controls.activate(
        PLAYER,
        str(uuid4()),
        source,
        state(game).revision,
        "I actually show this affection before the real onlooker",
    )
    pause_tick(game, gateway)
    controls.choose(
        PLAYER,
        str(uuid4()),
        source,
        state(game).revision,
        ChoiceAnswer(
            options=(outcome,),
            text=json.dumps(
                {
                    "account": "My actual witnessed-affection choice",
                    "tag": "Saw our closeness",
                    "play": "flirt",
                    "context": "I actually use my charm against the onlooker",
                }
            ),
        ),
    )
    if outcome == "child":
        child = controls.view(PLAYER, source)["child"]
        game.dice.faces = (4, 4)
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="flirt",
                heat=0,
                source_work=child["id"],
                target=4,
                context=child["account"],
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        pick(game, PLAYER, "flirt_questions", ("hurt",))
        assert action and not rules.can_disclose(state(game), current_ref(state(game), 4), source)
    elif outcome.endswith("tag"):
        recipient = "3" if outcome == "pair_tag" else "4"
        assert any(x.label == "Saw our closeness" for x in state(game).sheets[recipient].tags)
    assert controls.view(PLAYER, source)["phase"] == "complete"
    tick(worker, gateway, 3)
    pause_tick(game, gateway)


def test_nonpair_actual_seven_no_roll_pair_not_private_audience(ledger, tmp_path, monkeypatch):

    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, three=True)
    source = intimate(controls, game, 4, "seven")
    before = state(game)
    baseline_permissions = {k: dict(v) for k, v in gateway.values.items()}
    from girlframe.services.p1_source_pause import projection

    def pause_state():
        with ledger.engine.connect() as connection:
            return projection(game, connection, source)["state"]

    controls.activate(
        PLAYER,
        str(uuid4()),
        source,
        before.revision,
        "Actual voluntary intimacy with this original other person",
    )
    assert pause_state() == "acquiring"
    pause_tick(game, gateway)
    assert pause_state() == "held"
    assert gateway.values != baseline_permissions
    with pytest.raises(WorkflowError):
        controls.view(OTHER, source)
    controls.choose(
        FOUR,
        "real-unrolled-stop",
        source,
        state(game).revision,
        ChoiceAnswer(options=("stop",), text="I actually stop"),
    )
    assert game.dice.calls == 0
    assert rules.get(state(game), source).action is None
    assert depth(state(game), current_ref(state(game), 2), current_ref(state(game), 3)) == depth(
        before, current_ref(before, 2), current_ref(before, 3)
    )
    pause_tick(game, gateway)
    assert pause_state() == "closed"
    assert gateway.values == baseline_permissions


def test_delegated_alpha_actual_other_partner_source_no_persona_copy(ledger, tmp_path, monkeypatch):
    from girlframe.services.m3_alpha_sex import SexService

    game, worker, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, pair_book="ALPHA"
    )
    source = intimate(controls, game, 4, "delegated")
    actual = state(game)
    sex = SexService(game)
    delegated = sex.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(actual, 4),
        actual.revision,
        "Our actual voluntary copied-rule source",
        bonded_source=source,
    )["id"]
    sex.respond(
        FOUR,
        str(uuid4()),
        delegated,
        state(game).revision,
        True,
        "My own genuine source confirmation",
    )
    game.dice.faces = (4, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="alpha_sex",
            heat=0,
            source_work=delegated,
            target_actor=current_ref(state(game), 4),
            context="Our actual completed Alpha-source intimacy",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert action and state(game).sheets["2"].girl == "BONDED"
    assert current_ref(state(game), 2) == current_ref(actual, 2)
    assert controls.view(PLAYER, source)["phase"] == "complete"


def test_delegated_am_native_uses_real_counterpart_receipt_without_extra_roll(
    ledger, tmp_path, monkeypatch
):
    from girlframe.discord_adapter.m3_bonded_support import open_delegated
    from girlframe.services.m3_mockingbird_plays import MockingbirdService

    game, worker, gateway, controls = ready(
        ledger, tmp_path, monkeypatch, three=True, pair_book="AM"
    )
    source = intimate(controls, game, 4, "delegated")
    actual = state(game)
    counterpart = MockingbirdService(game)
    original = counterpart.propose(
        FOUR,
        str(uuid4()),
        900,
        current_ref(actual, 4),
        "mockingbird_sex",
        (current_ref(actual, 2),),
        "Our real voluntary counterpart source",
    )["id"]
    counterpart.attest(PLAYER, str(uuid4()), original, current_ref(actual, 2), True)
    game.dice.faces = (1, 1)
    action = game.begin(
        FOUR,
        str(uuid4()),
        900,
        state(game).sheets["4"].revision,
        PlayInput(
            play="mockingbird_sex",
            source_work=original,
            heat=0,
            context="The actual counterpart's own completed Sex source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    calls = game.dice.calls
    balances = {
        uid: (x.heat, tuple(y.marked for y in x.identities))
        for uid, x in state(game).sheets.items()
    }

    async def native():
        interaction = current(2, 87901)
        interaction.channel_id = 901  # Saved controls may reopen from elsewhere.
        await interaction.response.defer(ephemeral=True)
        await open_delegated(interaction, game, source)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert ("circuits", "Actual circuit contact: use Just Code") not in form.fields[0].options
        form.values["source"] = (action,)
        response = current(2, 87902)
        response.channel_id = 901
        await form.confirm.callback(response)
        assert form.completed

    asyncio.run(native())
    assert game.dice.calls == calls
    assert balances == {
        uid: (x.heat, tuple(y.marked for y in x.identities))
        for uid, x in state(game).sheets.items()
    }
    assert state(game).sheets["2"].girl == "BONDED"
    assert controls.view(PLAYER, source)["phase"] == "complete"
