"""One normal actual Dive gain, same-Core unplug/replug and Foundation removal."""

from uuid import uuid4

from test_enforcer_requisitions import approved
from test_janus_battery import connected
from test_janus_battery import start as start_battery
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, start, state, tick

from girlframe.engine import m3_janus_storage as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_janus import BATTERY, CORE
from girlframe.engine.m3_janus_requisitions import STORAGE
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_frame_control import FrameControlService
from girlframe.services.m3_janus_requisitions import JanusRequisitionService
from girlframe.services.m3_janus_storage import StorageService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService


def test_actual_storage_changes_only_while_same_core_plugged_and_surgery_preserves_asset(
    ledger, tmp_path, monkeypatch
):
    import girlframe.services.m3_janus_requisitions as acquisitions

    game, worker, gateway, core, connection = connected(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(CORE, BATTERY, STORAGE))
    monkeypatch.setattr(acquisitions, "IMPLEMENTED", (*acquisitions.IMPLEMENTED, STORAGE))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.actual_storage_funds", actual)
    purchases = JanusRequisitionService(game)
    menu = purchases.menu(PLAYER)
    purchases.buy_rule(
        PLAYER, str(uuid4()), menu["source_sha256"], STORAGE, "Actual Void Storage acquisition"
    )

    def battery():
        identity = start_battery(game, core)
        tick(worker, gateway, 3)
        if game.inspect(PLAYER, identity)["state"] != "tag_window":
            game.roll(PLAYER, str(uuid4()), identity)
        pass_tags(game)
        answer(game, PLAYER, "janus_select", options=("cognition", "offset"))
        tick(worker, gateway, 4)

    battery()
    actor = current_ref(state(game), 2)
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    original = asset.model_copy(deep=True)
    game.dice.faces = (4, 5)
    dive = start(game, play="dive_deep")
    tick(worker, gateway, 3)
    pass_tags(game)
    if any(x["kind"] == "mockingbird_risk" for x in game.choices(PLAYER)):
        answer(game, PLAYER, "mockingbird_risk", flag=False)
    answer(game, PLAYER, "dive_select", options=("void_and_unmark_all",), text="Actual communion")
    answer(
        game,
        PLAYER,
        "dive_effect",
        fields={"asset": asset.id, "storage": "yes"},
        text="Actual temporary Void alteration while this original Harpy is plugged in",
    )
    tick(worker, gateway, 4)
    service = StorageService(game)
    point = service.view(PLAYER)["points"][0]
    assert point["active"]
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id) == original
    assert next(x for x in game.sheet(PLAYER)["assets"] if x["id"] == asset.id)["void"]
    assert game.inspect(PLAYER, dive)["state"] == "complete"

    contact = FrameControlService(game)
    contact.unplug(
        PLAYER,
        str(uuid4()),
        connection,
        state(game).revision,
        "I physically remove my actual neural jack",
    )
    assert not service.view(PLAYER)["points"][0]["active"]
    assert not next(x for x in game.sheet(PLAYER)["assets"] if x["id"] == asset.id)["void"]
    connection = contact.propose(
        PLAYER,
        str(uuid4()),
        900,
        actor,
        core,
        "My actual jack reconnects to the same original Core",
    )["id"]
    contact.decide(
        ADMIN,
        str(uuid4()),
        connection,
        state(game).revision,
        True,
        "The original actual spinal contact is established again",
    )
    game.dice.faces = (2, 2)
    battery()
    assert service.view(PLAYER)["points"][0]["active"]
    with ledger.engine.connect() as c:
        actual_view = resolve(state(game), actor, profiles(c, ledger.campaign_id))
        assert next(x for x in actual_view.assets if x.id == asset.id).void

    cast = CastService(ActorService(MissionService(ledger)))
    source = cast.view(OTHER, 900)
    cast.change(OTHER, str(uuid4()), 900, source["game_revision"], source["cast_revision"],
                "withdraw", core)

    periods = OffDutyService(MissionService(ledger))
    period = periods.begin(ADMIN, str(uuid4()))["id"]
    # Existing shared-roll fixture: activation setup is isolated, surgery still
    # requires the actual original Go Off-Duty receipt, not this phase label.
    with ledger.transaction() as c:
        value = periods._get(c, period)
        value.phase = "active"
        value.revision += 1
        event = game.event(c, 1, str(uuid4()), "synthetic.active_period")
        periods._save(c, value, event)
    duty = start(game, play="go_off_duty", off_duty_id=period)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, duty)["state"] == "complete"
    tick(worker, gateway, 4)
    data = service.view(PLAYER)
    request = service.request(
        PLAYER,
        str(uuid4()),
        data["revision"],
        point["id"],
        period,
        "Actual Foundation surgical request for this stored point",
    )["id"]
    data = service.get(ADMIN, request)
    service.confirm(
        ADMIN,
        str(uuid4()),
        request,
        data["revision"],
        "The Foundation actually surgically removes the stored point from this Harpy",
    )
    assert not service.view(PLAYER)["points"]
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id) == original
    assert rules.points(state(game))[0].removed_period == period
