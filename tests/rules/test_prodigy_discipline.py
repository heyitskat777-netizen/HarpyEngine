"""Prodigy notches and Ace protection come from actual Cadre Punishments."""

import pytest
from test_ancillary_creation import enable, scenario
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_ancillary_cadre as cadre
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_ancillary_cadre import AncillaryCadreService
from girlframe.services.m3_ancillary_discipline import (
    EARNED,
    FAVOURITE,
    KIND,
    AncillaryDisciplineService,
)
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_role_punishments import RolePunishmentService
from girlframe.services.onboarding import WorkflowError


def test_prodigy_confidence_and_favourite_follow_real_punishments(
    ledger,
    tmp_path,
    monkeypatch,
):
    game = scenario(ledger)
    enable(ledger, game, tmp_path, monkeypatch, extra=(EARNED, FAVOURITE))
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
        (soldier.token, prodigy.token),
    )
    for viewer, actor in ((OTHER, prodigy), (PLAYER, soldier)):
        ranks.approve(
            viewer, "join-" + actor.token, group["id"], state(game).revision, actor.token, True
        )

    discipline = AncillaryDisciplineService(game)
    roles = RolePunishmentService(game)

    def enact(actor, owner, label):
        first = discipline.start(
            ADMIN,
            label + "-start",
            900,
            state(game).revision,
            actor.token,
        )["id"]
        inst = Instruction(
            kind="quality_time",
            details_json=Details(kind="quality_time", tag=label).model_dump_json(),
        )
        roles.change(ADMIN, label + "-instruction", first, state(game).revision, instruction=inst)
        roles.change(
            ADMIN,
            label + "-scene",
            first,
            state(game).revision,
            scene="We carry out the actual review together.",
        )
        roles.change(owner, label + "-owner", first, state(game).revision, attest=True)
        roles.change(
            ADMIN,
            label + "-execute",
            first,
            state(game).revision,
            execute=True,
            account="The actual conversation and critique ended.",
        )

    enact(soldier, PLAYER, "Actual first Punishment")
    assert not is_helpless(state(game), prodigy)
    (notch,) = discipline.confidence_menu(OTHER, prodigy)["owned"]
    enact(prodigy, OTHER, "Actual second Punishment")
    assert is_helpless(state(game), prodigy, active_handler(state(game)))
    assert discipline.confidence_menu(OTHER, prodigy)["owned"] == (notch,)
    discipline.spend(OTHER, "advance-actual", prodigy, notch, state(game).revision)
    final = state(game)
    assert cadre.actual_members(final, cadre.current(final, prodigy))[0] == prodigy
    assert any(
        x.get("kind") == KIND and x.get("id") == notch and x.get("spent") for x in final.facts
    )
    with pytest.raises(WorkflowError, match="eligible"):
        discipline.start(ADMIN, "cannot-punish-ace", 900, final.revision, prodigy.token)
