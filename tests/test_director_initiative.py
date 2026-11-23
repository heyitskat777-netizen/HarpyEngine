"""An approved event gives initiative only to the AI actor who can witness it."""

from test_director_activity_scene import P2Scene
from test_director_continuity import roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_worldbuilding_knowledge import VISIBLE, established

from girlframe.ai.director_dossiers import (
    DossierPressure,
    DossierProfile,
    DossierState,
    PressurePlan,
)
from girlframe.engine.campaign_opening import Opening
from girlframe.services.campaign_difficulty import EVENT
from girlframe.services.director_session import DirectorSessionService


def test_handler_initiative_requires_ai_authorization_and_uses_the_witnessed_event(routed):
    observer, context, scene, _, _ = routed
    handler, _ = roles(observer, scene)
    world, committed = established(routed)
    disclosure = world.disclose(
        ADMIN, "initiative-evidence", scene, committed["id"], VISIBLE, (handler,), topic="briefing"
    )
    reference = disclosure["reference_ids"][0]
    app = P2Scene(DirectorSessionService(context))
    dossier = app.session.dossiers.propose(
        ADMIN,
        "initiative-dossier",
        scene,
        handler,
        0,
        DossierProfile(),
        DossierState(
            pressures=(
                DossierPressure(
                    text="I need to track the spare relay key.",
                    pressure_id="relay-key",
                    pressure=PressurePlan(
                        stake="Keep the relief crew supplied.",
                        next_step="Offer to hold the spare until the handover.",
                    ),
                    knowledge_refs=(reference,),
                ),
            ),
        ),
    )
    app.session.dossiers.confirm(ADMIN, "confirm-initiative-dossier", scene, dossier["id"])
    opening = Opening(
        scene="approved-introduction",
        channel=901,
        handler=ADMIN.user_id,
        audience=(ADMIN.user_id, PLAYER.user_id, OTHER.user_id),
        plan="approved-plan",
        goals="Keep the pump staffed.",
        difficulty="normal",
        introduction="Check in.",
        first_mission_day=4,
        handler_control="player",
    )
    with observer.store.transaction() as c:
        observer.store._audit(
            c, ADMIN.user_id, "player-control", EVENT, opening.model_dump(mode="json")
        )
    assert app.read(ADMIN, scene, "scene-initiative") == {"options": []}

    with observer.store.transaction() as c:
        observer.store._audit(
            c,
            ADMIN.user_id,
            "ai-control",
            EVENT,
            opening.model_dump(mode="json") | {"handler_control": "ai"},
        )
    (option,) = app.read(ADMIN, scene, "scene-initiative")["options"]
    assert option["actor"] == handler.model_dump(mode="json")
    assert option["source"] == {"kind": "event", "id": reference}
    assert VISIBLE not in str(option)
    request = app.write(
        ADMIN, "event-initiative", scene, "scene-initiative-open", {"option": option["id"]}
    )
    packet = app.session.reactions.packet(ADMIN, scene, request["id"])
    trigger = packet["role"]["initiative"]["trigger"]
    assert VISIBLE in trigger["text"] and trigger["classification"] == "established_world"
