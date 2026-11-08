"""Owned three-chooser setup completes real borrowed Higher Standard runtime."""

import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, start, state, tick
from test_medical import awake, selection
from test_mission_service import launched
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_standards import open_setup, open_standards
from girlframe.engine.creation_details import StandardChoice
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, PlaySwap, has_rule, keep_automatic
from girlframe.engine.m3_medical import Exchange
from girlframe.engine.m3_standards import RULE
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_reactions import ReactionService
from girlframe.services.m3_standards import StandardsService
from girlframe.services.onboarding import WorkflowError


def pending(store):
    medical, game, identity = awake(store)
    selected = Exchange(removed=selection().removed, acquired=RULE)
    data = medical.get(PLAYER, identity)
    result = medical.exchange(
        PLAYER,
        "request-higher-standard",
        identity,
        data["revision"],
        data["game_revision"],
        selected,
    )
    assert result["stage"] == "standards_setup"
    assert not has_rule(state(game).sheets["2"], RULE, "PRINCESS")
    standards = StandardsService(store)
    preview = standards.preview(PLAYER, identity)
    from girlframe.engine.m3_actor_state import ActorRef

    peer = ActorRef.model_validate(
        next(x["ref"] for x in preview["peers"] if x["ref"]["entity"] == "3")
    )
    result = standards.start(
        PLAYER,
        "original-own-standard",
        preview["game_revision"],
        peer,
        StandardChoice(slot=0),
        identity,
    )
    return medical, standards, game, identity, result["id"], selected


def compile_three(standards, identity):
    for chooser, slot in ((OTHER, 1), (ADMIN, 2)):
        data = standards.get(chooser, identity)
        standards.choose(
            chooser,
            "owned-standard-" + str(chooser.user_id),
            identity,
            data["revision"],
            StandardChoice(slot=slot),
        )
    data = standards.get(PLAYER, identity)
    return standards.finalize(
        PLAYER, "compile-actual-three", identity, data["revision"], data["game_revision"]
    )


def test_real_medical_three_original_choices_activate_borrowed_mission_bonus(ledger):
    medical, standards, game, identity, setup, selected = pending(ledger)
    assert standards.get(OTHER, setup)["can_choose"]
    with pytest.raises(WorkflowError):
        data = standards.get(PLAYER, setup)
        standards.choose(
            PLAYER, "cannot-answer-peer", setup, data["revision"], StandardChoice(slot=3)
        )
    compile_three(standards, setup)
    assert not state(game).sheets["2"].girl_runtime
    data = medical.get(PLAYER, identity)
    medical.exchange(
        PLAYER,
        "activate-actual-borrowed-rule",
        identity,
        data["revision"],
        data["game_revision"],
        selected,
    )
    sheet = state(game).sheets["2"]
    assert sheet.girl == "MOCKINGBIRD" and has_rule(sheet, RULE, "PRINCESS")
    assert {x.role for x in sheet.girl_runtime.standards} == {"own", "peer", "handler"}
    with ledger.transaction() as c:
        canon = state(game)
        canon.order = (3, 2)
        game.event(c, 1, "rank-for-borrowed-standard", "synthetic.state", canon)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"playbooks"}}
            )
        }
    )
    missions = MissionService(ledger)
    mid, rev = launched(missions)
    end = missions.end(ADMIN, "end-borrowed-standard", mid, rev, True)
    task = next(x for x in missions.get(ADMIN, mid)["work"] if x["kind"] == "princess_mission_end")
    reactions = ReactionService(missions)
    data = reactions.get(ADMIN, task["id"])
    assert len(data["standards"]) == 3 and sum(x["is_order"] for x in data["standards"]) == 1
    reactions.princess(
        ADMIN,
        "actual-borrowed-standard-review",
        task["id"],
        data["revision"],
        data["game_revision"],
        upheld=True,
        rationale="Actual standards upheld",
    )
    assert state(game).sheets["2"].permissions == 1
    missions.complete(ADMIN, "borrowed-standard-reward-snapshot", mid, end["revision"])
    assert state(game).sheets["2"].permissions == 3


