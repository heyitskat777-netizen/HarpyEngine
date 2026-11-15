"""Existing physical setup for actual native recipients of required Harpy Void."""

from uuid import uuid4

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.m3_physical import PhysicalService


def place_sin_recipient(game, owner, reviewer):
    """Owner and GM establish scenario facts before the original mandatory source.

    Existing placement is retained. A new body uses the existing canonical map and
    normal independent review, without pretending any printed consequence occurred.
    """
    physical = PhysicalService(game.store)
    view = physical.preview(owner)
    if view["placement"] is not None:
        return
    proposal = physical.propose(
        owner,
        str(uuid4()),
        view["game_revision"],
        InitialPlacement(
            actor=ActorRef.model_validate(view["actor"]),
            frame_instance=view["frame_instance"],
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            mode="outside_frame",
            account="The original Girl is beside her own Frame at this scenario's scene cell",
            facts_confirmed=True,
        ),
    )
    physical.decide(
        reviewer,
        str(uuid4()),
        proposal["id"],
        proposal["revision"],
        "accept",
        "The actual owner and separate GM confirm these initial scenario physical facts",
    )
