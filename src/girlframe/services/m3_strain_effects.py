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
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_contraband_state import ContrabandFind
from girlframe.engine.m3_supply_state import SupplyLoss
from girlframe.engine.rolls import IndexSource, OsIndex
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
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
            if choice.rule_id in ("strain.budget.low.1.1", "strain.budget.low.1.2"):
                period = self.strain.periods._get(c, row["off_duty_id"])
                if set(period.pilots) != set(state.order) or any(
                    period.character_ids.get(str(uid)) != state.sheets[str(uid)].character_id
                    for uid in period.pilots
                ):
                    raise WorkflowError("Review the original photoshoot participants before Tags")
                if choice.rule_id == "strain.budget.low.1.1":
                    from girlframe.services.m3_medical import MedicalService

                    _, public_appointment = MedicalService(self.store)._handler(c)
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
