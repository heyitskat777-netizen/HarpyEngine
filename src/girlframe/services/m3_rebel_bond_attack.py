"""A private authored betrayal closes only after a genuine original Cadre intervention."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_bond_attack as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import clear_helpless, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Attack, ...]:
    result = []
    human = str(viewer.user_id)
    for attack in rules.attacks(state):
        if viewer.user_id == attack.controller or (
            human == attack.handler.entity and same_handler_body(state, attack.handler)
        ):
            result.append(attack)
            continue
        original = state.sheets.get(human)
        if (
            attack.attempt
            and original is not None
            and any(
                x.entity == human and x.incarnation == original.character_id
                for x in attack.defenders
            )
        ):
            result.append(attack)
    return tuple(result)


def _event(c: Connection, strain: StrainService, identity: str | None) -> Any:
    return c.execute(
        sa.select(
            t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json, t.events.c.seq
        ).where(
            t.events.c.campaign_id == strain.store.campaign_id,
            t.events.c.id == identity,
        )
    ).first()


class AttackService:
    def __init__(self, strain: StrainService):
        self.strain, self.game, self.store = strain, strain.game, strain.store

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Attack:
        case = next((x for x in visible(state, viewer) if x.id == identity), None)
        if case is None:
            raise WorkflowError("This original betrayal belongs to its actual involved parties")
        return case

    def _present(
        self,
        c: Connection,
        state: GameState,
        case: rules.Attack,
        channel: int,
    ) -> tuple[SceneCast | None, tuple[ActorRef, ...]]:
        from girlframe.services.m3_battle import _cast

        try:
            cast = _cast(self.game, c, state, channel)
        except WorkflowError:
            return None, ()
        period = self.strain.periods._get(c, case.period)
        present = {x.actor: x.controller for x in cast.roles}
        if present.get(case.assassin) != case.controller or present.get(case.handler) != int(
            case.handler.entity
        ):
            return None, ()
        body = resolve(state, case.handler, ())
        attacker = resolve(state, case.assassin, ())
        if (
            body.cell is None
            or body.cell != attacker.cell
            or attacker.custody not in (None, "free")
        ):
            return None, ()
        bound = profiles(c, self.store.campaign_id)
        return cast, tuple(
            x.actor
            for x in cast.roles
            if x.actor.kind == "pilot"
            and x.controller == int(x.actor.entity)
            and x.controller != case.controller
            and period.character_ids.get(x.actor.entity) == x.actor.incarnation
            and x.actor.entity not in period.ended_characters
            and resolve(state, x.actor, bound, require_current_profile=False).cell == body.cell
        )

    def _rescue(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        case: rules.Attack,
        action: dict[str, Any],
    ) -> str | None:
        if (
            case.cast is None
            or case.attempt is None
            or action["state"] != "complete"
            or action["scene_id"] != case.cast.id
        ):
            return None
        data = action["data"]
        meta = data.get("battle") or {}
        if (
            action["actor_id"] != str(viewer.user_id)
            or data.get("play") != "go_for_the_core"
            or meta.get("target") != case.assassin.model_dump(mode="json")
            or not any(
                x.entity == action["actor_id"] and meta.get("actor") == x.model_dump(mode="json")
                for x in case.defenders
            )
        ):
            return None
        death = _event(c, self.strain, meta.get("fatal_event"))
        attempted = _event(c, self.strain, case.attempt)
        if (
            death is None
            or attempted is None
            or death.kind != "m3.battle_actual_death"
            or death.seq <= attempted.seq
        ):
            return None
        payload = json.loads(death.payload_json)
        npc = rules.actor(state, case.assassin.entity, alive=False)
        if (
            npc.alive
            or payload.get("action_id") != action["id"]
            or payload.get("target") != case.assassin.model_dump(mode="json")
        ):
            return None
        return str(meta["fatal_event"])

    def get(self, viewer: GuildViewer, identity: str, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            is_rescuer = any(x.entity == str(viewer.user_id) for x in case.defenders)
            choices = []
            if is_rescuer and case.cast is not None and not case.finished:
                actions = t.m2["m2_actions"]
                for action_id in c.scalars(
                    sa.select(actions.c.id).where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.scene_id == case.cast.id,
                        actions.c.actor_id == str(viewer.user_id),
                        actions.c.state == "complete",
                    )
                ):
                    if self._rescue(c, state, viewer, case, self.game.action(c, action_id)):
                        choices.append((action_id, "Recover actual Core strike " + action_id[:8]))
            return dict(
                revision=state.revision,
                finished=bool(case.finished),
                attempted=bool(case.attempt),
                can_attempt=(
                    viewer.user_id == case.controller
                    and not case.attempt
                    and bool(self._present(c, state, case, channel)[1])
                ),
                account=case.attempt_account,
                rescues=tuple(choices),
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        *,
        account: str = "",
        action: str | None = None,
    ) -> dict[str, Any]:
        account = account.strip()
        if (action is None and not 0 < len(account) <= 1200) or (action is not None and account):
            raise WorkflowError(
                "Record your own actual attempt or identify the original rescue Play"
            )

        def authorize(c: Connection) -> None:
            for scope in ("strain", "plays", "world"):
                self.strain.missions.access.authorize(c, viewer, scope)
            self.game.unpaused(c)
            self._case(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, revision)
            case = self._case(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            period = self.strain.periods._get(c, case.period)
            if (
                row["state"] != "pending"
                or row["off_duty_id"] != case.period
                or row["owner_id"] != case.handler.entity
                or body.get("rule_id") != rules.RULE
                or body.get("bond_attack_requested") != case.source
                or period.phase != "preparing"
                or case.finished
                or not same_handler_body(state, case.handler)
            ):
                raise WorkflowError("Recover the actual pending High Rebellion betrayal")
            event = str(uuid4())
            if action is None:
                npc = rules.actor(state, case.assassin.entity)
                cast, defenders = self._present(c, state, case, channel)
                if (
                    case.attempt
                    or npc.controller != viewer.user_id
                    or case.controller != viewer.user_id
                    or case.faction not in npc.secret_factions
                    or cast is None
                    or not defenders
                    or not all(
                        HandlerService(self.store)._member(c, user)
                        for user in (
                            case.controller,
                            int(case.handler.entity),
                            *(int(x.entity) for x in defenders),
                        )
                    )
                ):
                    raise WorkflowError(
                        "Use the original Rebel and Handler with an actual present Cadre defender"
                    )
                state = make_helpless(state, case.handler, case.assassin, event)
                updated = case.model_copy(
                    update=dict(
                        cast=cast, defenders=defenders, attempt=event, attempt_account=account
                    )
                )
            else:
                proof = self._rescue(c, state, viewer, case, self.game.action(c, action))
                if proof is None:
                    raise WorkflowError(
                        "Use the original Cadre defender's completed Core strike"
                    )
                if any(
                    x.active
                    and x.subject == case.handler
                    and x.foe == case.assassin
                    and x.source_events == (case.attempt,)
                    for x in state.helpless_conditions
                ):
                    state = clear_helpless(state, case.handler, event, case.assassin)
                updated = case.model_copy(update=dict(defense=proof, finished=event))
            rules.save(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.rebel_bond_attack",
                state,
                event_id=event,
                work_id=identity,
            )
            if updated.finished:
                self.strain._save(
                    c, row, event, body | dict(bond_defended=updated.defense), resolved=True
                )
            return dict(id=identity, finished=bool(updated.finished))

        return self.strain.missions._write(
            viewer,
            key,
            "m3.rebel_bond_attack",
            dict(id=identity, revision=revision, channel=channel, account=account, action=action),
            operation,
            authorize,
        )
