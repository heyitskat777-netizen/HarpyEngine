"""Transactional actor casting with immutable legacy-scene evidence."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_actors, m3_cast
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


class CastService:
    def __init__(self, actors: ActorService):
        self.actors, self.game, self.store = actors, actors.game, actors.store

    def _safe(self, c: Connection, channel: int) -> None:
        from girlframe.services.p1_source_pause import require_clear

        require_clear(self.game, c, channel)
        lock = self.game.lock(c, channel)
        actions = t.m2["m2_actions"]
        if (
            self.game.pending_actions(c)
            or (lock and lock["state"] != "released")
            or c.scalar(
                sa.select(actions.c.id)
                .where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.channel_id == str(channel),
                    actions.c.state.not_in(("complete", "aborted")),
                )
                .limit(1)
            )
        ):
            raise WorkflowError(
                "Restore chat and resolve the pending Play before changing its cast."
            )

    def _legacy(self, c: Connection, scene: dict[str, Any]) -> SceneCast:
        events = list(
            c.execute(
                sa.select(t.events)
                .where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind.in_(("m2.scene_bound", "m2.scene_joined", "m2.scene_left")),
                )
                .order_by(t.events.c.seq.desc())
            ).mappings()
        )
        events = [
            x
            for x in events
            if str(json.loads(x["payload_json"]).get("channel")) == scene["channel_id"]
        ]
        bound = next((x for x in events if x["kind"] == "m2.scene_bound"), None)
        outcome = (
            c.scalar(
                sa.select(t.commands.c.outcome_json).where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key == bound["command_key"],
                )
            )
            if bound
            else None
        )
        if bound is None or outcome is None or json.loads(outcome).get("scene") != scene["id"]:
            raise WorkflowError("SOURCE_CAST_MISSING: recover this scene's actual bind event.")
        roles: list[CastRole] = []
        facilitator, facilitator_source = None, None
        for uid in scene["participants"]:
            joined = next(
                (x for x in events if x["seq"] > bound["seq"] and x["actor_id"] == str(uid)), None
            )
            if joined is None or joined["kind"] != "m2.scene_joined":
                raise WorkflowError("SOURCE_CAST_MISSING: recover the actual explicit scene join.")
            history = t.m2["m2_state_history"]
            body = c.scalar(
                sa.select(history.c.body_json)
                .select_from(history.join(t.events, history.c.event_id == t.events.c.id))
                .where(
                    history.c.campaign_id == self.store.campaign_id, t.events.c.seq <= joined["seq"]
                )
                .order_by(t.events.c.seq.desc())
                .limit(1)
            )
            if body is None:
                raise WorkflowError("SOURCE_CAST_MISSING: recover the original joined character.")
            original = GameState.model_validate_json(body)
            if uid == original.handler:
                facilitator, facilitator_source = uid, joined["id"]
                if str(uid) not in original.sheets:
                    continue
            sheet = original.sheets.get(str(uid))
            identity = (
                (
                    sheet.character_id
                    or c.scalar(
                        sa.select(t.snapshots.c.character_id).where(
                            t.snapshots.c.campaign_id == self.store.campaign_id,
                            t.snapshots.c.user_id == str(uid),
                            t.snapshots.c.revision == sheet.source_profile_revision,
                        )
                    )
                )
                if sheet
                else None
            )
            if identity is None:
                raise WorkflowError("SOURCE_CAST_MISSING: recover the original character snapshot.")
            roles.append(
                CastRole(
                    actor=ActorRef(kind="pilot", entity=str(uid), incarnation=identity),
                    controller=uid,
                    source_event=joined["id"],
                )
            )
        return SceneCast(
            id=scene["id"],
            channel=int(scene["channel_id"]),
            roles=tuple(roles),
            facilitator=facilitator,
            facilitator_source=facilitator_source,
        )

    def _current(self, c: Connection, state: GameState, channel: int) -> tuple[SceneCast, bool]:
        scene = self.game.scene(c, channel)
        cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
        return (cast, False) if cast else (self._legacy(c, scene), True)

    def view(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        from girlframe.engine.m3_npc_job_prompts import PROMPTS

        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            cast, legacy = self._current(c, state, channel)
            bindings = profiles(c, self.store.campaign_id)
            from girlframe.services.m3_captured import CapturedService

            capture_service: CapturedService | None = None
            if viewer.user_id == cast.facilitator:
                capture_service = CapturedService(self.game)
                try:
                    capture_service._gate(c, viewer)
                except (ValueError, WorkflowError):
                    capture_service = None
            visible = []
            offers = []
            known_refs = set()
            for role in cast.roles:
                try:
                    actor = m3_actors.resolve(state, role.actor, bindings)
                except ValueError:
                    if role.controller == viewer.user_id:
                        visible.append(
                            {
                                "ref": role.actor.model_dump(mode="json"),
                                "token": role.actor.token,
                                "label": "Your previous role — withdraw or recover",
                                "stale": True,
                                "own": True,
                            }
                        )
                    continue
                if role.controller == viewer.user_id and actor.controller != viewer.user_id:
                    visible.append(
                        {
                            "ref": role.actor.model_dump(mode="json"),
                            "token": role.actor.token,
                            "label": "Your previous role — withdraw or recover",
                            "stale": True,
                            "own": True,
                        }
                    )
                    continue
                known = actor.ref.kind in ("pilot", "handler") or actor.controller == viewer.user_id
                known |= any(
                    ActorRef(kind="external_pilot", entity=x.id) == actor.ref
                    and (x.revealed or int(x.frame_owner.entity) == viewer.user_id)
                    for x in state.janus_cores
                )
                if state.world and actor.ref.kind in ("npc", "external_pilot", "gorgon"):
                    revealed = {
                        "npc": {x.id for x in state.world.npcs if x.revealed},
                        "external_pilot": {x.id for x in state.world.pilots if x.revealed},
                        "gorgon": {x.id for x in state.world.gorgons if x.revealed},
                    }[actor.ref.kind]
                    known = known or actor.ref.entity in revealed
                    known |= bool(
                        viewer.user_id == state.handler
                        and actor.rules == "director"
                        and any(
                            x.active and actor.ref.entity in x.directors
                            for x in state.director_contexts
                        )
                    )
                from girlframe.engine.m3_harpy_mask import active as human_mask
                from girlframe.engine.m3_prince import presentation
                from girlframe.services.m3_consume_support import knowledge_allowed

                part = presentation(state, actor.ref, cast.id)
                disguise = human_mask(state, actor.ref, cast.id) if actor.girl == "harpy" else None
                if disguise and actor.alive and not actor.offstage_source:
                    part = disguise.appearance
                    known = known or any(x.controller == viewer.user_id for x in cast.roles)
                known = known and knowledge_allowed(state, actor.ref)
                if known:
                    owned_npc = (
                        next((x for x in state.world.npcs if x.id == actor.ref.entity), None)
                        if state.world
                        and actor.ref.kind == "npc"
                        and actor.controller == role.controller == viewer.user_id
                        else None
                    )
                    prompts = (
                        {job: PROMPTS[job] for job in owned_npc.jobs if job in PROMPTS}
                        if owned_npc
                        else {}
                    )
                    harpy_actions: dict[str, bool] = {}
                    can_escape = False
                    if actor.rules == "girl_frame" and viewer.user_id == actor.controller:
                        from girlframe.services.m3_escape import EscapeService

                        escape_service = EscapeService(self.game)
                        try:
                            escape_service._gate(c, viewer)
                            escape_service._where(c, state, channel, actor.ref)
                            can_escape = True
                        except (ValueError, WorkflowError):
                            pass
                    can_capture = False
                    if capture_service and actor.ref.kind in ("npc", "external_pilot"):
                        try:
                            _, _, _, _, candidates = capture_service._source(
                                c, state, channel, actor.ref
                            )
                            can_capture = bool(candidates)
                        except (ValueError, WorkflowError):
                            pass
                    if (
                        actor.ref.kind == "external_pilot"
                        and actor.girl == "harpy"
                        and actor.controller == role.controller == viewer.user_id
                    ):
                        from girlframe.engine.m3_harpy_advancements import (
                            EAGLE,
                            KISS,
                            MANIC_PIXIE,
                            MASK,
                            NOTHING,
                            ONLY_SHE_MATTERS,
                            SONG_OF_LOVE_LOST,
                            VISIONS,
                        )
                        from girlframe.services.m3_harpy_advancements import scene_harpy

                        for tag, rule in (
                            ("only_she_matters", ONLY_SHE_MATTERS),
                            ("harpy_song", SONG_OF_LOVE_LOST),
                            ("harpy_eagle", EAGLE),
                            ("harpy_gaze", MANIC_PIXIE),
                            ("harpy_visions", VISIONS),
                            ("harpy_rewrite", NOTHING),
                            ("harpy_mask", MASK),
                            ("harpy_kiss", KISS),
                        ):
                            try:
                                scene_harpy(
                                    self.game, c, state, viewer.user_id, cast, actor.ref, rule
                                )
                            except (ValueError, WorkflowError):
                                continue
                            harpy_actions[tag] = True
                    can_abysstech = False
                    if (
                        actor.rules == "ancillary"
                        and actor.girl == "ABYSSAL ACOLYTE"
                        and actor.controller == viewer.user_id
                    ):
                        from girlframe.services.m3_abysstech import AbysstechService

                        abysstech = AbysstechService(self.game)
                        try:
                            abysstech._gate(c, viewer)
                            original, body, tools = abysstech._acolyte(c, state, channel, actor.ref)
                            can_abysstech = bool(
                                tools and abysstech._girls(c, state, original, body)
                            )
                        except (ValueError, WorkflowError):
                            pass
                    if (
                        actor.girl == "harpy"
                        and actor.controller == role.controller == viewer.user_id
                    ):
                        from girlframe.services.m3_harpy_intimacy import HarpyIntimacyService

                        intimacy = HarpyIntimacyService(self.game)
                        try:
                            intimacy._gate(c, viewer)
                            _, _, _, intimate_people = intimacy._where(c, state, channel, actor.ref)
                            if intimate_people:
                                harpy_actions["harpy_intimacy"] = True
                        except (ValueError, WorkflowError):
                            pass
                    can_patronage = False
                    if actor.controller == viewer.user_id and (
                        actor.rules == "ancillary"
                        and actor.girl == "MERCENARY"
                        or owned_npc is not None
                        and "patron" in owned_npc.jobs
                    ):
                        from girlframe.services.m3_mercenary_patron import MercenaryPatronService

                        patronage = MercenaryPatronService(self.game)
                        try:
                            patronage._gate(c, viewer)
                            can_patronage = (
                                bool(patronage.withdrawal(c, state, viewer, channel, actor.ref))
                                if actor.ref.kind == "npc"
                                else True
                            )
                        except (ValueError, WorkflowError):
                            pass
                    can_debt = can_debt_contact = False
                    if actor.controller == role.controller == viewer.user_id:
                        from girlframe.services.m3_mercenary_debt import DebtService

                        try:
                            debt = DebtService(self.game)
                            if any(item.holder == actor.ref for item in state.held_items):
                                _, mercenaries = debt.options(c, state, viewer, channel, actor.ref)
                                can_debt = bool(mercenaries)
                            if actor.rules == "ancillary" and actor.girl == "MERCENARY":
                                can_debt_contact = bool(
                                    debt.contact_options(c, state, viewer, channel, actor.ref)
                                )
                        except (ValueError, WorkflowError):
                            pass
                    can_recall = False
                    if (
                        actor.controller == role.controller == viewer.user_id
                        and actor.rules == "ancillary"
                        and actor.girl == "REVOLUTIONARY IDEALIST"
                    ):
                        from girlframe.services.m3_chronically_online import (
                            ChronicallyOnlineService,
                        )

                        try:
                            can_recall = bool(
                                ChronicallyOnlineService(self.game).options(
                                    c, state, viewer, channel, actor.ref
                                )
                            )
                        except (ValueError, WorkflowError):
                            pass
                    can_chained_placement = False
                    if actor.controller == role.controller == viewer.user_id and (
                        actor.rules == "ancillary"
                    ):
                        from girlframe.services.m3_chained_darling import ChainedPlacementService

                        try:
                            can_chained_placement = bool(
                                ChainedPlacementService(self.game).available(
                                    c, state, viewer, channel, actor.ref
                                )
                            )
                        except (ValueError, WorkflowError):
                            pass
                    can_ancillary_intimacy = False
                    if (
                        actor.controller == role.controller == viewer.user_id
                        and actor.rules == "ancillary"
                    ):
                        from girlframe.services.m3_ancillary_intimacy import (
                            AncillaryIntimacyService,
                        )

                        try:
                            can_ancillary_intimacy = bool(
                                AncillaryIntimacyService(self.game).options(
                                    c, state, viewer, channel, actor.ref
                                )
                            )
                        except (ValueError, WorkflowError):
                            pass
                    known_refs.add(actor.ref)
                    visible.append(
                        {
                            "ref": actor.ref.model_dump(mode="json"),
                            "token": actor.ref.token,
                            "label": actor.label + (" · presents as: " + part if part else ""),
                            "perceived_part": part,
                            "can_detect_act": part is None,
                            "stale": role.controller != actor.controller,
                            "own": role.controller == viewer.user_id,
                            **({"job_prompts": prompts} if prompts else {}),
                            **harpy_actions,
                            **({"escape_source": True} if can_escape else {}),
                            **({"abysstech": True} if can_abysstech else {}),
                            **({"patronage": True} if can_patronage else {}),
                            **({"mercenary_debt": True} if can_debt else {}),
                            **({"debt_contact": True} if can_debt_contact else {}),
                            **({"chronically_online": True} if can_recall else {}),
                            **({"chained_placement": True} if can_chained_placement else {}),
                            **({"ancillary_intimacy": True} if can_ancillary_intimacy else {}),
                            **({"capture_source": True} if can_capture else {}),
                            **(
                                {"director_phone": True}
                                if owned_npc
                                and actor.rules == "director"
                                and viewer.user_id != state.handler
                                else {}
                            ),
                        }
                    )
                if (
                    actor.controller == role.controller == viewer.user_id
                    and actor.rules == "director"
                    and viewer.user_id != state.handler
                    and cast.adjudicator != actor.ref
                ):
                    offers.append(
                        {
                            "ref": actor.ref.model_dump(mode="json"),
                            "token": actor.ref.token,
                            "label": actor.label,
                        }
                    )
            can_form_cadre = False
            if cast.facilitator == viewer.user_id:
                from girlframe.services.m3_ancillary_cadre import AncillaryCadreService

                try:
                    can_form_cadre = AncillaryCadreService(self.game).available(
                        c, state, viewer, channel
                    )
                except (ValueError, WorkflowError):
                    pass
            return {
                "scene": cast.id,
                "channel": channel,
                "cast_revision": cast.revision,
                "game_revision": state.revision,
                "legacy": legacy,
                "roles": visible,
                "facilitator": cast.facilitator,
                "own_facilitator": cast.facilitator == viewer.user_id,
                "can_form_ancillary_cadre": can_form_cadre,
                "may_facilitate": state.handler == viewer.user_id,
                "adjudicator": cast.adjudicator.model_dump(mode="json")
                if cast.adjudicator in known_refs
                else None,
                "adjudicator_selected": cast.adjudicator is not None,
                "adjudicator_options": offers,
            }

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        cast_revision: int,
        action: str,
        ref: ActorRef | None = None,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.actors.missions.access.authorize(c, viewer, "world", director_response=True)
            # Withdrawing is OOC recovery, including during a safety pause.
            if action not in ("withdraw", "withdraw_facilitator"):
                self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            cast, legacy = self._current(c, state, channel)
            if state.revision != expected or cast.revision != cast_revision:
                raise WorkflowError("STALE_CAST: refresh the actual scene roles.")
            self._safe(c, channel)
            event_id = str(uuid4())
            try:
                if action == "join" and ref is not None:
                    actor = self.actors._actor(c, viewer, state, ref)
                    from girlframe.services.m3_scene_requisitions import guard

                    guard(c, self.store, cast.id, ref)
                    if ref.kind == "pilot":
                        scenes = t.m2["m2_scenes"]
                        others = c.execute(
                            sa.select(scenes).where(
                                scenes.c.campaign_id == self.store.campaign_id,
                                scenes.c.open.is_(True),
                                scenes.c.id != cast.id,
                            )
                        ).mappings()
                        if any(
                            actor.controller in json.loads(x["participants_json"]) for x in others
                        ):
                            raise ValueError("Withdraw this Girl from her current scene first")
                    updated = m3_cast.join(
                        [*state.scene_casts, *([cast] if legacy else [])],
                        cast.id,
                        actor,
                        viewer.user_id,
                        event_id,
                    )
                elif action == "withdraw" and ref is not None:
                    updated = m3_cast.withdraw(cast, ref, viewer.user_id)
                elif action == "adjudicate" and ref is not None:
                    updated = m3_cast.choose_adjudicator(
                        state, cast, ref, viewer.user_id, profiles(c, self.store.campaign_id)
                    )
                elif (
                    action == "withdraw_facilitator"
                    and ref is None
                    and cast.facilitator == viewer.user_id
                ):
                    updated = cast.model_copy(
                        update={
                            "facilitator": None,
                            "facilitator_source": None,
                            "revision": cast.revision + 1,
                        }
                    )
                elif action == "facilitate" and ref is None and state.handler == viewer.user_id:
                    if cast.facilitator == viewer.user_id:
                        raise ValueError("You are already facilitating this scene")
                    updated = cast.model_copy(
                        update={
                            "facilitator": viewer.user_id,
                            "facilitator_source": event_id,
                            "revision": cast.revision + 1,
                        }
                    )
                else:
                    raise ValueError("Choose your own actual role or the appointed facilitator")
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            state.scene_casts = [x for x in state.scene_casts if x.id != cast.id] + [updated]
            # This legacy projection has only real Pilot humans and the facilitator.
            # NPC controllers do not silently acquire a Girl's scene participation.
            people = sorted(
                {x.controller for x in updated.roles if x.actor.kind == "pilot"}
                | ({updated.facilitator} if updated.facilitator is not None else set())
            )
            table = t.m2["m2_scenes"]
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
                .values(participants_json=json.dumps(people), revision=table.c.revision + 1)
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.scene_cast_changed",
                state,
                event_id=event_id,
                scene=cast.id,
                action=action,
            )
            return {"scene": cast.id, "cast_revision": updated.revision}

        return self.store._write(
            viewer,
            key,
            "m3.scene_cast_changed",
            {
                "channel": channel,
                "expected": expected,
                "cast_revision": cast_revision,
                "action": action,
                "ref": ref.model_dump(mode="json") if ref else None,
            },
            operation,
            auto_audit=False,
            authorize=authorize,
        )


def withdraw_easy_target(
    game: "GameService", c: Connection, state: GameState, work: str, event: str
) -> ActorRef:
    """One proved contempt role leaves its actual held scene, preserving controller aliases."""
    from girlframe.engine import m3_easy_target as rules
    from girlframe.services.m3_easy_target import leave_actor

    actor = leave_actor(game, c, state, work, event)
    reaction = next(x for x in rules.records(state, rules.Reaction) if x.id == work)
    source = next(x for x in rules.records(state, rules.Session) if x.id == reaction.session)
    before = next(x for x in state.scene_casts if x.id == source.cast.id and x.open)
    after = m3_cast.withdraw(before, actor, reaction.controller)
    state.scene_casts = [after if x.id == before.id else x for x in state.scene_casts]
    people = sorted(
        {x.controller for x in after.roles if x.actor.kind == "pilot"}
        | ({after.facilitator} if after.facilitator is not None else set())
    )
    table = t.m2["m2_scenes"]
    c.execute(
        table.update()
        .where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == before.id,
        )
        .values(participants_json=json.dumps(people), revision=table.c.revision + 1)
    )
    return actor


def change_doll_presence(
    game: "GameService",
    viewer: GuildViewer,
    key: str,
    channel: int,
    source: str,
    revision: int,
    account: str,
    *,
    returning: bool,
) -> dict[str, Any]:
    """Commit a source-proved fictional exit/return, retaining the known map cell."""
    if not account.strip() or len(account) > 1200:
        raise WorkflowError("Describe your actual departure or return to this scene")

    def authorize(c: Connection) -> None:
        from girlframe.services.m3_access import Access

        Access(game.store).authorize(c, viewer, "plays")

    def operation(c: Connection) -> dict[str, Any]:
        from girlframe.engine.m3_vatgrown import record_departure, record_return
        from girlframe.services.m3_vatgrown import departure_source, return_source

        game.unpaused(c)
        state = load_state(c, game.store.campaign_id)
        if state.revision != revision:
            raise WorkflowError("STALE_SOURCE: reopen your actual Doll source")
        if game.pending_actions(c):
            raise WorkflowError(
                "Finish the actual pending consequences before departing or returning"
            )
        scene = game.scene(c, channel)
        lock = game.lock(c, channel)
        if lock and lock["state"] != "released":
            raise WorkflowError("Restore the actual scene chat before departing or returning")
        before = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
        if before is None:
            raise WorkflowError("Recover the actual original scene cast")
        event = str(uuid4())
        if returning:
            departure = return_source(game, c, state, viewer, source, channel)
            actual = m3_actors.resolve(state, departure.actor, profiles(c, game.store.campaign_id))
            after = m3_cast.join(state.scene_casts, before.id, actual, viewer.user_id, event)
            fact_id = record_return(state, departure, before, after, event, account.strip()).id
        else:
            effect = departure_source(game, c, state, viewer, source, channel)
            after = m3_cast.withdraw(before, effect.actor, viewer.user_id)
            fact_id = record_departure(state, effect, before, after, event, account.strip()).id
        state.scene_casts = [x for x in state.scene_casts if x.id != before.id] + [after]
        people = sorted(
            {x.controller for x in after.roles if x.actor.kind == "pilot"}
            | ({after.facilitator} if after.facilitator is not None else set())
        )
        table = t.m2["m2_scenes"]
        c.execute(
            table.update()
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == before.id)
            .values(participants_json=json.dumps(people), revision=table.c.revision + 1)
        )
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.vatgrown_returned" if returning else "m3.vatgrown_departed",
            state,
            event_id=event,
            source=source,
            scene=before.id,
        )
        return {"id": fact_id, "scene": before.id, "revision": state.revision}

    return game.store._write(
        viewer,
        key,
        "m3.vatgrown_returned" if returning else "m3.vatgrown_departed",
        {"channel": channel, "source": source, "revision": revision, "account": account},
        operation,
        auto_audit=False,
        authorize=authorize,
    )
