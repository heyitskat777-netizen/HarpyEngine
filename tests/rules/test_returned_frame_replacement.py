"""A returned original resumes an unfulfilled Frame loss through new real work."""

import json
from uuid import uuid4

import sqlalchemy as sa
from test_defeat_replacement import destroyed
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_replacement_service import accept, propose, quote
from test_strain import facts
from test_strain_service import D6
from test_void_frame_replacement import escaped
from test_world import gorgon, initial

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_strain_effects import Choice, TagChoice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.m3_careers import CareerService, end_in_transaction, synchronize_end
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_replacement import DEFEAT_ROOT, ReplacementService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService


def end_original(store, game):
    source, identity = str(uuid4()), str(uuid4())
    with store.transaction() as c:
        canon = state(game)
        changed = end_in_transaction(
            c,
            game,
            canon,
            current_ref(canon, 2),
            reason="imprisonment",
            source_event=source,
            account="Actual original is imprisoned, with her existing Frame loss",
            archive_id=identity,
        )
        game.event(
            c, 1, str(uuid4()), "synthetic.actual_original_imprisonment", changed, event_id=source
        )
        synchronize_end(c, game, changed.career_archives[-1])
    return identity


def return_original(store, game, archive):
    service = CareerService(store)
    offered = service.offer_return(
        ADMIN, str(uuid4()), archive, state(game).revision, 0, "The original is actually released"
    )
    service.answer_return(
        PLAYER,
        str(uuid4()),
        offered["id"],
        state(game).revision,
        accept=True,
        account="The original owner chooses to return",
    )


def rows(store):
    with store.engine.connect() as c:
        table = t.m3["m3_required_work"]
        return list(
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == store.campaign_id)
                .order_by(table.c.revision)
            ).mappings()
        )


def prepare_period(store, game, periods, identity):

    strain = StrainService(periods, dice=D6(1))
    current = state(game)
    count = sum(any(a.void for a in s.assets) for s in current.sheets.values())
    frames = [[a for a in sheet.assets if a.family == "frame"] for sheet in current.sheets.values()]
    repair_trigger = any(a and all(x.damaged for x in a) for a in frames) or (
        bool(frames) and all(any(x.damaged for x in a) for a in frames)
    )
    strain.prepare(
        ADMIN,
        str(uuid4()),
        identity,
        periods.get(ADMIN, identity)["revision"],
        current.revision,
        facts(
            at_least_half_have_void=2 * count >= len(current.order),
            no_girl_void=count == 0,
            frame_full_or_all_frames_some_repairs=repair_trigger,
        ),
    )
    effects = EffectService(strain)
    for track, face, column, choice in (
        (
            "void",
            1,
            1,
            Choice(
                rule_id="strain.void.low.1.1",
                account="Actual edge threat",
                gorgon=gorgon("directed", "return-threat", (10, 0)),
            ),
        ),
        (
            "rebellion",
            1,
            1,
            Choice(
                rule_id="strain.rebellion.low.1.1",
                account="Actual group",
                target="city0",
                faction=Faction(
                    id="return-rebels",
                    name="Rebels",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Actual dissent",
                ),
            ),
        ),
        (
            "budget",
            2 if repair_trigger else 4,
            2,
            Choice(
                rule_id="strain.budget.high.2.2" if repair_trigger else "strain.budget.low.4.2",
                account="Actual high-Budget flaws" if repair_trigger else "Actual reduced repairs",
                tags=tuple(
                    TagChoice(owner=uid, label="Actual recorded shortage flaw")
                    for uid in (*current.order, current.handler)
                )
                if repair_trigger
                else (),
            ),
        ),
    ):
        request = next(x for x in state(game).strain.requests if x.track == track)
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)
    return CycleService(periods)


def finish_survivor_period(store, game, periods, identity):
    from test_career_off_duty import roll_survivor
    from test_off_duty_cycle import activate, call, movement

    cycle = prepare_period(store, game, periods, identity)
    activate(cycle, game, identity)
    roll_survivor(cycle, game, identity)
    call(cycle, game, OTHER, identity, "scene", None, (), "")
    call(cycle, game, OTHER, identity, "recover", RecoveryChoice())
    call(
        cycle, game, ADMIN, identity, "handler_scene", "routine", (1, 3), "Actual survivor routine"
    )
    call(cycle, game, ADMIN, identity, "acknowledge", None)
    call(cycle, game, OTHER, identity, "acknowledge", None)
    call(cycle, game, ADMIN, identity, "review_status", (3,), "Actual surviving roster")
    assert call(cycle, game, ADMIN, identity, "finish", movement(game))["phase"] == "complete"


