"""The two flesh layers are actual World Assets, never an additional HP pool."""

from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Asset, Gorgon


class LayerSource(Model):
    actor: ActorRef
    event: str = Field(min_length=1)
    layers: tuple[str, str]
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_source(self) -> "LayerSource":
        if (
            self.actor.kind != "gorgon"
            or len(set(self.layers)) != 2
            or not self.event.strip()
            or not self.account.strip()
        ):
            raise ValueError("Use the actual original Gorgon and two distinct source flesh layers")
        return self


def layers_clear(body: Gorgon) -> bool:
    if body.flesh_layers is None:
        return True
    pierced = {x.id for x in body.assets if x.damaged} | {x.id for x in body.destroyed_assets}
    return set(body.flesh_layers) <= pierced


def require_layers_clear(body: Gorgon) -> None:
    if not layers_clear(body):
        raise ValueError("Pierce both actual Leviathan flesh-layer Assets before exposing its Core")


def protect(
    original: GameState,
    actor: ActorRef,
    descriptions: tuple[str, str],
    account: str,
    event: str,
) -> GameState:
    body = (
        next((x for x in original.world.gorgons if x.id == actor.entity and x.alive), None)
        if original.world and actor.kind == "gorgon"
        else None
    )
    if body is None or "leviathan" not in body.types:
        raise ValueError("Only the actual living Leviathan can raise its own flesh layers")
    if body.flesh_layers is not None or any(
        x.get("kind") == "leviathan_layers" and x.get("actor") == actor.model_dump_json()
        for x in original.facts
    ):
        raise ValueError("These original flesh layers already exist; do not reset their damage")
    if not event.strip() or not account.strip() or any(not x.strip() for x in descriptions):
        raise ValueError("Describe the actual two layers and their source action")
    ids = tuple(
        str(uuid5(NAMESPACE_URL, "girlframe:leviathan-layer:" + actor.entity + ":" + str(i)))
        for i in (1, 2)
    )
    assets = tuple(
        Asset(id=identity, name="Flesh layer " + str(i), description=text.strip(), family="gorgon")
        for i, (identity, text) in enumerate(zip(ids, descriptions, strict=True), start=1)
    )
    source = LayerSource(actor=actor, event=event, layers=(ids[0], ids[1]), account=account)
    state = GameState.model_validate_json(original.model_dump_json())
    assert state.world is not None
    state.world = update(
        state.world,
        gorgons=tuple(
            x.model_copy(
                update=dict(
                    assets=(*x.assets, *assets),
                    flesh_layers=source.layers,
                    flesh_layers_event=event,
                    exposed=False,
                )
            )
            if x.id == body.id
            else x
            for x in state.world.gorgons
        ),
    )
    state.facts.append(
        dict(
            kind="leviathan_layers",
            actor=actor.model_dump_json(),
            event=event,
            body=source.model_dump_json(),
        )
    )
    return GameState.model_validate_json(state.model_dump_json())
