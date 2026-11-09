"""AM's printed no-extra-roll path reads genuine counterpart sources privately."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_sex as learned
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, has_rule
from girlframe.engine.m3_learned_play_state import LearnedPlayUse
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, load_registry
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_dose_up import _cast, _native, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_learned_plays import _prove, _replace, available
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "girl.am.sex-play"
# These are existing actual source adapters, not substitute Plays or copied effects.
PARTNER_PLAYS = (
    "alpha_sex",
    "princess_sex",
    "mockingbird_sex",
    "stim_sex",
    "oldgen_sex",
    "casualty_sex",
    "vatgrown_sex",
    "newgirl_sex",
)


class SexService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(
        self,
        viewer: GuildViewer,
        channel: int,
        *,
        bonded_source: str | None = None,
        changeling_source: str | None = None,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            access = Access(self.store)
            access.authorize(c, viewer, "plays", director_response=True)
            assert access.registry is not None
            access.registry.require_available(RULE)
            state = load_state(c, self.store.campaign_id)
            if bonded_source is not None and changeling_source is not None:
                raise WorkflowError("Keep genuine psychic contact separate from Bonded delegation")
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None:
                raise WorkflowError("Use the actual original living Girl")
            borrowed_target: ActorRef | None = None
            if bonded_source is not None:
                from girlframe.engine import m3_bonded as bonded
                from girlframe.services.m3_bonded import admit_delegation

                route = bonded.get(state, bonded_source)
                if route.target is None:
                    raise WorkflowError("Use the actual original counterpart")
                channel = route.cast.channel
                borrowed_target = route.target
                admit_delegation(
                    self.game,
                    c,
                    state,
                    current_ref(state, viewer.user_id),
                    route.target,
                    RULE,
                    bonded_source,
                )
            elif changeling_source is not None:
                from girlframe.services.m3_changeling_sex import (
                    admit_contact,
                )
                from girlframe.services.m3_changeling_sex import (
                    prove as prove_remote,
                )

                remote_route = prove_remote(self.game, c, state, changeling_source)
                if remote_route.initiator.actor != current_ref(
                    state, viewer.user_id
                ) or not has_rule(sheet, RULE, "AM"):
                    raise WorkflowError(
                        "Only the actual original AM follows her real counterpart's Sex source"
                    )
                admit_contact(
                    self.game,
                    c,
                    state,
                    remote_route.performer,
                    remote_route.partner,
                    remote_route.rule,
                    remote_route.id,
                )
                borrowed_target = remote_route.performer
            elif not has_rule(sheet, RULE, "AM"):
                raise WorkflowError("This no-extra-roll source belongs to the actual original AM")
            actor = current_ref(state, viewer.user_id)
            scene = self.game.scene(c, channel)
            if viewer.user_id not in scene["participants"]:
                raise WorkflowError("Join the actual source scene first")
            table = t.m2["m2_actions"]
            sources = []
            owned_choices = self.game.choices(viewer)
            for saved in c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                    table.c.scene_id == scene["id"],
                )
            ).mappings():
                data = json.loads(saved["body_json"])
                play = data.get("play")
                if play not in PARTNER_PLAYS:
                    continue
                meta = data.get(play)
                if play == "mockingbird_sex":
                    meta = data.get("mockingbird")
                    targets = [x["actor"] for x in (meta or {}).get("parties", ())[:1]]
                elif play == "newgirl_sex":
                    targets = (meta or {}).get("partners", ())
                else:
                    targets = [(meta or {}).get("target")]
                if not isinstance(meta, dict) or not any(
                    x is not None and ActorRef.model_validate(x) == actor for x in targets
                ):
                    continue
                if bonded_source is not None and (
                    borrowed_target is None
                    or meta.get("actor") != borrowed_target.model_dump(mode="json")
                ):
                    continue
                if meta.get("actor") == actor.model_dump(mode="json"):
                    continue
                # Existing rule service rechecks genuine consent, incarnation and audience.
                actual = self.game.action(c, saved["id"])
                self.game.inspect(viewer, actual["id"])
                receipt = None
                if data.get("receipt"):
                    _roll_source(self.game, c, actual)
                    receipt = data["receipt"]["id"]
                sources.append(
                    dict(
                        id=actual["id"],
                        play=play,
                        state=actual["state"],
                        receipt=receipt,
                        choices=[x["id"] for x in owned_choices if x["action_id"] == actual["id"]],
                    )
                )
            return dict(
                actor=actor.model_dump(mode="json"),
                revision=state.revision,
                sources=sources,
                channel=channel,
                no_additional_roll=True,
                bonded_source=bonded_source,
                **(
                    {"changeling_source": changeling_source}
                    if changeling_source is not None
                    else {}
                ),
            )

    def bind_source(
        self, viewer: GuildViewer, key: str, source_id: str, action_id: str
    ) -> dict[str, Any]:
        """Bind the genuine counterpart Action, without another performance or roll."""

        def operation(c: sa.Connection) -> dict[str, Any]:
            from uuid import uuid4

            from girlframe.engine import m3_bonded as bonded
            from girlframe.services.m3_bonded import admit_delegation, prove

            self.game.unpaused(c)
            access = Access(self.store)
            access.authorize(c, viewer, "plays", director_response=True)
            assert access.registry is not None
            access.registry.require_available(RULE)

            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, source_id)
            if value.target is None or value.actor != current_ref(state, viewer.user_id):
                raise WorkflowError(
                    "Only the actual original Bonded owns this no-extra-roll source"
                )
            admit_delegation(self.game, c, state, value.actor, value.target, RULE, source_id)
            action = self.game.action(c, action_id)
            if (
                action["scene_id"] != value.cast.id
                or action["data"]["play"] not in PARTNER_PLAYS
                or str(action["actor_id"]) != value.target.entity
                or action["data"].get("character_ids", {}).get(value.target.entity)
                != value.target.incarnation
            ):
                raise WorkflowError("Use the actual original counterpart's real Sex source")
            # Reuse the ordinary source's own private inspection/proof and real roles.
            self.game.inspect(viewer, action_id)
            meta = action["data"].get(action["data"]["play"])
            if action["data"]["play"] == "mockingbird_sex":
                meta = action["data"].get("mockingbird")
                targets = [x["actor"] for x in (meta or {}).get("parties", ())[:1]]
            elif action["data"]["play"] == "newgirl_sex":
                targets = (meta or {}).get("partners", ())
            else:
                targets = [(meta or {}).get("target")]
            if not any(
                x is not None and ActorRef.model_validate(x) == value.actor for x in targets
            ):
                raise WorkflowError(
                    "The real source must involve this original Bonded, not their account"
                )
            existing = next(
                (x for x in bonded.records(state, bonded.Delegation) if x.source == source_id), None
            )
            if existing:
                if existing.session != action_id:
                    raise WorkflowError("Preserve the original no-extra-roll counterpart source")
                return dict(id=source_id, action=action_id)
            event = str(uuid4())
            bonded.put(
                state,
                bonded.Delegation(
                    id=source_id + ":delegation",
                    source=source_id,
                    session=action_id,
                    rule=RULE,
                    actor=value.actor,
                    target=value.target,
                    event=event,
                ),
            )
            bonded.put(state, value.model_copy(update=dict(phase="bound")))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bonded_am_source",
                state,
                event_id=event,
                source=source_id,
                action_id=action_id,
            )
            if action["state"] == "complete":
                from girlframe.services.m3_bonded import synchronize_delegation

                synchronize_delegation(self.game, c, action, event)
            return dict(id=source_id, action=action_id)

        return self.store._write(
            viewer,
            key,
            "m3.bonded_am_source",
            dict(source=source_id, action=action_id),
            operation,
            auto_audit=False,
            authorize=lambda c: self.game.authorize(c, viewer, game=False),
        )

    def _write_learned(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str | None,
        revision: int,
        name: str,
        payload: dict[str, Any],
        change: Callable[[Connection, GameState, str], str],
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("Reopen the actual current learned AM source")
            if identity is not None:
                source = learned.source(state, identity)
                if viewer.user_id not in source.controllers.values():
                    raise WorkflowError(
                        "Only original source participants own this private control"
                    )
            event = str(uuid4())
            source_id = change(c, state, event)
            self.game.event(c, viewer.user_id, key, name, state, event_id=event, source=source_id)
            synchronize_learned(self.game, c, state, source_id, event)
            current = learned.source(load_state(c, self.store.campaign_id), source_id)
            return dict(
                id=source_id,
                revision=load_state(c, self.store.campaign_id).revision,
                phase=current.phase,
            )

        return self.store._write(
            viewer,
            key,
            name,
            dict(source=identity, revision=revision, **payload),
            operation,
            auto_audit=False,
            authorize=lambda c: _access_learned(self.game, c, viewer),
        )

    def lesson_menu(
        self,
        viewer: GuildViewer,
        channel: int,
        lesson: str | None = None,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access_learned(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            offered = lessons(self.game, c, state, actor)
            if lesson is not None and lesson not in {x["id"] for x in offered}:
                raise WorkflowError("Reopen your genuine unused no-roll AM lesson")
            targets = []
            if offered:
                cast = _cast(self.game, c, state, channel)
                own = _native(self.game, c, state, actor)
                for role in cast.roles:
                    if role.actor == actor or role.actor.kind != "pilot":
                        continue
                    try:
                        other = _native(self.game, c, state, role.actor)
                    except (ValueError, WorkflowError):
                        continue
                    if (
                        own.inside_frame is False
                        and other.inside_frame is False
                        and own.cell is not None
                        and own.cell == other.cell
                        and not is_helpless(state, actor)
                        and not is_helpless(state, role.actor)
                    ):
                        targets.append(
                            dict(
                                ref=role.actor.model_dump(mode="json"),
                                id=role.actor.token,
                                label=other.label,
                            )
                        )
            return dict(
                revision=state.revision,
                channel=channel,
                lessons=offered,
                targets=targets,
                tasks=self._tasks(c, viewer),
            )

    def invite(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        target: ActorRef,
        revision: int,
        account: str,
        *,
        learned_source: str,
    ) -> dict[str, Any]:
        def change(c: Connection, state: GameState, event: str) -> str:
            actor = current_ref(state, viewer.user_id)
            offered = lessons(self.game, c, state, actor)
            if (
                learned_source not in {x["id"] for x in offered}
                or actor == target
                or not account.strip()
                or len(account) > 1200
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Use your actual unused lesson and voluntary original source")
            cast = _cast(self.game, c, state, channel)
            people = [_native(self.game, c, state, x) for x in (actor, target)]
            if any(x.vessel_id is None for x in people):
                raise WorkflowError("Establish the actual original bodies first")
            assert self.store.policy.m3_approval is not None
            source = learned.Source(
                id=str(uuid4()),
                lesson=learned_source,
                actor=actor,
                target=target,
                controllers={x.ref.token: x.controller for x in people},
                vessels={x.ref.token: x.vessel_id or "" for x in people},
                positions={x.ref.token: x.position_sha256 or "" for x in people},
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                event=event,
                account=account.strip(),
                mode="both_am"
                if has_rule(state.sheets[target.entity], RULE, "AM")
                else "counterpart",
            )
            _live(self.game, c, state, source)
            if cast not in state.scene_casts:
                state.scene_casts.append(cast)
            grant = _grant(self.game, c, state, source)
            _replace(state, grant.model_copy(update=dict(claimed_source=source.id)))
            learned.put(state, source)
            return source.id

        return self._write_learned(
            viewer,
            key,
            None,
            revision,
            "m3.learned_am_invited",
            dict(
                channel=channel,
                target=target.model_dump(mode="json"),
                account=account,
                lesson=learned_source,
            ),
            change,
        )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def change(c: Connection, state: GameState, event: str) -> str:
            source = prove_learned(self.game, c, state, identity)
            if (
                source.phase != "invited"
                or source.consent_event is not None
                or current_ref(state, viewer.user_id) != source.target
                or type(accept) is not bool
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Only the original counterpart authors this voluntary answer")
            _live(self.game, c, state, source)
            learned.put(
                state,
                learned.Consent(
                    id=identity + ":consent",
                    source=identity,
                    actor=source.target,
                    controller=viewer.user_id,
                    accepted=accept,
                    account=account.strip(),
                    event=event,
                ),
            )
            learned.put(
                state,
                source.model_copy(
                    update=dict(
                        phase="active" if accept else "declined",
                        consent_event=event,
                    )
                ),
            )
            if not accept:
                _replace(
                    state,
                    _grant(self.game, c, state, source).model_copy(
                        update=dict(claimed_source=None)
                    ),
                )
            return identity

        return self._write_learned(
            viewer,
            key,
            identity,
            revision,
            "m3.learned_am_confirmed",
            dict(accept=accept, account=account),
            change,
        )

    def bind_counterpart(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        action_id: str,
    ) -> dict[str, Any]:
        def change(c: Connection, state: GameState, event: str) -> str:
            source = prove_learned(self.game, c, state, identity)
            if (
                source.phase != "active"
                or source.mode != "counterpart"
                or source.counterpart_action is not None
            ):
                raise WorkflowError("Bind the original counterpart's actual source once")
            _live(self.game, c, state, source)
            _counterpart_proof(self.game, c, state, source, action_id)
            if any(x.counterpart_action == action_id for x in learned.sources(state)):
                raise WorkflowError("That actual counterpart performance already has its source")
            source = source.model_copy(update=dict(counterpart_action=action_id, bound_event=event))
            source = _use(self.game, c, state, source, event)
            learned.put(state, source)
            _stage_effects(self.game, c, state, source, event)
            return identity

        return self._write_learned(
            viewer,
            key,
            identity,
            revision,
            "m3.learned_am_counterpart_bound",
            dict(action=action_id),
            change,
        )

    def perform(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
        *,
        circuits_touched: bool = False,
    ) -> dict[str, Any]:
        def change(c: Connection, state: GameState, event: str) -> str:
            source = prove_learned(self.game, c, state, identity)
            person = current_ref(state, viewer.user_id)
            if (
                source.phase != "active"
                or person not in (source.actor, source.target)
                or source.controllers[person.token] != viewer.user_id
                or circuits_touched is not False
                or not account.strip()
                or len(account) > 1200
                or any(
                    x.source == identity and x.actor == person for x in learned.performances(state)
                )
            ):
                raise WorkflowError(
                    "Record only your original person's actual performed scene, not circuit access"
                )
            _live(self.game, c, state, source)
            if source.mode == "counterpart" and source.counterpart_action is None:
                raise WorkflowError("Bind the counterpart's real rolled Sex source first")
            from girlframe.services.m3_recovery import pending as pending_recovery

            table = t.m2["m2_actions"]
            held = sa.select(table.c.id).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.state.not_in(("complete", "aborted")),
            )
            if source.counterpart_action is not None:
                held = held.where(table.c.id != source.counterpart_action)
            if c.scalar(held.limit(1)) or pending_recovery(self.game, c, include_unrolled=True):
                raise WorkflowError(
                    "Resolve unrelated or interrupted Plays before recording this source"
                )
            learned.put(
                state,
                learned.Performance(
                    id=identity + ":" + person.token,
                    source=identity,
                    actor=person,
                    controller=viewer.user_id,
                    account=account.strip(),
                    event=event,
                ),
            )
            source = _use(self.game, c, state, source, event)
            learned.put(state, source)
            _stage_effects(self.game, c, state, source, event)
            return identity

        return self._write_learned(
            viewer,
            key,
            identity,
            revision,
            "m3.learned_am_performed",
            dict(account=account, circuits_touched=circuits_touched),
            change,
        )

    def withdraw(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        def change(c: Connection, state: GameState, event: str) -> str:
            source = prove_learned(self.game, c, state, identity)
            person = current_ref(state, viewer.user_id)
            if (
                source.phase not in ("invited", "active")
                or source.used_event is not None
                or source.counterpart_action is not None
                or not account.strip()
                or len(account) > 1200
                or person not in (source.actor, source.target)
            ):
                raise WorkflowError(
                    "Withdraw only an unused voluntary source; known/performed use is not refunded"
                )
            grant = _grant(self.game, c, state, source)
            _replace(state, grant.model_copy(update=dict(claimed_source=None)))
            learned.put(
                state,
                source.model_copy(
                    update=dict(
                        phase="withdrawn",
                        withdrawn_event=event,
                        withdrawn_by=person,
                        withdrawal_account=account.strip(),
                    )
                ),
            )
            return identity

        return self._write_learned(
            viewer,
            key,
            identity,
            revision,
            "m3.learned_am_withdrawn",
            dict(account=account),
            change,
        )

    def complete(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        def change(c: Connection, state: GameState, event: str) -> str:
            source = prove_learned(self.game, c, state, identity)
            if not account.strip() or len(account) > 1200 or source.phase != "active":
                raise WorkflowError("Review only actual pending performed-source completion")
            if not _stage_effects(self.game, c, state, source, event):
                raise WorkflowError(
                    "Both real performances and genuine counterpart costs/work must finish"
                )
            return identity

        return self._write_learned(
            viewer, key, identity, revision, "m3.learned_am_checked", dict(account=account), change
        )

    def view_learned(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = learned.source(state, identity)
            if viewer.user_id not in value.controllers.values():
                raise WorkflowError(
                    "Only original participants read this private learned AM source"
                )
            value = prove_learned(self.game, c, state, identity)
            from girlframe.services.p1_unrolled_sex import tasks

            performed = [x for x in learned.performances(state) if x.source == identity]
            own = next(
                x
                for x in (value.actor, value.target)
                if value.controllers[x.token] == viewer.user_id
            )
            actions = []
            if (
                value.phase == "active"
                and value.mode == "counterpart"
                and value.counterpart_action is None
            ):
                table = t.m2["m2_actions"]
                for row in c.execute(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == value.cast.id,
                        table.c.actor_id == value.target.entity,
                    )
                ):
                    try:
                        action = _counterpart_proof(self.game, c, state, value, row.id)
                    except (WorkflowError, ValueError):
                        continue
                    actions.append(
                        dict(id=action["id"], label=action["data"]["play"].replace("_", " "))
                    )
            return dict(
                id=identity,
                revision=state.revision,
                body=value.model_dump(mode="json"),
                performances=[x.model_dump(mode="json") for x in performed],
                unrolled_gender=tasks(self.game, c, state, value, viewer),
                actions=actions,
                can_confirm=value.phase == "invited" and own == value.target,
                can_perform=value.phase == "active"
                and (value.mode == "both_am" or value.counterpart_action is not None)
                and not any(x.actor == own for x in performed),
                can_withdraw=value.phase in ("invited", "active") and value.used_event is None,
                can_complete=value.phase == "active"
                and len(performed) == 2
                and _counterpart_complete(self.game, c, state, value),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        from girlframe.engine.p1_unrolled_sex import gifts

        for source in learned.sources(state):
            if viewer.user_id not in source.controllers.values():
                continue
            prove_learned(self.game, c, state, source.id)
            own_performed = any(
                x.source == source.id and x.controller == viewer.user_id
                for x in learned.performances(state)
            )
            pending_gifts = [x for x in gifts(state) if x.source == source.id and x.tag is None]
            terminal = source.phase in ("complete", "declined", "withdrawn")
            can_bind = False
            if (
                source.phase == "active"
                and source.mode == "counterpart"
                and source.counterpart_action is None
            ):
                table = t.m2["m2_actions"]
                for row in c.execute(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == source.cast.id,
                        table.c.actor_id == source.target.entity,
                    )
                ):
                    try:
                        _counterpart_proof(self.game, c, state, source, row.id)
                        can_bind = True
                        break
                    except (WorkflowError, ValueError):
                        continue
            can_perform = (
                source.phase == "active"
                and not own_performed
                and (source.mode == "both_am" or source.counterpart_action is not None)
            )
            can_finish = (
                source.phase == "active"
                and len([x for x in learned.performances(state) if x.source == source.id]) == 2
                and _counterpart_complete(self.game, c, state, source)
            )
            pending = (
                source.phase == "invited"
                and source.controllers[source.target.token] == viewer.user_id
                or can_bind
                or can_perform
                or can_finish
                or source.phase == "effects"
                and any(source.controllers[x.animal.token] == viewer.user_id for x in pending_gifts)
            )
            result.append(
                dict(
                    id=source.id,
                    revision=state.revision,
                    kind="m3_learned_am",
                    phase="resolved" if terminal else "pending",
                    pending=bool(pending),
                    waiting=not terminal and not pending,
                    label="Your actual learned AM no-roll source: " + source.phase,
                )
            )
        return result


def _access_learned(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(RULE)


def _grant(
    game: GameService, c: Connection, state: GameState, source: learned.Source
) -> LearnedPlayUse:
    sheet = state.sheets.get(source.actor.entity)
    runtime = (
        sheet.girl_runtime if sheet and sheet.character_id == source.actor.incarnation else None
    )
    grant = (
        next((x for x in runtime.learned_plays if x.id == source.lesson), None) if runtime else None
    )
    if (
        grant is None
        or grant.actor != source.actor
        or grant.rule_id != RULE
        or grant.claimed_action is not None
        or grant.rolled_event is not None
    ):
        raise WorkflowError("Recover the original actual no-roll lesson and learner")
    _prove(game, c, state, grant)
    return grant


def lessons(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
) -> tuple[dict[str, str], ...]:
    try:
        load_registry().require_available(RULE)
    except ValueError:
        return ()
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        return ()
    runtime = sheet.girl_runtime or GirlRuntime()
    permanent = sheet.model_copy(
        update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}
    )
    if has_rule(permanent, RULE, "AM"):
        return ()
    grant = available(game, c, state, actor, RULE)
    if grant is None:
        return ()
    return (dict(id=grant.id, label="AM Sex — one actual no-roll source", rule_id=RULE, play=""),)


def _live(game: GameService, c: Connection, state: GameState, source: learned.Source) -> None:
    cast = _cast(game, c, state, source.cast.channel)
    people = [_native(game, c, state, x) for x in (source.actor, source.target)]
    if (
        cast != source.cast
        or source.actor == source.target
        or source.mode == "both_am"
        and not has_rule(state.sheets[source.target.entity], RULE, "AM")
        or any(
            x.inside_frame is not False
            or x.cell is None
            or x.offstage_source
            or x.custody not in (None, "free")
            or is_helpless(state, x.ref)
            or source.controllers.get(x.ref.token) != x.controller
            or source.vessels.get(x.ref.token) != x.vessel_id
            or source.positions.get(x.ref.token) != x.position_sha256
            or not any(r.actor == x.ref and r.controller == x.controller for r in cast.roles)
            for x in people
        )
        or people[0].cell != people[1].cell
    ):
        raise WorkflowError("Preserve the actual voluntary original bodies, contact and cast")


def _audit(
    game: GameService, c: Connection, event: str, kinds: tuple[str, ...], owner: int, identity: str
) -> GameState:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] not in kinds
        or row["actor_id"] != str(owner)
        or json.loads(row["payload_json"]).get("source") != identity
    ):
        raise WorkflowError("Prove the actual original human's canonical no-roll source event")
    return _history(c, game, event)


def _counterpart_proof(
    game: GameService,
    c: Connection,
    state: GameState,
    source: learned.Source,
    identity: str,
) -> dict[str, Any]:
    action = game.action(c, identity)
    play = action["data"].get("play")
    meta = action["data"].get("mockingbird" if play == "mockingbird_sex" else play, {})
    targets = (
        [x["actor"] for x in meta.get("parties", ())[:1]]
        if play == "mockingbird_sex"
        else meta.get("partners", ())
        if play == "newgirl_sex"
        else [meta.get("target")]
    )
    born_seq = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == source.event
        )
    )
    confirms = c.execute(
        sa.select(t.events.c.seq, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.play_confirmed", "m3.play_confirmed")),
            t.events.c.actor_id == str(source.controllers[source.target.token]),
        )
    ).all()
    if (
        play not in PARTNER_PLAYS
        or str(action["actor_id"]) != source.target.entity
        or action["scene_id"] != source.cast.id
        or int(action["channel_id"]) != source.cast.channel
        or meta.get("actor") != source.target.model_dump(mode="json")
        or source.actor.model_dump(mode="json") not in targets
        or meta.get("cast_sha256") != fingerprint(source.cast)
        or action["data"].get("character_ids", {}).get(source.target.entity)
        != source.target.incarnation
        or not action["data"].get("receipt")
        or born_seq is None
        or not any(
            x.seq > born_seq and json.loads(x.payload_json).get("action_id") == identity
            for x in confirms
        )
    ):
        raise WorkflowError(
            "Bind a new actual independently confirmed counterpart source and receipt"
        )
    # Existing source-specific proofs retain actual consent, roles, costs and result ownership.
    if play == "mockingbird_sex":
        from girlframe.services.m3_mockingbird_effects import source_trigger

        source_trigger(game, c, action, state)
    elif play == "alpha_sex":
        from girlframe.services.m3_alpha_sex import prove as prove_alpha

        prove_alpha(game, c, state, meta["session"])
    elif play == "princess_sex":
        from girlframe.services.m3_princess_sex import prove as prove_princess

        prove_princess(game, c, state, meta["session"])
    elif play == "stim_sex":
        from girlframe.services.m3_stim_sex import prove as prove_stim

        prove_stim(game, c, state, meta["session"])
    elif play == "oldgen_sex":
        from girlframe.services.m3_oldgen_sex import prove as prove_oldgen

        prove_oldgen(game, c, state, meta["session"])
    elif play == "casualty_sex":
        from girlframe.services.m3_casualty import prove_sex

        prove_sex(game, c, state, meta["session"])
    elif play == "vatgrown_sex":
        from girlframe.services.m3_vatgrown_plays import prove as prove_vatgrown

        prove_vatgrown(game, c, state, meta["session"])
    elif play == "newgirl_sex":
        from girlframe.services.m3_newgirl_sex import prove as prove_newgirl

        prove_newgirl(game, c, state, meta["session"])
    _roll_source(game, c, action)
    return action


def _counterpart_complete(
    game: GameService, c: Connection, state: GameState, source: learned.Source
) -> bool:
    if source.mode == "both_am":
        return source.counterpart_action is None
    if source.counterpart_action is None:
        return False
    action = _counterpart_proof(game, c, state, source, source.counterpart_action)
    if action["state"] != "complete" or game.pending(c, action["id"]):
        return False
    table = t.m3["m3_required_work"]
    rows = {
        x["id"]: dict(x)
        for x in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id)
            .order_by(table.c.revision)
        ).mappings()
    }
    bodies = {identity: json.loads(row["body_json"]) for identity, row in rows.items()}
    chain = {
        identity for identity, body in bodies.items() if body.get("source_action") == action["id"]
    }
    while True:
        children = {
            identity for identity, body in bodies.items() if body.get("source_work") in chain
        }
        if children <= chain:
            break
        chain |= children
    return all(rows[identity]["state"] == "resolved" for identity in chain)


def _use(
    game: GameService, c: Connection, state: GameState, source: learned.Source, event: str
) -> learned.Source:
    if source.used_event is not None:
        return source
    grant = _grant(game, c, state, source)
    if (
        grant.claimed_source != source.id
        or grant.used_event is not None
        or grant.claimed_action is not None
        or grant.rolled_event is not None
    ):
        raise WorkflowError("Consume only this original real no-roll source once")
    _replace(state, grant.model_copy(update=dict(used_event=event)))
    return source.model_copy(update=dict(used_event=event))


def _stage_effects(
    game: GameService,
    c: Connection,
    state: GameState,
    source: learned.Source,
    event: str,
) -> bool:
    if source.effect_event is not None:
        return True
    performed = {x.actor for x in learned.performances(state) if x.source == source.id}
    if performed != {source.actor, source.target} or not _counterpart_complete(
        game, c, state, source
    ):
        return False
    if source.used_event is None:
        raise WorkflowError("The actual performed source must retain its one-use provenance")
    source = source.model_copy(update=dict(phase="effects", effect_event=event))
    learned.put(state, source)
    from girlframe.services.p1_unrolled_sex import offer

    offer(game, c, state, source, event)
    return True


def prove_learned(
    game: GameService, c: Connection, state: GameState, identity: str
) -> learned.Source:
    source = learned.source(state, identity)
    birth = _audit(
        game,
        c,
        source.event,
        ("m3.learned_am_invited",),
        source.controllers[source.actor.token],
        identity,
    )
    original = learned.source(birth, identity)
    stable = (
        "id",
        "lesson",
        "actor",
        "target",
        "controllers",
        "vessels",
        "positions",
        "cast",
        "registry",
        "event",
        "account",
        "mode",
        "kind",
        "action",
    )
    grant = _grant(game, c, birth, source)
    if (
        any(getattr(original, k) != getattr(source, k) for k in stable)
        or original.phase != "invited"
        or any(
            getattr(original, k) is not None
            for k in (
                "consent_event",
                "counterpart_action",
                "bound_event",
                "used_event",
                "effect_event",
                "completed_event",
                "withdrawn_event",
                "withdrawn_by",
            )
        )
        or grant.claimed_source != source.id
        or grant.used_event is not None
        or grant.claimed_action is not None
        or grant.rolled_event is not None
        or source.cast not in birth.scene_casts
        or not source.cast.open
    ):
        raise WorkflowError("Preserve original no-roll source, bodies, reservation and free grant")
    bindings = snapshot_profiles(c, game.store.campaign_id, birth)
    people = [resolve(birth, x, bindings) for x in (source.actor, source.target)]
    if (
        source.actor == source.target
        or source.cast.adjudicator is not None
        or source.cast.facilitator != birth.handler
        or source.mode == "both_am"
        and not has_rule(birth.sheets[source.target.entity], RULE, "AM")
        or any(
            x.ref.kind != "pilot"
            or x.rules != "girl_frame"
            or not x.alive
            or x.inside_frame is not False
            or x.cell is None
            or x.offstage_source
            or x.custody not in (None, "free")
            or is_helpless(birth, x.ref)
            or birth.sheets[x.ref.entity].medical_state != "fit"
            or source.controllers.get(x.ref.token) != x.controller
            or source.vessels.get(x.ref.token) != x.vessel_id
            or source.positions.get(x.ref.token) != x.position_sha256
            or not any(r.actor == x.ref and r.controller == x.controller for r in source.cast.roles)
            for x in people
        )
        or people[0].cell != people[1].cell
    ):
        raise WorkflowError("Prove actual original invitation bodies and source-time ownership")
    if source.consent_event:
        answered = _audit(
            game,
            c,
            source.consent_event,
            ("m3.learned_am_confirmed",),
            source.controllers[source.target.token],
            identity,
        )
        consent = [x for x in learned.consents(answered) if x.source == identity]
        if (
            len(consent) != 1
            or consent[0].actor != source.target
            or consent[0].controller != source.controllers[source.target.token]
            or consent[0].event != source.consent_event
            or learned.source(answered, identity).phase
            != ("active" if consent[0].accepted else "declined")
        ):
            raise WorkflowError("Recover actual independent original counterpart consent")
        if (
            not consent[0].accepted
            and source.phase != "declined"
            or consent[0].accepted
            and source.phase in ("invited", "declined")
        ):
            raise WorkflowError("A real refusal cannot become a performed source")
    elif source.phase != "invited" and source.phase != "withdrawn":
        raise WorkflowError("The actual original counterpart must answer before performance")
    performed = [x for x in learned.performances(state) if x.source == identity]
    if len({x.actor for x in performed}) != len(performed):
        raise WorkflowError("Keep one actual owned performance per original person")
    for item in performed:
        saved = _audit(game, c, item.event, ("m3.learned_am_performed",), item.controller, identity)
        if (
            item.actor not in (source.actor, source.target)
            or source.controllers[item.actor.token] != item.controller
            or item not in learned.performances(saved)
            or item.circuits_touched is not False
            or source.consent_event is None
        ):
            raise WorkflowError(
                "Preserve the original human's actual performance, not inferred consent"
            )
    if source.counterpart_action:
        if source.bound_event is None or source.mode != "counterpart":
            raise WorkflowError("Keep the actual counterpart source binding event")
        bound = _history(c, game, source.bound_event)
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == source.bound_event,
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["kind"] != "m3.learned_am_counterpart_bound"
            or row["actor_id"] not in {str(x) for x in source.controllers.values()}
            or json.loads(row["payload_json"]).get("source") != identity
            or learned.source(bound, identity).counterpart_action != source.counterpart_action
        ):
            raise WorkflowError("Preserve the original actual counterpart binding")
        _counterpart_proof(game, c, state, source, source.counterpart_action)
    elif source.bound_event is not None:
        raise WorkflowError("A counterpart binding needs its actual Action")
    # A genuinely released invitation remains historical after its unspent lesson
    # is claimed by a different source. Prove that release at its own event;
    # active/used sources still require their exact present reservation and use.
    released_event = (
        source.consent_event
        if source.phase == "declined"
        else source.withdrawn_event
        if source.phase == "withdrawn"
        else None
    )
    if source.phase in ("declined", "withdrawn") and released_event is None:
        raise WorkflowError("A released source needs its actual original release event")
    current = _grant(
        game, c, _history(c, game, released_event) if released_event else state, source
    )
    if source.used_event:
        used = _history(c, game, source.used_event)
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == source.used_event,
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["kind"] not in ("m3.learned_am_performed", "m3.learned_am_counterpart_bound")
            or row["actor_id"] not in {str(x) for x in source.controllers.values()}
            or json.loads(row["payload_json"]).get("source") != identity
            or learned.source(used, identity).used_event != source.used_event
            or _grant(game, c, used, source).used_event != source.used_event
            or current.used_event != source.used_event
            or current.claimed_source != identity
        ):
            raise WorkflowError("Preserve the real known/performed once-use; never invent a roll")
    elif current.used_event is not None:
        raise WorkflowError("Keep the exact original no-roll consumption event")
    if source.effect_event:
        effected = _history(c, game, source.effect_event)
        if (
            learned.source(effected, identity).effect_event != source.effect_event
            or {x.actor for x in learned.performances(effected) if x.source == identity}
            != {source.actor, source.target}
            or not _counterpart_complete(game, c, effected, source)
            or source.used_event is None
        ):
            raise WorkflowError(
                "Prove both performances and actual completed counterpart consequences"
            )
    if (
        source.phase in ("effects", "complete")
        and source.effect_event is None
        or (source.phase == "complete") != (source.completed_event is not None)
        or (source.phase == "withdrawn") != (source.withdrawn_event is not None)
        or source.withdrawn_event is None
        and (source.withdrawn_by is not None or source.withdrawal_account)
    ):
        raise WorkflowError("Preserve actual source stage/completion/withdrawal provenance")
    if source.withdrawn_event:
        if source.withdrawn_by not in (source.actor, source.target):
            raise WorkflowError("Keep the original source withdrawal author")
        ended = _audit(
            game,
            c,
            source.withdrawn_event,
            ("m3.learned_am_withdrawn",),
            source.controllers[source.withdrawn_by.token],
            identity,
        )
        if (
            learned.source(ended, identity) != source
            or source.phase != "withdrawn"
            or source.used_event
            or source.counterpart_action
            or not source.withdrawal_account
            or current.claimed_source is not None
            or performed
        ):
            raise WorkflowError("Withdraw only actual unused source, preserving its true history")
    if source.phase == "declined":
        if (
            source.consent_event is None
            or current.claimed_source is not None
            or source.used_event is not None
            or performed
        ):
            raise WorkflowError("A refusal creates no performed source or spent use")
    elif source.phase not in ("withdrawn",) and current.claimed_source != identity:
        raise WorkflowError("Preserve this exact original source reservation")
    if source.completed_event:
        ended = _history(c, game, source.completed_event)
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == source.completed_event,
                )
            )
            .mappings()
            .first()
        )
        from girlframe.engine.p1_unrolled_sex import gifts

        if (
            row is None
            or row["kind"] != "m3.learned_am_completed"
            or row["actor_id"] not in {str(x) for x in source.controllers.values()}
            or json.loads(row["payload_json"]).get("source") != identity
            or learned.source(ended, identity) != source
            or source.phase != "complete"
            or source.effect_event is None
            or any(x.tag is None for x in gifts(ended) if x.source == identity)
        ):
            raise WorkflowError("Preserve true source completion and actual mandatory gifts")
    return source


def synchronize_learned(
    game: GameService,
    c: Connection,
    state: GameState,
    identity: str,
    event: str,
) -> None:
    source = prove_learned(game, c, state, identity)
    if source.phase != "effects" or source.completed_event:
        return
    from girlframe.engine.p1_unrolled_sex import gifts
    from girlframe.services.p1_unrolled_sex import prove as prove_gift

    actual = [x for x in gifts(state) if x.source == identity]
    if any(x.tag is None for x in actual):
        return
    for gift in actual:
        prove_gift(game, c, state, gift.id)
    cause = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if (
        cause is None
        or cause["actor_id"] not in {str(x) for x in source.controllers.values()}
        or cause["kind"]
        not in (
            "m3.learned_am_performed",
            "m3.learned_am_checked",
            "m3.learned_am_counterpart_bound",
            "m3.unrolled_animal_tag",
        )
    ):
        raise WorkflowError("Use only actual owned performance/gift completion as source cause")
    cause_payload = json.loads(cause["payload_json"])
    if (
        cause_payload.get("source_id" if cause["kind"] == "m3.unrolled_animal_tag" else "source")
        != identity
    ):
        raise WorkflowError("Keep completion attached to this exact original performed source")
    final = str(uuid4())
    learned.put(state, source.model_copy(update=dict(phase="complete", completed_event=final)))
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == cause["command_key"],
        )
    )
    game.event(
        c,
        int(cause["actor_id"]),
        cause["command_key"],
        "m3.learned_am_completed",
        state,
        event_id=final,
        event_index=0 if index is None else index + 1,
        source=identity,
        source_event=event,
    )
