"""Source-bound Strain effects; selection/description never substitutes for mechanics."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_strain_effects as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_contraband_state import ContrabandFind
from girlframe.engine.m3_supply_state import SupplyLoss
from girlframe.engine.rolls import IndexSource, OsIndex
from girlframe.services.m2_state import load_state
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class EffectService:
    def __init__(self, strain: StrainService, *, selector: IndexSource | None = None):
        self.strain, self.store, self.game = strain, strain.store, strain.game
        self.selector = selector if selector is not None else OsIndex()
        self.selection_source: Literal["os", "test_injected"] = (
            "os" if selector is None else "test_injected"
        )

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] != "strain_event":
            raise WorkflowError("Unknown Strain event effect.")
        return dict(row)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            self.strain.missions._handler(c, viewer)
            row = self._row(c, identity)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("This effect belongs to its assigned Handler.")
            body = json.loads(row["body_json"])
            state = load_state(c, self.store.campaign_id)
            supply = next((x for x in state.supply_losses if x.id == identity), None)
            label = "Original character"
            if supply is not None:
                try:
                    owner = int(supply.owner.entity)
                    if (
                        self.game.character_binding(c, state, owner, require_current_profile=False)
                        == supply.owner.incarnation
                    ):
                        label = state.sheets[str(owner)].callsign
                except WorkflowError:
                    pass
            return {
                **{k: row[k] for k in ("id", "revision", "state", "off_duty_id")},
                "rule_id": body["rule_id"],
                "supported": body["rule_id"] in rules.SUPPORTED,
                "game_revision": state.revision,
                "supply_outcome": {
                    "recipient": label,
                    "resource": supply.resource,
                    "rng_source": supply.rng_source,
                    "population_size": len(supply.population),
                }
                if supply is not None
                else None,
            }

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        choice: rules.Choice,
    ) -> dict[str, Any]:
        choice = rules.Choice.model_validate_json(choice.model_dump_json())

        def authorize(c: Connection) -> None:
            self.strain._authorize(c, viewer)
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.engine.m3_actor_bonds import current_ref
            from girlframe.engine.m3_actors import resolve
            from girlframe.services.m3_actors import profiles

            row = self._row(c, identity)
            self.strain._check(c, viewer, row, revision)
            state = self.strain._state(c, game_revision)
            if json.loads(row["body_json"])["rule_id"] != choice.rule_id:
                raise WorkflowError(
                    "The selected effect does not match this actual saved Strain event."
                )
            event_id = str(uuid4())
            supply = None
            contraband = None
            public_appointment = None
            cleanup_index = None
            cleanup_rng = None
            if choice.rule_id == "strain.budget.high.6.1":
                from girlframe.services.m3_medical import MedicalService

                _, public_appointment = MedicalService(self.store)._handler(c)
            if choice.rule_id in (
                "strain.budget.low.1.1",
                "strain.budget.low.1.2",
                "strain.budget.low.2.1",
                "strain.budget.low.2.2",
                "strain.budget.low.4.1",
                "strain.budget.low.5.1",
                "strain.budget.low.6.1",
                "strain.budget.high.4.1",
                "strain.budget.high.6.1",
                "strain.rebellion.low.5.2",
                "strain.rebellion.high.4.2",
            ):
                period = self.strain.periods._get(c, row["off_duty_id"])
                if set(period.pilots) != set(state.order) or any(
                    period.character_ids.get(str(uid)) != state.sheets[str(uid)].character_id
                    for uid in period.pilots
                ):
                    raise WorkflowError("Review the original photoshoot participants before Tags")
                if choice.rule_id == "strain.budget.low.1.1":
                    from girlframe.services.m3_medical import MedicalService

                    _, public_appointment = MedicalService(self.store)._handler(c)
            if choice.rule_id == "strain.budget.high.4.1":
                from girlframe.services.m3_actors import ActorService
                from girlframe.services.m3_cast import CastService

                rules.fields(choice, {"target", "fighters", "fight_channel"})
                if (
                    choice.fight_channel is None
                    or len(set(choice.fighters)) != 2
                    or len(choice.fighters) != 2
                ):
                    raise WorkflowError("Choose two actual distinct Girls and this real Play scene")
                scene = self.game.scene(c, choice.fight_channel)
                cast, _ = CastService(ActorService(self.strain.missions))._current(
                    c, state, choice.fight_channel
                )
                fight_refs = tuple(current_ref(state, uid) for uid in choice.fighters)
                if (
                    scene["id"] != choice.target
                    or cast.facilitator != state.handler
                    or any(
                        not any(
                            x.actor == ref and x.controller == int(ref.entity) for x in cast.roles
                        )
                        for ref in fight_refs
                    )
                ):
                    raise WorkflowError(
                        "Join both original Girls and the actual facilitator to this fight scene"
                    )
                bodies = [
                    resolve(state, x, profiles(c, self.store.campaign_id)) for x in fight_refs
                ]
                if bodies[0].cell is None or bodies[0].cell != bodies[1].cell:
                    raise WorkflowError(
                        "Record known actual co-present fight bodies; no movement is inferred"
                    )
            if choice.rule_id == "strain.budget.low.4.1":
                rules.fields(choice, {"target", "victim", "cleanup_mode"})
                past = self.strain.missions._mission(c, choice.victim or "")
                site = (
                    next((x for x in state.world.locations if x.id == choice.target), None)
                    if state.world
                    else None
                )
                if past.phase != "complete" or site is None or choice.cleanup_mode is None:
                    raise WorkflowError("Choose a completed past mission and its actual map site")
                if choice.cleanup_mode == "exposure":
                    for uid in state.order:
                        actual = resolve(
                            state,
                            current_ref(state, uid),
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        )
                        if (
                            actual.offstage_source
                            or actual.custody
                            or actual.subsumed
                            or actual.vitals_active is False
                            or actual.cell is not None
                            and actual.cell != site.cell
                        ):
                            raise WorkflowError(
                                "Recover cleanup exposure at this site before its random draw"
                            )
                    cleanup_index = self.selector.choose(len(state.order))
                    if type(cleanup_index) is not int or not 0 <= cleanup_index < len(state.order):
                        raise WorkflowError(
                            "The cleanup random source returned an invalid Cadre index"
                        )
                    cleanup_rng = self.selection_source
            if choice.rule_id == "strain.rebellion.low.2.2":
                rules.fields(choice, {"target"})
                period = self.strain.periods._get(c, row["off_duty_id"])
                base = (
                    next(
                        (
                            x
                            for x in state.world.locations
                            if x.id == choice.target
                            and x.kind == "base"
                            and x.allegiance == "foundation"
                            and x.condition != "destroyed"
                        ),
                        None,
                    )
                    if state.world
                    else None
                )
                if base is None or set(period.pilots) != set(state.order):
                    raise WorkflowError(
                        "Use the actual Cadre and surviving Foundation base for this find."
                    )
                population = tuple(
                    ActorRef(
                        kind="pilot",
                        entity=str(uid),
                        incarnation=self.game.character_binding(
                            c, state, uid, require_current_profile=False
                        ),
                    )
                    for uid in period.pilots
                )
                if any(period.character_ids.get(x.entity) != x.incarnation for x in population):
                    raise WorkflowError(
                        "Recover the original period characters before the random find."
                    )
                for actor in population:
                    actual = resolve(
                        state,
                        actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    if actual.cell is not None and actual.cell != base.cell:
                        raise WorkflowError(
                            "The event cannot move a known absent Girl to this base. "
                            "Resolve actual travel first."
                        )
                index = self.selector.choose(len(population))
                # Validate before indexing; bool/negative/out-of-range results never select a Girl.
                if type(index) is not int or not 0 <= index < len(population):
                    raise WorkflowError("The random source did not produce a valid Cadre index.")
                contraband = ContrabandFind(
                    id=identity,
                    period=period.id,
                    source_event=event_id,
                    base=base.id,
                    population=population,
                    index=index,
                    rng_source=self.selection_source,
                    label=state.sheets[population[index].entity].callsign,
                )
            if choice.rule_id == "strain.budget.low.3.2":
                rules.fields(choice, {"missing_resource"})
                if not choice.missing_resource or not choice.missing_resource.strip():
                    raise WorkflowError("Describe the actual resource missing from the shipment.")
                period = self.strain.periods._get(c, row["off_duty_id"])
                if period.phase != "preparing" or any(
                    x.roll is not None or x.action_id is not None for x in period.progress.values()
                ):
                    raise WorkflowError(
                        "The random supply loss must be bound before this period's Plays."
                    )
                population = tuple(
                    ActorRef(
                        kind="pilot",
                        entity=str(uid),
                        incarnation=self.game.character_binding(
                            c, state, uid, require_current_profile=False
                        ),
                    )
                    for uid in period.pilots
                )
                if any(period.character_ids.get(x.entity) != x.incarnation for x in population):
                    raise WorkflowError(
                        "Recover the actual unchanged period characters before drawing."
                    )
                index = self.selector.choose(len(population))
                supply = SupplyLoss(
                    id=identity,
                    period=period.id,
                    source_event=event_id,
                    population=population,
                    index=index,
                    rng_source=self.selection_source,
                    resource=choice.missing_resource,
                )
            if (
                choice.rule_id in {"strain.void.low.4.1", "strain.void.low.5.1"}
                and choice.victim is not None
            ):
                from girlframe.services.m3_world import require_onstage

                require_onstage(state, ActorRef(kind="npc", entity=choice.victim))
                victim_body = resolve(state, ActorRef(kind="npc", entity=choice.victim), ())
                if victim_body.cell is None or (
                    choice.gorgon is not None and victim_body.cell != choice.gorgon.cell
                ):
                    raise WorkflowError(
                        "Choose the present original NPC at the introduction's actual location."
                    )
            if choice.rule_id == "strain.void.low.4.1":
                from girlframe.services.m3_battle_director import bind_legacy_context_bodies

                state = bind_legacy_context_bodies(self.game, c, state)
            updated = rules.apply(
                state,
                choice,
                identity,
                period_id=row["off_duty_id"],
                supply=supply,
                source_event=event_id,
                contraband=contraband,
                tag_setter_appointment=public_appointment,
                cleanup_index=cleanup_index,
                cleanup_rng=cleanup_rng,
            )
            scientific_period, scientific_events = None, []
            if choice.rule_id == "strain.budget.low.3.1":
                from girlframe.engine.m3_scientific_observation import materialize

                assert choice.scientific_demand is not None
                scientific_period = self.strain.periods._get(c, row["off_duty_id"])
                for subject in choice.scientific_demand.subjects:
                    character = self.game.character_binding(
                        c, updated, subject, require_current_profile=False
                    )
                    if scientific_period.character_ids.get(str(subject)) != character:
                        raise WorkflowError(
                            "Recover the actual scientific target's character first."
                        )
                    child_event = str(uuid4())
                    scientific_period, updated = materialize(
                        scientific_period,
                        updated,
                        viewer.user_id,
                        subject,
                        identity,
                        child_event,
                        character,
                    )
                    scientific_events.append((subject, child_event))
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_effect_applied",
                updated,
                event_id=event_id,
                work_id=identity,
                rule_id=choice.rule_id,
            )
            if choice.rule_id == "strain.void.low.4.1":
                from girlframe.services.m3_battle import synchronize_casts
                from girlframe.services.m3_battle_director import create_replacements
                from girlframe.services.m3_handler_void import synchronize_endings

                synchronize_casts(self.game, c, event)
                synchronize_endings(self.game, c, event, viewer, key)
                create_replacements(self.game, c, event)
            for event_index, (subject, child_event) in enumerate(scientific_events, start=1):
                self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.scientific_observation_ordered",
                    event_id=child_event,
                    event_index=event_index,
                    source_work=identity,
                    subject=subject,
                )
            if scientific_period is not None:
                self.strain.periods._save(c, scientific_period, event)
            if choice.rule_id == "strain.budget.low.4.1":
                from girlframe.engine.m3_budget_cleanup import get as get_cleanup
                from girlframe.services.m3_work import related

                cleanup = get_cleanup(updated, identity + ":cleanup")
                owner = (
                    int(cleanup.people[cleanup.selected].entity)
                    if cleanup.selected is not None
                    else viewer.user_id
                )
                related(
                    c,
                    self.store,
                    row,
                    cleanup.id,
                    owner,
                    owner,
                    "budget_cleanup",
                    dict(cleanup=cleanup.id, source_work=identity),
                    event,
                )
            if choice.rule_id == "strain.budget.high.4.1":
                from girlframe.services.m3_work import related

                related(
                    c,
                    self.store,
                    row,
                    identity + ":fight",
                    viewer.user_id,
                    viewer.user_id,
                    "budget_fight",
                    dict(fight=identity + ":fight", source_work=identity, due_stage="active"),
                    event,
                )
            if choice.rule_id == "strain.budget.high.4.2":
                from girlframe.services.m3_work import related

                related(
                    c,
                    self.store,
                    row,
                    identity + ":candidate",
                    viewer.user_id,
                    int(choice.victim or "0"),
                    "budget_candidate",
                    dict(candidate=identity + ":candidate", source_work=identity),
                    event,
                )
            if choice.rule_id == "strain.budget.high.1.1":
                from girlframe.services.m3_work import related

                related(
                    c,
                    self.store,
                    row,
                    identity + ":meeting",
                    viewer.user_id,
                    viewer.user_id,
                    "budget_director_meeting",
                    dict(meeting=identity + ":meeting", source_work=identity),
                    event,
                )
            if choice.rule_id == "strain.budget.low.6.1":
                from girlframe.services.m3_work import related

                related(
                    c,
                    self.store,
                    dict(row)
                    | dict(off_duty_id=None, scene_id=None, mission_id=None, campaign_context=True),
                    identity + ":assassination",
                    viewer.user_id,
                    viewer.user_id,
                    "budget_assassination",
                    dict(
                        assignment=identity + ":assassination",
                        source_work=identity,
                        source_period=row["off_duty_id"],
                    ),
                    event,
                )
            if choice.rule_id == "strain.budget.high.6.1":
                from girlframe.services.m3_work import related

                assert choice.storage_owner is not None
                related(
                    c,
                    self.store,
                    dict(row)
                    | dict(off_duty_id=None, scene_id=None, mission_id=None, campaign_context=True),
                    identity + ":storage",
                    viewer.user_id,
                    choice.storage_owner,
                    "budget_storage",
                    dict(
                        storage=identity + ":storage",
                        source_work=identity,
                        source_period=row["off_duty_id"],
                    ),
                    event,
                )
            if choice.rule_id == "strain.budget.low.5.1":
                from girlframe.services.m3_work import related

                related(
                    c,
                    self.store,
                    row,
                    identity + ":visit",
                    viewer.user_id,
                    viewer.user_id,
                    "budget_visitor",
                    dict(visit=identity + ":visit", source_work=identity),
                    event,
                )
            if choice.rule_id == "strain.rebellion.low.5.2":
                from girlframe.services.m3_work import related

                related(
                    c,
                    self.store,
                    row,
                    identity + ":contact",
                    viewer.user_id,
                    viewer.user_id,
                    "rebel_contact",
                    dict(contact=identity + ":contact", source_work=identity),
                    event,
                )
            if choice.rule_id == "strain.budget.low.2.1":
                from girlframe.services.m3_work import related

                related(
                    c,
                    self.store,
                    row,
                    identity + ":function",
                    viewer.user_id,
                    viewer.user_id,
                    "political_function",
                    dict(function=identity + ":function", source_work=identity),
                    event,
                )
            self.strain._save(
                c,
                row,
                event,
                json.loads(row["body_json"]) | {"choice": choice.model_dump(mode="json")},
                resolved=True,
            )
            return {"id": identity, "state": "resolved", "game_revision": updated.revision}

        try:
            return self.strain.missions._write(
                viewer,
                key,
                "m3.strain_effect_applied",
                {
                    "id": identity,
                    "revision": revision,
                    "game_revision": game_revision,
                    "choice": choice.model_dump(mode="json"),
                },
                operation,
                authorize,
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid Strain effect choices; reopen the current world review."
            ) from None
