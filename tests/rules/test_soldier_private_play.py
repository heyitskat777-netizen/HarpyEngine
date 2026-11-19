"""A Soldier's original middle result applies genuine Cadre and Bond effects."""

from test_ancillary_creation import enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_cadre as cadre
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
from girlframe.services.m3_ancillary_intimacy import SOLDIER, AncillaryIntimacyService, records
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService


def test_soldier_private_middle_raises_actual_status_and_deepens_original_bond(
    ledger,
    tmp_path,
    monkeypatch,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(SOLDIER,))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    cast_service = CastService(ActorService(missions))
    partner = current_ref(state(game), OTHER.user_id)

    def create(viewer, book, name, bond):
        invitation = creation.invite(
            ADMIN,
            "invite-" + name,
            state(game).revision,
            viewer.user_id,
            "base0",
        )

        def gear(label):
            return ancillary.NamedAsset(name=label, description="Original actual gear.")

        frame = "SOLDIER_3" if book == "SOLDIER" else "JANUS"
        data = ancillary.Draft(
            book=book,
            name=name,
            bond=bond,
            frame_catalogue=frame,
            girl_assets=tuple(gear(x) for x in ancillary.STARTERS[book].assets[:2]),
            frame_assets=tuple(gear(x) for x in ancillary.frame_assets(book, frame)[:2]),
        )
        created = creation.respond(
            viewer, "create-" + name, invitation["id"], state(game).revision, data
        )
        actor = ActorRef.model_validate(created["actor"])
        change(cast_service, viewer, "join", actor)
        return actor

    soldier = create(PLAYER, "SOLDIER", "Original Soldier", partner)
    prodigy = create(OTHER, "PRODIGY", "Original Prodigy", current_ref(state(game), PLAYER.user_id))
    ranks = AncillaryCadreService(game)
    group = ranks.propose(
        ADMIN,
        "formation",
        900,
        state(game).revision,
        active_handler(state(game)).token,
        (prodigy.token, soldier.token),
    )
    for viewer, actor in ((OTHER, prodigy), (PLAYER, soldier)):
        ranks.approve(
            viewer, "join-" + actor.token, group["id"], state(game).revision, actor.token, True
        )

    placement = ChainedPlacementService(game)
    draft = placement.propose(
        PLAYER,
        "soldier-outside",
        900,
        soldier,
        state(game).revision,
        "outside_frame",
        "I am outside my Frame.",
    )
    placement.decide(ADMIN, "actual-placement", draft["id"], state(game).revision, True)
    physical = PhysicalService(ledger)
    physical.operate(
        OTHER,
        "other-exits",
        state(game).revision,
        CockpitAction(
            actor=partner,
            operation="exit",
            expected_position=physical.preview(OTHER)["position_sha256"],
            account="I join her nearby.",
            confirmed=True,
        ),
        channel=900,
    )
    service = AncillaryIntimacyService(game)
    game.dice = Dice((4, 4))
    actual = service.offer(PLAYER, "middle", 900, soldier, state(game).revision, partner.token)[
        "id"
    ]
    for viewer, choice in ((OTHER, "yes"), (ADMIN, "yes"), (PLAYER, "roll"), (PLAYER, "deepen")):
        service.act(viewer, choice + str(viewer.user_id), actual, state(game).revision, choice)
    final = state(game)
    assert depth(final, soldier, partner) == 2
    assert cadre.actual_members(final, cadre.current(final, soldier)) == (soldier, prodigy)
    assert records(final)[0].disposition == "soldier_advanced"