def test_native_standards_forms_each_actual_chooser_and_pending_exchange_resume(ledger):
    medical, standards, game, identity, setup, _ = pending(ledger)

    async def run():
        for uid, slot in ((3, "1"), (1, "2")):
            interaction = current(uid, 28400 + uid)
            await interaction.response.defer(ephemeral=True)
            await open_setup(interaction, StandardsService(ledger), setup)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            assert not await form.interaction_check(current(2))
            form.values.update(standard=(slot,))
            await form.confirm.callback(current(uid, 28410 + uid))
            assert form.completed
        owner = current(2, 28420)
        await owner.response.defer(ephemeral=True)
        await open_standards(owner, StandardsService(ledger), identity)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("yes",))
        await form.confirm.callback(current(2, 28421))
        assert form.completed
        await open_standards(owner, StandardsService(ledger), identity)
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("yes",))
        await form.confirm.callback(current(2, 28422))
        assert form.completed

    asyncio.run(run())
    assert medical.get(PLAYER, identity)["stage"] == "complete"
    assert has_rule(state(game).sheets["2"], RULE, "PRINCESS")


def test_pending_choices_survive_pause_missing_chooser_and_source_cannot_be_replaced(ledger):
    medical, standards, game, identity, setup, selected = pending(ledger)
    ledger.safety(OTHER, "standards-pause", ledger.status(OTHER)["revision"], pause=True)
    data = standards.get(OTHER, setup)
    standards.choose(
        OTHER, "ooc-standard-while-paused", setup, data["revision"], StandardChoice(slot=1)
    )
    assert not standards.get(PLAYER, setup)["can_finalize"]
    assert not state(game).sheets["2"].girl_runtime
    ledger.safety(OTHER, "standards-resume", ledger.status(OTHER)["revision"], pause=False)
    data = standards.get(ADMIN, setup)
    standards.choose(
        ADMIN, "actual-handler-standard", setup, data["revision"], StandardChoice(slot=2)
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].character_id = "different-original-person"
        game.event(c, 1, "actual-peer-replacement", "synthetic.state", canon)
    assert standards.get(PLAYER, setup)["stale"]
    data = medical.get(PLAYER, identity)
    result = medical.exchange(
        PLAYER,
        "no-replacement-consent",
        identity,
        data["revision"],
        data["game_revision"],
        selected,
    )
    assert result["stage"] == "standards_setup"
    assert not has_rule(state(game).sheets["2"], RULE, "PRINCESS")
    data = standards.get(PLAYER, setup)
    standards.withdraw(PLAYER, "withdraw-stale-chooser", setup, data["revision"])
    assert standards.preview(PLAYER, identity)["existing"] is None


def test_actual_post_medical_keep_head_uses_acquired_passive_without_changing_book(ledger):
    medical, game, identity = awake(ledger)
    data = medical.get(PLAYER, identity)
    medical.exchange(
        PLAYER, "acquire-beautiful", identity, data["revision"], data["game_revision"], selection()
    )
    game.dice.faces = (4, 5)
    worker, gateway = GameWorker(game), Gateway()
    action = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual acquired passive")
    assert "sexy" in game.inspect(PLAYER, action)["result"]["positive"]
    assert state(game).sheets["2"].girl == "MOCKINGBIRD"


def test_native_and_acquired_automatic_traits_coexist_and_removed_native_stops(ledger):
    from test_mission_service import service

    _, game = service(ledger, girl="PRINCESS")
    sheet = state(game).sheets["2"]
    sheet.girl_runtime = GirlRuntime(
        swaps=(
            PlaySwap(
                removed_rule=RULE,
                acquired_rule="girl.alpha.itching-for-a-fight",
                source_playbook="ALPHA",
                source_event="synthetic",
            ),
        )
    )
    assert keep_automatic(sheet) == {"sexy", "vicious"}
    assert keep_automatic(sheet.model_dump(mode="json")) == {"sexy", "vicious"}
    assert not has_rule(sheet, RULE, "PRINCESS")
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"] = sheet
        game.event(c, 1, "removed-native-standard", "synthetic.state", canon)
    missions = MissionService(ledger)
    identity, revision = launched(missions)
    result = missions.end(ADMIN, "no-removed-trigger", identity, revision, True)
    assert result["rewards_committed"]
    assert not any(
        x["kind"] == "princess_mission_end" for x in missions.get(ADMIN, identity)["work"]
    )


