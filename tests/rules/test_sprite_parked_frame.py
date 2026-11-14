"""A genuine Roused strike hits the parked Frame, not its absent original Girl."""

from uuid import uuid4

from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_world import gorgon
from test_wyvern import free_chat, ready, roll

from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import frame_position, resolve
from girlframe.engine.m3_world import introduce_gorgon
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_sprite import SpriteService
from girlframe.services.m3_wyvern import prove_use


def test_real_parked_frame_strike_offers_sprite_at_frame_not_absent_girl(
    ledger, tmp_path, monkeypatch
):
    import test_m2_game
    from test_creation import selected
    from test_creation_review import ready as creation_ready

    # The shared fixture defaults the second pilot to JANUS, whose separate Core
    # is deliberately excluded from parked strikes. Create a real non-Core Frame
    # through the existing reviewed/activated character setup instead.
    monkeypatch.setattr(
        test_m2_game,
        "ready",
        lambda store, girl, frame: creation_ready(store, girl, frame, other_frame="THE ENFORCER"),
    )
    monkeypatch.setattr(
        test_m2_game, "selected", lambda girl, frame: selected(girl, "THE ENFORCER")
    )
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    target = current_ref(state(game), 3)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].public_fields = tuple(
            dict.fromkeys((*canon.sheets["3"].public_fields, "assets"))
        )
        canon.world = introduce_gorgon(
            canon.world, gorgon("sprite", "parked-frame-shield", revealed=True)
        ).world
        game.event(c, 1, str(uuid4()), "synthetic.actual_disclosed_frame_and_sprite", canon)
    MovementService(game).move(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        (1, 0),
        account="I walk away from my vacant Frame, leaving it beside the Sprite",
    )
    before = state(game)
    with ledger.engine.connect() as c:
        body = resolve(before, target, profiles(c, ledger.campaign_id))
    assert body.cell == (1, 0) and not body.inside_frame
    assert frame_position(before, target, body.frame_instance) == (0, 0)
    asset = next(x.id for x in before.sheets["3"].assets if x.family == "frame" and not x.damaged)
    action = roll(game, worker, gateway)
    free_chat(worker, gateway)
    with ledger.engine.connect() as c:
        receipt = game.action(c, action)["data"]["receipt"]
    used = controls.use_roused(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        target,
        "strike",
        asset=asset,
        target_frame=body.frame_instance,
    )
    pending = next(x for x in rules.records(state(game), rules.RousedUse) if x.id == used["id"])
    assert pending.work and pending.completed_event is None
    sprite = SpriteService(ledger)
    data = sprite.get(ADMIN, pending.work[0])
    option = next(x for x in data["options"] if x["actor"]["entity"] == "parked-frame-shield")
    sprite.respond(
        ADMIN,
        str(uuid4()),
        pending.work[0],
        data["revision"],
        data["game_revision"],
        ActorRef.model_validate(option["actor"]),
        option["asset"],
        "My Sprite intercepts the actual blow against the nearby vacant Frame",
    )
    after = state(game)
    assert not next(x for x in after.sheets["3"].assets if x.id == asset).damaged
    shield = next(x for x in after.world.gorgons if x.id == "parked-frame-shield")
    assert next(x for x in shield.assets if x.id == option["asset"]).damaged
    assert after.placements == before.placements
    assert rules.roused(after, current_ref(after, 2)) is None
    with ledger.engine.connect() as c:
        assert prove_use(game, c, after, used["id"]).completed_event
        assert game.action(c, action)["data"]["receipt"] == receipt
    assert game.dice.calls == 1
