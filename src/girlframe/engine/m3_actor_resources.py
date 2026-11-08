"""Pure source-specific Heat/Identity ports; non-Girls never become proxy Pilot sheets."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState, IdentityState, mark_identity, spend_heat
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve


class Commitment(Model):
    heat: int = Field(ge=0)
    identity: str | None = None
    gain: int = Field(default=0, ge=0, le=5)
    pair_share: int = Field(default=0, ge=0, le=5)


class Followup(Model):
    kind: str
    actor: ActorRef
    source_pdf: int


class Committed(Model):
    state: GameState
    followups: tuple[Followup, ...] = ()


class RebelInventory(Model):
    actor: ActorRef
    controller: int
    initial_event: str
    account: str = Field(min_length=1, max_length=1200)
    heat: int = Field(ge=0)
    identities: tuple[IdentityState, ...]

    @model_validator(mode="after")
    def ordinary_inventory(self) -> "RebelInventory":
        if (
            self.actor.kind != "external_pilot"
            or len(self.identities) > 4
            or len({x.id for x in self.identities}) != len(self.identities)
            or len({x.slot for x in self.identities}) != len(self.identities)
            or any(
                x.slot is None
                or x.paired
                or x.protected
                or x.am_limiter
                or x.obsession_sources
                or not x.name.strip()
                for x in self.identities
            )
        ):
            raise ValueError("Only an actual ordinary Rebel Girl inventory has this resource port")
        return self


def rebel_inventory(state: GameState, actor: ActorRef) -> RebelInventory | None:
    pilot = (
        next(
            (
                x
                for x in state.world.pilots
                if actor.kind == "external_pilot" and x.id == actor.entity
            ),
            None,
        )
        if state.world
        else None
    )
    if pilot is None or pilot.rebel_resources_json is None:
        return None
    if pilot.kind != "rebel" or pilot.girl.upper() != "MOCKINGBIRD":
        raise ValueError(
            "UNSUPPORTED_REBEL_INVENTORY: conditional Girl resources need their own port"
        )
    value = RebelInventory.model_validate_json(pilot.rebel_resources_json)
    if value.actor != actor or value.controller != pilot.controller:
        raise ValueError("Preserve the actual original Rebel Girl resource controller")
    return value


def save_rebel_inventory(state: GameState, value: RebelInventory) -> None:
    old = rebel_inventory(state, value.actor)
    if old is not None and (old.initial_event, old.account, old.controller) != (
        value.initial_event,
        value.account,
        value.controller,
    ):
        raise ValueError("Never reset or reauthor this original Rebel inventory")
    if state.world is None:
        raise ValueError("The actual world Rebel Girl is missing")
    state.world = state.world.model_copy(
        update=dict(
            pilots=tuple(
                x.model_copy(update=dict(rebel_resources_json=value.model_dump_json()))
                if x.id == value.actor.entity
                else x
                for x in state.world.pilots
            )
        )
    )


def commit(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    prepared: Commitment,
    expected: str,
    *,
    require_current_profile: bool = True,
) -> Committed:
    state = GameState.model_validate_json(original.model_dump_json())
    view = resolve(state, actor, bindings, require_current_profile=require_current_profile)
    prepared = Commitment.model_validate_json(prepared.model_dump_json())
    if view.source_sha256 != expected:
        raise ValueError("STALE_RESOURCES: confirm the actual actor's current resources")
    if prepared.identity is not None:
        from girlframe.engine.m3_leviathan_obsession import require_identity_gain

        require_identity_gain(state, actor, prepared.identity)
    followups: list[Followup] = []
    if view.rules == "clone_am":
        from girlframe.engine.m3_clone_am import additional_identities, current, owner
        from girlframe.engine.m3_clone_am import commit as commit_clone

        original_copy = current(state, actor)
        original_sheet = owner(state, actor)
        was_full = all(
            x.marked
            for x in (
                *original_sheet.identities,
                *additional_identities(state, original_sheet.owner),
            )
        )
        commit_clone(
            state, actor, prepared.identity, prepared.gain, prepared.heat, prepared.pair_share
        )
        if (
            original_sheet.frame == "PROJECT ANKOU"
            and not was_full
            and all(
                x.marked
                for x in (
                    *original_sheet.identities,
                    *additional_identities(state, original_sheet.owner),
                )
            )
        ):
            followups.append(
                Followup(kind="ankou_feedback", actor=original_copy.original, source_pdf=84)
            )
    elif view.rules == "girl_frame":
        from girlframe.engine.m3_clone_am import additional_identities

        sheet = state.sheets[actor.entity]
        was_full = all(
            x.marked for x in (*sheet.identities, *additional_identities(state, sheet.owner))
        )
        if prepared.identity is not None:
            share = mark_identity(
                sheet, prepared.identity, prepared.gain, prepared.pair_share, state=state
            )
            if share:
                pair = next((x for x in bindings if x.owner == sheet.pair), None)
                if pair is None:
                    raise ValueError("The actual Pair's character binding is unavailable")
                resolve(
                    state,
                    ActorRef(kind="pilot", entity=str(pair.owner), incarnation=pair.character_id),
                    bindings,
                    require_current_profile=False,
                )
                from girlframe.engine.m3_leviathan_obsession import allowed_gain

                pair_ref = ActorRef(
                    kind="pilot", entity=str(pair.owner), incarnation=pair.character_id
                )
                state.sheets[str(pair.owner)].heat += allowed_gain(
                    state, pair_ref, share, "Paired Identity received share"
                )
                state.sheets[str(pair.owner)].revision += 1
        elif prepared.gain or prepared.pair_share:
            raise ValueError("Heat gain requires an actual eligible Identity")
        spend_heat(sheet, prepared.heat)
        sheet.revision += 1
        if (
            sheet.frame == "PROJECT ANKOU"
            and not was_full
            and all(
                x.marked for x in (*sheet.identities, *additional_identities(state, sheet.owner))
            )
        ):
            followups.append(Followup(kind="ankou_feedback", actor=actor, source_pdf=84))
    elif view.rules == "handler_girl":
        context = next(x for x in state.director_contexts if x.id == actor.incarnation and x.active)
        if prepared.pair_share:
            raise ValueError("The actual Handler context has no Paired Identity or Pair")
        if prepared.identity is not None:
            identity: IdentityState | None = next(
                (x for x in context.identities if x.id == prepared.identity), None
            )
            if identity is None or identity.marked or not 1 <= prepared.gain <= 3:
                raise ValueError("Mark one actual unmarked ordinary Identity for one to three Heat")
            identity.marked = True
            state.handler_heat += prepared.gain
            context.revision += 1
        elif prepared.gain:
            raise ValueError("Heat gain requires an actual eligible Identity")
        if prepared.heat > state.handler_heat or (
            state.handler_heat >= 5 and prepared.heat != state.handler_heat
        ):
            raise ValueError("Spend available Heat; holding five or more requires spending all")
        state.handler_heat -= prepared.heat
    elif actor.kind == "external_pilot" and view.girl == "harpy":
        from girlframe.engine.m3_harpy_defeat import harpy, update

        actual = harpy(state, actor)
        actual_heat, actual_identities = actual.heat, actual.identities
        was_full = bool(actual.identities) and all(x.marked for x in actual.identities)
        if prepared.pair_share:
            raise ValueError("A Harpy cannot borrow a former Girl's Pair resource port")
        if prepared.identity is not None:
            selected = next((x for x in actual.identities if x.id == prepared.identity), None)
            if selected is None or selected.marked or not 1 <= prepared.gain <= 3:
                raise ValueError("Mark an actual unmarked Harpy Identity for one to three Heat")
            if selected.paired:
                raise ValueError(
                    "UNSUPPORTED_RULE: this retained Paired Identity needs its own port"
                )
            actual_identities = tuple(
                x.model_copy(update={"marked": True}) if x.id == selected.id else x
                for x in actual.identities
            )
            actual_heat += prepared.gain
        elif prepared.gain:
            raise ValueError("Heat gain requires an actual eligible Harpy Identity")
        if prepared.heat > actual_heat or (actual_heat >= 5 and prepared.heat != actual_heat):
            raise ValueError("Spend actual available Heat; holding five or more requires all")
        state = update(state, actor, heat=actual_heat - prepared.heat, identities=actual_identities)
        if (
            "frame.ankou.feedback-loop" in getattr(actual, "plays", ())
            and not was_full
            and all(x.marked for x in actual_identities)
        ):
            followups.append(Followup(kind="ankou_feedback", actor=actor, source_pdf=84))
    elif actor.kind == "external_pilot" and rebel_inventory(state, actor) is not None:
        inventory = rebel_inventory(state, actor)
        assert inventory is not None
        if prepared.pair_share:
            raise ValueError("This ordinary Rebel Girl has no Paired resource port")
        values = list(inventory.identities)
        heat = inventory.heat
        if prepared.identity is not None:
            rebel_selected = next((x for x in values if x.id == prepared.identity), None)
            if rebel_selected is None or rebel_selected.marked or not 1 <= prepared.gain <= 3:
                raise ValueError(
                    "Mark an actual owned unmarked Rebel Identity for one to three Heat"
                )
            rebel_selected.marked = True
            heat += prepared.gain
        elif prepared.gain:
            raise ValueError("Rebel Heat gain needs its actual Identity")
        if prepared.heat > heat or heat >= 5 and prepared.heat != heat:
            raise ValueError("Spend actual available Rebel Heat; five or more requires all")
        save_rebel_inventory(
            state,
            inventory.model_copy(update=dict(heat=heat - prepared.heat, identities=tuple(values))),
        )
    else:
        raise ValueError(
            "UNSUPPORTED_RULE: this role has no supported Girl Heat/Identity resource port"
        )
    return Committed(state=state, followups=tuple(followups))
