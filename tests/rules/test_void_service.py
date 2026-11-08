"""Real owned Dive source → private native transformation → actual new original-person body."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_dive import threshold_source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_void import open_void
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_void_state import RebirthChoice
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_void import VoidService
from girlframe.services.onboarding import WorkflowError


def ready(store):
    game, worker, gateway, root, work = threshold_source(store)
    return VoidService(store), game, worker, gateway, root, work


def respond(svc, work, operation, data, *, viewer=PLAYER, key=None, view=None):
    view = view or svc.get(viewer, work)
    return svc.respond(
        viewer,
        key or str(uuid4()),
        work,
        view["revision"],
        view["game_revision"],
        view["expected"],
        operation,
        data,
    )


def five_no(svc, work):
    data = svc.get(PLAYER, work)
    respond(
        svc,
        work,
        "begin",
        dict(identity=data["identities"][0]["id"], account="PRIVATE_ACTUAL_ENTRY"),
    )
    for _ in range(5):
        respond(
            svc,
            work,
            "answer",
            dict(answer=False, honest=True, account="PRIVATE_ACTUAL_HONEST_ANSWER"),
        )
    assert svc.get(PLAYER, work)["stage"] == "rebirth"


def test_real_source_native_honest_questions_rebirth_saved_resources_and_exact_actual_new_body(
    ledger,
):
    svc, game, worker, gateway, root, work = ready(ledger)
    original = state(game).sheets["2"]
    original_vessel = state(game).placements[0].vessel_id

    async def begin():
        interaction = current(2, 81101)
        await interaction.response.defer(ephemeral=True)
        await open_void(interaction, svc, work, operation="begin")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].options == tuple((x.id, x.name) for x in original.identities)
        form.values.update(identity=(original.identities[0].id,), account="PRIVATE_ACTUAL_ENTRY")
        await form.confirm.callback(current(2, 81102))
        assert form.completed

    asyncio.run(begin())
    for number in range(5):

        async def answer(number=number):
            interaction = current(2, 81200 + number * 2)
            await interaction.response.defer(ephemeral=True)
            await open_void(interaction, svc, work)
            form = interaction.edit_original_response.call_args.kwargs["view"]
            assert {x[0] for x in form.fields[0].options} == {"yes", "no"}
            form.values.update(answer=("no",), honest=("honest",))
            await form.confirm.callback(current(2, 81201 + number * 2))
            assert form.completed

        asyncio.run(answer())
    data = svc.get(PLAYER, work)
    choice = data["rebirth_choice"] | dict(
        retained_identities=[original.identities[1].id],
        new_identities=["PRIVATE_NEW_SELF"],
        account="PRIVATE_ACTUAL_REBIRTH",
    )
    respond(svc, work, "save_rebirth", dict(choice=choice, account="PRIVATE_SAVE"))
    assert svc.get(PLAYER, work)["rebirth_choice"] == choice
    data = svc.get(PLAYER, work)
    result = respond(
        svc,
        work,
        "rebirth",
        dict(choice=choice, account="PRIVATE_ACTUAL_REBIRTH"),
        key="actual-final-rebirth",
        view=data,
    )
    assert (
        respond(
            svc,
            work,
            "rebirth",
            dict(choice=choice, account="PRIVATE_ACTUAL_REBIRTH"),
            key="actual-final-rebirth",
            view=data,
        )
        == result
    )
    canon = state(game)
    assert "2" not in canon.sheets and 2 not in canon.order
    assert canon.career_archives[-1].actor.incarnation == original.character_id
    harpy = canon.harpy_states[0]
    assert harpy.old_body_vessel == original_vessel and harpy.body_vessel != original_vessel
    assert [x.name for x in harpy.identities] == [
        original.identities[1].name,
        "PRIVATE_NEW_SELF",
        "Free",
    ]
    assert (
        harpy.controller == 2
        and harpy.heat == original.heat
        and harpy.permissions == original.permissions
    )
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert svc.get(PLAYER, work)["stage"] == "converted"
    with ledger.engine.connect() as c:
        assert (
            resolve(
                canon,
                canon.void_thresholds[-1].resulting_actor,
                profiles(c, ledger.campaign_id),
            ).vessel_id
            == harpy.body_vessel
        )
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    tick(worker, gateway, 6)
    assert "PRIVATE_" not in json.dumps(gateway.messages)
    with ledger.transaction() as c:
        c.execute(t.m2["m2_state"].delete())
    assert game.rebuild() > 0 and state(game) == canon


def test_private_authority_pause_stale_and_rollback_do_not_answer_or_move_original_body(ledger):
    svc, game, *_, work = ready(ledger)
    data = svc.get(PLAYER, work)
    assert "sheet_json" not in str(svc.get(ADMIN, work))
    with pytest.raises(WorkflowError):
        svc.get(OTHER, work)
    choice = dict(identity=data["identities"][0]["id"], account="PRIVATE_ACTUAL_ENTRY")
    before = state(game)
    with pytest.raises(WorkflowError, match="original Girl"):
        respond(svc, work, "begin", choice, viewer=ADMIN, view=data)
    ledger.safety(OTHER, "pause-void", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        respond(svc, work, "begin", choice, view=data)
    ledger.safety(OTHER, "resume-void", ledger.status(OTHER)["revision"], pause=False)
    with pytest.raises(WorkflowError, match="STALE_VOID"):
        respond(svc, work, "begin", choice, view=data | dict(expected="0" * 64))
    assert state(game) == before


def test_parallel_real_same_response_consumes_one_question_and_wrong_honesty_never_defaults(ledger):
    svc, game, *_, work = ready(ledger)
    data = svc.get(PLAYER, work)
    respond(svc, work, "begin", dict(identity=data["identities"][0]["id"], account="Actual entry"))
    data = svc.get(PLAYER, work)
    with pytest.raises(WorkflowError, match="honestly answer"):
        respond(svc, work, "answer", dict(answer=False, account="No forged honesty"), view=data)
    command = dict(answer=False, honest=True, account="My actual honest no")

    def submit(_):
        return respond(svc, work, "answer", command, key="same-actual-answer", view=data)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, range(2)))
    assert outcomes[0] == outcomes[1]
    assert len(state(game).void_thresholds[-1].answers) == 1


def test_saved_rebirth_cannot_repair_original_assets_or_retain_forged_resources(ledger):
    svc, game, *_, work = ready(ledger)
    five_no(svc, work)
    data = svc.get(PLAYER, work)
    choice = RebirthChoice.model_validate_json(json.dumps(data["rebirth_choice"]))
    bad = choice.model_copy(update={"retained_tags": ("invented-tag",)})
    before = state(game)
    with pytest.raises(WorkflowError, match="actual original owned"):
        respond(
            svc,
            work,
            "rebirth",
            dict(choice=bad.model_dump(mode="json"), account="No forged Tag"),
            view=data,
        )
    assert state(game) == before


def test_unplaced_source_requires_original_owner_proposal_and_handler_review_without_travel(
    ledger, monkeypatch
):
    from girlframe.engine import m3_physical as physical

    with monkeypatch.context() as patch:
        patch.setattr(physical, "initial", lambda original, *args, **kwargs: original)
        svc, game, *_, work = ready(ledger)
    assert svc.get(PLAYER, work)["stage"] == "physical_review"
    before = state(game)
    respond(
        svc,
        work,
        "propose_occupancy",
        dict(mode="inside_frame", account="PRIVATE_ORIGINAL_OCCUPANCY"),
    )
    assert not state(game).placements
    with pytest.raises(WorkflowError):
        respond(svc, work, "confirm_occupancy", dict(account="Cannot selfapprove"))
    data = svc.get(ADMIN, work)
    respond(
        svc,
        work,
        "confirm_occupancy",
        dict(account="PRIVATE_ACTUAL_INDEPENDENT_CONFIRMATION"),
        viewer=ADMIN,
        view=data,
    )
    after = state(game)
    body = after.placements[0]
    assert body.girl_cell is body.frame_cell is None
    assert body.vessel_id == "vessel:" + body.actor.token
    assert body.proposed_event != body.source_event
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == body.proposed_event))
            == "2"
        )
        assert (
            c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == body.source_event))
            == "1"
        )
    assert after.sheets == before.sheets and svc.get(PLAYER, work)["stage"] == "enclosed"


def test_mutated_saved_escape_choice_cannot_forge_original_owner_cost(ledger):
    svc, game, *_, work = ready(ledger)
    data = svc.get(PLAYER, work)
    asset = next(x["id"] for x in data["assets"] if x["family"] == "girl" and not x["damaged"])
    respond(svc, work, "choose_escape", dict(asset=asset, account="Actual selected cost"))
    with ledger.transaction() as c:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.id == work)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        bad = json.loads(row["body_json"]) | dict(damage_asset="forged-different-choice")
        c.execute(
            table.insert().values(
                **{k: v for k, v in row.items() if k not in ("revision", "body_json")},
                revision=row["revision"] + 1,
                body_json=json.dumps(bad),
            )
        )
    with pytest.raises(WorkflowError, match="SOURCE_VOID_MISSING"):
        svc.get(ADMIN, work)


def test_actual_entry_into_already_corrupt_frame_creates_source_bound_real_resistance_work(ledger):
    from test_cockpit_service import command, placed

    from girlframe.services.m3_void import source

    physical, game = placed(ledger)
    data, choice = command(physical)
    physical.operate(PLAYER, "actual-leave-first", data["game_revision"], choice)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = state(game)
        for asset in canon.sheets["2"].assets:
            if asset.family == "frame":
                asset.void = True
        game.event(c, 1, "actual-old-frame-corruption", "synthetic.state", canon)
    data, choice = command(physical, "sit")
    result = physical.operate(PLAYER, "actual-corrupt-frame-entry", data["game_revision"], choice)
    assert result["void_works"] and state(game).placements[0].mode == "inside_frame"
    svc = VoidService(ledger)
    work = result["void_works"][0]
    assert svc.get(PLAYER, work)["stage"] == "resist_pending"
    with ledger.engine.connect() as c:
        _, body, _ = source(game, c, work)
        assert body["reason"] == "physical_entry" and body["source_action"] is None
        assert not game.pending_actions(c)


@pytest.mark.parametrize("placement,frame_cell", [("outside_frame", (2, 0)), (None, None)])
def test_real_allure_actual_arrival_requires_owner_proposal_and_independent_handler_evidence(
    ledger, placement, frame_cell
):
    game, *_, work = threshold_source(
        ledger, family="girl", placement=placement, frame_cell=frame_cell
    )
    svc = VoidService(ledger)
    if placement is None:
        respond(
            svc,
            work,
            "propose_occupancy",
            dict(mode="outside_frame", account="PRIVATE_ORIGINAL_OUTSIDE_FACTS"),
        )
        respond(
            svc,
            work,
            "confirm_occupancy",
            dict(account="PRIVATE_INDEPENDENT_OUTSIDE_CONFIRMATION"),
            viewer=ADMIN,
        )
    data = svc.get(PLAYER, work)
    assert data["stage"] == "allured"
    before = state(game)
    body = before.placements[0]
    selected = data["identities"][0]["id"]
    with pytest.raises(WorkflowError, match="same known cell"):
        respond(svc, work, "begin", dict(identity=selected, account="Cannot assume arrival"))
    respond(
        svc,
        work,
        "propose_approach",
        dict(identity=selected, account="PRIVATE_ACTUAL_COMPLETED_APPROACH"),
    )
    assert state(game).placements == before.placements
    with pytest.raises(WorkflowError):
        respond(svc, work, "confirm_approach", dict(account="Cannot selfconfirm actual travel"))
    respond(
        svc,
        work,
        "confirm_approach",
        dict(account="PRIVATE_ACTUAL_INDEPENDENT_ARRIVAL"),
        viewer=ADMIN,
    )
    after = state(game)
    actual = after.placements[0]
    assert actual.vessel_id == body.vessel_id and actual.actor == body.actor
    assert actual.frame_cell == actual.girl_cell == frame_cell
    assert actual.mode == "inside_frame"
    assert after.sheets["2"].assets == before.sheets["2"].assets
    assert svc.get(PLAYER, work)["stage"] == "questions"
    assert next(x for x in after.sheets["2"].identities if x.id == selected).name == "Free"


def test_actual_arrival_confirmation_rejects_changed_facts_until_owner_reproposes(ledger):
    game, *_, work = threshold_source(
        ledger, family="girl", placement="outside_frame", frame_cell=(2, 0)
    )
    svc = VoidService(ledger)
    chosen = svc.get(PLAYER, work)["identities"][0]["id"]
    proposal = dict(identity=chosen, account="Actual completed approach")
    respond(svc, work, "propose_approach", proposal)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].heat += 1
        game.event(c, 3, "actual-intervening-source-state", "synthetic.state", canon)
    with pytest.raises(WorkflowError, match="STALE_APPROACH"):
        respond(
            svc, work, "confirm_approach", dict(account="Stale source confirmation"), viewer=ADMIN
        )
    respond(svc, work, "propose_approach", proposal)
    respond(
        svc,
        work,
        "confirm_approach",
        dict(account="Actual fresh source confirmation"),
        viewer=ADMIN,
    )
    assert state(game).placements[0].girl_cell == (2, 0)


def test_real_shared_actor_stops_allure_then_only_actual_guardian_releases_and_entry_retriggers(
    ledger,
):
    from test_cockpit_service import command

    from girlframe.services.m3_physical import PhysicalService

    game, worker, gateway, root, work = threshold_source(
        ledger, family="girl", placement="outside_frame"
    )
    svc = VoidService(ledger)
    data = svc.get(PLAYER, work)
    guardian = next(x["ref"] for x in data["guardians"] if x["ref"]["entity"] == "3")
    assert state(game).placements[0].girl_cell == (0, 0)
    respond(svc, work, "protect", dict(guardian=guardian, account="PRIVATE_ACTUAL_HELP_REQUEST"))
    with pytest.raises(WorkflowError):
        respond(svc, work, "accept_protection", dict(account="Cannot forge another body's help"))
    respond(
        svc, work, "accept_protection", dict(account="PRIVATE_ACTUAL_PHYSICAL_HOLD"), viewer=OTHER
    )
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert state(game).placements[0].custody.model_dump(mode="json") == guardian
    assert svc.get(PLAYER, work)["protection_active"]
    assert any(x["id"] == work for x in svc.tasks(OTHER))
    with pytest.raises(WorkflowError):
        respond(svc, work, "release_protection", dict(account="Cannot forge her release"))
    before = state(game)

    async def release():
        interaction = current(3, 81801)
        await interaction.response.defer(ephemeral=True)
        await open_void(interaction, svc, work)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(confirm=("release",), account="PRIVATE_ACTUAL_RELEASE")
        await form.confirm.callback(current(3, 81802))
        assert form.completed

    asyncio.run(release())
    after = state(game)
    assert after.placements[0].custody is None
    assert after.placements[0].girl_cell == before.placements[0].girl_cell
    assert after.sheets == before.sheets
    assert not svc.get(PLAYER, work)["protection_active"]
    assert not any(x["id"] == work for x in svc.tasks(OTHER))
    tick(worker, gateway, 6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    physical = PhysicalService(ledger)
    data, entry = command(physical, "sit")
    result = physical.operate(
        PLAYER, "actual-post-release-frame-entry", data["game_revision"], entry
    )
    assert result["void_works"]
    assert svc.get(PLAYER, result["void_works"][0])["stage"] == "questions"
