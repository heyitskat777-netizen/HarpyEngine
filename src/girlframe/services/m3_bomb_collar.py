"""Actual current Cadre collars, permanent Tag exception and real survival/death work."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bomb_collar as rules
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine.m2 import GameState, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

tags = rules.tags
save_tag = rules.save_tag


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    if value is None:
        raise WorkflowError("Recover the exact actual Bomb Collar acquisition")
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
        raise WorkflowError("Preserve the exact original held award and collar spend")
    return value


def collar(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Collar:
    value = next((x for x in rules.collars(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original body's bomb collar")
    receipt = paid(game, c, state, value.acquisition)
    born = next(
        (x for x in rules.collars(_history(c, game, value.event)) if x.id == identity), None
    )
    if (
        born is None
        or value.event != receipt.event
        or any(
            getattr(born, k) != getattr(value, k)
            for k in ("id", "acquisition", "target", "vessel", "event")
        )
        or any(
            getattr(born.tag, k) != getattr(value.tag, k)
            for k in ("id", "label", "giver_actor", "observers")
        )
        or value.tag.id != value.id
        or value.tag.rejection_pending
    ):
        raise WorkflowError("Preserve this source-supplied actual body collar and permanent Tag")
    return value


def prove_tag(
    game: GameService, c: Connection, state: GameState, owner: int, tag: TagState
) -> bool:
    if not tag.id.startswith("bomb-collar:"):
        return False
    value = collar(game, c, state, tag.id)
    body = next((x for x in state.placements if x.actor == value.target), None)
    if (
        value.target != current_ref(state, owner)
        or value.trigger is not None
        or value.tag != tag
        or body is None
        or body.vessel_id != value.vessel
    ):
        raise WorkflowError("Use only this original current body's actual untriggered collar")
    return True


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Trigger:
    value = next((x for x in rules.triggers(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover this actual collar detonation source")
    item = collar(game, c, state, value.collar)
    born = next(
        (x for x in rules.triggers(_history(c, game, value.event)) if x.id == identity), None
    )
    if (
        born is None
        or item.trigger != value.id
        or any(
            getattr(born, k) != getattr(value, k)
            for k in (
                "id",
                "collar",
                "target",
                "vessel",
                "handler",
                "appointment",
                "event",
                "cast",
                "account",
            )
        )
    ):
        raise WorkflowError("Recover the exact original Handler trigger/body/cast")
    return value


def work(game: GameService, c: Connection, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != "bomb_collar_survival":
        raise WorkflowError("Recover the original collar's actual survival work")
    return dict(row)


def prepare_survival(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not prepared.source_work or not prepared.source_work.startswith("bomb-trigger:"):
        return None
    BombCollarService(game.store)._access(c, viewer)
    value = source(game, c, state, prepared.source_work)
    row = work(game, c, value.id)
    cast = _cast(game, c, state, channel)
    body = next((x for x in state.placements if x.actor == value.target), None)
    if (
        value.phase != "survival"
        or row["state"] == "resolved"
        or value.target != current_ref(state, viewer.user_id)
        or prepared.play not in ("dive_deep", "keep_your_head")
        or prepared.parent is not None
        or prepared.target is not None
        or prepared.target_actor is not None
        or prepared.off_duty_id is not None
        or prepared.order_id is not None
        or fingerprint(cast) != fingerprint(value.cast)
        or body is None
        or body.vessel_id != value.vessel
    ):
        raise WorkflowError("Only the original affected Girl plays this actual source survival")
    actions = t.m2["m2_actions"]
    if c.scalar(
        sa.select(actions.c.id).where(
            actions.c.campaign_id == game.store.campaign_id,
            sa.func.json_extract(actions.c.body_json, "$.bomb_collar_source.work") == value.id,
        )
    ):
        raise WorkflowError("Resume the original real collar survival action; never reroll it")
    return dict(work=value.id, actor=value.target.model_dump(mode="json"), source_event=value.event)


def complete_action(
    game: GameService, c: Connection, action: dict[str, Any], event: str, key: str
) -> None:
    meta = action["data"].get("bomb_collar_source")
    if not meta or action["state"] != "complete":
        return
    state = load_state(c, game.store.campaign_id)
    value = source(game, c, state, meta["work"])
    if value.phase != "survival":
        if value.action != action["id"]:
            raise WorkflowError("This detonation already owns another actual outcome")
        return
    row = work(game, c, value.id)
    saved = game.action(c, action["id"])
    audit = c.execute(
        sa.select(t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).scalar_one_or_none()
    if (
        saved["state"] != "complete"
        or saved["data"] != action["data"]
        or not saved["data"].get("receipt")
        or audit is None
        or json.loads(audit).get("action_id") != action["id"]
        or meta["source_event"] != value.event
        or meta["actor"] != value.target.model_dump(mode="json")
        or action["data"]["prepared"]["source_work"] != value.id
    ):
        raise WorkflowError("Complete the genuine canonical original survival Play first")
    _history(c, game, event)
    play, result = action["data"]["play"], action["data"]["result"]
    lethal = play == "keep_your_head" and result.get("enough") is False
    if play == "dive_deep":
        dive = action["data"]["dive"]
        if any(not x.get("complete") for x in dive["steps"]) or any(
            not x.get("completed_event") for x in dive["followups"]
        ):
            raise WorkflowError("Finish every actual Dive effect and immediate consequence")
    elif (
        play != "keep_your_head"
        or type(result.get("enough")) is not bool
        or not result.get("ruling")
    ):
        raise WorkflowError("Use the real normal Keep sufficiency result for this detonation")
    effect = str(uuid4())
    archive = next((x for x in state.career_archives if x.actor == value.target), None)
    phase = "ended" if archive else "survived"
    if lethal and archive is None:
        state = end_in_transaction(
            c,
            game,
            state,
            value.target,
            reason="death",
            source_event=effect,
            account="Actual bomb-collar detonation; Keep was insufficient: "
            + result["ruling"][:1000],
            archive_id="bomb-death:" + value.id,
        )
        archive = next((x for x in state.career_archives if x.actor == value.target), None)
        phase = "death" if archive else "prevented"
    updated = value.model_copy(
        update=dict(
            phase=phase,
            action=action["id"],
            result_event=event,
            effect_event=effect,
            archive=archive.id if archive else None,
        )
    )
    rules.put(state, rules.Trigger.model_validate_json(updated.model_dump_json()))
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    game.event(
        c,
        int(value.target.entity),
        key,
        "m3.bomb_collar_outcome",
        state,
        event_id=effect,
        event_index=0 if index is None else index + 1,
        source_id=value.id,
        action_id=action["id"],
        result_event=event,
    )
    table = t.m3["m3_required_work"]
    payload = json.loads(row["body_json"]) | dict(
        phase=phase, effect_event=effect, action=action["id"]
    )
    c.execute(
        table.insert().values(
            **{
                k: v
                for k, v in row.items()
                if k not in ("revision", "event_id", "state", "body_json")
            },
            revision=row["revision"] + 1,
            event_id=effect,
            state="resolved",
            body_json=json.dumps(payload),
        )
    )
    if archive is not None:
        synchronize_end(c, game, archive, exclude_work=(value.id,))


class BombCollarService:
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
        self, viewer: GuildViewer, key: str, award_id: str, revision: int, account: str
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
                or not account.strip()
                or rules.acquisitions(state)
            ):
                raise WorkflowError("Spend one genuine held advancement on unowned Bomb Collars")
            event = str(uuid4())
            receipt = rules.Acquisition(
                id="bomb-collars:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            collars = []
            for uid in state.order:
                actor = current_ref(state, uid)
                actual = resolve(
                    state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
                )
                body = next((x for x in state.placements if x.actor == actor), None)
                if (
                    body is None
                    or actual.rules != "girl_frame"
                    or state.sheets[str(uid)].girl == "AM"
                    or actual.offstage_source
                ):
                    raise WorkflowError(
                        "UNSUPPORTED_COLLAR_BODY: establish each native Girl's actual body; "
                        "AM/external bodies need their own port"
                    )
                identity = "bomb-collar:" + receipt.id + ":" + actor.token
                collars.append(
                    rules.Collar(
                        id=identity,
                        acquisition=receipt.id,
                        target=actor,
                        vessel=body.vessel_id,
                        event=event,
                        tag=TagState(
                            id=identity,
                            label="Wearing a bomb collar",
                            giver=int(handler.entity),
                            giver_actor=handler,
                            observers=tuple(sorted(set(state.order) | {int(handler.entity)})),
                        ),
                    )
                )
            if not collars:
                raise WorkflowError("An actual current Cadre is required for its supplied collars")
            rules.put(state, receipt)
            for item in collars:
                rules.put(state, item)
            awards.put(
                state,
                awards.Award.model_validate_json(
                    award.model_copy(
                        update=dict(
                            phase="spent",
                            acquired_rule=rules.RULE,
                            acquisition=receipt.id,
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
            return dict(id=receipt.id, phase="acquired")

        return self._write(
            viewer,
            key,
            "m3.bomb_collar_buy",
            dict(award=award_id, revision=revision, account=account),
            operation,
        )

    def trigger(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            item = collar(self.game, c, state, identity)
            receipt = paid(self.game, c, state, item.acquisition)
            cast = _cast(self.game, c, state, channel)
            if (
                viewer.user_id != int(receipt.handler.entity)
                or not same_handler_body(state, receipt.handler)
                or HandlerCreationService(self.store)._appointment_source(c, viewer.user_id)
                != receipt.appointment
                or state.revision != revision
                or item.trigger is not None
                or self.game.pending_actions(c)
                or not account.strip()
            ):
                raise WorkflowError(
                    "Only the original current Handler triggers this actual untriggered collar"
                )
            prove_tag(self.game, c, state, int(item.target.entity), item.tag)
            if not any(x.actor == item.target for x in cast.roles):
                raise WorkflowError("Join the actual affected Girl in this source response scene")
            event, identity2 = str(uuid4()), "bomb-trigger:" + str(uuid4())
            value = rules.Trigger(
                id=identity2,
                collar=item.id,
                target=item.target,
                vessel=item.vessel,
                handler=receipt.handler,
                appointment=receipt.appointment,
                event=event,
                cast=cast,
                account=account.strip(),
            )
            rules.put(state, item.model_copy(update=dict(trigger=value.id)))
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.bomb_collar_triggered",
                state,
                event_id=event,
                source_id=value.id,
                collar_id=item.id,
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                value.id,
                int(item.target.entity),
                int(item.target.entity),
                "bomb_collar_survival",
                dict(
                    phase="survival",
                    immediate=True,
                    source_event=event,
                    actor=item.target.model_dump(mode="json"),
                ),
                event,
            )
            return dict(id=value.id, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.bomb_collar_trigger",
            dict(id=identity, revision=revision, channel=channel, account=account),
            operation,
        )

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, prepared: PlayInput
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if state.revision != revision or prepared.source_work != value.id:
                raise WorkflowError("Refresh this actual original survival response")
            channel = value.cast.channel
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None:
                raise WorkflowError("Only the original affected Girl owns its survival Play")
        return self.game.begin(viewer, key, channel, sheet.revision, prepared)

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            trigger = next(
                (
                    source(self.game, c, state, x.id)
                    for x in rules.triggers(state)
                    if x.id == identity
                ),
                None,
            )
            if trigger:
                if viewer.user_id not in (int(trigger.handler.entity), int(trigger.target.entity)):
                    raise WorkflowError("This actual detonation belongs to its original people")
                sheet = state.sheets.get(trigger.target.entity)
                return dict(
                    kind="trigger",
                    id=trigger.id,
                    revision=state.revision,
                    body=trigger.model_dump(mode="json"),
                    own=viewer.user_id == int(trigger.target.entity),
                    sheet=sheet.model_dump(mode="json")
                    if sheet
                    and sheet.character_id == trigger.target.incarnation
                    and viewer.user_id == int(trigger.target.entity)
                    else None,
                )
            receipts = [
                paid(self.game, c, state, x.id)
                for x in rules.acquisitions(state)
                if x.handler.entity == str(viewer.user_id)
            ]
            if identity and identity not in {x.id for x in receipts}:
                raise WorkflowError("This acquisition belongs to its original Handler")
            return dict(
                kind="acquisition",
                revision=state.revision,
                acquisition=receipts[0].id if receipts else None,
                awards=[
                    dict(id=x.id, label=x.account)
                    for x in awards.awards(state)
                    if x.phase == "held" and x.handler.entity == str(viewer.user_id)
                ],
                collars=[
                    x.model_dump(mode="json")
                    for x in rules.collars(state)
                    if receipts and x.acquisition == receipts[0].id
                ],
                scenes=[
                    dict(channel=int(x["channel_id"]), id=x["id"])
                    for x in c.execute(
                        sa.select(t.m2["m2_scenes"]).where(
                            t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                            t.m2["m2_scenes"].c.open.is_(True),
                        )
                    ).mappings()
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Bomb Collars",
                phase="acquired",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]
        for value in rules.triggers(state):
            if viewer.user_id in (int(value.handler.entity), int(value.target.entity)):
                actions = t.m2["m2_actions"]
                started = c.scalar(
                    sa.select(actions.c.id).where(
                        actions.c.campaign_id == self.store.campaign_id,
                        sa.func.json_extract(actions.c.body_json, "$.bomb_collar_source.work")
                        == value.id,
                    )
                )
                result.append(
                    dict(
                        id=value.id,
                        revision=state.revision,
                        label="Actual bomb collar — " + value.phase,
                        phase=value.phase,
                        pending=value.phase == "survival"
                        and started is None
                        and viewer.user_id == int(value.target.entity),
                    )
                )
        return result
