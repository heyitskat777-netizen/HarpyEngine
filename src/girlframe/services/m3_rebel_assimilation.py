"""The selected group's new employment Play is authored and used by its Handler."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_assimilation as rules
from girlframe.engine import m3_rebel_funding as funding
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_state import load_state
from girlframe.services.m3_budget_tags import _selection, _work
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

INSTALL = "m3.rebel_assimilation_established"
USE = "m3.foundation_employment_play"


class AssimilationService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _source(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
        rule: str = rules.RULE,
    ) -> tuple[dict[str, Any], str]:
        row, original = _selection(c, self.game, identity, rule=rule)
        handler = active_handler(original)
        body = json.loads(row["body_json"])
        selection = (
            next((x for x in original.strain.endgames if x.id == body["source_work"]), None)
            if original.strain
            else None
        )
        if (
            handler is None
            or handler.entity != str(viewer.user_id)
            or row["owner_id"] != handler.entity
            or not same_handler_body(state, handler)
            or selection is None
            or selection.faction is None
        ):
            raise WorkflowError(
                "Only the original Handler can act on the selected group's work Play"
            )
        return row, selection.faction

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            rule = json.loads(_work(c, self.store, identity)["body_json"]).get("rule_id")
            if rule not in (rules.RULE, funding.RULE):
                raise WorkflowError("Open the actual original assimilation Endgame")
            row, faction = self._source(c, state, viewer, identity, rule)
            value = next((x for x in rules.assimilations(state) if x.id == identity), None)
            group = (
                next((x for x in state.world.factions if x.id == faction), None)
                if state.world
                else None
            )
            return dict(
                revision=state.revision,
                installed=value is not None,
                phase=row["state"],
                group=group.name if group else "Original group",
                play=value.employment_play if value else None,
                rule=rule,
                funding_groups=tuple(
                    (x.id, x.name)
                    for x in state.world.factions
                    if x.id != faction and x.kind == "rebel" and x.active
                )
                if state.world and rule == funding.RULE
                else (),
            )

    def install(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        play: rules.EmploymentPlay | None = None,
        *,
        funded_group: str | None = None,
        account: str = "",
    ) -> dict[str, Any]:
        if play is not None:
            play = rules.EmploymentPlay.model_validate(
                {k: v.strip() for k, v in play.model_dump().items()}
            )
        account = account.strip()
        if (play is None) != (funded_group is not None) or (
            funded_group is not None and not 0 < len(account) <= 1200
        ):
            raise WorkflowError(
                "Record the actual work Play or the separate secretly funded original group"
            )
        rule = funding.RULE if funded_group is not None else rules.RULE

        def authorize(c: Connection) -> None:
            for scope in ("strain", "world", "plays"):
                self.strain.missions.access.authorize(c, viewer, scope)
            self.game.unpaused(c)
            self._source(c, load_state(c, self.store.campaign_id), viewer, identity, rule)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, revision)
            row, group_id = self._source(c, state, viewer, identity, rule)
            group = (
                next((x for x in state.world.factions if x.id == group_id), None)
                if state.world
                else None
            )
            handler = active_handler(state)
            if (
                row["state"] != "pending"
                or group is None
                or handler is None
                or self.strain.periods._get(c, row["off_duty_id"]).phase != "preparing"
            ):
                raise WorkflowError("Recover the actual original active group and pending Endgame")
            event = str(uuid4())
            changed = rules.assimilate(
                state,
                rules.Assimilation(
                    id=identity,
                    original=group,
                    handler=handler,
                    source=row["event_id"],
                    rule=rule,
                    event=event,
                    employment_play=play,
                ),
            )
            if funded_group is not None:
                funding.fund(
                    changed,
                    funding.Funding(
                        id=identity,
                        group=funded_group,
                        sponsor=handler,
                        event=event,
                        account=account,
                    ),
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                INSTALL,
                changed,
                event_id=event,
                work_id=identity,
                faction=group.id,
            )
            self.strain._save(c, row, event, json.loads(row["body_json"]), resolved=True)
            return dict(id=identity, state="resolved")

        return self.strain.missions._write(
            viewer,
            key,
            INSTALL,
            dict(id=identity, revision=revision, play=play.model_dump(mode="json"))
            if play
            else dict(id=identity, revision=revision, funded_group=funded_group, account=account),
            operation,
            authorize,
        )

    def use(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        *,
        trigger_met: bool,
        account: str,
    ) -> dict[str, Any]:
        account = account.strip()
        if trigger_met is not True or not 0 < len(account) <= 1200:
            raise WorkflowError(
                "Confirm the original trigger and describe your own work in this scene"
            )

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "plays")
            self.game.unpaused(c)
            self._source(c, load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_rebel_ambush import _cast

            state = self.strain._state(c, revision)
            handler = active_handler(state)
            value = next((x for x in rules.assimilations(state) if x.id == identity), None)
            cast = _cast(self.game, c, state, channel)
            if (
                handler is None
                or handler.entity != str(viewer.user_id)
                or value is None
                or cast is None
                or not any(
                    x.controller == viewer.user_id and same_handler_body(state, x.actor)
                    for x in cast.roles
                )
            ):
                raise WorkflowError(
                    "Run the original Handler's work Play in an actual joined scene"
                )
            proof = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.event,
                )
            ).first()
            if proof is None or proof.kind != INSTALL or proof.actor_id != handler.entity:
                raise WorkflowError("Recover the original installed employment Play")
            event = str(uuid4())
            rules.apply_play(
                state,
                value,
                rules.WorkPlayUse(
                    id=event,
                    employment=identity,
                    play_source=value.event,
                    handler=handler,
                    scene=cast.id,
                    account=account,
                ),
            )
            self.game.event(
                c, viewer.user_id, key, USE, state, event_id=event, work_id=identity, scene=cast.id
            )
            return dict(id=identity, event=event)

        return self.strain.missions._write(
            viewer,
            key,
            USE,
            dict(
                id=identity,
                revision=revision,
                channel=channel,
                trigger_met=trigger_met,
                account=account,
            ),
            operation,
            authorize,
        )
