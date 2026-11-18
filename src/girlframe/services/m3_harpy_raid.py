"""Require an actual completed attack between the original actors at the base."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_raid as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Context
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _context_proof
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    event: str,
    harpy: str,
    base: str,
    obsession: int,
) -> None:
    world = state.world
    site = next((x for x in world.locations if x.id == base), None) if world else None
    handler = active_handler(state)
    period = strain.periods._get(c, row["off_duty_id"])
    if (
        site is None
        or site.kind != "base"
        or not site.operational
        or site.allegiance != "foundation"
        or not in_responsibility(state, site.cell)
        or handler is None
        or obsession not in period.pilots
        or not period.pilots
        or any(x.id == row["id"] for x in rules.raids(state))
    ):
        raise WorkflowError("Choose the actual occupied Foundation base and original Girl")
    people = tuple(current_ref(state, uid) for uid in period.pilots)
    if any(period.character_ids.get(x.entity) != x.incarnation for x in people):
        raise WorkflowError("Recover the actual original Cadre")
    ref = ActorRef(kind="external_pilot", entity=harpy)
    HarpyDefeatService(strain.store, strain.game)._runtime(c, state, ref)
    bound = profiles(c, strain.store.campaign_id)
    attacker = resolve(state, ref, bound, require_current_profile=False)
    defenders = tuple(
        x
        for x in people
        if resolve(state, x, bound, require_current_profile=False).cell == site.cell
    )
    if (
        not defenders
        or attacker.girl != "harpy"
        or attacker.cell != site.cell
        or attacker.custody not in (None, "free")
        or not HandlerService(strain.store)._member(c, attacker.controller)
    ):
        raise WorkflowError("Stage the actual free Harpy and original Cadre at the occupied base")
    rules.save(
        state,
        rules.Raid(
            id=row["id"],
            source=event,
            base=site.id,
            cell=site.cell,
            harpy=ref,
            controller=attacker.controller,
            handler=handler,
            obsession=current_ref(state, obsession),
            defenders=defenders,
        ),
    )


class RaidService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _own(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Raid:
        raid = next((x for x in rules.raids(state) if x.id == identity), None)
        if raid is None or viewer.user_id not in (raid.controller, int(raid.handler.entity)):
            raise WorkflowError("Only the original Harpy controller and Handler have this raid")
        return raid

    def _prove(
        self,
        c: Connection,
        state: GameState,
        raid: rules.Raid,
        action: dict[str, Any],
    ) -> None:
        battle = action["data"].get("battle") or {}
        fact = next(
            (
                x
                for x in reversed(state.facts)
                if x.get("kind") == "battle_context" and x.get("id") == battle.get("context")
            ),
            None,
        )
        actual = Context.model_validate_json(fact["body"]) if fact else None
        if (
            action["state"] != "complete"
            or action["actor_id"] != str(raid.controller)
            or actual is None
            or actual.scene != action["scene_id"]
            or actual.declaration.play != "all_out_assault"
            or actual.declaration.actor != raid.harpy
            or actual.declaration.target not in raid.defenders
            or any(x.action == action["id"] for x in rules.raids(state))
            or not any(
                x.get("kind") == "battle_context_used"
                and x.get("action") == action["id"]
                and x.get("context") == actual.id
                and x.get("event") == battle.get("roll_event")
                for x in state.facts
            )
        ):
            raise WorkflowError("Choose the original Harpy's unused completed Assault")
        _context_proof(self.game, c, actual)
        receipt = t.m2["m2_receipts"]
        receipt_id = c.scalar(
            sa.select(receipt.c.id).where(
                receipt.c.campaign_id == self.store.campaign_id,
                receipt.c.action_id == action["id"],
            )
        )
        if not receipt_id or action["data"].get("receipt", {}).get("id") != receipt_id:
            raise WorkflowError("Recover the actual attack's saved dice receipt")
        events, history = t.events, t.m2["m2_state_history"]
        start = c.scalar(
            sa.select(events.c.seq).where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.id == raid.source,
            )
        )
        reviewed = c.execute(
            sa.select(events.c.seq, history.c.body_json)
            .join(
                history,
                (events.c.campaign_id == history.c.campaign_id)
                & (events.c.id == history.c.event_id),
            )
            .where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.id == actual.confirmed_event,
            )
        ).first()
        if start is None or reviewed is None or reviewed.seq <= start:
            raise WorkflowError("Use a real new battle at the base after this source")
        original = GameState.model_validate_json(reviewed.body_json)
        binding = snapshot_profiles(c, self.store.campaign_id, original)
        if (
            original.world is None
            or not any(x.id == raid.base and x.cell == raid.cell for x in original.world.locations)
            or any(
                resolve(original, ref, binding, require_current_profile=False).cell != raid.cell
                for ref in (raid.harpy, actual.declaration.target)
            )
        ):
            raise WorkflowError("The completed attack must have taken place at this actual base")

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            raid = self._own(state, viewer, identity)
            eligible = []
            if viewer.user_id == raid.controller and not raid.action:
                actions = t.m2["m2_actions"]
                for row in c.execute(
                    sa.select(actions).where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.actor_id == str(viewer.user_id),
                        actions.c.state == "complete",
                    )
                ).mappings():
                    action = dict(row) | {"data": json.loads(row["body_json"])}
                    try:
                        self._prove(c, state, raid, action)
                    except (WorkflowError, ValueError):
                        continue
                    eligible.append((action["id"], f"Completed Assault · {action['id'][:8]}"))
            site = (
                next(
                    (x.name for x in state.world.locations if x.id == raid.base),
                    raid.base,
                )
                if state.world
                else raid.base
            )
            subject = state.sheets.get(raid.obsession.entity)
            return dict(
                revision=state.revision,
                attacks=tuple(eligible),
                base=site,
                obsession=subject.callsign
                if subject and subject.character_id == raid.obsession.incarnation
                else "original selected Girl",
                action=raid.action,
            )

    def finish(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: str,
    ) -> dict[str, str]:
        def authorization(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.strain.missions.access.authorize(c, viewer, "plays")
            self.game.unpaused(c)
            raid = self._own(load_state(c, self.store.campaign_id), viewer, identity)
            if raid.controller != viewer.user_id:
                raise WorkflowError("Only the original Harpy's controller confirms the actual raid")

        def operation(c: Connection) -> dict[str, str]:
            state = self.strain._state(c, expected)
            raid = self._own(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                raid.action
                or row["state"] != "pending"
                or body["rule_id"] != rules.RULE
                or body.get("raid_requested") != raid.source
                or not same_handler_body(state, raid.handler)
                or self.strain.periods._get(c, row["off_duty_id"]).phase != "preparing"
            ):
                raise WorkflowError("Recover the original still-pending raid")
            self._prove(c, state, raid, self.game.action(c, action))
            event = str(uuid4())
            rules.save(state, raid.model_copy(update=dict(action=action, completion=event)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_harpy_raid_completed",
                state,
                event_id=event,
                work_id=identity,
                action_id=action,
            )
            self.strain._save(c, row, event, body | {"raid_action": action}, resolved=True)
            return dict(id=identity, state="resolved", action=action)

        return self.strain.missions._write(
            viewer,
            key,
            "m3.strain_harpy_raid_completed",
            dict(id=identity, expected=expected, action=action),
            operation,
            authorization,
        )
