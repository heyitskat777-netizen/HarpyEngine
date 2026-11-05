"""Real Heat roll → exact Dive choosers → owned table effects → restored chat."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_beneath_service import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_dive import open_dive
from girlframe.engine import m3_physical as physical
from girlframe.engine.m2 import ChoiceAnswer, IdentityState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_world_state import Board, Npc, World
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dive import prove_void_source
from girlframe.services.onboarding import WorkflowError


def rolled(store, faces=(4, 5), *, placement=None, marked=False):
    game, worker, gateway = ready(store, faces)
    if placement or marked:
        with store.transaction() as c:
            canon = state(game)
            if marked:
                for item in canon.sheets["2"].identities:
                    item.marked = True
                canon.sheets["2"].sedation_locked = (canon.sheets["2"].identities[0].id,)
            if placement:
                canon.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
                actor = ActorRef(
                    kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id
                )
                frame = resolve(
                    canon, actor, profiles(c, store.campaign_id), require_current_profile=False
                ).frame_instance
                proposal = InitialPlacement(
                    actor=actor,
                    frame_instance=frame,
                    girl_cell=(0, 0),
                    frame_cell=(0, 0),
                    mode=placement,
                    account="Actual original body and Frame facts",
                    facts_confirmed=True,
                )
                canon = physical.initial(
                    canon,
                    profiles(c, store.campaign_id),
                    proposal,
                    "actual-vessel",
                    "actual-placement-proposal",
                    "actual-handler-review",
                )
            game.event(c, 1, "actual-dive-fixture-state", "synthetic.state", canon)
    identity = game.begin(
        PLAYER,
        "actual-dive",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            context="Actual link communion",
            trigger_confirmed=True,
            heat=0,
            piloting=placement == "piloting",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, identity


def choose(game, viewer, option, account="Actual source communion"):
    return answer(game, viewer, "dive_select", options=(option,), text=account)


@pytest.mark.parametrize("faces,chooser", [((1, 1), ADMIN), ((4, 5), PLAYER)])
def test_actual_low_handler_and_mid_player_choose_then_owner_erases_and_each_table_human_answers(
    ledger, faces, chooser
):
    game, worker, gateway, identity = rolled(ledger, faces)
    row = next(x for x in game.choices(chooser) if x["kind"] == "dive_select")
    wrong = PLAYER if chooser == ADMIN else ADMIN
    with pytest.raises(WorkflowError):
        game.respond(
            wrong,
            "not-the-chooser",
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("erase_identity_and_table_question",), text="Wrong"),
        )
    choose(game, chooser, "erase_identity_and_table_question")
    old = state(game).sheets["2"].identities[1]
    answer(
        game, PLAYER, "dive_effect", fields={"identity": old.id}, text="What actually waits below?"
    )
    assert old.id not in {x.id for x in state(game).sheets["2"].identities}
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    for viewer in (PLAYER, OTHER):
        answer(game, viewer, "dive_table_answer", text="Original human " + str(viewer.user_id))
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    answer(game, ADMIN, "dive_table_answer", text="Original facilitator answer")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "What actually waits below?" not in json.dumps(gateway.messages)


def test_gain_void_rewrites_actual_asset_unmarks_every_unlocked_identity_and_preserves_damage(
    ledger,
):
    game, worker, gateway, identity = rolled(ledger, marked=True)
    choose(game, PLAYER, "void_and_unmark_all")
    original = state(game).sheets["2"]
    asset = next(x for x in original.assets if x.family == "frame" and not x.void)
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": asset.id},
        text="Actual flesh-threaded housing",
    )
    after = state(game).sheets["2"]
    assert next(x for x in after.assets if x.id == asset.id).void
    assert (
        next(x for x in after.assets if x.id == asset.id).description
        == "Actual flesh-threaded housing"
    )
    assert [x.marked for x in after.identities] == [True, False, False, False]
    assert [x.damaged for x in after.assets] == [x.damaged for x in original.assets]
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_high_independent_choosers_may_repeat_option_then_status_lowers_once(ledger):
    game, worker, gateway, identity = rolled(ledger, (6, 6))
    before = state(game).order
    for viewer in (PLAYER, ADMIN):
        choose(game, viewer, "erase_identity_and_table_question")
        own = state(game).sheets["2"].identities[0]
        answer(
            game,
            PLAYER,
            "dive_effect",
            fields={"identity": own.id},
            text="Another actual table question",
        )
        for human in (PLAYER, OTHER, ADMIN):
            answer(game, human, "dive_table_answer", text="Actual answer")
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert before == (2, 3) and state(game).order == (3, 2)
    assert len([x for x in state(game).facts if x.get("kind") == "dive_spike_status"]) == 1
    assert game.dice.calls == 1 and len(state(game).sheets["2"].identities) == 2


def test_table_identity_requires_every_actual_human_and_rejection_resets_old_approvals(ledger):
    game, worker, gateway, identity = rolled(ledger)
    choose(game, PLAYER, "table_replaces_identity")
    old = state(game).sheets["2"].identities[1]
    answer(game, ADMIN, "dive_effect", fields={"identity": old.id}, text="First table proposal")
    for viewer, accepted in ((PLAYER, True), (OTHER, False), (ADMIN, True)):
        answer(game, viewer, "dive_table_agreement", flag=accepted, text="Actual table response")
    assert next(x.name for x in state(game).sheets["2"].identities if x.id == old.id) == old.name
    answer(game, ADMIN, "dive_effect", fields={"identity": old.id}, text="Revised actual Identity")
    for viewer in (PLAYER, ADMIN):
        answer(game, viewer, "dive_table_agreement", flag=True)
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    answer(game, OTHER, "dive_table_agreement", flag=True)
    assert (
        next(x.name for x in state(game).sheets["2"].identities if x.id == old.id)
        == "Revised actual Identity"
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_nearby_npcs_exact_actual_cell_only_handler_chooses_each_manifestation(ledger):
    game, worker, gateway = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(
            board=Board(minimum=(-2, -2), maximum=(2, 2)),
            locations=(),
            npcs=(
                Npc(
                    id="close-one",
                    name="Actual nearby1",
                    cell=(0, 0),
                    jobs=("guard",),
                    detail="Actual",
                    controller=1,
                ),
                Npc(
                    id="close-two",
                    name="Actual nearby2",
                    cell=(0, 0),
                    jobs=("mechanic",),
                    detail="Actual",
                    controller=1,
                ),
                Npc(
                    id="far",
                    name="Distant NPC",
                    cell=(1, 1),
                    jobs=("civilian",),
                    detail="Actual",
                    controller=1,
                ),
            ),
        )
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        frame = resolve(
            canon, actor, profiles(c, ledger.campaign_id), require_current_profile=False
        ).frame_instance
        canon = physical.initial(
            canon,
            profiles(c, ledger.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=frame,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="outside_frame",
                account="Actual",
                facts_confirmed=True,
            ),
            "vessel",
            "proposal",
            "review",
        )
        game.event(c, 1, "actual-nearby-npcs", "synthetic.state", canon)
    action = game.begin(
        PLAYER,
        "nearby-dive",
        900,
        state(game).sheets["2"].revision,
        PlayInput(play="dive_deep", heat=0, context="Actual radiation", trigger_confirmed=True),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, PLAYER, "nearby_npcs_gain_void")
    data = game.decision(
        ADMIN, next(x["id"] for x in game.choices(ADMIN) if x["kind"] == "dive_effect")
    )
    assert {x["id"] for x in data["dive"]["npcs"]} == {"close-one", "close-two"}
    with pytest.raises(WorkflowError):
        answer(game, ADMIN, "dive_effect", fields={"close-one": "brain"})
    answer(game, ADMIN, "dive_effect", fields={"close-one": "brain", "close-two": "flesh"})
    npcs = {x.id: x for x in state(game).world.npcs}
    assert npcs["close-one"].tags[0].label == "Void of the brain"
    assert npcs["close-two"].tags[0].label == "Void of the flesh" and not npcs["far"].tags
    assert game.inspect(PLAYER, action)["state"] == "complete"


def test_subsumption_requires_actual_own_cockpit_and_locks_inactive_vitals_without_teleport(ledger):
    game, worker, gateway, identity = rolled(ledger, placement="inside_frame")
    original = state(game).placements[0]
    choose(game, PLAYER, "locked_cockpit_extraction_requires_frame_consent")
    answer(game, PLAYER, "dive_effect", flag=True)
    canon = state(game)
    assert canon.placements[0].subsumed and not canon.placements[0].vitals_active
    assert canon.placements[0].girl_cell == original.girl_cell
    assert len(canon.frame_locks) == 1 and canon.frame_locks[0].subject == original.actor
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    with ledger.engine.connect() as c:
        with pytest.raises(ValueError):
            physical.extract(
                canon, profiles(c, ledger.campaign_id), original.actor, "new-source", "No consent"
            )


def test_outside_frame_still_dives_but_cannot_select_teleporting_subsumption(ledger):
    game, worker, gateway, identity = rolled(ledger, placement="outside_frame")
    with pytest.raises(WorkflowError):
        choose(game, PLAYER, "locked_cockpit_extraction_requires_frame_consent")
    choose(game, PLAYER, "erase_identity_and_table_question")
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"identity": state(game).sheets["2"].identities[0].id},
        text="Actual outside Frame question",
    )
    for viewer in (PLAYER, OTHER, ADMIN):
        answer(game, viewer, "dive_table_answer", text="Actual outside answer")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and not state(game).frame_locks


def test_native_long_table_question_pages_private_owner_and_resumes_after_restart(ledger):
    game, worker, gateway, identity = rolled(ledger)
    choose(game, PLAYER, "erase_identity_and_table_question")
    question = "*" * 1200
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"identity": state(game).sheets["2"].identities[1].id},
        text=question,
    )

    async def run():
        row = next(x for x in game.choices(OTHER) if x["kind"] == "dive_table_answer")
        interaction = current(3, 30801)
        await interaction.response.defer(ephemeral=True)
        await open_dive(interaction, game, row["id"])
        pages = interaction.edit_original_response.call_args.kwargs["view"]
        assert len(pages.pages) > 1 and pages.respond.disabled and "\\*" in pages.text()
        assert not await pages.interaction_check(current(2, 30802))
        while pages.index < len(pages.pages) - 1:
            await pages.next.callback(current(3, 30803 + pages.index))
        responding = current(3, 30810)
        await pages.respond.callback(responding)
        form = responding.edit_original_response.call_args.kwargs["view"]
        form.values.update(text="This original human's actual answer")
        await form.confirm.callback(current(3, 30811))
        assert form.completed

    asyncio.run(run())
    answer(game, PLAYER, "dive_table_answer", text="Actual original Girl answer")
    answer(game, ADMIN, "dive_table_answer", text="Actual facilitator answer")
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_paused_table_response_waits_and_effect_failure_rolls_back_without_reroll(
    ledger, monkeypatch
):
    from girlframe.engine import m3_dive as rules

    game, worker, gateway, identity = rolled(ledger)
    choose(game, PLAYER, "void_and_unmark_all")
    old = state(game)
    asset = next(x for x in old.sheets["2"].assets if not x.void)
    fn = rules.apply

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic effect failure")

    monkeypatch.setattr(rules, "apply", fail)
    with pytest.raises(RuntimeError):
        answer(game, PLAYER, "dive_effect", fields={"asset": asset.id}, text="Actual Void change")
    assert state(game) == old and game.dice.calls == 1
    monkeypatch.setattr(rules, "apply", fn)
    ledger.safety(OTHER, "pause-dive-effect", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        answer(game, PLAYER, "dive_effect", fields={"asset": asset.id}, text="Actual Void change")
    ledger.safety(OTHER, "resume-dive-effect", ledger.status(OTHER)["revision"], pause=False)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_effect")

    def submit(key):
        try:
            return game.respond(
                PLAYER,
                key,
                row["id"],
                row["revision"],
                ChoiceAnswer(fields={"asset": asset.id}, text="Actual Void change"),
            )
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("dive-duplicate-a", "dive-duplicate-b")))
    assert sum(isinstance(x, dict) for x in results) == 1 and game.dice.calls == 1
    assert len([x for x in state(game).facts if x.get("kind") == "dive_effect"]) == 1


def test_table_proposal_cannot_replace_protected_identity_or_smuggle_extra_resources(ledger):
    game, worker, gateway, identity = rolled(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].identities.append(
            IdentityState(id="actual-protected", name="Protected extra", protected=True)
        )
        game.event(c, 1, "actual-protected-identity", "synthetic.state", canon)
    choose(game, PLAYER, "table_replaces_identity")
    with pytest.raises(WorkflowError, match="unprotected"):
        answer(
            game,
            ADMIN,
            "dive_effect",
            fields={"identity": "actual-protected"},
            text="Cannot replace this",
        )
    with pytest.raises(WorkflowError):
        answer(
            game,
            ADMIN,
            "dive_effect",
            fields={"identity": state(game).sheets["2"].identities[0].id, "asset": "frame:0"},
            text="Extra resource",
        )
    assert state(game).sheets["2"].identities[-1].name == "Protected extra"


def threshold_source(
    ledger,
    girl="ALPHA",
    *,
    family="frame",
    placement="inside_frame",
    girl_cell=(0, 0),
    frame_cell=(0, 0),
):
    """Real source fixture reusable by the Void service/interaction tests."""
    from test_m2_game import Gateway
    from test_mission_service import service

    from girlframe.delivery.m2_worker import GameWorker

    _, game = service(ledger, girl=girl)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"plays"}}
            )
        }
    )
    game.dice.faces = (4, 5)
    worker, gateway = GameWorker(game), Gateway()
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        frame = resolve(
            canon, actor, profiles(c, ledger.campaign_id), require_current_profile=False
        ).frame_instance
        if placement is not None:
            canon = physical.initial(
                canon,
                profiles(c, ledger.campaign_id),
                InitialPlacement(
                    actor=actor,
                    frame_instance=frame,
                    girl_cell=girl_cell,
                    frame_cell=frame_cell,
                    mode=placement,
                    account="Actual cockpit facts",
                    facts_confirmed=True,
                ),
                "actual-void-vessel",
                "actual-void-proposal",
                "actual-void-review",
            )
        frames = [x for x in canon.sheets["2"].assets if x.family == family]
        for asset in frames[:-1]:
            asset.void = True
        target = frames[-1].id
        game.event(c, 1, "prior-actual-frame-void", "synthetic.state", canon)
    identity = game.begin(
        PLAYER,
        "actual-final-" + family + "-corruption",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep",
            context="Actual final " + family + " corruption",
            trigger_confirmed=True,
            heat=0,
            piloting=placement == "piloting",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, PLAYER, "void_and_unmark_all")
    answer(
        game, PLAYER, "dive_effect", fields={"asset": target}, text="Actual final Void alteration"
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_void_threshold")
    work_id = json.loads(row["body_json"])["work_id"]
    return game, worker, gateway, identity, work_id


def test_actual_void_threshold_holds_root_until_real_escape_then_preserves_original_source_proof(
    ledger,
):
    from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon
    from girlframe.services.m3_void import VoidService, source

    game, worker, gateway, identity, work_id = threshold_source(ledger)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_void_threshold")
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    with pytest.raises(WorkflowError, match="not an acknowledgment"):
        game.respond(
            PLAYER, "cannot-ack-threshold", row["id"], row["revision"], ChoiceAnswer(flag=True)
        )
    with ledger.engine.connect() as c:
        work, body, original = source(game, c, work_id)
        first = dict(
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.campaign_id == ledger.campaign_id,
                    t.m3["m3_required_work"].c.id == work_id,
                    t.m3["m3_required_work"].c.revision == 1,
                )
            )
            .mappings()
            .one()
        )
        prove_void_source(game, c, first, body, original)
        with pytest.raises(WorkflowError, match="SOURCE_DIVE_VOID_MISSING"):
            prove_void_source(game, c, first, body | {"source_choice": "invented"}, original)
        assert game.lock(c, 900)["state"] == "held"
    svc = VoidService(ledger)
    data = svc.get(PLAYER, work_id)
    assert data["stage"] == "enclosed"
    asset = next(x["id"] for x in data["assets"] if x["family"] == "girl" and not x["damaged"])
    svc.respond(
        PLAYER,
        "owned-real-escape-choice",
        work_id,
        data["revision"],
        data["game_revision"],
        data["expected"],
        "choose_escape",
        dict(asset=asset, account="Actual chosen bodily cost"),
    )
    data = svc.get(ADMIN, work_id)
    frames = [x for x in state(game).sheets["2"].assets if x.family == "frame"]
    gorgon = Gorgon(
        id="actual-abandoned-gorgon",
        name="Actual abandoned Frame",
        cell=(0, 0),
        gorgon_class="aggressive",
        types=("sentinel",),
        assets=tuple(
            Asset(
                id=x.id,
                name=x.name,
                description=x.description,
                family="gorgon",
                void=x.void,
                damaged=x.damaged,
            )
            for x in frames
        ),
        core_plan=CorePlan(assets=(frames[0].id,), weakness="Actual known Core weakness"),
    )
    result = svc.respond(
        ADMIN,
        "actual-frame-escape-confirmation",
        work_id,
        data["revision"],
        data["game_revision"],
        data["expected"],
        "escape",
        dict(
            gorgon=gorgon.model_dump(mode="json"), account="Actual escape damages chosen Girl Asset"
        ),
    )
    assert result["stage"] == "escaped"
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset).damaged
    assert state(game).sheets["2"].frame_scrapped and state(game).world.gorgons[0].id == gorgon.id
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_mockingbird_sitting_inside_own_frame_still_opens_actual_resistance_threshold(ledger):
    from girlframe.services.m3_void import VoidService

    game, worker, gateway, identity, work_id = threshold_source(ledger, girl="MOCKINGBIRD")
    assert state(game).placements[0].mode == "inside_frame"
    assert not game.inspect(PLAYER, identity)["state"] == "complete"
    data = VoidService(ledger).get(PLAYER, work_id)
    assert data["stage"] == "resist_pending" and data["threshold"]["family"] == "frame"


def test_real_cast_copresence_proves_npc_target_and_one_human_with_two_roles_counts_once(ledger):
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService

    game, worker, gateway = ready(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"world"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(
            board=Board(minimum=(-10, -10), maximum=(10, 10)),
            locations=(),
            npcs=(
                Npc(
                    id="actually-cast-npc",
                    name="Actual cast NPC",
                    cell=(5, 5),
                    jobs=("guard",),
                    detail="Actual",
                    controller=1,
                ),
            ),
        )
        game.event(c, 1, "actual-cast-context", "synthetic.state", canon)
    casts = CastService(ActorService(MissionService(ledger)))
    view = casts.view(ADMIN, 900)
    casts.change(
        ADMIN,
        "actual-npc-cast-join",
        900,
        view["game_revision"],
        view["cast_revision"],
        "join",
        ActorRef(kind="npc", entity="actually-cast-npc"),
    )
    identity = game.begin(
        PLAYER,
        "actual-source-cast-dive",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep", heat=0, context="Actual cast copresence", trigger_confirmed=True
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    with ledger.engine.connect() as c:
        action = game.action(c, identity)
        assert action["data"]["dive"]["table"] == [1, 2, 3]
    choose(game, PLAYER, "nearby_npcs_gain_void")
    answer(game, ADMIN, "dive_effect", fields={"actually-cast-npc": "abstract"})
    canon = state(game)
    assert canon.world.npcs[0].tags[0].label == "Void of the abstract"
    assert not canon.placements and game.inspect(PLAYER, identity)["state"] == "complete"


def test_no_unknown_or_empty_npc_targets_and_same_account_replacement_cannot_answer_original_table(
    ledger,
):
    game, worker, gateway, identity = rolled(ledger)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_select")
    assert "nearby_npcs_gain_void" not in game.decision(PLAYER, row["id"])["dive"]["options"]
    with pytest.raises(WorkflowError):
        choose(game, PLAYER, "nearby_npcs_gain_void")
    choose(game, PLAYER, "erase_identity_and_table_question")
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"identity": state(game).sheets["2"].identities[0].id},
        text="Actual original table question",
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].character_id = "replacement-cid-same-account"
        game.event(c, 1, "actual-table-character-replacement", "synthetic.state", canon)
    with pytest.raises(WorkflowError):
        answer(
            game,
            OTHER,
            "dive_table_answer",
            text="A different original character cannot supply this",
        )
    assert game.inspect(PLAYER, identity)["state"] != "complete"


def test_dive_commits_owned_identity_heat_once_then_uses_actual_shared_tag_window(ledger):
    from girlframe.engine.m2 import TagState

    game, worker, gateway = ready(ledger, (2, 3))
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].tags.append(
            TagState(
                id="actual-relevant-tag", label="Actual relevant Tag", giver=3, observers=(1, 2, 3)
            )
        )
        game.event(c, 1, "actual-tag-before-dive", "synthetic.state", canon)
    actual = state(game).sheets["2"]
    identity = game.begin(
        PLAYER,
        "actual-heat-tag-dive",
        900,
        actual.revision,
        PlayInput(
            play="dive_deep",
            identity=actual.identities[0].id,
            gain=2,
            heat=2,
            context="Actual linked danger",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert state(game).sheets["2"].heat == 0 and state(game).sheets["2"].identities[0].marked
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("actual-relevant-tag",),
        number=1,
        text="Actually relevant to link communion",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    inspect = game.inspect(PLAYER, identity)
    decision = game.decision(
        PLAYER, next(x["id"] for x in game.choices(PLAYER) if x["kind"] == "dive_select")
    )
    assert inspect["receipt"]["pre_total"] == 7 and decision["result"]["total"] == 9
    assert decision["result"]["tier"] == "mid"
    assert any(x["kind"] == "dive_select" for x in game.choices(PLAYER))
    assert state(game).sheets["2"].tags[-1].marked and game.dice.calls == 1
