"""High Void 2.2 preserves the private draw and actual player-authored disclosure."""

import json
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_bunk_harpy as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyRuntime
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_void_state import HarpyState
from girlframe.engine.rolls import IndexSource
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def unlinked(state: GameState, body: ActorView) -> bool:
    if body.ref.kind == "pilot":
        pose = next((x for x in state.placements if x.actor == body.ref), None)
        if pose is None or not pose.vitals_active or pose.incapacitated or pose.subsumed:
            return False
    else:
        bodies: tuple[NativeHarpyRuntime | HarpyState, ...] = (
            *state.native_harpies,
            *state.harpy_states,
        )
        native = next((x for x in bodies if x.id == body.ref.entity), None)
        if native is None or native.body_incapacitated:
            return False
    return (
        body.alive
        and body.inside_frame is False
        and body.vitals_active is not False
        and body.custody in (None, "free")
        and not body.subsumed
        and body.cell is not None
    )


def candidates(state: GameState, viewer: GuildViewer) -> tuple[tuple[str, str], ...]:
    """Offer actual independently controlled Harpies without projecting the draw."""
    actors = [ActorRef(kind="external_pilot", entity=x.id) for x in state.native_harpies]
    actors += [ActorRef(kind="external_pilot", entity=x.id) for x in state.harpy_states]
    result = []
    for actor in actors:
        try:
            body = resolve(state, actor, ())
        except ValueError:
            continue
        if body.controller != viewer.user_id and unlinked(state, body) and body.girl == "harpy":
            result.append((actor.entity, body.label))
    return tuple(result)


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    source: str,
    target: str,
    selector: IndexSource,
    rng_source: Literal["os", "test_injected"],
) -> None:
    period = strain.periods._get(c, row["off_duty_id"])
    handler = active_handler(state)
    harpy = ActorRef(kind="external_pilot", entity=target)
    HarpyDefeatService(strain.store, strain.game)._runtime(c, state, harpy)
    harpy_body = resolve(state, harpy, ())
    world = state.world
    base = (
        next(
            (
                x
                for x in world.locations
                if x.cell == harpy_body.cell
                and x.kind == "base"
                and x.foundation_operational
                and in_responsibility(state, x.cell)
            ),
            None,
        )
        if world
        else None
    )
    members = HandlerService(strain.store)
    if (
        handler is None
        or base is None
        or harpy_body.girl != "harpy"
        or not unlinked(state, harpy_body)
        or harpy_body.controller == period.handler
        or not members._member(c, harpy_body.controller)
        or any(x.id == row["id"] for x in rules.encounters(state))
    ):
        raise WorkflowError("Use a living unlinked Harpy under independent control at a Cadre base")
    known = profiles(c, strain.store.campaign_id)
    population = []
    for owner in period.pilots:
        if (
            owner == harpy_body.controller
            or str(owner) in period.ended_characters
            or not members._member(c, owner)
        ):
            continue
        actor = current_ref(state, owner)
        if period.character_ids.get(actor.entity) != actor.incarnation:
            raise WorkflowError("Recover the exact original Off-Duty roster before drawing")
        body = resolve(state, actor, known, require_current_profile=False)
        if body.cell == base.cell and unlinked(state, body):
            population.append(actor)
    if not population:
        raise WorkflowError("Recover at least one actual Girl outside her Frame at this base")
    rules.save(
        state,
        rules.Encounter(
            id=row["id"],
            source=source,
            period=period.id,
            handler=handler,
            harpy=harpy,
            controller=harpy_body.controller,
            base=base.id,
            cell=base.cell,
            population=tuple(population),
            index=selector.choose(len(population)),
            rng_source=rng_source,
        ),
    )


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Encounter, ...]:
    result = []
    for case in rules.encounters(state):
        uid = str(viewer.user_id)
        if viewer.user_id == case.controller:
            try:
                if resolve(state, case.harpy, ()).controller == viewer.user_id:
                    result.append(case)
            except ValueError:
                continue
        elif case.girl.entity == uid and case.arrived is not None:
            sheet = state.sheets.get(uid)
            if sheet is not None and sheet.character_id == case.girl.incarnation:
                result.append(case)
        elif case.handler.entity == uid and case.disclosed is not None:
            if same_handler_body(state, case.handler):
                result.append(case)
    return tuple(result)


