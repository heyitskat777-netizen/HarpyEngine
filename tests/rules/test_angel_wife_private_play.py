"""A private Angel-Wife decision can suppress dice or resolve the actual low result."""

from test_ancillary_creation import REBEL, enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_intimacy import (
    ANGEL,
    CHASTE,
    AncillaryIntimacyService,
    records,
)
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_chained_darling import ChainedPlacementService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_physical import PhysicalService


def test_angel_wife_private_chaste_then_low_original_effect(ledger, tmp_path, monkeypatch):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(ANGEL, CHASTE))
    missions = MissionService(ledger)
    creation = AncillaryService(missions)
    invitation = creation.invite(
        ADMIN,
        "private-angel-invite",
        state(game).revision,
        PLAYER.user_id,
        "city0",
        "group",
        contacts=(REBEL,),
    )
    victim = current_ref(state(game), OTHER.user_id)

    def gear(name):
        return ancillary.NamedAsset(name=name, description="Actual original gear.")

    draft = ancillary.Draft(
        name="Original Angel-Wife",
        book="ANGEL-WIFE",
        bond=REBEL,
        frame_catalogue="JANUS",
        girl_assets=tuple(gear(x) for x in ancillary.STARTERS["ANGEL-WIFE"].assets[:2]),
        frame_assets=tuple(gear(x) for x in ancillary.frame_assets("ANGEL-WIFE", "JANUS")[:2]),
    )
    created = creation.respond(
        PLAYER,
        "private-original-angel",
        invitation["id"],
        state(game).revision,
        draft,
    )
    actor = ActorRef.model_validate(created["actor"])
    cast = CastService(ActorService(missions))
    change(cast, PLAYER, "join", actor)
    placement = ChainedPlacementService(game)
    initial = placement.propose(
        PLAYER,
        "angel-outside",
        900,
        actor,
        state(game).revision,
        "outside_frame",
        "I am outside my own Frame.",
    )
    placement.decide(ADMIN, "confirmed-angel", initial["id"], state(game).revision, True)
    MovementService(game).move(
        OTHER,
        "angel-counterpart-arrives",
        state(game).revision,
        900,
        victim,
        (0, 4),
        frame=True,
        account="I arrive in the same square.",
    )
    physical = PhysicalService(ledger)
    position = physical.preview(OTHER)["position_sha256"]
    physical.operate(
        OTHER,
        "angel-counterpart-exits",
        state(game).revision,
        CockpitAction(
            actor=victim,
            operation="exit",
            expected_position=position,
            account="I step outside nearby.",
            confirmed=True,
        ),
        channel=900,
    )
    service = AncillaryIntimacyService(game)
    game.dice = Dice((3, 3))

    def opening(prefix):
        identity = service.offer(
            PLAYER,
            prefix + "-private",
            900,
            actor,
            state(game).revision,
            victim.token,
        )["id"]
        for viewer in (OTHER, ADMIN):
            service.act(
                viewer,
                prefix + "-approved-" + str(viewer.user_id),
                identity,
                state(game).revision,
                "yes",
            )
        return identity

    blocked = opening("chaste")
    service.act(PLAYER, "owned-belief", blocked, state(game).revision, "not_man")
    assert records(state(game))[0].disposition == "chaste"
    assert game.dice.calls == 0
    case = opening("actual-play")
    service.act(PLAYER, "new-owned-belief", case, state(game).revision, "man")
    service.act(PLAYER, "angel-low", case, state(game).revision, "roll")
    original = ancillary.find(state(game), actor)
    wife = next(x for x in original.identities if x.name == "Wife")
    slot = next(x for x in original.identities if x.name == "Wired")
    service.act(
        OTHER,
        "actual-identity",
        case,
        state(game).revision,
        slot.id,
        account="I can make my own choices",
    )
    service.act(OTHER, "actual-low-helplessness", case, state(game).revision, "yes")
    final = state(game)
    assert is_helpless(final, actor, victim)
    assert game.dice.calls == 1
    saved = ancillary.find(final, actor)
    assert wife in saved.identities
    assert any(
        x.name == "I can make my own choices" and x.slot == slot.slot for x in saved.identities
    )