def test_standards_activation_rolls_back_and_duplicate_final_exchange_applies_once(
    ledger, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    medical, standards, game, identity, setup, selected = pending(ledger)
    compile_three(standards, setup)
    before = state(game)
    data = medical.get(PLAYER, identity)
    original = medical._save

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic failure after actual state event")

    monkeypatch.setattr(medical, "_save", fail)
    with pytest.raises(RuntimeError):
        medical.exchange(
            PLAYER,
            "failed-three-standard-exchange",
            identity,
            data["revision"],
            data["game_revision"],
            selected,
        )
    assert state(game) == before
    monkeypatch.setattr(medical, "_save", original)

    def submit(key):
        try:
            return medical.exchange(
                PLAYER, key, identity, data["revision"], data["game_revision"], selected
            )
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("owned-atomic-exchange-a", "owned-atomic-exchange-b")))
    assert sum(isinstance(x, dict) for x in results) == 1
    assert len(state(game).sheets["2"].girl_runtime.swaps) == 1
    assert len(state(game).sheets["2"].girl_runtime.standards) == 3


def test_new_native_baseline_uses_actual_three_chooser_setup_without_legacy_draft_class(ledger):
    from test_mission_service import service

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_girl_runtime_state import change_playbook_runtime

    _, game = service(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"subsystems": ledger.policy.m3_approval.subsystems | {"plays"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"], _ = change_playbook_runtime(
            canon.sheets["2"], "PRINCESS", "synthetic-book-change"
        )
        game.event(c, 1, "actual-new-native-baseline", "synthetic.state", canon)
    standards = StandardsService(ledger)
    data = standards.preview(PLAYER)
    peer = ActorRef.model_validate(
        next(x["ref"] for x in data["peers"] if x["ref"]["entity"] == "3")
    )
    setup = standards.start(
        PLAYER, "new-native-own-standard", data["game_revision"], peer, StandardChoice(slot=4)
    )["id"]
    compile_three(standards, setup)
    sheet = state(game).sheets["2"]
    assert sheet.review.creation.girl_playbook == "MOCKINGBIRD" and sheet.girl == "PRINCESS"
    assert len(sheet.girl_runtime.standards) == 3 and has_rule(sheet, RULE, "PRINCESS")


def test_borrowed_hound_actual_status_modifier_and_punishment_reset(ledger):
    from girlframe.engine.m3_punishments import Details, apply

    medical, game, identity = awake(ledger)
    selected = Exchange(
        removed=selection().removed, acquired="girl.alpha.nothing-more-than-a-hound"
    )
    data = medical.get(PLAYER, identity)
    medical.exchange(
        PLAYER, "borrow-actual-hound", identity, data["revision"], data["game_revision"], selected
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.order = (3, 2)
        game.event(c, 1, "actual-dog-rank", "synthetic.state", canon)
    game.dice.faces = (4, 5)
    worker, gateway = GameWorker(game), Gateway()
    action = start(game)
    tick(worker, gateway, 3)
    answer(game, PLAYER, "tag_window", options=("pass",), fields={"status": "1"})
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    assert state(game).sheets["2"].status_marked
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual borrowed Hound Status")
    assert game.inspect(PLAYER, action)["state"] == "complete"
    before = state(game)
    target = tuple(x.id for x in before.sheets["2"].identities[:2])
    after = apply(
        before,
        2,
        1,
        Details(kind="sedation", identities=target),
        entity_id="synthetic-punishment",
        off_duty=False,
    ).state
    assert not after.sheets["2"].status_marked
    assert before.sheets["2"].status_marked and before.sheets["2"].girl == "MOCKINGBIRD"


@pytest.mark.parametrize(
    "girl,removed,acquired,expected",
    [
        ("PRINCESS", RULE, "girl.alpha.itching-for-a-fight", {"sexy", "vicious"}),
        (
            "PRINCESS",
            "girl.princess.objectively-beautiful",
            "girl.oldgen.elder-bitch",
            {"experienced"},
        ),
    ],
)
def test_actual_keep_runtime_and_native_ui_respect_borrowed_and_removed_rules(
    ledger, girl, removed, acquired, expected
):
    from test_m2_game import setup_game

    from girlframe.discord_adapter.m2_ui import choice_fields

    game, worker, gateway, _ = setup_game(ledger, girl=girl, faces=(4, 5))
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].girl_runtime = GirlRuntime(
            swaps=(
                PlaySwap(
                    removed_rule=removed,
                    acquired_rule=acquired,
                    source_playbook="ALPHA" if "alpha" in acquired else "OLDGEN",
                    source_event="synthetic",
                ),
            )
        )
        game.event(c, 1, "synthetic-owned-swap", "synthetic.state", canon)
    action = start(game)
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")
    fields = choice_fields(game.decision(PLAYER, row["id"]))
    negatives = next(x for x in fields if x.key == "denied")
    assert ("sexy" not in dict(negatives.options)) == ("sexy" in expected)
    assert ("vicious" not in dict(negatives.options)) == ("vicious" in expected)
    assert any(x.key == "flag" for x in fields) == ("experienced" in expected)
    answer(
        game,
        PLAYER,
        "actor_keep",
        options=("tough", "in_control"),
        denied=("desperate",),
        flag="experienced" in expected,
    )
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual owned passive traits")
    positives = set(game.inspect(PLAYER, action)["result"]["positive"])
    assert expected <= positives
    assert ("sexy" in positives) == ("sexy" in expected)
    assert ("vicious" in positives) == ("vicious" in expected)


def test_removed_mockingbird_risk_factor_stops_its_corruption_exception(ledger):
    from test_mission_service import service

    from girlframe.engine.m3_core import corrupt

    _, game = service(ledger)
    sheet = state(game).sheets["2"]
    sheet.girl_runtime = GirlRuntime(
        swaps=(
            PlaySwap(
                removed_rule="girl.mockingbird.risk-factor",
                acquired_rule="girl.princess.objectively-beautiful",
                source_playbook="PRINCESS",
                source_event="synthetic",
            ),
        )
    )
    girls = [x for x in sheet.assets if x.family == "girl"]
    for asset in girls[:-1]:
        asset.void = True
    girls[-1].void = False
    result = corrupt(sheet, girls[-1].id, "Actual Void alteration", piloting=False)
    assert any(x.kind == "girl_void_threshold" for x in result.followups)
    assert not any(x.kind == "mockingbird_resist" for x in result.followups)


def test_forged_appended_standard_choice_cannot_replace_original_human_response(ledger):
    import json

    from girlframe.database import tables as t

    medical, standards, game, identity, setup, selected = pending(ledger)
    data = standards.get(OTHER, setup)
    standards.choose(
        OTHER, "source-owned-peer-standard", setup, data["revision"], StandardChoice(slot=1)
    )
    with ledger.transaction() as c:
        row = standards._row(c, setup)
        body = json.loads(row["body_json"])
        body["choices"]["peer"]["choice"] = StandardChoice(slot=8).model_dump(mode="json")
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{k: v for k, v in row.items() if k not in ("revision", "body_json")},
                revision=row["revision"] + 1,
                body_json=json.dumps(body),
            )
        )
    with pytest.raises(WorkflowError, match="SOURCE_STANDARDS_MISSING"):
        standards.get(PLAYER, setup)
    assert not has_rule(state(game).sheets["2"], RULE, "PRINCESS")
