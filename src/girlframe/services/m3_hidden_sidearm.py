"""Paid real concealed gun, source-bound Helpless/death and actual unrolled reconsideration."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_hidden_sidearm as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless, make_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_item_state import HeldItem
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast, damage_actor
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_items import prove_item
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    if value is None:
        raise WorkflowError("Recover the actual Hidden Sidearm purchase")
    born = next(
        (x for x in rules.acquisitions(_history(c, game, value.event)) if x.id == identity), None
    )
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.acquisition != value.id
        or award.acquired_rule != rules.RULE
        or award.spend_event != value.event
        or (handler, appointment) != (value.handler, value.appointment)
    ):
        raise WorkflowError("Recover the exact original held award and Hidden Sidearm source")
    return value


def prove_gun(game: GameService, c: Connection, state: GameState, item: HeldItem) -> None:
    receipt = next((x for x in rules.acquisitions(state) if x.gun == item.id), None)
    if receipt is None:
        raise WorkflowError("Recover the actual original source-provided sidearm")
    receipt = paid(game, c, state, receipt.id)
    if (
        item.source_event != receipt.event
        or item.source_owner != receipt.handler
        or item.confirmed_event != receipt.event
        or item.confirmed_by != receipt.handler
        or item.confirmed_controller != int(receipt.handler.entity)
        or not item.weapon
    ):
        raise WorkflowError("Preserve the original ordinary sidearm and factual Handler ownership")


def current(
    game: GameService, c: Connection, state: GameState, identity: str
) -> tuple[rules.Acquisition, HeldItem]:
    value = paid(game, c, state, identity)
    if (
        not same_handler_body(state, value.handler)
        or HandlerCreationService(game.store)._appointment_source(c, int(value.handler.entity))
        != value.appointment
    ):
        raise WorkflowError("Only the original current Handler uses this personal sidearm")
    item = prove_item(c, game, state, value.gun)
    body = resolve(
        state, value.handler, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        item.holder != value.handler
        or item.condition != "intact"
        or item.location_mode != "carried"
        or not body.alive
        or body.offstage_source
        or body.custody not in (None, "free")
    ):
        raise WorkflowError("The actual living free Handler must have this intact gun available")
    return value, item


def concealment(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Concealment:
    value = next((x for x in rules.concealments(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover actual concealment beneath the coat")
    receipt = paid(game, c, state, value.acquisition)
    born = next(
        (x for x in rules.concealments(_history(c, game, value.event)) if x.id == identity), None
    )
    if (
        born is None
        or any(
            getattr(born, k) != getattr(value, k)
            for k in ("id", "acquisition", "handler", "gun", "event", "account")
        )
        or (value.handler, value.gun) != (receipt.handler, receipt.gun)
    ):
        raise WorkflowError("Preserve this actual original concealment occurrence")
    return value


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Reveal:
    value = next((x for x in rules.reveals(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual revealed sidearm source")
    hidden = concealment(game, c, state, value.concealment)
    born = next(
        (x for x in rules.reveals(_history(c, game, value.event)) if x.id == identity), None
    )
    if (
        born is None
        or hidden.reveal != value.id
        or any(
            getattr(born, k) != getattr(value, k)
            for k in (
                "id",
                "acquisition",
                "concealment",
                "gun",
                "handler",
                "target",
                "vessel",
                "cast",
                "event",
                "account",
                "choice",
                "action",
            )
        )
    ):
        raise WorkflowError("Preserve the original concealed reveal, people and source choice")
    return value


def _hostile(action: dict[str, Any], target: ActorRef, handler: ActorRef) -> bool:
    meta = action["data"].get("engage", {})
    return bool(
        action["state"] in ("acquiring", "ready_to_roll")
        and action["data"].get("receipt") is None
        and meta.get("actor") == target.model_dump(mode="json")
        and meta.get("target") == handler.model_dump(mode="json")
    )


def _cancel(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], reason: str
) -> None:
    if action["data"].get("receipt") is not None:
        raise WorkflowError("A known roll cannot become an unrolled source cancellation")
    action["data"]["result"] = dict(withdrawn=True, source="hidden_sidearm", reason=reason)
    action["state"] = "complete"
    game.queue(
        c,
        action,
        "outcome",
        dict(
            play=action["data"]["play"],
            callsign=state.sheets[action["actor_id"]].callsign
            if action["actor_id"] in state.sheets
            else "Original ended Girl",
            receipt=None,
            total=None,
            tier=None,
            withdrawn=True,
            source="hidden_sidearm",
            reason=reason,
        ),
    )


def refresh(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"].get("engage")
    if meta is None or action["data"].get("receipt") is not None:
        raise WorkflowError("Resume only this exact original unrolled Engage")
    actual_cast = _cast(game, c, state, int(action["channel_id"]))
    if fingerprint(actual_cast) != meta["cast_sha256"]:
        raise WorkflowError("Recover the unchanged actual cast before original continuation")
    acting = resolve(
        state, ActorRef.model_validate(meta["actor"]), profiles(c, game.store.campaign_id)
    )
    target = resolve(
        state, ActorRef.model_validate(meta["target"]), profiles(c, game.store.campaign_id)
    )
    if (
        not any(not x.damaged for x in acting.assets)
        or acting.offstage_source
        or target.offstage_source
    ):
        raise WorkflowError("The original real actors lack this Engage's actual capability")
    meta.update(actor_sha256=acting.source_sha256, target_sha256=target.source_sha256)
    action["data"]["sheet_revision"] = state.sheets[action["actor_id"]].revision


def require_clear(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    identity = action["data"].get("hidden_sidearm")
    if identity and source(game, c, state, identity).phase == "reconsidering":
        raise WorkflowError(
            "SIDEARM_PAUSE: the original target must actually reconsider or take the shot"
        )


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any]:
    value = source(game, c, state, action["data"]["hidden_sidearm"])
    view = resolve(
        state, value.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    return dict(
        body=value.model_dump(mode="json"),
        assets=[
            dict(id=x.id, name=x.name) for x in view.assets if x.family == "girl" and not x.damaged
        ],
    )


def apply_response(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = source(game, c, state, json.loads(request["body_json"])["reveal"])
    current(game, c, state, value.acquisition)
    actual = resolve(
        state, value.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    actor = resolve(
        state, value.handler, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    body = next((x for x in state.placements if x.actor == value.target), None)
    if (
        value.phase != "reconsidering"
        or value.action != action["id"]
        or request["actor_id"] != value.target.entity
        or current_ref(state, int(value.target.entity)) != value.target
        or not answer.text.strip()
        or len(answer.options) != 1
        or body is None
        or body.vessel_id != value.vessel
        or actual.cell != actor.cell
        or actual.inside_frame is not False
        or fingerprint(_cast(game, c, state, int(action["channel_id"]))) != fingerprint(value.cast)
    ):
        raise WorkflowError("Only the original threatened Girl resolves this actual paused action")
    event = action["data"]["response_event"]
    if answer.options == ("reconsider",):
        if answer.fields:
            raise WorkflowError("Actual withdrawal does not also select damage")
        updated = value.model_copy(
            update=dict(phase="withdrawn", response_event=event, response=answer.text.strip())
        )
        _cancel(game, c, state, action, "actual_reconsideration")
    elif answer.options == ("continue",):
        if set(answer.fields) != {"asset"} or not any(
            x.id == answer.fields["asset"] and x.family == "girl" and not x.damaged
            for x in actual.assets
        ):
            raise WorkflowError(
                "The actual target chooses its intact Girl Asset for this ordinary shot"
            )
        changed, required = damage_actor(
            game,
            c,
            state,
            target=value.target,
            asset_id=answer.fields["asset"],
            source_action=action["id"],
            source_work=None,
            event=event,
            actor=value.handler,
            opponent=value.handler,
            chooser_controller=int(value.handler.entity),
            occurrence="hidden_sidearm_followthrough",
            physical_blow=True,
        )
        if required:
            raise WorkflowError(
                "UNSUPPORTED_SIDEARM_DAMAGE_CONSEQUENCE: this real protection needs its "
                "specific source continuation"
            )
        for name in GameState.model_fields:
            setattr(state, name, getattr(changed, name))
        helpless = is_helpless(state, value.target, value.handler)
        updated = value.model_copy(
            update=dict(
                phase="shot_helpless" if helpless else "shot",
                response_event=event,
                response=answer.text.strip(),
                asset=answer.fields["asset"],
            )
        )
        if helpless:
            _cancel(game, c, state, action, "actual_shot_helpless")
        else:
            refresh(game, c, state, action)
            action["state"] = "ready_to_roll"
    else:
        raise WorkflowError("Actually withdraw the original action or continue and take the shot")
    rules.put(state, rules.Reveal.model_validate_json(updated.model_dump_json()))


class HiddenSidearmService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy")
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        return self.store._write(
            viewer,
            key,
            kind,
            body,
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        revision: int,
        account: str,
        *,
        actual: bool,
        existing: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _, state, handler, appointment, award = HandlerAdvancementService(self.store)._source(
                c, viewer, award_id
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if (
                state.revision != revision
                or award is None
                or award.phase != "held"
                or not actual
                or not account.strip()
                or any(x.handler == handler for x in rules.acquisitions(state))
            ):
                raise WorkflowError(
                    "Spend one held award for the actual concealed ordinary sidearm"
                )
            event = str(uuid4())
            identity = "hidden-sidearm-acquisition:" + award_id
            if existing:
                item = prove_item(c, self.game, state, existing)
                if (
                    item.holder != handler
                    or not item.weapon
                    or item.condition != "intact"
                    or item.location_mode != "carried"
                ):
                    raise WorkflowError("Conceal only the actual carried intact ordinary firearm")
            else:
                item = HeldItem(
                    id="hidden-sidearm:" + event,
                    holder=handler,
                    name="Concealed ordinary sidearm",
                    description=account.strip(),
                    source_event=event,
                    source_owner=handler,
                    origin_event=event,
                    confirmed_by=handler,
                    confirmed_controller=viewer.user_id,
                    confirmed_event=event,
                    weapon=True,
                )
                state.held_items.append(item)
            value = rules.Acquisition(
                id=identity,
                award=award_id,
                handler=handler,
                appointment=appointment,
                gun=item.id,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            rules.put(
                state,
                rules.Concealment(
                    id="sidearm-hidden:" + event,
                    acquisition=value.id,
                    handler=handler,
                    gun=item.id,
                    event=event,
                    account=account.strip(),
                ),
            )
            awards.put(
                state,
                awards.Award.model_validate_json(
                    award.model_copy(
                        update=dict(
                            phase="spent",
                            acquired_rule=rules.RULE,
                            acquisition=value.id,
                            spend_event=event,
                            spend_account=account.strip(),
                        )
                    ).model_dump_json()
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
            )
            return dict(id=value.id, phase="acquired")

        return self._write(
            viewer,
            key,
            "m3.hidden_sidearm_buy",
            dict(
                award=award_id, revision=revision, account=account, actual=actual, existing=existing
            ),
            operation,
        )

    def conceal(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
        *,
        actual: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value, _ = current(self.game, c, state, identity)
            if (
                viewer.user_id != int(value.handler.entity)
                or state.revision != revision
                or not actual
                or not account.strip()
                or self.game.pending_actions(c)
                or any(
                    x.acquisition == value.id and x.reveal is None
                    for x in rules.concealments(state)
                )
            ):
                raise WorkflowError(
                    "Record actual new concealment without replacing an unrevealed occurrence"
                )
            event = str(uuid4())
            hidden = rules.Concealment(
                id="sidearm-hidden:" + event,
                acquisition=value.id,
                handler=value.handler,
                gun=value.gun,
                event=event,
                account=account.strip(),
            )
            rules.put(state, hidden)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.hidden_sidearm_concealed",
                state,
                event_id=event,
                concealment=hidden.id,
            )
            return dict(id=hidden.id)

        return self._write(
            viewer,
            key,
            "m3.hidden_sidearm_conceal",
            dict(id=identity, revision=revision, account=account, actual=actual),
            operation,
        )

    def reveal(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        target: ActorRef,
        choice: Literal["helpless", "kill", "pause"],
        account: str,
        *,
        actual: bool,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            receipt, _ = current(self.game, c, state, identity)
            hidden = next(
                (
                    concealment(self.game, c, state, x.id)
                    for x in rules.concealments(state)
                    if x.acquisition == receipt.id and x.reveal is None
                ),
                None,
            )
            if (
                viewer.user_id != int(receipt.handler.entity)
                or state.revision != revision
                or hidden is None
                or not actual
                or not account.strip()
            ):
                raise WorkflowError(
                    "Reveal this actual still-concealed gun with true reach and presence"
                )
            cast = _cast(self.game, c, state, channel)
            bound = profiles(c, self.store.campaign_id)
            acting, enemy = (
                resolve(state, x, bound, require_current_profile=False)
                for x in (receipt.handler, target)
            )
            body = next((x for x in state.placements if x.actor == target), None)
            if (
                target.kind != "pilot"
                or current_ref(state, int(target.entity)) != target
                or state.sheets[target.entity].girl == "AM"
                or enemy.inside_frame is not False
                or not enemy.alive
                or enemy.offstage_source
                or acting.offstage_source
                or enemy.cell is None
                or acting.cell is not None
                and acting.cell != enemy.cell
                or body is None
                or not all(any(r.actor == x for r in cast.roles) for x in (receipt.handler, target))
            ):
                raise WorkflowError(
                    "UNSUPPORTED_SIDEARM_TARGET: use actual in-reach original Handler and "
                    "out-of-Frame native Girl bodies/cast; never teleport or strike a Frame "
                    "Core"
                )
            event, identity2 = str(uuid4()), "sidearm-reveal:" + str(uuid4())
            if acting.cell is None:
                state.facts.append(
                    dict(
                        kind="hidden_sidearm_actual_position",
                        actor=receipt.handler.model_dump_json(),
                        cell=json.dumps(enemy.cell),
                        event=event,
                        reveal=identity2,
                        account=account.strip(),
                    )
                )
            action = self.game.action(c, action_id) if action_id else None
            if action and (
                action["channel_id"] != str(channel)
                or not _hostile(action, target, receipt.handler)
            ):
                raise WorkflowError("Bind only the real original unrolled go-after Engage")
            if not action and self.game.pending_actions(c):
                raise WorkflowError(
                    "Resolve actual pending Plays or name this exact unrolled interruption"
                )
            if choice == "pause" and action is None:
                raise WorkflowError("Pause must hold its real original unrolled action")
            archive = None
            if choice == "helpless":
                state = make_helpless(state, target, receipt.handler, event)
                phase = "helpless"
            elif choice == "kill":
                state = end_in_transaction(
                    c,
                    self.game,
                    state,
                    target,
                    reason="death",
                    source_event=event,
                    account="Actual revealed sidearm immediate lethal shot: " + account[:1000],
                    archive_id="sidearm-death:" + identity2,
                )
                archive = next(
                    (
                        x
                        for x in state.career_archives
                        if x.actor == target and x.source_event == event
                    ),
                    None,
                )
                phase = "death" if archive else "prevented"
            elif choice == "pause":
                phase = "reconsidering"
            else:
                raise WorkflowError("Choose one of the three printed revealed-sidearm effects")
            value = rules.Reveal.model_validate_json(
                json.dumps(
                    dict(
                        id=identity2,
                        acquisition=receipt.id,
                        concealment=hidden.id,
                        gun=receipt.gun,
                        handler=receipt.handler.model_dump(mode="json"),
                        target=target.model_dump(mode="json"),
                        vessel=body.vessel_id,
                        cast=cast.model_dump(mode="json"),
                        event=event,
                        account=account.strip(),
                        choice=choice,
                        phase=phase,
                        action=action_id,
                        archive=archive.id if archive else None,
                    )
                )
            )
            rules.put(state, value)
            rules.put(state, hidden.model_copy(update=dict(reveal=value.id)))
            if action:
                action["data"]["hidden_sidearm"] = value.id
                if phase == "reconsidering":
                    self.game.request(
                        c, action, int(target.entity), "sidearm_reconsider", dict(reveal=value.id)
                    )
                    action["state"] = "awaiting_choices"
                elif phase in ("helpless", "death"):
                    _cancel(self.game, c, state, action, "actual_" + phase)
                else:
                    refresh(self.game, c, state, action)
                self.game.save_action(c, action)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.hidden_sidearm_revealed",
                state,
                event_id=event,
                reveal_id=value.id,
                action_id=action_id,
            )
            if archive:
                synchronize_end(c, self.game, archive)
            return dict(id=value.id, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.hidden_sidearm_reveal",
            dict(
                id=identity,
                revision=revision,
                channel=channel,
                target=target.model_dump(mode="json"),
                choice=choice,
                account=account,
                actual=actual,
                action=action_id,
            ),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = next(
                (
                    source(self.game, c, state, x.id)
                    for x in rules.reveals(state)
                    if x.id == identity
                ),
                None,
            )
            if value:
                if viewer.user_id not in (int(value.handler.entity), int(value.target.entity)):
                    raise WorkflowError("This revealed threat belongs to its original people")
                return dict(
                    kind="reveal", revision=state.revision, body=value.model_dump(mode="json")
                )
            receipts = [
                paid(self.game, c, state, x.id)
                for x in rules.acquisitions(state)
                if x.handler.entity == str(viewer.user_id)
            ]
            if identity and identity not in {x.id for x in receipts}:
                raise WorkflowError("This personal sidearm belongs to its original Handler")
            receipt = receipts[0] if receipts else None
            hidden = next(
                (
                    x
                    for x in rules.concealments(state)
                    if receipt and x.acquisition == receipt.id and x.reveal is None
                ),
                None,
            )
            scenes = []
            targets = {}
            actions = []
            for row in c.execute(
                sa.select(t.m2["m2_scenes"]).where(
                    t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_scenes"].c.open.is_(True),
                )
            ).mappings():
                cast = _cast(self.game, c, state, int(row["channel_id"]))
                if receipt and not any(x.actor == receipt.handler for x in cast.roles):
                    continue
                scenes.append(dict(channel=cast.channel, id=cast.id))
                for role in cast.roles:
                    if role.actor.kind == "pilot":
                        target_view = resolve(
                            state,
                            role.actor,
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        )
                        targets[role.actor.token] = dict(
                            ref=role.actor.model_dump(mode="json"), label=target_view.label
                        )
            if receipt:
                table = t.m2["m2_actions"]
                for identity2 in c.scalars(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.state.in_(("acquiring", "ready_to_roll")),
                    )
                ):
                    action = self.game.action(c, identity2)
                    for target_data in targets.values():
                        if _hostile(
                            action, ActorRef.model_validate(target_data["ref"]), receipt.handler
                        ):
                            actions.append(
                                dict(
                                    id=action["id"],
                                    target=target_data["ref"],
                                    channel=int(action["channel_id"]),
                                )
                            )
            return dict(
                kind="acquisition",
                revision=state.revision,
                acquisition=receipt.id if receipt else None,
                concealed=hidden is not None,
                awards=[
                    dict(id=x.id, label=x.account)
                    for x in awards.awards(state)
                    if x.phase == "held" and x.handler.entity == str(viewer.user_id)
                ],
                scenes=scenes,
                targets=list(targets.values()),
                actions=actions,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Hidden Sidearm",
                phase="acquired",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]
        result.extend(
            dict(
                id=x.id,
                revision=state.revision,
                label="Revealed sidearm — " + x.phase,
                phase=x.phase,
                pending=False,
            )
            for x in rules.reveals(state)
            if viewer.user_id in (int(x.handler.entity), int(x.target.entity))
        )
        return result
