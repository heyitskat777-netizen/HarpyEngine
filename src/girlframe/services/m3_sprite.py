"""Owned physical interception windows; no new RNG, retargeted receipt or forged pass."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_sprite as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Required
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_collateral import append, latest
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def physical_incoming(
    game: GameService,
    c: Connection,
    source_action: str | None,
    occurrence: str,
    physical_blow: bool | None,
) -> bool:
    if physical_blow is not None:
        return physical_blow
    if not source_action:
        return False
    action = game.action(c, source_action)
    if action["data"].get("engage"):
        return False
    if occurrence in ("assault", "enforcer_firepower") or occurrence.startswith("collateral:"):
        return True
    row = c.execute(
        sa.select(t.m2["m2_choices"].c.kind).where(
            t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_choices"].c.id == occurrence,
            t.m2["m2_choices"].c.action_id == source_action,
        )
    ).first()
    return row is not None and (
        row.kind in ("battle_low_damage", "battle_target_damage")
        or row.kind == "battle_actor_damage"
        and action["data"].get("play") == "go_for_the_core"
    )


def defer(
    game: GameService,
    c: Connection,
    state: GameState,
    *,
    target: ActorRef,
    asset: str | None,
    source_action: str | None,
    source_work: str | None,
    event: str,
    opponent: ActorRef | None,
    chooser: int | None,
    occurrence: str,
    indirect: bool = False,
    effect: str = "damage",
) -> tuple[GameState, tuple[str, ...]]:
    available = rules.candidates(state, target, opponent, profiles(c, game.store.campaign_id))
    if not available:
        return state, ()
    identity = str(
        uuid5(NAMESPACE_URL, "actual-sprite-blow:" + event + ":" + target.token + ":" + occurrence)
    )
    blow = rules.Blow.model_validate(
        dict(
            target=target,
            asset=asset,
            opponent=opponent,
            chooser=chooser,
            source_action=source_action,
            source_work=source_work,
            source_event=event,
            occurrence=occurrence,
            indirect=indirect,
            effect=effect,
            candidates=available,
        )
    )
    required = Required(
        kind="sprite_intercept",
        target=target,
        opponent=opponent,
        source_pdf=166,
        details=dict(blow=blow.model_dump_json()),
    )
    changed = GameState.model_validate_json(state.model_dump_json())
    changed.facts.append(
        dict(
            kind="battle_damage_stage",
            id=identity,
            stamp=identity,
            event=event,
            source_action=source_action or "",
            source_work=source_work or "",
            requirement=required.model_dump_json(),
            chooser=str(chooser or 0),
        )
    )
    return changed, (identity,)


def defer_fatal(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    event: str,
    *,
    opponent: ActorRef,
    chooser: int,
) -> tuple[GameState, tuple[str, ...]]:
    return defer(
        game,
        c,
        state,
        target=target,
        asset=None,
        source_action=action["id"],
        source_work=None,
        event=event,
        opponent=opponent,
        chooser=chooser,
        occurrence="fatal",
        effect="fatal",
    )


def materialize(
    game: GameService,
    c: Connection,
    fact: dict[str, str],
    required: Required,
    body: dict[str, Any],
    parent: dict[str, Any],
    action: dict[str, Any] | None,
    event: str,
) -> None:
    blow = rules.Blow.model_validate_json(required.details["blow"])
    owners = sorted({x.controller for x in blow.candidates})
    requests = []
    if action:
        for owner in owners:
            requests.append(
                game.request(
                    c,
                    action,
                    owner,
                    "battle_sprite_intercept",
                    dict(work_id=fact["id"], source_action=action["id"]),
                )
            )
        game.save_action(c, action)
    body.update(
        phase="choose",
        decisions={},
        continuations=requests,
        damage_source_event=event,
        blow=blow.model_dump(mode="json"),
    )
    related(
        c,
        game.store,
        parent,
        fact["id"],
        owners[0],
        resolve(
            load_state(c, game.store.campaign_id),
            blow.target,
            profiles(c, game.store.campaign_id),
            require_current_profile=False,
        ).controller,
        "sprite_intercept",
        body,
        event,
    )


def _finish(
    game: GameService,
    c: Connection,
    row: dict[str, Any],
    body: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    append(c, row, event, body | dict(phase="complete"), "resolved")
    choices = t.m2["m2_choices"]
    for identity in body.get("continuations", ()):
        request = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == game.store.campaign_id, choices.c.id == identity
                )
            )
            .mappings()
            .first()
        )
        if request is None or json.loads(request["body_json"]).get("work_id") != row["id"]:
            raise WorkflowError("Recover each actual original Sprite-controller opportunity.")
        c.execute(
            choices.update()
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == identity,
                choices.c.state == "pending",
            )
            .values(state="completed_by_work", revision=choices.c.revision + 1)
        )
    from girlframe.services.m3_battle import complete_damage_work

    complete_damage_work(game, c, row, event, viewer, key)


def complete_children(
    game: GameService,
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> bool:
    try:
        row = latest(game, c, identity)
    except WorkflowError:
        return False
    if row["kind"] != "sprite_intercept":
        return False
    body = json.loads(row["body_json"])
    if row["state"] == "resolved":
        return True
    if body.get("phase") != "waiting" or any(
        latest(game, c, x)["state"] != "resolved" for x in body.get("followups", ())
    ):
        return True
    _finish(game, c, row, body, event, viewer, key)
    return True


class SpriteService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, identity: str) -> tuple[dict[str, Any], rules.Blow]:
        row = latest(self.game, c, identity)
        if row["kind"] != "sprite_intercept":
            raise WorkflowError("Open the actual source Sprite interception.")
        body = json.loads(row["body_json"])
        source = body["damage_source_event"]
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == source,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        fact = (
            next(
                (
                    x
                    for x in original.facts
                    if x.get("kind") == "battle_damage_stage" and x.get("id") == identity
                ),
                None,
            )
            if original
            else None
        )
        required = Required.model_validate_json(fact["requirement"]) if fact else None
        blow = rules.Blow.model_validate_json(json.dumps(body["blow"]))
        if (
            required is None
            or required.kind != "sprite_intercept"
            or rules.Blow.model_validate_json(required.details["blow"]) != blow
            or source != blow.source_event
        ):
            raise WorkflowError("Prove this exact original physical blow and Sprite opportunities.")
        return row, blow

    def choice_source(self, viewer: GuildViewer, identity: str) -> str:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            choices = t.m2["m2_choices"]
            request = (
                c.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == self.store.campaign_id,
                        choices.c.id == identity,
                        choices.c.kind == "battle_sprite_intercept",
                        choices.c.actor_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .first()
            )
            if request is None:
                raise WorkflowError("This Sprite opportunity belongs to another actual controller.")
            work = json.loads(request["body_json"])["work_id"]
            row, blow = self._proof(c, work)
            if request["id"] not in json.loads(row["body_json"])[
                "continuations"
            ] or viewer.user_id not in {x.controller for x in blow.candidates}:
                raise WorkflowError("Prove your exact source-owned Sprite opportunity.")
            return str(work)

    def decision(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        work = self.choice_source(viewer, identity)
        with self.store.engine.connect() as c:
            choices = t.m2["m2_choices"]
            request = (
                c.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == self.store.campaign_id,
                        choices.c.id == identity,
                        choices.c.actor_id == str(viewer.user_id),
                        choices.c.state == "pending",
                    )
                )
                .mappings()
                .first()
            )
            if request is None:
                raise WorkflowError("This actual Sprite opportunity is already resolved.")
            action = self.game.action(c, request["action_id"])
            return dict(
                id=identity,
                kind="battle_sprite_intercept",
                sprite_intercept=True,
                work_id=work,
                parent=action["id"],
                channel=int(action["channel_id"]),
                body=dict(work_id=work),
                revision=request["revision"],
            )

    def _options(self, state: GameState, blow: rules.Blow, owner: int) -> list[dict[str, Any]]:
        available: list[dict[str, Any]] = []
        assert state.world is not None
        target = None
        try:
            target = resolve(state, blow.target, profiles_for(state), require_current_profile=False)
        except ValueError:
            pass
        for candidate in blow.candidates:
            if candidate.controller != owner:
                continue
            sprite = next(
                (x for x in state.world.gorgons if x.id == candidate.actor.entity and x.alive), None
            )
            if sprite is None:
                continue
            actual = resolve(state, candidate.actor, ())
            if (
                actual.controller != owner
                or target is None
                or actual.cell is None
                or target.cell is None
                or actual.cell != target.cell
            ):
                continue
            available.extend(
                dict(
                    actor=candidate.actor.model_dump(mode="json"),
                    token=candidate.actor.token,
                    asset=x.id,
                    label=sprite.name + ": " + x.name,
                )
                for x in sprite.assets
                if x.id in candidate.assets and not x.damaged
            )
        return available

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row, blow = self._proof(c, identity)
            if viewer.user_id not in {x.controller for x in blow.candidates}:
                raise WorkflowError("Only an actual offered Sprite's controller reads this window.")
            state = load_state(c, self.store.campaign_id)
            body = json.loads(row["body_json"])
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                state=row["state"],
                phase=body["phase"],
                answered=str(viewer.user_id) in body["decisions"],
                options=self._options(state, blow, viewer.user_id),
                effect=blow.effect,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        work = t.m3["m3_required_work"]
        rows = list(
            c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id, work.c.kind == "sprite_intercept"
                )
                .order_by(work.c.revision)
            ).mappings()
        )
        values = {x["id"]: dict(x) for x in rows}
        return [
            dict(
                id=x["id"],
                revision=x["revision"],
                label="Your Sprite can intercept a blow",
                incoming=True,
                state="pending",
            )
            for x in values.values()
            if x["state"] == "pending"
            and (body := json.loads(x["body_json"]))["phase"] == "choose"
            and str(viewer.user_id) not in body["decisions"]
            and viewer.user_id in {item["controller"] for item in body["blow"]["candidates"]}
        ]

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        sprite: ActorRef | None,
        asset: str | None,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            row, blow = self._proof(c, identity)
            state = load_state(c, self.store.campaign_id)
            body = json.loads(row["body_json"])
            owner = str(viewer.user_id)
            if (
                row["state"] != "pending"
                or body["phase"] != "choose"
                or row["revision"] != revision
                or state.revision != game_revision
                or owner in body["decisions"]
                or viewer.user_id not in {x.controller for x in blow.candidates}
                or not account.strip()
            ):
                raise WorkflowError(
                    "STALE_SPRITE: this actual controller owns one original opportunity."
                )
            if (sprite is None) != (asset is None):
                raise WorkflowError("Explicitly pass or choose one actual owned Sprite and Asset.")
            if sprite is not None and not any(
                x["actor"] == sprite.model_dump(mode="json") and x["asset"] == asset
                for x in self._options(state, blow, viewer.user_id)
            ):
                raise WorkflowError(
                    "Choose your actual living co-located Sprite's originally intact Asset."
                )
            event = str(uuid4())
            body["decisions"][owner] = dict(choice="intercept" if sprite else "pass", event=event)
            state.facts.append(
                dict(
                    kind="sprite_opportunity_answered",
                    id=identity,
                    controller=owner,
                    sprite=sprite.model_dump_json() if sprite else "",
                    asset=asset or "",
                    event=event,
                    account=account,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.sprite_opportunity_answered",
                state,
                event_id=event,
                source_work=identity,
                intercepted=sprite is not None,
            )
            append(c, row, event, body, "pending")
            if sprite is not None or {int(x) for x in body["decisions"]} == {
                x.controller for x in blow.candidates
            }:
                self._apply(c, identity, blow, sprite, asset, event, viewer, key)
            return dict(id=identity, game_revision=load_state(c, self.store.campaign_id).revision)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.sprite_opportunity_answered",
                dict(
                    id=identity,
                    revision=revision,
                    game_revision=game_revision,
                    sprite=sprite.model_dump(mode="json") if sprite else None,
                    asset=asset,
                    account=account,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _apply(
        self,
        c: Connection,
        identity: str,
        blow: rules.Blow,
        sprite: ActorRef | None,
        asset: str | None,
        prior: str,
        viewer: GuildViewer | None,
        key: str,
    ) -> None:
        from girlframe.services.m3_battle import damage_actor, synchronize_damage

        row = latest(self.game, c, identity)
        body = json.loads(row["body_json"])
        state = load_state(c, self.store.campaign_id)
        event = str(uuid4())
        followups: tuple[str, ...] = ()
        from girlframe.engine.m3_battle import original_ended

        if original_ended(state, blow.target):
            _finish(self.game, c, row, body | dict(original_ended=prior), prior, viewer, key)
            return
        if blow.effect == "fatal" and sprite is None:
            append(c, row, prior, body | dict(phase="applying"), "pending")
            if blow.source_action is None:
                raise WorkflowError("Recover the actual original fatal Play source.")
            action = self.game.action(c, blow.source_action)
            if action["data"].get("battle"):
                from girlframe.services.m3_battle import _apply_fatal

                _apply_fatal(self.game, c, state, action, prior, viewer, key, allow_sprite=False)
                action["data"]["battle"]["fixed_paid"] = "fatal_after_sprite_declines"
                self.game.save_action(c, action)
            elif action["data"].get("gorgon_play"):
                from girlframe.services.m3_gorgon_play import apply_fatal

                apply_fatal(self.game, c, action, prior, viewer, key, allow_sprite=False)
            else:
                raise WorkflowError("Recover the exact actual fatal source consumer.")
            _finish(self.game, c, latest(self.game, c, identity), body, prior, viewer, key)
            return
        target = sprite or blow.target
        selected = asset if sprite else blow.asset
        if blow.effect == "destroy" and sprite is None:
            from girlframe.services.m3_gorgon_runtime import _destroy

            if blow.source_action is None or selected is None:
                raise WorkflowError("Recover the actual contested losing Asset source.")
            source_action = self.game.action(c, blow.source_action)
            source_action["data"]["response_event"] = event
            followups = _destroy(
                self.game,
                c,
                state,
                source_action,
                target,
                selected,
                "sprite_resolution",
                allow_sprite=False,
                source_work=identity,
            )
            self.game.save_action(c, source_action)
        else:
            state, followups = damage_actor(
                self.game,
                c,
                state,
                target=target,
                asset_id=selected,
                source_action=blow.source_action,
                source_work=identity,
                event=event,
                actor=None,
                opponent=blow.opponent,
                chooser_controller=blow.chooser,
                occurrence="sprite_resolution",
                indirect=blow.indirect,
                allow_sprite=False,
            )
        if sprite is not None and blow.effect == "fatal" and blow.source_action:
            action = self.game.action(c, blow.source_action)
            if action["data"].get("battle"):
                action["data"]["battle"].update(
                    fixed_paid="intercepted_by_actual_sprite",
                    fatal_pending=False,
                    fatal_intercepted=event,
                )
            else:
                action["data"]["gorgon_play"]["fatal_intercepted"] = event
            self.game.save_action(c, action)
        state.facts.append(
            dict(
                kind="sprite_blow_resolved",
                id=identity,
                event=event,
                intercepted=sprite.model_dump_json() if sprite else "",
                original=blow.target.model_dump_json(),
            )
        )
        actual = c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == prior
            )
        )
        index = c.scalar(
            sa.select(sa.func.max(t.events.c.event_index)).where(
                t.events.c.campaign_id == self.store.campaign_id, t.events.c.command_key == key
            )
        )
        if actual is None:
            raise WorkflowError("Recover the actual source command for this physical blow.")
        self.game.event(
            c,
            viewer.user_id if viewer else actual,
            key,
            "m3.sprite_blow_resolved",
            state,
            event_id=event,
            event_index=index + 1 if index is not None else 0,
            source_work=identity,
            source_event=prior,
            intercepted=sprite is not None,
        )
        current = latest(self.game, c, identity)
        append(c, current, event, body | dict(phase="waiting", followups=followups), "pending")
        synchronize_damage(self.game, c, event)
        if not followups:
            _finish(self.game, c, latest(self.game, c, identity), body, event, viewer, key)


def profiles_for(state: GameState) -> tuple[ProfileBinding, ...]:
    """Read-only current bindings for physical eligibility, never SQL identity authority."""
    return tuple(
        ProfileBinding(
            owner=x.owner, character_id=x.character_id, profile_revision=x.source_profile_revision
        )
        for x in state.sheets.values()
        if x.character_id
    )