def options(case: rules.Encounter, viewer: GuildViewer) -> tuple[tuple[str, str], ...]:
    if viewer.user_id == case.controller:
        if case.arrived is None:
            return (("appear", "Enter the Girl's bunk"),)
        if case.disclosed is None:
            return (("late", "Leave the bunk before the Handler notices"),)
    if (
        case.girl.entity == str(viewer.user_id)
        and case.arrived is not None
        and case.disclosed is None
    ):
        return (("contact", "Contact the Handler"),)
    return ()


class BunkService:
    def __init__(self, strain: StrainService):
        self.strain, self.game, self.store = strain, strain.game, strain.store

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Encounter:
        case = next((x for x in visible(state, viewer) if x.id == identity), None)
        if case is None:
            raise WorkflowError("This bunk encounter belongs to its actual original audience")
        return case

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            girl = state.sheets.get(case.girl.entity)
            harpy = resolve(state, case.harpy, (), require_alive=False)
            receiving = viewer.user_id == int(case.handler.entity)
            girl_name = (
                girl.callsign
                if girl is not None and girl.character_id == case.girl.incarnation
                else "Original Girl"
            )
            return dict(
                revision=state.revision,
                girl=girl_name if not receiving or case.method == "contact" else "",
                harpy=harpy.label if not receiving else "",
                method=case.method,
                appearance=case.appearance if not receiving else "",
                disclosure=case.disclosure,
                options=options(case, viewer),
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
        account: str,
    ) -> dict[str, Any]:
        account = account.strip()
        if not 0 < len(account) <= 900:
            raise WorkflowError(
                "Describe the actual appearance, contact or late notice in up to 900 characters"
            )

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            self._case(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, revision)
            case = self._case(state, viewer, identity)
            if choice not in {x[0] for x in options(case, viewer)}:
                raise WorkflowError("Only the original performer may make this current bunk choice")
            row = EffectService(self.strain)._row(c, identity)
            source = json.loads(row["body_json"])
            period = self.strain.periods._get(c, case.period)
            if (
                row["off_duty_id"] != case.period
                or row["owner_id"] != case.handler.entity
                or source.get("rule_id") != rules.RULE
                or source.get("bunk_requested") != case.source
                or not same_handler_body(state, case.handler)
                or not all(
                    HandlerService(self.store)._member(c, user)
                    for user in (case.controller, int(case.girl.entity), int(case.handler.entity))
                )
                or current_ref(state, int(case.girl.entity)) != case.girl
                or HarpyDefeatService(self.store, self.game)
                ._runtime(c, state, case.harpy)
                .controller
                != case.controller
            ):
                raise WorkflowError(
                    "Recover the actual original bunk encounter and present players"
                )
            event = str(uuid4())
            if choice == "appear":
                known = profiles(c, self.store.campaign_id)
                if (
                    period.phase != "preparing"
                    or row["state"] != "pending"
                    or state.world is None
                    or not any(
                        x.id == case.base and x.cell == case.cell and x.foundation_operational
                        for x in state.world.locations
                    )
                    or any(
                        body.cell != case.cell or not unlinked(state, body)
                        for body in (
                            resolve(state, case.harpy, ()),
                            resolve(state, case.girl, known, require_current_profile=False),
                        )
                    )
                ):
                    raise WorkflowError(
                        "Both original bodies must be outside their Frames at the actual base"
                    )
                updated = case.model_copy(update=dict(arrived=event, appearance=account))
            else:
                if row["state"] != "resolved" or source.get("bunk_arrived") != case.arrived:
                    raise WorkflowError(
                        "Recover the actual Harpy arrival before sharing any knowledge"
                    )
                updated = case.model_copy(
                    update=dict(method=choice, disclosed=event, disclosure=account)
                )
            rules.save(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.void_bunk_encounter",
                state,
                event_id=event,
                work_id=identity,
            )
            if choice == "appear":
                self.strain._save(c, row, event, source | {"bunk_arrived": event}, resolved=True)
            return dict(id=identity, stage=choice)

        return self.strain.missions._write(
            viewer,
            key,
            "m3.void_bunk_encounter",
            dict(id=identity, revision=revision, choice=choice, account=account),
            operation,
            authorize,
        )
