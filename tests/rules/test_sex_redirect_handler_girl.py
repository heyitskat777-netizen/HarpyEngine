"""Real mid Sex source redirects actual Void into the original Handler's Girl-rules body."""

from types import SimpleNamespace
from uuid import uuid4

from test_battle_director import source as director_source
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, pass_tags, state, tick

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_girl_void import girl_assets
from girlframe.engine.m3_mockingbird_state import SEX
from girlframe.services import m3_mockingbird_plays as plays
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_handler_girl_void import HandlerGirlVoidService
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_missions import MissionService

ledger = ledger_fixture


def test_real_mid_redirect_into_handler_girl_preserves_source_damage_and_waits_for_actual_owners(
    ledger, monkeypatch
):
    game, _, _, _, director_service, damage_work, director = director_source(ledger)
    # Finish the unrelated actual Director source first; no synthetic completion is inserted.
    data = director_service.get(OTHER, damage_work)
    director_service.respond(
        OTHER,
        str(uuid4()),
        damage_work,
        data["revision"],
        "injury",
        "Actual original Director survives with an injured arm",
    )
    game.dice, game.rng_source = Dice((4, 5)), "test_injected"
    monkeypatch.setattr(
        plays, "load_registry", lambda: SimpleNamespace(require_available=lambda identity: None)
    )
    monkeypatch.setattr(plays, "sex_ready", lambda: True)
    casts = CastService(ActorService(MissionService(ledger)))
    change(casts, OTHER, "join", director)
    change(casts, OTHER, "adjudicate", director)
    context = ActorRef(kind="handler", entity="1", incarnation=state(game).director_contexts[-1].id)
    change(casts, ADMIN, "join", context)
    with ledger.transaction() as c:
        canon = state(game)
        original = next(x for x in canon.sheets["3"].assets if x.family == "girl")
        original.void = True
        original.damaged = True
        original.description = "Actual source Girl Asset's existing Void alteration"
        asset_id = original.id
        game.event(c, 3, str(uuid4()), "synthetic.existing_original_void_asset", canon)
    before = state(game)
    actor, primary = current_ref(before, 2), current_ref(before, 3)
    source = plays.MockingbirdService(game)
    proposed = source.propose(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        SEX,
        (primary, context),
        "Actual accepted source interaction with both original people",
        primary=primary,
    )
    source.attest(OTHER, str(uuid4()), proposed["id"], primary, True)
    source.attest(ADMIN, str(uuid4()), proposed["id"], context, True)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=SEX,
            source_work=proposed["id"],
            context="Actual original mid source",
            trigger_confirmed=True,
            heat=0,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "mockingbird_sex_select", options=("collect",))
    answer(
        game,
        PLAYER,
        "mockingbird_sex_redirect",
        fields={"source_asset": asset_id, "destination": context.token, "destination_asset": ""},
    )
    answer(
        game,
        OTHER,
        "mockingbird_sex_restore",
        text="Actual source owner restores only the prior non-Void description",
    )
    canon = state(game)
    episode = canon.handler_girl_void[-1]
    assert episode.actor == context and episode.phase == "facts"
    assert not canon.handler_void and "1" not in canon.sheets
    original = next(x for x in canon.sheets["3"].assets if x.id == asset_id)
    assert not original.void and original.damaged
    assert game.inspect(PLAYER, action)["state"] != "complete" and game.dice.calls == 1
    service = HandlerGirlVoidService(ledger, game)
    work = episode.work
    with ledger.engine.connect() as c:
        import sqlalchemy as sa

        from girlframe.database import tables as t

        row = (
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(t.m3["m3_required_work"].c.id == work)
                .order_by(t.m3["m3_required_work"].c.revision)
            )
            .mappings()
            .first()
        )
        assert row["kind"] == "mockingbird_redirect_handler_girl_void"
    service.propose(
        ADMIN,
        str(uuid4()),
        work,
        canon.revision,
        "Existing optical implant",
        "Actual existing damaged cybernetic eye",
        "Actual patient confirms it predates this interaction",
        damaged=True,
        weapon=False,
    )
    service.review(
        OTHER,
        str(uuid4()),
        work,
        state(game).revision,
        allow=True,
        account="Actual original Director factually verifies the existing damaged implant",
    )
    data = service.get(PLAYER, work)
    assert data["phase"] == "asset" and data["can_act"]
    chosen = data["assets"][0]["id"]
    item = state(game).held_items[-1]
    with ledger.engine.connect() as c:
        assert prove_item(c, game, state(game), item.id) == item
    service.select(PLAYER, str(uuid4()), work, state(game).revision, chosen)
    service.rewrite(
        ADMIN,
        str(uuid4()),
        work,
        state(game).revision,
        "Actual patient describes the existing implant's Void alteration",
    )
    tick(worker, gateway, 5)
    final = state(game)
    assert girl_assets(final, context)[0].id == chosen
    assert girl_assets(final, context)[0].void and girl_assets(final, context)[0].damaged
    assert next(x for x in final.sheets["3"].assets if x.id == asset_id).damaged
    assert not next(x for x in final.sheets["3"].assets if x.id == asset_id).void
    assert final.handler_heat == before.handler_heat and final.placements == before.placements
    assert final.handler_girl_void[-1].assigned_frame is None
    assert not final.harpy_states and "1" not in final.sheets
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
