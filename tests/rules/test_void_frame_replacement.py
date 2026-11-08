"""A real escaped Frame becomes a Gorgon before a distinct later replacement."""

from test_dive import threshold_source
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_replacement_service import accept, propose, quote
from test_void_service import respond

from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_replacement import DEFEAT_ROOT, ReplacementService
from girlframe.services.m3_void import VoidService


def escaped(ledger):
    game, worker, gateway, root, work = threshold_source(ledger)
    service = VoidService(ledger)
    before = state(game).sheets["2"]
    frame_assets = [x for x in before.assets if x.family == "frame"]
    girl_asset = next(x for x in before.assets if x.family == "girl" and not x.damaged)
    respond(service, work, "choose_escape", dict(asset=girl_asset.id, account="Actual escape"))
    actual = Gorgon(
        id="original-abandoned-frame",
        name="Original abandoned Frame",
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
            for x in frame_assets
        ),
        core_plan=CorePlan(assets=(frame_assets[0].id,), weakness="Actual exposed access"),
    )
    respond(
        service,
        work,
        "escape",
        dict(gorgon=actual.model_dump(mode="json"), account="Actual original Frame abandonment"),
        viewer=ADMIN,
    )
    assert game.inspect(PLAYER, root)["state"] == "complete"
    tick(worker, gateway, 6)
    assert state(game).sheets["2"].frame_scrapped
    assert state(game).world.gorgons[0].id == actual.id
    abandoned = state(game).world.gorgons[0]
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks"}}
            )
        }
    )
    return game, before, abandoned, girl_asset


def test_actual_abandoned_frame_has_source_proved_next_period_free_package(ledger):
    game, before, abandoned, girl_asset = escaped(ledger)
    frame_assets = [x for x in before.assets if x.family == "frame"]
    missions = MissionService(ledger)
    periods = OffDutyService(missions)
    period = periods.begin(ADMIN, "real-next-off-duty-after-escape")
    task = next(x for x in missions.owned_work(PLAYER) if x["kind"] == DEFEAT_ROOT)
    assert task["off_duty_id"] == period["id"]
    replacement = ReplacementService(missions)
    selected = propose(replacement, task["id"])
    quote(replacement, selected["package_id"])
    accept(replacement, task["id"])
    after = state(game)
    assert not after.sheets["2"].frame_scrapped
    assert after.sheets["2"].character_id == before.character_id
    assert after.sheets["2"].permissions == before.permissions
    assert next(x for x in after.sheets["2"].assets if x.id == girl_asset.id).damaged
    assert after.world.gorgons[0] == abandoned
    assert {a.id for a in abandoned.assets} == {a.id for a in frame_assets}