def test_return_before_transfer_gets_new_owned_free_replacement_without_reopening_source(ledger):
    game, periods, replacement = destroyed(ledger)
    archive = end_original(ledger, game)
    closed = next(
        r
        for r in rows(ledger)
        if r["kind"] == "defeat_frame_replacement" and r["state"] == "resolved"
    )
    return_original(ledger, game, archive)
    period = periods.begin(ADMIN, str(uuid4()))
    original = state(game).sheets["2"].model_copy(deep=True)
    work = next(w for w in periods.missions.owned_work(PLAYER) if w["kind"] == DEFEAT_ROOT)
    assert work["off_duty_id"] == period["id"]
    proof = json.loads(next(r for r in rows(ledger) if r["id"] == work["id"])["body_json"])[
        "return_proof"
    ]
    assert proof["closed_work"] == closed["id"] and proof["closed_archive"] == archive
    proposed = propose(replacement, work["id"])
    quote(replacement, proposed["package_id"])
    accept(replacement, work["id"])
    after = state(game).sheets["2"]
    assert after.character_id == original.character_id and not after.frame_scrapped
    assert after.permissions == original.permissions and after.heat == original.heat
    assert after.identities == original.identities
    assert closed in rows(ledger)
    assert not any(
        r["id"] == closed["id"] and r["revision"] > closed["revision"] for r in rows(ledger)
    )
    game.rebuild()
    assert state(game).sheets["2"] == after


def test_return_after_transfer_waits_for_real_next_period_and_preserves_old_work(ledger):
    game, periods, replacement = destroyed(ledger)
    # Synthetic initial-world facts precede the actual period. No critical
    # period completion, return, replacement or work proof is fabricated.
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"strain", "world"}}
            )
        }
    )
    world = initial()
    WorldService(periods.missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    with ledger.transaction() as c:
        canon = state(game)
        for sheet in canon.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.nonvoid_baseline", canon)
    strain = StrainService(periods, dice=D6(1))
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    first = periods.begin(ADMIN, str(uuid4()))
    original_work = next(w for w in periods.missions.owned_work(PLAYER) if w["kind"] == DEFEAT_ROOT)
    archive = end_original(ledger, game)
    finish_survivor_period(ledger, game, periods, first["id"])
    archived = state(game).career_archives[-1]
    return_original(ledger, game, archive)
    next_period = periods.begin(ADMIN, str(uuid4()))
    work = next(w for w in periods.missions.owned_work(PLAYER) if w["kind"] == DEFEAT_ROOT)
    assert work["id"] != original_work["id"] and work["off_duty_id"] == next_period["id"]
    task_body = json.loads(next(r for r in rows(ledger) if r["id"] == work["id"])["body_json"])
    assert task_body["return_proof"]["closed_work"] == original_work["id"]
    proposed = propose(replacement, work["id"])
    quote(replacement, proposed["package_id"])
    accept(replacement, work["id"])
    assert not state(game).sheets["2"].frame_scrapped
    assert state(game).career_archives[-1] == archived
    original_rows = [r for r in rows(ledger) if r["id"] == original_work["id"]]
    assert original_rows[-1]["state"] == "resolved"
    assert (
        json.loads(original_rows[-1]["body_json"])["resolution"]
        == "original_character_career_ended"
    )


def test_returned_void_escape_preserves_actual_gorgon_and_damage_through_free_replacement(ledger):
    game, original, abandoned, escaped_asset = escaped(ledger)
    archive = end_original(ledger, game)
    return_original(ledger, game, archive)
    missions = MissionService(ledger)
    period = OffDutyService(missions).begin(ADMIN, str(uuid4()))
    task = next(w for w in missions.owned_work(PLAYER) if w["kind"] == DEFEAT_ROOT)
    assert task["off_duty_id"] == period["id"]
    replacement = ReplacementService(missions)
    selected = propose(replacement, task["id"])
    quote(replacement, selected["package_id"])
    accept(replacement, task["id"])
    after = state(game)
    assert after.sheets["2"].character_id == original.character_id
    assert not after.sheets["2"].frame_scrapped
    assert next(a for a in after.sheets["2"].assets if a.id == escaped_asset.id).damaged
    assert after.world.gorgons[0] == abandoned
