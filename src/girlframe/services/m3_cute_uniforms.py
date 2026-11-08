"""Finite genuine advancement, actual dressing and source-owned uniform consequences."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_cute_uniforms as rules
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine.m2 import (
    AssetState,
    ChoiceAnswer,
    GameState,
    IdentityState,
    PlayInput,
    TagState,
    shift_status,
)
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import install
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_janus_storage import ids as stored_ids
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

# Public narrow pure ports for the existing Tag pipeline.
tags = rules.tags
save_tag = rules.save_tag


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual acquired Cute Uniforms source")
    born = next(
        (x for x in rules.acquisitions(_history(c, game, value.event)) if x.id == identity), None
    )
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.acquired_rule != rules.RULE
        or award.acquisition != value.id
        or award.spend_event != value.event
        or (handler, appointment) != (value.handler, value.appointment)
    ):
        raise WorkflowError("Recover this exact original Handler advancement acquisition")
    return value


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Uniform:
    value = next((x for x in rules.uniforms(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover this actual original uniform")
    receipt = paid(game, c, state, value.acquisition)
    proposed = next(
        (x for x in rules.uniforms(_history(c, game, value.event)) if x.id == identity), None
    )
    stable = (
        "id",
        "acquisition",
        "handler",
        "target",
        "name",
        "description",
        "cell",
        "position",
        "event",
    )
    if (
        proposed is None
        or proposed.phase != "proposed"
        or any(getattr(proposed, k) != getattr(value, k) for k in stable)
        or value.handler != receipt.handler
    ):
        raise WorkflowError("Recover the actual Handler-authored uniform proposal")
    if value.dressing_event:
        dressed = next(
            (
                x
                for x in rules.uniforms(_history(c, game, value.dressing_event))
                if x.id == identity
            ),
            None,
        )
        if (
            dressed is None
            or dressed.phase != "worn"
            or dressed.tag is None
            or value.tag is None
            or any(
                getattr(dressed.tag, k) != getattr(value.tag, k)
                for k in ("id", "label", "giver", "giver_actor", "observers")
            )
        ):
            raise WorkflowError("Recover the original owner-confirmed actual dressing")
    return value


def prove_tag(
    game: GameService, c: Connection, state: GameState, owner: int, tag: TagState
) -> bool:
    if not tag.id.startswith("cute-uniform:"):
        return False
    value = source(game, c, state, tag.id)
    if value not in rules.owned(state, owner) or value.tag != tag:
        raise WorkflowError("Recover the original Girl's actual worn uniform Tag")
    return True


def prepare_keep(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    *,
    actor: ActorRef | None = None,
) -> dict[str, Any] | None:
    if prepared.play != "keep_your_head":
        return None
    actor = actor or current_ref(state, viewer.user_id)
    values = tuple(x for x in rules.owned(state, int(actor.entity)) if x.wearing)
    if not values:
        return None
    for value in values:
        source(game, c, state, value.id)
    return dict(
        actor=actor.model_dump(mode="json"),
        uniforms=[dict(id=x.id, event=x.dressing_event) for x in values],
        presentation=rules.PRESENTATION,
    )


def pre_roll(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    meta = action["data"].get("cute_uniforms")
    if not meta:
        return
    actor = ActorRef.model_validate(meta["actor"])
    actual = tuple(x for x in rules.owned(state, int(actor.entity)) if x.wearing)
    if (
        current_ref(state, int(actor.entity)) != actor
        or [dict(id=x.id, event=x.dressing_event) for x in actual] != meta["uniforms"]
    ):
        raise WorkflowError("The actual worn uniform changed before this Keep")
    for value in actual:
        source(game, c, state, value.id)


def validate_keep_choice(action: dict[str, Any], answer: ChoiceAnswer) -> None:
    if (
        action["data"].get("cute_uniforms")
        and answer.fields.get("cute_uniform") != "helpless_adorable"
    ):
        raise WorkflowError("While wearing the uniform also choose: I seem helpless and adorable.")


def apply_keep_result(action: dict[str, Any]) -> None:
    meta = action["data"].get("cute_uniforms")
    if meta:
        action["data"]["result"]["forced_presentations"] = [
            dict(presentation=rules.PRESENTATION, uniforms=meta["uniforms"], source=rules.RULE)
        ]


def resolve_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    body: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    if not str(body.get("tag", "")).startswith("cute-uniform:"):
        return False
    actor = int(action["actor_id"])
    value = source(game, c, state, body["tag"])
    tag = value.tag
    if (
        tag is None
        or value not in rules.owned(state, actor)
        or len(answer.options) != 1
        or answer.options[0] not in ("reject", "embrace", "embrace_asset")
    ):
        raise WorkflowError("The actual affected original Girl chooses this uniform's response")
    sheet = state.sheets[str(actor)]
    if answer.options == ("reject",):
        from girlframe.engine.m3_beneath import rejection_blocked
        from girlframe.engine.m3_girl_runtime_state import mentor_tag

        if rejection_blocked(state, actor, tag.id) or mentor_tag(sheet, tag, state):
            raise WorkflowError("This actual Tag's existing rejection restriction still applies")
        tag.rejection_pending = True
        rules.save_tag(state, actor, tag)
        game.obligation(state, action, "reject_tag", actor, tag=tag.id)
    elif answer.options == ("embrace_asset",):
        if value.asset is None:
            asset_id = value.id + ":asset"
            result = install(
                sheet,
                AssetState(
                    id=asset_id, family="girl", name=value.name, description=value.description
                ),
                replace=answer.fields.get("replace") or None,
                effective_void=stored_ids(state, value.target),
                state=state,
            )
            state.sheets[str(actor)] = result.sheet
            rules.put(state, value.model_copy(update=dict(asset=asset_id)))
        elif not any(x.id == value.asset for x in sheet.assets):
            raise WorkflowError(
                "The previously embraced uniform Asset is no longer owned; it cannot be duplicated"
            )
        tag.marked = False
        tag.rejection_pending = False
        rules.save_tag(state, actor, tag)
    else:
        if len(answer.denied) != 1:
            raise WorkflowError("Choose the actual ordinary Identity slot to replace")
        from girlframe.engine.m3_leviathan_obsession import require_unlocked

        require_unlocked(sheet.identities, answer.denied)
        old = next(
            (x for x in sheet.identities if x.id == answer.denied[0] and not x.protected), None
        )
        from girlframe.services.m2_choices import ChoiceEngine

        if (
            old is None
            or not ChoiceEngine(game).duplicate_labels()
            and any(x.name.casefold() == tag.label.casefold() for x in sheet.identities)
        ):
            raise WorkflowError(
                "Choose a replaceable ordinary Identity and a distinct uniform label"
            )
        identity = IdentityState(
            id=str(uuid4()), name=tag.label, marked=old.id in sheet.sedation_locked, slot=old.slot
        )
        sheet.identities = [x for x in sheet.identities if x.id != old.id] + [identity]
        if identity.marked:
            sheet.sedation_locked = tuple(x for x in sheet.sedation_locked if x != old.id) + (
                identity.id,
            )
        tag.marked = False
        tag.rejection_pending = False
        rules.put(state, value.model_copy(update=dict(embraced_identity=identity.id, tag=tag)))
    state.sheets[str(actor)].revision += 1
    return True


def reject_tag(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    tag: TagState,
    event: str,
) -> bool:
    if not tag.id.startswith("cute-uniform:"):
        return False
    value = source(game, c, state, tag.id)
    actor = int(action["actor_id"])
    from girlframe.engine.m3_beneath import rejection_blocked
    from girlframe.engine.m3_girl_runtime_state import mentor_tag

    play = action["data"]["play"]
    actual_refusal = (
        play == "disobey_orders"
        and action["data"]["result"].get("tier") == "mid"
        and bool(action["data"].get("receipt"))
    )
    if (
        value not in rules.owned(state, actor)
        or value.tag != tag
        or value.embraced_identity is not None
        or not (actual_refusal or play == "reject_tag" and tag.rejection_pending)
        or not same_handler_body(state, value.handler)
        or rejection_blocked(state, actor, tag.id)
        or mentor_tag(state.sheets[str(actor)], tag, state)
    ):
        raise WorkflowError("Recover the actual printed uniform rejection and original Handler")
    rules.put(
        state,
        value.model_copy(
            update=dict(
                phase="rejected",
                wearing=False,
                rejection_event=event,
                punishment=value.id + ":punishment",
            )
        ),
    )
    from girlframe.services.m3_intracadre_marriage import allocate_punishment

    allocate_punishment(
        game,
        c,
        state,
        value.target,
        source_event=event,
        source_id=value.id,
        work_id=value.id + ":punishment",
    )
    action["data"]["cute_uniform_rejection"] = dict(uniform=value.id, event=event)
    return True


def reject(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> bool:
    obligation = next(x for x in state.obligations if x.id == action["data"]["obligation_id"])
    identity = obligation.details.get("tag", "")
    if not identity.startswith("cute-uniform:"):
        return False
    value = source(game, c, state, identity)
    if value.tag is None:
        raise WorkflowError("Recover the actual owed uniform Tag")
    return reject_tag(game, c, state, action, value.tag, event)


def synchronize_rejection(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("cute_uniform_rejection")
    if not meta:
        return
    state = load_state(c, game.store.campaign_id)
    value = source(game, c, state, meta["uniform"])
    if (
        value.rejection_event != meta["event"]
        or value.phase != "rejected"
        or value.punishment is None
    ):
        raise WorkflowError("Recover the actual performed uniform rejection event")
    table = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(table.c.id)
        .where(table.c.campaign_id == game.store.campaign_id, table.c.id == value.punishment)
        .limit(1)
    ):
        return
    if value.rejection_event != event:
        raise WorkflowError("Recover the original performed rejection event before creating work")
    from girlframe.engine import m3_intracadre_marriage as marriage

    allocation = next(
        (x for x in marriage.records(state, marriage.Allocation) if x.source_id == value.id), None
    )
    recipient = allocation.subject if allocation else value.target
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
        value.punishment,
        int(value.handler.entity),
        int(recipient.entity),
        "punishment",
        dict(
            reason="cute_uniform_rejection",
            uniform=value.id,
            rejection_action=action["id"],
            source_event=event,
            character=recipient.incarnation,
            **marriage.allocation_fields(state, value.id),
            original_handler=value.handler.model_dump(mode="json"),
            source_pdf=154,
            immediate=True,
        ),
        event,
    )


def _validate_original_punishment(
    game: GameService, c: Connection, state: GameState, row: dict[str, Any]
) -> None:
    body = json.loads(row["body_json"])
    if body.get("reason") != "cute_uniform_rejection":
        return
    value = source(game, c, state, body["uniform"])
    action = game.action(c, body["rejection_action"])
    from girlframe.services.m3_intracadre_marriage import original_offender

    recipient = ActorRef(kind="pilot", entity=row["subject_id"], incarnation=body["character"])
    offender = original_offender(game, c, state, value.id, body["source_event"], recipient)
    born = next(
        (x for x in rules.uniforms(_history(c, game, body["source_event"])) if x.id == value.id),
        None,
    )
    if (
        born is None
        or born.phase != "rejected"
        or born.rejection_event != body["source_event"]
        or value.punishment != row["id"]
        or offender != value.target
        or body["original_handler"] != value.handler.model_dump(mode="json")
        or not same_handler_body(state, value.handler)
        or current_ref(state, int(value.target.entity)) != value.target
        or action["data"].get("cute_uniform_rejection")
        != dict(uniform=value.id, event=body["source_event"])
    ):
        raise WorkflowError(
            "Recover the real uniform rejection and original Handler-owned Punishment"
        )

    table = t.m3["m3_required_work"]
    versions = list(
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == row["id"],
                table.c.revision <= row["revision"],
            )
            .order_by(table.c.revision)
        ).mappings()
    )
    executor = value.handler
    frozen = (
        "reason",
        "uniform",
        "rejection_action",
        "source_event",
        "character",
        "original_handler",
    )
    if not versions or versions[0]["owner_id"] != executor.entity:
        raise WorkflowError("Recover the original Handler-owned uniform consequence")
    for version in versions:
        saved = json.loads(version["body_json"])
        if any(saved.get(k) != body.get(k) for k in frozen):
            raise WorkflowError("Preserve the exact original uniform rejection source")
        if version["owner_id"] != executor.entity:
            audit = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id,
                        t.events.c.id == version["event_id"],
                    )
                )
                .mappings()
                .first()
            )
            command = (
                c.execute(
                    sa.select(t.commands).where(
                        t.commands.c.campaign_id == game.store.campaign_id,
                        t.commands.c.interaction_key == audit["command_key"],
                    )
                )
                .mappings()
                .first()
                if audit
                else None
            )
            outcome = json.loads(command["outcome_json"]) if command else {}
            if (
                audit is None
                or audit["kind"] != "m3.punishment_delegated"
                or audit["actor_id"] != executor.entity
                or json.loads(audit["payload_json"]).get("work_id") != row["id"]
                or outcome.get("id") != row["id"]
                or outcome.get("state") != "delegated"
                or not saved.get("discipline_owner_character")
            ):
                raise WorkflowError("Recover the real source owner's actual delegated Punishment")
            executor = ActorRef(
                kind="pilot",
                entity=version["owner_id"],
                incarnation=saved["discipline_owner_character"],
            )
        elif (
            executor.kind == "pilot"
            and saved.get("discipline_owner_character") != executor.incarnation
        ):
            raise WorkflowError("A delegated Punishment stays with its original Pilot")
    if (
        executor.entity != row["owner_id"]
        or executor.kind == "pilot"
        and game.character_binding(c, state, int(executor.entity), require_current_profile=False)
        != executor.incarnation
    ):
        raise WorkflowError("Recover the genuine current executor of the uniform Punishment")


def _application_before(
    game: GameService, c: Connection, row: dict[str, Any], event: str
) -> GameState:
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    table = t.m3["m3_required_work"]
    resolved = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == row["id"],
                table.c.event_id == event,
                table.c.state == "resolved",
            )
        )
        .mappings()
        .first()
    )
    if (
        audit is None
        or audit["kind"] != "m3.punishment_applied"
        or resolved is None
        or json.loads(resolved["body_json"]).get("applied_event") != event
    ):
        raise WorkflowError("Complete only this source's genuine canonical Punishment application")
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, t.events.c.id == history.c.event_id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < audit["seq"],
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if raw is None:
        raise WorkflowError("Recover the actual pre-Punishment original-body source")
    return GameState.model_validate_json(raw)


def validate_punishment_work(
    game: GameService, c: Connection, state: GameState, row: dict[str, Any]
) -> None:
    body = json.loads(row["body_json"])
    if body.get("reason") != "cute_uniform_rejection":
        return
    if row["state"] == "resolved" and body.get("applied_event"):
        state = _application_before(game, c, row, body["applied_event"])
    _validate_original_punishment(game, c, state, row)


def complete_punishment(game: GameService, c: Connection, row: dict[str, Any], event: str) -> None:
    body = json.loads(row["body_json"])
    if body.get("reason") == "cute_uniform_rejection":
        _validate_original_punishment(game, c, _application_before(game, c, row, event), row)
    # The actual discipline effect is complete even when it ended the original body.


class CuteUniformService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            HandlerService(self.store).authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            held = [
                paid(self.game, c, state, x.id)
                for x in rules.acquisitions(state)
                if same_handler_body(state, x.handler)
            ]
            return dict(
                revision=state.revision,
                owned=bool(held),
                awards=HandlerAdvancementService(self.store)._tasks(c, viewer),
                targets=[
                    dict(
                        actor=current_ref(state, uid).model_dump(mode="json"),
                        token=current_ref(state, uid).token,
                        label=state.sheets[str(uid)].callsign,
                    )
                    for uid in state.order
                ],
                uniforms=[
                    dict(id=x.id, label=x.name, phase=x.phase)
                    for x in rules.uniforms(state)
                    if x.handler.entity == str(viewer.user_id)
                ],
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
                or any(same_handler_body(state, x.handler) for x in rules.acquisitions(state))
            ):
                raise WorkflowError("Spend one actual held advancement on unowned Cute Uniforms")
            event = str(uuid4())
            value = rules.Acquisition(
                id="cute-uniforms:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            advancement.put(
                state,
                advancement.Award.model_validate_json(
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

        return self.store._write(
            viewer,
            key,
            "m3.cute_uniforms_acquired",
            dict(award=award_id, revision=revision, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        target: ActorRef,
        name: str,
        description: str,
        present: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            HandlerService(self.store).authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            values = [x for x in rules.acquisitions(state) if same_handler_body(state, x.handler)]
            if (
                state.revision != revision
                or len(values) != 1
                or not present
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("The actual original Handler must be present for this dressing")
            receipt = paid(self.game, c, state, values[0].id)
            HandlerAdvancementService(self.store)._current(
                c, state, receipt.handler, receipt.appointment
            )
            if (
                target.kind != "pilot"
                or current_ref(state, int(target.entity)) != target
                or any(x.target == target and x.phase == "proposed" for x in rules.uniforms(state))
            ):
                raise WorkflowError(
                    "Select an actual current original Girl without another pending dressing"
                )
            bindings = profiles(c, self.store.campaign_id)
            actual = resolve(state, target, bindings, require_current_profile=False)
            handler = resolve(state, receipt.handler, bindings, require_current_profile=False)
            if (
                actual.cell is None
                or actual.position_sha256 is None
                or actual.offstage_source
                or handler.offstage_source
                or handler.cell is not None
                and handler.cell != actual.cell
            ):
                raise WorkflowError(
                    "A conflicting Handler position requires genuine movement before dressing"
                )
            event = str(uuid4())
            value = rules.Uniform(
                id="cute-uniform:" + event,
                acquisition=receipt.id,
                handler=receipt.handler,
                target=target,
                name=name.strip(),
                description=description.strip(),
                cell=actual.cell,
                position=actual.position_sha256,
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.cute_uniform_proposed",
                state,
                event_id=event,
                uniform=value.id,
            )
            return dict(id=value.id, phase=value.phase)

        return self.store._write(
            viewer,
            key,
            "m3.cute_uniform_proposed",
            dict(
                revision=revision,
                target=target.model_dump(mode="json"),
                name=name,
                description=description,
                present=present,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if str(viewer.user_id) not in (value.handler.entity, value.target.entity):
                raise WorkflowError("This actual uniform belongs to its original participants")
            if str(viewer.user_id) == value.target.entity and (
                value.target.entity not in state.sheets
                or current_ref(state, viewer.user_id) != value.target
            ):
                raise WorkflowError("This physical uniform belongs to its original Girl")
            return dict(
                id=value.id,
                revision=state.revision,
                phase=value.phase,
                name=value.name,
                description=value.description,
                target=value.target.entity,
                handler=value.handler.entity,
                cell=value.cell,
                asset=value.asset,
                wearing=value.wearing,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                phase=x.phase,
                label=(
                    "Confirm actual uniform dressing"
                    if x.phase == "proposed"
                    else "Actual worn uniform — clothing control"
                ),
                revision=state.revision,
            )
            for x in rules.uniforms(state)
            if x.phase in ("proposed", "worn")
            and x.target.entity == str(viewer.user_id)
            and x.target.entity in state.sheets
            and current_ref(state, viewer.user_id) == x.target
        ]

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if (
                state.revision != revision
                or value.phase != "proposed"
                or value.target.entity != str(viewer.user_id)
                or current_ref(state, viewer.user_id) != value.target
                or not account.strip()
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("The actual affected original Girl confirms this dressing")
            if accept:
                receipt = paid(self.game, c, state, value.acquisition)
                HandlerAdvancementService(self.store)._current(
                    c, state, receipt.handler, receipt.appointment
                )
                bindings = profiles(c, self.store.campaign_id)
                actual = resolve(state, value.target, bindings, require_current_profile=False)
                handler = resolve(state, value.handler, bindings, require_current_profile=False)
                if (
                    actual.cell != value.cell
                    or actual.position_sha256 != value.position
                    or actual.offstage_source
                    or handler.offstage_source
                    or handler.cell is not None
                    and handler.cell != actual.cell
                ):
                    raise WorkflowError(
                        "Confirm actual unchanged co-presence; never teleport the Handler"
                    )
            event = str(uuid4())
            if accept:
                if handler.cell is None:
                    state.facts.append(
                        dict(
                            kind="cute_uniform_actual_dressing_position",
                            actor=value.handler.model_dump_json(),
                            cell=json.dumps(value.cell),
                            event=event,
                            uniform=value.id,
                            confirmed_by=value.target.model_dump_json(),
                        )
                    )
                tag = TagState(
                    id=value.id,
                    label=value.name,
                    giver=int(value.handler.entity),
                    giver_actor=value.handler,
                    observers=(int(value.handler.entity), int(value.target.entity)),
                )
                rules.put(
                    state,
                    value.model_copy(
                        update=dict(
                            phase="worn",
                            wearing=True,
                            tag=tag,
                            dressing_event=event,
                            dressing_account=account.strip(),
                        )
                    ),
                )
                shift_status(state, viewer.user_id, -1)
                state.sheets[str(viewer.user_id)].revision += 1
            else:
                rules.put(state, value.model_copy(update=dict(phase="declined")))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.cute_uniform_dressing_confirmed"
                if accept
                else "m3.cute_uniform_proposal_declined",
                state,
                event_id=event,
                uniform=identity,
            )
            return dict(id=identity, phase="worn" if accept else "declined")

        return self.store._write(
            viewer,
            key,
            "m3.cute_uniform_dressing",
            dict(id=identity, revision=revision, accept=accept, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def wearing(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
        wear: bool = False,
    ) -> dict[str, Any]:
        """Actual owner dressing/undressing never fabricates Handler dressing or rejection."""

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if (
                state.revision != revision
                or value.phase != "worn"
                or value.wearing == wear
                or value.target.entity != str(viewer.user_id)
                or current_ref(state, viewer.user_id) != value.target
                or not account.strip()
                or len(account) > 1200
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "The original Girl records only an actual completed change in wearing"
                )
            rules.put(state, value.model_copy(update=dict(wearing=wear)))
            event = str(uuid4())
            state.facts.append(
                dict(
                    kind="cute_uniform_actual_clothing_change",
                    uniform=identity,
                    actor=value.target.model_dump_json(),
                    event=event,
                    wearing=json.dumps(wear),
                    account=account.strip(),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.cute_uniform_wearing_changed",
                state,
                event_id=event,
                uniform=identity,
                wearing=wear,
            )
            return dict(id=identity, wearing=wear)

        return self.store._write(
            viewer,
            key,
            "m3.cute_uniform_doffed",
            dict(id=identity, revision=revision, account=account, wear=wear),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
