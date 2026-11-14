"""Exact Borrowed Wings custody and explicit exceptional engineer return packages."""

from typing import Literal

from pydantic import Field

from girlframe.engine import m3_doctor as doctor
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_core import install
from girlframe.engine.m3_item_state import ItemTransfer
from girlframe.engine.m3_items import actual_asset


class Custody(Model):
    kind: Literal["pilot", "item", "gorgon"]
    actor: ActorRef
    asset: AssetState
    item: str | None = None


class Package(Model):
    loan: str
    source: Custody
    destination: ActorRef
    frame: str
    replace: str | None = None
    account: str = Field(min_length=1, max_length=1200)
    quote_event: str
    handler: int
    game_revision: int


class Receipt(Model):
    id: str
    package: Package
    event: str
    confirmed_by: int
    received: AssetState
    replaced: AssetState | None = None


def loan(state: GameState, identity: str) -> doctor.Loan:
    value = next(
        (x for x in doctor.values(state, "doctor_loan", doctor.Loan) if x.id == identity), None
    )
    if value is None or value.phase != "borrowed":
        raise ValueError("Open the actual still-borrowed Wings component")
    return value


def frame(state: GameState, actor: ActorRef) -> str:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation or sheet.frame_scrapped:
        raise ValueError("SOURCE_PORT_REQUIRED: original donor needs an actual receiving Frame")
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)


def locate(state: GameState, value: doctor.Loan) -> Custody:
    """Aliases of one physical object do not create another candidate or a JSON copy."""
    candidates: list[Custody] = []
    for owner, sheet in state.sheets.items():
        for asset in sheet.assets:
            if asset.id != value.asset:
                continue
            actor = ActorRef(kind="pilot", entity=owner, incarnation=sheet.character_id)
            if actor != value.doctor and not any(
                x.asset_owner == actor and x.asset_id == value.asset for x in state.held_items
            ):
                raise ValueError("SOURCE_PORT_REQUIRED: recover the exact component transfer chain")
            candidates.append(Custody(kind="pilot", actor=actor, asset=asset))
    for item in state.held_items:
        if item.asset_id != value.asset:
            continue
        item_asset = actual_asset(state, item)
        if item_asset is None:
            raise ValueError("SOURCE_PORT_REQUIRED: recover the exact held Wings component")
        if item.holder.kind == "pilot":
            candidates = [x for x in candidates if x.actor != item.holder]
        candidates.append(Custody(kind="item", actor=item.holder, asset=item_asset, item=item.id))
    for body in state.world.gorgons if state.world else ():
        for gorgon_asset in (*body.assets, *body.destroyed_assets):
            if gorgon_asset.id != value.asset:
                continue
            if gorgon_asset in body.destroyed_assets:
                raise ValueError(
                    "SOURCE_PORT_REQUIRED: destroyed graft needs actual salvage/repair"
                )
            if not any(
                x.actor == value.doctor and x.gorgon and x.gorgon.entity == body.id
                for x in state.void_thresholds
            ):
                raise ValueError("SOURCE_PORT_REQUIRED: recover original Doctor conversion custody")
            if (
                gorgon_asset.id in body.core_plan.assets
                or gorgon_asset.id == body.protected_asset
                or gorgon_asset.id in (body.flesh_layers or ())
            ):
                raise ValueError(
                    "SOURCE_PORT_REQUIRED: linked Gorgon graft needs its actual "
                    "core/protection/layer relocation provider"
                )
            original = AssetState.model_validate_json(value.source_asset_json)
            actual = original.model_copy(
                update=dict(
                    id=gorgon_asset.id,
                    name=gorgon_asset.name,
                    description=gorgon_asset.description,
                    damaged=gorgon_asset.damaged,
                    void=gorgon_asset.void,
                    classification_event=gorgon_asset.classification_event,
                )
            )
            candidates.append(
                Custody(kind="gorgon", actor=ActorRef(kind="gorgon", entity=body.id), asset=actual)
            )
    if len(candidates) != 1:
        raise ValueError(
            "SOURCE_PORT_REQUIRED: locate exactly one actual Wings component; "
            "never reconstruct or duplicate it"
        )
    return candidates[0]


def transfer(original: GameState, package: Package, event: str, owner: int) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    value = loan(state, package.loan)
    source = locate(state, value)
    if (
        source != package.source
        or package.destination != value.donor
        or owner != int(value.donor.entity)
    ):
        raise ValueError("Preserve original donor ownership and the exact quoted current custody")
    if frame(state, value.donor) != package.frame or package.game_revision != state.revision:
        raise ValueError("STALE_RETURN: review the actual receiving Frame and current custody")
    received = source.asset.model_copy(
        update=dict(id=AssetState.model_validate_json(value.source_asset_json).id, family="frame")
    )
    donor = state.sheets[value.donor.entity]
    replaced = next((x for x in donor.assets if x.id == package.replace), None)
    if source.kind in ("pilot", "item"):
        if source.actor.kind == "pilot":
            carrier = state.sheets[source.actor.entity]
            carrier.assets = [x for x in carrier.assets if x.id != source.asset.id]
            carrier.revision += 1
        if source.item:
            item = next(x for x in state.held_items if x.id == source.item)
            moved = item.model_copy(
                update=dict(
                    holder=value.donor,
                    asset_owner=value.donor,
                    asset_id=received.id,
                    asset_json=received.model_dump_json(),
                    state_event=event,
                    transferred_event=event,
                    location_mode="carried",
                    scene_id=None,
                    location_event=event,
                )
            )
            state.held_items = [moved if x.id == item.id else x for x in state.held_items]
            if source.actor != value.donor:
                state.item_transfers.append(
                    ItemTransfer(
                        id="transfer:" + event,
                        item=item.id,
                        source=source.actor,
                        recipient=value.donor,
                        action=value.id,
                        event=event,
                        account=package.account,
                        prior_event=item.state_event or item.transferred_event or item.source_event,
                        removed_asset=source.asset.id,
                        received_asset=received.id,
                    )
                )
    else:
        assert state.world is not None
        state.world = type(state.world).model_validate_json(
            state.world.model_copy(
                update=dict(
                    gorgons=tuple(
                        x.model_copy(
                            update=dict(
                                assets=tuple(a for a in x.assets if a.id != source.asset.id)
                            )
                        )
                        if x.id == source.actor.entity
                        else x
                        for x in state.world.gorgons
                    )
                )
            ).model_dump_json()
        )
    from girlframe.engine.m3_janus_storage import ids

    updated = install(
        state.sheets[value.donor.entity],
        received,
        replace=package.replace,
        effective_void=ids(state, value.donor),
        state=state,
    ).sheet
    state.sheets[value.donor.entity] = updated
    doctor.put(
        state, "doctor_loan", value.model_copy(update=dict(phase="returned", return_event=event))
    )
    receipt = Receipt(
        id=value.id,
        package=package,
        event=event,
        confirmed_by=owner,
        received=received,
        replaced=replaced,
    )
    state.facts.append(
        dict(kind="doctor_wings_return_receipt", id=value.id, body=receipt.model_dump_json())
    )
    return GameState.model_validate_json(state.model_dump_json())
