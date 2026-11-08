"""Genuine Ankou sources, actual owned choices and durable private consequences."""

import json
from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services import m3_ankou_support as support
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = (
    "ankou_processor_benefits",
    "ankou_processor_symptoms",
    "ankou_interrupt",
    "ankou_interrupt_child",
)


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
) -> None:
    Access(game.store).authorize(c, viewer, "plays", director_response=True)
    if (
        action is not None
        and action["data"].get("ankou")
        and viewer.user_id not in action["data"]["ankou"]["table"]
    ):
        raise WorkflowError("Only the original actual processor source table may answer")


def require_rule(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, rule: str
) -> None:
    rules.frame(state, actor)
    registry = Access(game.store).registry
    if registry is None:
        raise WorkflowError("Recover the actual reviewed Ankou rule source")
    registry.require_available(rule)
    if rule in rules.REQUISITIONS:
        held = rules.held(state, actor, rule)
        if not held:
            raise WorkflowError("Acquire this actual original Frame's Requisition first")
        for receipt in held:
            purchase_proof(c, game.store, receipt)


def prove_proposal(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Proposal:
    value = rules.get(state, rules.Proposal, identity)
    birth = support.prove_birth(
        game, c, value.event, "m3.ankou_processor_proposed", int(value.actor.entity)
    )
    original = rules.get(birth, rules.Proposal, identity)
    if value.model_copy(update={"action": None, "bound_event": None}) != original:
        raise WorkflowError("Preserve the original actual processor proposal, minds and exemptions")
    require_rule(game, c, birth, value.actor, rules.PROCESSOR)
    if value.bound_event:
        saved = rules.get(_history(c, game, value.bound_event), rules.Proposal, identity)
        if saved.action != value.action or saved.bound_event != value.bound_event:
            raise WorkflowError("Preserve the real original processor Action binding")
    return value


def prove_source(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Processor:
    value = rules.get(state, rules.Processor, identity)
    action = game.action(c, identity)
    meta = action["data"]["ankou"]
    rolled, total = _roll_source(game, c, action)
    born = rules.get(_history(c, game, value.event), rules.Processor, identity)
    if (
        any(
            getattr(value, k) != getattr(born, k)
            for k in (
                "id",
                "actor",
                "frame",
                "cast",
                "handler",
                "handler_controller",
                "registry",
                "minds",
                "positions",
                "roll_event",
                "total",
                "event",
            )
        )
        or value.roll_event != rolled
        or value.total != total
        or meta["proposal"] != meta["id"]
    ):
        raise WorkflowError(
            "Preserve the actual immutable processor receipt, range and original minds"
        )
    proposal = prove_proposal(game, c, _history(c, game, value.roll_event), meta["proposal"])
    if (
        proposal.action != identity
        or proposal.actor != value.actor
        or proposal.minds != value.minds
    ):
        raise WorkflowError("Recover the exact actual admitted processor source")
    if value.selected_event:
        selected = rules.get(_history(c, game, value.selected_event), rules.Processor, identity)
        if any(
            getattr(selected, k) != getattr(value, k) for k in ("benefits", "assets")
        ) or not set(selected.tags) <= set(value.tags):
            raise WorkflowError("Preserve every genuine selected processor benefit")
    if value.symptoms_event:
        symptomatic = rules.get(_history(c, game, value.symptoms_event), rules.Processor, identity)
        if symptomatic.symptoms != value.symptoms or symptomatic.tags != value.tags:
            raise WorkflowError("Preserve the actual selected processor symptom Tags")
    return value


def prove_relay(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Relay:
    value = rules.get(state, rules.Relay, identity)
    birth = support.prove_birth(
        game, c, value.event, "m3.ankou_relay_activated", int(value.actor.entity)
    )
    original = rules.get(birth, rules.Relay, identity)
    if any(
        getattr(value, k) != getattr(original, k)
        for k in (
            "id",
            "actor",
            "frame",
            "cast",
            "handler",
            "handler_controller",
            "benefits",
            "event",
        )
    ):
        raise WorkflowError("Preserve the actual original activated emotional relay")
    require_rule(game, c, birth, value.actor, rules.RELAY)
    if value.consequence_event:
        selected = support.prove_birth(
            game, c, value.consequence_event, "m3.ankou_relay_consequence", value.handler_controller
        )
        if rules.get(selected, rules.Relay, identity).consequence != value.consequence:
            raise WorkflowError("Preserve the actual original Handler's consequence choice")
    return value


def prove_obsession(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, target: ActorRef
) -> rules.Obsession | None:
    values = [
        x
        for x in rules.records(state, rules.Obsession)
        if x.actor == actor and x.target == target and not x.ended_event
    ]
    if not values:
        return None
    value = values[-1]
    try:
        if rules.frame(state, actor) != value.frame or not rules.held(
            state, actor, rules.OBSESSIVE
        ):
            return None
    except ValueError:
        return None
    birth = support.prove_birth(
        game, c, value.event, "m3.ankou_obsession_chosen", int(actor.entity)
    )
    if rules.get(birth, rules.Obsession, value.id) != value.model_copy(
        update={"sequence": None, "replacement_event": None}
    ):
        raise WorkflowError("Preserve the original one-sided Obsession person/source")
    require_rule(game, c, birth, actor, rules.OBSESSIVE)
    return value


def _positions(
    game: GameService, c: Connection, state: GameState, people: tuple[ActorRef, ...]
) -> dict[str, str]:
    bound = profiles(c, game.store.campaign_id)
    result = {}
    for actor in people:
        view = resolve(state, actor, bound)
        if not view.alive or view.offstage_source or view.position_sha256 is None:
            raise WorkflowError("Establish the actual living mind's current physical source")
        result[actor.token] = view.position_sha256
    return result


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    actor = current_ref(state, viewer.user_id)
    require_rule(game, c, state, actor, rules.PROCESSOR)
    if prepared.play != rules.PLAY or prepared.source_work is None or prepared.parent is not None:
        raise WorkflowError("Use the actual owned processor range/exemption proposal")
    value = prove_proposal(game, c, state, prepared.source_work)
    cast = _cast(game, c, state, channel)
    support.cast_actor(game, c, state, cast, actor)
    if (
        value.actor != actor
        or value.action
        or value.frame != rules.frame(state, actor)
        or fingerprint(cast) != fingerprint(value.cast)
    ):
        raise WorkflowError("Use this actual original unbound processor source scene")
    minds = support.processor_minds(game, c, state, actor, value.exempt_cadre, value.exempt)
    if (
        not minds
        or minds != value.minds
        or _positions(game, c, state, (actor, *minds)) != value.positions
    ):
        raise WorkflowError("Refresh the actual living processors' range/body source before acting")
    approval = game.store.policy.m3_approval
    assert approval is not None
    table = sorted(
        {
            viewer.user_id,
            value.handler_controller,
            *(resolve(state, x, profiles(c, game.store.campaign_id)).controller for x in minds),
        }
    )
    return dict(
        id=value.id,
        proposal=value.id,
        actor=actor.model_dump(mode="json"),
        frame=value.frame,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=table,
        handler=value.handler.model_dump(mode="json"),
        handler_controller=value.handler_controller,
        minds=[x.model_dump(mode="json") for x in minds],
        positions=value.positions,
        registry=approval.registry_sha256,
        phase="prepared",
    )


def bind(state: GameState, action: dict[str, Any], event: str) -> None:
    meta = action["data"]["ankou"]
    value = rules.get(state, rules.Proposal, meta["proposal"])
    if value.action is not None:
        raise WorkflowError("This actual processor source already has an Action")
    rules.put(state, value.model_copy(update={"action": action["id"], "bound_event": event}))


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    authorize(game, c, viewer, action)
    meta = action["data"]["ankou"]
    value = prove_proposal(game, c, state, meta["proposal"])
    if value.action != action["id"] or value.actor != support.actual_action_actor(action):
        raise WorkflowError("Use the actual original processor Actor and bound Action")
    cast = _cast(game, c, state, int(action["channel_id"]))
    if (
        fingerprint(cast) != meta["cast_sha256"]
        or support.processor_minds(game, c, state, value.actor, value.exempt_cadre, value.exempt)
        != value.minds
        or _positions(game, c, state, (value.actor, *value.minds)) != value.positions
    ):
        raise WorkflowError("Refresh the changed actual processor scene/body/range before dice")
    require_rule(game, c, state, value.actor, rules.PROCESSOR)


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if any(x.id == action["id"] for x in rules.records(state, rules.Processor)):
        return
    meta = action["data"]["ankou"]
    rolled, total = _roll_source(game, c, action)
    value = rules.Processor(
        id=action["id"],
        actor=ActorRef.model_validate(meta["actor"]),
        frame=meta["frame"],
        cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
        handler=ActorRef.model_validate(meta["handler"]),
        handler_controller=meta["handler_controller"],
        registry=meta["registry"],
        minds=tuple(ActorRef.model_validate(x) for x in meta["minds"]),
        positions=meta["positions"],
        roll_event=rolled,
        total=total,
        event=action["data"]["response_event"],
    )
    rules.put(state, value)
    meta["phase"] = "choices"
    game.request(c, action, int(value.actor.entity), KINDS[0], dict(source=value.id))


def _finish(state: GameState, action: dict[str, Any], value: rules.Processor, event: str) -> None:
    rules.put(state, value.model_copy(update={"completed_event": event}))
    action["data"]["ankou"]["phase"] = "complete"
    action["data"].setdefault("result", {}).update(source=value.id, phase="complete")


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    if row["kind"] not in KINDS:
        return False
    if row["kind"] in ("ankou_interrupt", "ankou_interrupt_child"):
        return _interrupt_choice(game, c, state, action, row, answer)
    value = prove_source(game, c, state, action["id"])
    event = action["data"]["response_event"]
    if (
        row["actor_id"] != value.actor.entity
        or answer.denied
        or answer.member is not None
        or answer.flag is not None
        or answer.number is not None
    ):
        raise WorkflowError("The actual original Ankou owner selects these printed results")
    if row["kind"] == KINDS[0]:
        count = 3 if value.total >= 11 else 2 if value.total >= 8 else 1
        if (
            value.selected_event
            or len(answer.options) != count
            or any(x not in rules.PROCESSOR_BENEFITS for x in answer.options)
        ):
            raise WorkflowError("Choose exactly the actual tier's number of printed benefits")
        if any(answer.options.count(x) > 1 for x in ("champion", "eyes", "will")):
            raise WorkflowError("Only the printed Identity benefit can be selected repeatedly")
        assets, tags = [], []
        allowed_fields: set[str] = set()
        for index, choice in enumerate(answer.options):
            if choice == "identity":
                fields = {"erase" + str(index), "unmark" + str(index), "gain" + str(index)}
                allowed_fields.update(fields)
                erased, unmark = (
                    answer.fields.get("erase" + str(index), ""),
                    answer.fields.get("unmark" + str(index), ""),
                )
                gain = int(answer.fields.get("gain" + str(index), "0"))
                if erased == unmark or gain not in (1, 2, 3):
                    raise WorkflowError(
                        "Erase one actual Identity, unmark a different marked one and gain1–3Heat"
                    )
                support.erase_identity(state, value.actor, erased)
                entry = next(
                    (
                        x
                        for x in state.sheets[value.actor.entity].identities
                        if x.id == unmark and x.marked
                    ),
                    None,
                )
                if entry is None or entry.id in state.sheets[value.actor.entity].sedation_locked:
                    raise WorkflowError("Unmark a different actually marked eligible Identity")
                entry.marked = False
                support.gain_heat(state, value.actor, gain, event, "Ankou Processor Core")
            elif choice == "champion":
                tags.append(
                    support.add_tag(
                        game,
                        c,
                        state,
                        value.id,
                        value.actor,
                        value.actor,
                        "People’s Champion",
                        value.cast.id,
                        event,
                        "champion",
                    )
                )
            else:
                key = "replace" + str(index)
                allowed_fields.add(key)
                assets.append(
                    support.temporary_asset(
                        state, value.actor, value.id, choice, event, answer.fields.get(key)
                    )
                )
        if set(answer.fields) - allowed_fields:
            raise WorkflowError("Use only these actual selected source benefit controls")
        value = value.model_copy(
            update={
                "benefits": answer.options,
                "assets": tuple(assets),
                "tags": tuple(tags),
                "selected_event": event,
            }
        )
        rules.put(state, value)
        if value.total < 8 or value.total >= 11:
            game.request(c, action, int(value.actor.entity), KINDS[1], dict(source=value.id))
        else:
            _finish(state, action, value, event)
    else:
        count = 2 if value.total >= 11 else 1
        if (
            not value.selected_event
            or value.symptoms
            or answer.fields
            or len(answer.options) != count
            or len(set(answer.options)) != count
            or any(x not in rules.SYMPTOMS for x in answer.options)
        ):
            raise WorkflowError("Choose the actual tier's distinct printed processor symptoms")
        tags = list(value.tags)
        for mind in value.minds:
            for symptom in answer.options:
                tags.append(
                    support.add_tag(
                        game,
                        c,
                        state,
                        value.id,
                        value.actor,
                        mind,
                        symptom,
                        value.cast.id,
                        event,
                        "symptom",
                    )
                )
        value = value.model_copy(
            update={"symptoms": answer.options, "symptoms_event": event, "tags": tuple(tags)}
        )
        _finish(state, action, value, event)
    return True


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    if row["kind"] in ("ankou_interrupt", "ankou_interrupt_child"):
        task = prove_task(game, c, state, json.loads(row["body_json"])["task"])
        from girlframe.engine.m3_mockingbird import actor_tags

        return dict(
            source=task.id,
            target=task.target.model_dump(mode="json") if task.target else None,
            tags=[dict(id=x.id, label=x.label) for x in actor_tags(state, task.target)]
            if task.target
            else [],
            child=task.child,
            plays=(
                "keep_your_head",
                "check_sensors",
                "flirt",
                "all_out_assault",
                "engage",
                "put_someone_beneath_you",
            ),
        )
    value = prove_source(game, c, state, action["id"])
    sheet = state.sheets[value.actor.entity]
    return dict(
        source=value.id,
        total=value.total,
        count=3 if value.total >= 11 else 2 if value.total >= 8 else 1,
        symptom_count=2 if value.total >= 11 else 1,
        benefits=rules.PROCESSOR_BENEFITS,
        symptoms=rules.SYMPTOMS,
        identities=[
            dict(id=x.id, label=x.name, marked=x.marked)
            for x in sheet.identities
            if not (x.protected or x.paired or x.am_limiter)
        ],
        assets=[
            dict(id=x.id, label=x.name) for x in sheet.assets if x.family == "frame" and not x.void
        ],
    )


def synchronize(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    return None


def intercept_finish(game: GameService, c: Connection, action: dict[str, Any]) -> bool:
    return bool(action["data"].get("ankou") and action["data"]["ankou"]["phase"] != "complete")


class AnkouService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        kind: str,
        request: dict[str, Any],
        operation: Callable[[Connection, GameState, str], dict[str, Any]],
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            authorize(self.game, c, viewer)
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_ANKOU: reopen the original current source")
            event = str(uuid4())
            result = operation(c, state, event)
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, **result)
            synchronize_events(self.game, c, event)
            return result | dict(revision=load_state(c, self.store.campaign_id).revision)

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                dict(revision=revision, **request),
                run,
                auto_audit=False,
                authorize=lambda c: authorize(self.game, c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def buy(
        self, viewer: GuildViewer, key: str, revision: int, rule: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_requisitions import RequisitionService

            actor = current_ref(state, viewer.user_id)
            original = rules.frame(state, actor)
            Access(self.store).authorize(c, viewer, "economy")
            registry = Access(self.store).registry
            assert registry is not None
            registry.require_available(rule)
            if rule not in rules.REQUISITIONS or rules.held(state, actor, rule):
                raise WorkflowError("Choose one actual new Ankou Requisition")
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if available(state, actor) < 2:
                raise WorkflowError("This actual native Requisition costs2Permissions")
            identity = str(uuid4())
            payment = prepare_payment(self.game, c, state, viewer, actor, rule, 2, rules.FRAME)
            debit(state, actor, 2, event=event, source=identity, payment=payment)
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind="ability_unlock",
                    actor=actor,
                    frame_instance=original,
                    frame=rules.FRAME,
                    donor_frame=rules.FRAME,
                    rule_id=rule,
                    grant="ankou:" + identity,
                    price=2,
                    account=support.text(account),
                    source_event=event,
                )
            )
            state.sheets[actor.entity].revision += 1
            return dict(id=identity, requisition_id=identity, rule_id=rule, cost=2)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ability_unlock_purchased",
            dict(rule=rule, account=account),
            operation,
        )

    def propose_processor(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        account: str,
        *,
        exempt_cadre: bool = False,
        exempt: ActorRef | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.PROCESSOR)
            cast = _cast(self.game, c, state, channel)
            support.cast_actor(self.game, c, state, cast, actor)
            minds = support.processor_minds(self.game, c, state, actor, exempt_cadre, exempt)
            if not minds:
                raise WorkflowError(
                    "At least one actual living nonimmune mind must be in relay range"
                )
            if any(
                x.actor == actor and not x.unlinked_event
                for x in rules.records(state, rules.Processor)
            ):
                raise WorkflowError("End the actual current processor link before making another")
            handler = active_handler(state)
            if handler is None:
                raise WorkflowError("Recover the actual original Handler appointment")
            value = rules.Proposal(
                id=event,
                actor=actor,
                frame=rules.frame(state, actor),
                cast=cast,
                handler=handler,
                handler_controller=resolve(
                    state, handler, profiles(c, self.store.campaign_id)
                ).controller,
                minds=minds,
                positions=_positions(self.game, c, state, (actor, *minds)),
                exempt_cadre=exempt_cadre,
                exempt=exempt,
                account=support.text(account),
                event=event,
            )
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_processor_proposed",
            dict(
                channel=channel,
                account=account,
                exempt_cadre=exempt_cadre,
                exempt=exempt.model_dump(mode="json") if exempt else None,
            ),
            operation,
        )

    def unlink(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_source(self.game, c, state, identity)
            if int(value.actor.entity) != viewer.user_id or not value.completed_event:
                raise WorkflowError(
                    "Only the original owner ends their genuine completed processor link"
                )
            support.text(account)
            support.unlink(self.game, c, state, value, event)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_unlinked",
            dict(id=identity, account=account),
            operation,
        )

    def activate_relay(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        benefits: tuple[str, ...],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.RELAY)
            cast = _cast(self.game, c, state, channel)
            support.cast_actor(self.game, c, state, cast, actor)
            support.text(account)
            if (
                len(benefits) != 2
                or len(set(benefits)) != 2
                or any(x not in rules.BENEFITS for x in benefits)
                or rules.active_relays(state, actor)
            ):
                raise WorkflowError("Choose2distinct actual relay benefits for this scene")
            handler = active_handler(state)
            if handler is None:
                raise WorkflowError("Recover the actual original Handler appointment")
            value = rules.Relay(
                id=event,
                actor=actor,
                frame=rules.frame(state, actor),
                cast=cast,
                handler=handler,
                handler_controller=resolve(
                    state, handler, profiles(c, self.store.campaign_id)
                ).controller,
                benefits=benefits,
                event=event,
            )
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_relay_activated",
            dict(channel=channel, benefits=benefits, account=account),
            operation,
        )

    def choose_consequence(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        choice: Literal["death", "nominees", "feedback"],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_relay(self.game, c, state, identity)
            if viewer.user_id != value.handler_controller or value.consequence or value.ended_event:
                raise WorkflowError("The actual original Handler chooses1relay consequence")
            support.text(account)
            rules.put(
                state, value.model_copy(update={"consequence": choice, "consequence_event": event})
            )
            if choice == "feedback":
                from girlframe.services.m3_ankou_feedback_sequences import start

                start(
                    self.game,
                    c,
                    state,
                    value.actor,
                    value.cast,
                    value.id,
                    event,
                    count=1,
                    reason="relay",
                )
            elif choice == "nominees":
                from girlframe.engine.m3_actor_bonds import depth

                candidates = [
                    current_ref(state, x.owner) for x in state.sheets.values() if x.character_id
                ]
                if state.world:
                    candidates.extend(
                        ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.alive
                    )
                people = tuple(
                    x for x in candidates if x != value.actor and depth(state, value.actor, x) == 2
                )
                for person in people:
                    _task(
                        self.game,
                        c,
                        state,
                        value.id,
                        person,
                        "nominate",
                        value.cast,
                        event,
                        target=value.actor,
                    )
                if not people:
                    rules.put(
                        state,
                        value.model_copy(
                            update={
                                "consequence": choice,
                                "consequence_event": event,
                                "completed_event": event,
                            }
                        ),
                    )
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_relay_consequence",
            dict(id=identity, choice=choice, account=account),
            operation,
        )

    def choose_obsession(
        self, viewer: GuildViewer, key: str, revision: int, target: ActorRef, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.OBSESSIVE)
            actual = resolve(state, target, profiles(c, self.store.campaign_id))
            if actor == target or not actual.alive:
                raise WorkflowError("Choose one actual other living original person")
            existing = [
                x
                for x in rules.records(state, rules.Obsession)
                if x.actor == actor and not x.replacement_event
            ]
            for old in existing:
                if (
                    not old.sequence
                    or not rules.get(state, rules.FeedbackSequence, old.sequence).completed_event
                ):
                    raise WorkflowError(
                        "Complete all5 actual Feedback results before replacing this Obsession"
                    )
                rules.put(state, old.model_copy(update={"replacement_event": event}))
            value = rules.Obsession(
                id=event, actor=actor, target=target, frame=rules.frame(state, actor), event=event
            )
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_obsession_chosen",
            dict(target=target.model_dump(mode="json"), account=account),
            operation,
        )

    def encounter(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        actor: ActorRef,
        target: ActorRef,
        kind: Literal["touch", "spy", "seen"],
        account: str,
        *,
        period: str | None = None,
        thinks_private: bool = False,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            bound = profiles(c, self.store.campaign_id)
            own, other = resolve(state, actor, bound), resolve(state, target, bound)
            cast = _cast(self.game, c, state, channel)
            support.cast_actor(self.game, c, state, cast, actor)
            if (
                not own.alive
                or not other.alive
                or actor == target
                or viewer.user_id not in (own.controller, other.controller)
                or own.cell is None
                or own.cell != other.cell
                or not own.position_sha256
                or not other.position_sha256
            ):
                raise WorkflowError(
                    "Record a real current co-present interaction between the original people"
                )
            if kind == "spy" and (viewer.user_id != other.controller or not thinks_private):
                raise WorkflowError(
                    "The actual target authors their genuine private-expectation context"
                )
            if kind == "seen" and viewer.user_id != own.controller:
                raise WorkflowError("The actual observer records their own genuine sighting")
            if period:
                _period(self.game, c, state, period, actor)
            value = rules.Encounter(
                id=event,
                actor=actor,
                target=target,
                kind=kind,
                cast=cast,
                actor_position=own.position_sha256,
                target_position=other.position_sha256,
                author=viewer.user_id,
                account=support.text(account),
                event=event,
                period=period,
                thinks_private=thinks_private,
            )
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_encounter",
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                target=target.model_dump(mode="json"),
                kind=kind,
                account=account,
                period=period,
                thinks_private=thinks_private,
            ),
            operation,
        )

    def choose_task(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        choice: str,
        account: str,
        *,
        identity_to_erase: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            task = prove_task(self.game, c, state, identity)
            if task.controller != viewer.user_id or task.completed_event:
                raise WorkflowError(
                    "Only this actual original source chooser answers the outstanding work"
                )
            support.text(account)
            if task.kind == "fight_fawn":
                if choice not in ("fight", "fawn") or task.target is None:
                    raise WorkflowError("Choose Fight or Fawn against the actual original damager")
                token = rules.FightFawn(
                    id=task.id,
                    actor=task.actor,
                    target=task.target,
                    task=task.id,
                    play="all_out_assault" if choice == "fight" else "flirt",
                    event=event,
                )
                rules.put(state, token)
            elif task.kind == "emotion":
                relay = prove_relay(self.game, c, state, task.source)
                if relay.ended_event or task.target != relay.actor:
                    raise WorkflowError("This actual scene's emotional relay is no longer active")
                support.add_tag(
                    self.game,
                    c,
                    state,
                    relay.id,
                    relay.actor,
                    task.actor,
                    account,
                    relay.cast.id,
                    event,
                    "emotion",
                )
            elif task.kind == "nominate":
                if choice not in (
                    "pass",
                    "keep_your_head",
                    "check_sensors",
                    "flirt",
                    "all_out_assault",
                    "engage",
                    "put_someone_beneath_you",
                ):
                    raise WorkflowError(
                        "Choose a genuine supported Play, not an unperformed mechanical effect"
                    )
            elif task.kind == "death_identity":
                if not identity_to_erase:
                    raise WorkflowError(
                        "Erase one actual eligible Identity from the source NPC death"
                    )
                support.erase_identity(state, task.actor, identity_to_erase)
                support.gain_heat(state, task.actor, 4, event, "Ankou hears actual NPC death")
            elif task.kind == "disclosure":
                if task.target is None:
                    raise WorkflowError("Retain the original actual disclosure recipient")
                from girlframe.engine.m3_mockingbird import actor_tags

                actual = resolve(state, task.actor, profiles(c, self.store.campaign_id))
                label = next((x.name for x in actual.identities if x.id == choice), None)
                if label is None:
                    label = next(
                        (x.label for x in actor_tags(state, task.actor) if x.id == choice), None
                    )
                if label is None:
                    raise WorkflowError("Select one actual original source resource to disclose")
                body = dict(
                    person=task.actor.model_dump(mode="json"),
                    recipient=resolve(
                        state, task.target, profiles(c, self.store.campaign_id)
                    ).controller,
                    recipient_actor=task.target.model_dump(mode="json"),
                    resource=choice,
                    label=label,
                    account=account,
                    event=event,
                    request=task.id,
                    resource_kind="identity"
                    if any(x.id == choice for x in actual.identities)
                    else "tag",
                )
                state.facts.append(
                    dict(kind="ankou_disclosure", id=event, body=json.dumps(body, sort_keys=True))
                )
            elif task.kind == "company":
                if choice != "none" and any(x not in task.options for x in choice.split("\n")):
                    raise WorkflowError(
                        "Choose actual source companions from this original factual request"
                    )
                companions = (
                    ()
                    if choice == "none"
                    else tuple(ActorRef.model_validate_json(x) for x in choice.split("\n"))
                )
                if any(x.model_dump_json() not in task.options for x in companions) or len(
                    set(companions)
                ) != len(companions):
                    raise WorkflowError("Record the actual distinct original companions")
                positions = _positions(self.game, c, state, (task.actor, *companions))
                origin = resolve(state, task.actor, profiles(c, self.store.campaign_id))
                if any(
                    resolve(state, x, profiles(c, self.store.campaign_id)).cell != origin.cell
                    for x in companions
                ):
                    raise WorkflowError("The actual known physical companions must be co-present")
                rules.put(
                    state,
                    rules.Company(
                        id=event,
                        actor=task.actor,
                        companions=companions,
                        positions=positions,
                        author=viewer.user_id,
                        account=account,
                        event=event,
                        request=task.id,
                    ),
                )
            elif task.kind == "spy_context":
                if choice not in ("yes", "no") or task.target is None:
                    raise WorkflowError("Truthfully author your own expectation of privacy")
                if choice == "yes":
                    actor, other = task.target, task.actor
                    positions = _positions(self.game, c, state, (actor, other))
                    born = _history(c, self.game, task.event)
                    if positions != _positions(self.game, c, born, (actor, other)):
                        raise WorkflowError("Refresh the genuinely changed actual spying context")
                    rules.put(
                        state,
                        rules.Encounter(
                            id=event,
                            actor=actor,
                            target=other,
                            kind="spy",
                            cast=task.cast,
                            actor_position=positions[actor.token],
                            target_position=positions[other.token],
                            author=viewer.user_id,
                            account=account,
                            event=event,
                            thinks_private=True,
                            request=task.id,
                        ),
                    )
            elif task.kind == "missed_obsession":
                if choice not in ("seen", "not_seen"):
                    raise WorkflowError(
                        "Truthfully record the completed period's actual encounter fact"
                    )
                old = rules.get(state, rules.Obsession, task.source)
                if choice == "not_seen":
                    from girlframe.services.m3_ankou_feedback_sequences import start

                    sequence = start(
                        self.game,
                        c,
                        state,
                        old.actor,
                        task.cast,
                        old.id,
                        event,
                        count=5,
                        reason="obsession",
                    )
                    rules.put(
                        state,
                        old.model_copy(update={"sequence": sequence.id, "ended_event": event}),
                    )
                elif not any(
                    x.actor == old.actor
                    and x.target == old.target
                    and x.period == task.options[0]
                    and x.kind == "seen"
                    for x in rules.records(state, rules.Encounter)
                ):
                    raise WorkflowError(
                        "Record the genuine actual sighting source before claiming you saw them"
                    )
            else:
                raise WorkflowError(
                    "Perform the actual required Play; this is not an acknowledgment"
                )
            rules.put(
                state,
                task.model_copy(
                    update={
                        "choice": choice,
                        "account": account,
                        "selected_event": event,
                        "completed_event": event,
                    }
                ),
            )
            if task.kind == "nominate":
                peers = [
                    x
                    for x in rules.records(state, rules.Task)
                    if x.source == task.source and x.kind == "nominate"
                ]
                if all(x.completed_event for x in peers):
                    relay = rules.get(state, rules.Relay, task.source)
                    offered = tuple(
                        dict.fromkeys(x.choice for x in peers if x.choice and x.choice != "pass")
                    )
                    if offered:
                        _task(
                            self.game,
                            c,
                            state,
                            relay.id,
                            relay.actor,
                            "perform",
                            relay.cast,
                            event,
                            options=tuple(
                                dict.fromkeys(
                                    x.choice for x in peers if x.choice and x.choice != "pass"
                                )
                            ),
                        )
                    else:
                        rules.put(state, relay.model_copy(update={"completed_event": event}))
            return dict(id=task.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_task_answered",
            dict(id=identity, choice=choice, account=account, identity_to_erase=identity_to_erase),
            operation,
        )

    def speak(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        relay_id: str,
        target: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_relay(self.game, c, state, relay_id)
            own = resolve(state, value.actor, profiles(c, self.store.campaign_id))
            other = resolve(state, target, profiles(c, self.store.campaign_id))
            if (
                viewer.user_id != own.controller
                or value.ended_event
                or "speech" not in value.benefits
                or target not in support.range_people(self.game, c, state, value.actor)
            ):
                raise WorkflowError(
                    "Use your actual active head-speech source and actual recipient in range"
                )
            delivery = rules.Delivery(
                id=event,
                source=value.id,
                author=value.actor,
                target=target,
                author_controller=own.controller,
                target_controller=other.controller,
                account=support.text(account),
                event=event,
            )
            rules.put(state, delivery)
            return dict(id=delivery.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_head_speech",
            dict(relay=relay_id, target=target.model_dump(mode="json"), account=account),
            operation,
        )

    def touch(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        relay_id: str,
        encounter: str,
        asset: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            relay = prove_relay(self.game, c, state, relay_id)
            contact = prove_encounter(self.game, c, state, encounter)
            if (
                int(relay.actor.entity) != viewer.user_id
                or relay.ended_event
                or "touch" not in relay.benefits
                or contact.actor != relay.actor
                or contact.kind != "touch"
                or contact.cast.id != relay.cast.id
            ):
                raise WorkflowError("Use the actual active Relay and real current authored touch")
            support.text(account)
            value = rules.Touch(
                id=event,
                relay=relay.id,
                encounter=contact.id,
                actor=relay.actor,
                target=contact.target,
                asset=asset,
                frame=relay.frame
                if any(
                    x.id == asset and x.family == "frame"
                    for x in state.sheets[relay.actor.entity].assets
                )
                else None,
                event=event,
            )
            rules.put(state, value)
            from girlframe.services.m3_battle import damage_actor

            own = resolve(state, relay.actor, profiles(c, self.store.campaign_id))
            if value.frame and not own.inside_frame:
                from girlframe.services.m3_battle import damage_frame_at_scene

                changed, work = damage_frame_at_scene(
                    self.game,
                    c,
                    state,
                    target=relay.actor,
                    asset_id=asset,
                    source_action=None,
                    source_work=value.id,
                    event=event,
                    actor=relay.actor,
                    frame_instance=value.frame,
                    chooser_controller=viewer.user_id,
                    occurrence="ankou-touch:" + value.id,
                    allow_sprite=False,
                )
            else:
                changed, work = damage_actor(
                    self.game,
                    c,
                    state,
                    target=relay.actor,
                    asset_id=asset,
                    source_action=None,
                    source_work=value.id,
                    event=event,
                    actor=relay.actor,
                    opponent=contact.target,
                    chooser_controller=viewer.user_id,
                    physical_blow=False,
                )
            support.copy(state, changed)
            support.copy(state, make_helpless(state, contact.target, relay.actor, event))
            rules.put(state, value.model_copy(update={"work": work, "completed_event": event}))
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_touched",
            dict(relay=relay_id, encounter=encounter, asset=asset, account=account),
            operation,
        )

    def give_source_tag(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        source: str,
        kind: Literal["obsession", "spy"],
        label: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            bound = profiles(c, self.store.campaign_id)
            if kind == "obsession":
                value = rules.get(state, rules.Obsession, source)
                if (
                    prove_obsession(self.game, c, state, value.actor, value.target) is None
                    or resolve(state, value.target, bound).controller != viewer.user_id
                ):
                    raise WorkflowError(
                        "Only the actual original Obsession gives their one scene Tag"
                    )
                current_scene = _cast(
                    self.game, c, state, _owner_channel(self.game, c, state, value.actor)
                )
                if any(
                    x.source == source and x.kind == kind and x.scene == current_scene.id
                    for x in rules.records(state, rules.TagUse)
                ):
                    raise WorkflowError("This actual Obsession already gave its once-per-scene Tag")
                giver, target = value.target, value.actor
            else:
                encounter = prove_encounter(self.game, c, state, source)
                giver, target = encounter.actor, encounter.target
                require_rule(self.game, c, state, giver, rules.STALKER)
                if (
                    encounter.kind != "spy"
                    or not encounter.thinks_private
                    or resolve(state, giver, bound).controller != viewer.user_id
                ):
                    raise WorkflowError(
                        "Use the genuine source-target private-expectation spying fact"
                    )
                current_scene = encounter.cast
                if any(
                    x.source == source and x.kind == kind
                    for x in rules.records(state, rules.TagUse)
                ):
                    raise WorkflowError("This actual spying occurrence already gave its Tag")
            tag = support.add_tag(
                self.game, c, state, source, giver, target, label, current_scene.id, event, kind
            )
            return dict(id=tag)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_source_tag",
            dict(source=source, kind=kind, label=label),
            operation,
        )

    def quickchange(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        period: str,
        *,
        erase: str | None = None,
        source_person: ActorRef | None = None,
        source_identity: str | None = None,
        source_tag: str | None = None,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            require_rule(self.game, c, state, actor, rules.QUICKCHANGE)
            _period(self.game, c, state, period, actor)
            if any(
                x.actor == actor and x.period == period
                for x in rules.records(state, rules.Quickchange)
            ):
                raise WorkflowError("This actual GoOffDuty already used Quickchange")
            if not erase and source_person is None:
                raise WorkflowError("Actually erase and/or write a source-derived Identity")
            support.text(account)
            label = None
            if source_person is not None:
                if source_person == actor or bool(source_identity) == bool(source_tag):
                    raise WorkflowError(
                        "Choose one actual other character's original Identity or Tag"
                    )
                disclosed = disclosed_sources(self.game, c, state, viewer, source_person)
                label = next(
                    (x["label"] for x in disclosed if x["id"] == (source_identity or source_tag)),
                    None,
                )
                if label is None:
                    raise WorkflowError(
                        "Obtain genuine source-person disclosure; do not import a private sheet"
                    )
            if erase:
                support.erase_identity(state, actor, erase)
            written = rules.identity("quickchange", event) if label else None
            if label and written:
                support.write_identity(state, actor, written, label)
            value = rules.Quickchange(
                id=event,
                actor=actor,
                period=period,
                source_person=source_person,
                source_identity=source_identity,
                source_tag=source_tag,
                erased=erase,
                written=written,
                label=label,
                event=event,
            )
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            revision,
            "m3.ankou_quickchange",
            dict(
                period=period,
                erase=erase,
                source_person=source_person.model_dump(mode="json") if source_person else None,
                source_identity=source_identity,
                source_tag=source_tag,
                account=account,
            ),
            operation,
        )

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            actor = (
                current_ref(state, viewer.user_id) if str(viewer.user_id) in state.sheets else None
            )
            actual = None
            if actor:
                try:
                    actual = rules.frame(state, actor)
                except ValueError:
                    pass
            people = []
            if actual and actor:
                people = [
                    dict(
                        id=x.token,
                        ref=x.model_dump(mode="json"),
                        label=resolve(state, x, profiles(c, self.store.campaign_id)).label,
                    )
                    for x in support.range_people(self.game, c, state, actor)
                ]
            known_people = people
            if actor and actual:
                from girlframe.services.m3_actors import ActorService
                from girlframe.services.m3_missions import MissionService

                known = ActorService(MissionService(self.store)).known(viewer, actor)
                known_people = [
                    dict(id=ActorRef.model_validate(x["ref"]).token, ref=x["ref"], label=x["label"])
                    for x in known["actors"]
                    if ActorRef.model_validate(x["ref"]) != actor
                ]
            known_refs = {ActorRef.model_validate(x["ref"]) for x in known_people}
            people = [x for x in people if ActorRef.model_validate(x["ref"]) in known_refs]
            disclosed = []
            if actor and actual:
                for person in known_people:
                    ref = ActorRef.model_validate(person["ref"])
                    for resource in disclosed_sources(self.game, c, state, viewer, ref):
                        disclosed.append(
                            dict(
                                id=resource["id"],
                                label=str(person["label"]) + " — " + resource["label"],
                                person=person["ref"],
                                kind=resource.get("kind", "identity"),
                            )
                        )
            periods = []
            if actor:
                table = t.m3["m3_off_duty"]
                for raw in c.scalars(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id, table.c.phase == "active"
                    )
                ):
                    body = json.loads(raw)
                    if body.get("character_ids", {}).get(actor.entity) == actor.incarnation:
                        periods.append(dict(id=body["id"], label="Current actual Off-Duty"))
            return dict(
                known_people=known_people,
                disclosed=disclosed,
                periods=periods,
                revision=state.revision,
                actor=actor.model_dump(mode="json") if actor else None,
                frame=actual,
                people=people,
                tasks=self._tasks(c, viewer),
                heat=state.sheets[actor.entity].heat if actor else None,
                sheet_revision=state.sheets[actor.entity].revision if actor else None,
                identities=[
                    dict(id=x.id, label=x.name, marked=x.marked)
                    for x in state.sheets[actor.entity].identities
                ]
                if actor
                else [],
                held=[
                    r
                    for r in rules.REQUISITIONS
                    if actor and actual and rules.held(state, actor, r)
                ],
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            authorize(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            for cls in (
                rules.Relay,
                rules.Processor,
                rules.Task,
                rules.FeedbackSequence,
                rules.FeedbackStep,
                rules.Delivery,
                rules.Obsession,
                rules.Proposal,
                rules.Encounter,
                rules.Company,
                rules.Touch,
                rules.FightFawn,
                rules.Quickchange,
                rules.TagUse,
            ):
                value = next(
                    (x for x in rules.records(state, cls) if x.model_dump()["id"] == identity), None
                )
                if value is None:
                    continue
                if viewer.user_id not in _viewers(self.game, c, state, value):
                    raise WorkflowError("This actual original source record is private")
                source = value.model_dump(mode="json")
                if isinstance(value, rules.Delivery):
                    return dict(
                        id=value.model_dump()["id"],
                        revision=state.revision,
                        kind="delivery",
                        source=source,
                        summary=value.account,
                        can_save_notice=viewer.user_id == value.target_controller
                        and not value.saved_event,
                    )
                kind = next(
                    label for cls, label in rules.KINDS.items() if isinstance(value, cls)
                ).removeprefix("ankou_")
                data = dict(
                    id=identity,
                    revision=state.revision,
                    kind=kind,
                    source=source,
                    summary=kind.replace("_", " "),
                )
                if isinstance(value, rules.Processor):
                    from girlframe.services.m3_actors import ActorService
                    from girlframe.services.m3_missions import MissionService

                    prove_source(self.game, c, state, value.id)
                    source.pop("positions", None)
                    source["mind_count"] = len(value.minds)
                    known = ActorService(MissionService(self.store)).known(viewer, value.actor)
                    visible = {ActorRef.model_validate(x["ref"]) for x in known["actors"]}
                    source["minds"] = [
                        x.model_dump(mode="json") for x in value.minds if x in visible
                    ]
                    data.update(
                        can_unlink=viewer.user_id == int(value.actor.entity)
                        and bool(value.completed_event)
                        and not value.unlinked_event
                    )
                if isinstance(value, rules.Relay):
                    prove_relay(self.game, c, state, value.id)
                    data.update(
                        can_choose=viewer.user_id == value.handler_controller
                        and value.consequence is None
                    )
                if isinstance(value, rules.Task):
                    if viewer.user_id != value.controller and value.kind in (
                        "company",
                        "disclosure",
                    ):
                        source["options"] = []
                    prove_task(self.game, c, state, value.id)
                    data.update(
                        can_choose=viewer.user_id == value.controller and not value.completed_event
                    )
                    if viewer.user_id == value.controller:
                        if value.kind == "company":
                            data["company_options"] = [
                                dict(
                                    id=ActorRef.model_validate_json(x).token,
                                    value=x,
                                    label=resolve(
                                        state,
                                        ActorRef.model_validate_json(x),
                                        profiles(c, self.store.campaign_id),
                                    ).label,
                                )
                                for x in value.options
                            ]
                        actual = resolve(state, value.actor, profiles(c, self.store.campaign_id))
                        from girlframe.engine.m3_mockingbird import actor_tags

                        data.update(
                            resources=[dict(id=x.id, label=x.name) for x in actual.identities]
                            + [dict(id=x.id, label=x.label) for x in actor_tags(state, value.actor)]
                        )
                    if value.kind in ("perform", "interrupt") and not value.completed_event:
                        data.update(
                            counter=dict(
                                kind="ankou_effect_child",
                                parent=value.source_action if value.kind == "interrupt" else None,
                                channel=value.cast.channel,
                                body=dict(
                                    source_work=value.id,
                                    target=value.target.model_dump(mode="json")
                                    if value.target
                                    else None,
                                    allowed=value.options,
                                ),
                                play=value.options[0] if len(value.options) == 1 else None,
                            )
                            if value.child is None and value.options
                            else None,
                            can_resume=bool(value.child),
                        )
                if isinstance(value, rules.Relay):
                    own = viewer.user_id == int(value.actor.entity) and not value.ended_event
                    data.update(
                        can_speak=own and "speech" in value.benefits,
                        can_touch=own and "touch" in value.benefits,
                        can_sense=own and "sense" in value.benefits,
                        people=[
                            dict(
                                id=x.token,
                                ref=x.model_dump(mode="json"),
                                label=resolve(state, x, profiles(c, self.store.campaign_id)).label,
                            )
                            for x in support.range_people(self.game, c, state, value.actor)
                        ]
                        if own
                        else [],
                        encounters=[
                            dict(id=x.id, label=x.account)
                            for x in rules.records(state, rules.Encounter)
                            if x.actor == value.actor
                            and x.kind == "touch"
                            and x.cast.id == value.cast.id
                        ]
                        if own
                        else [],
                        assets=[
                            dict(id=x.id, label=x.name)
                            for x in state.sheets[value.actor.entity].assets
                            if not x.damaged
                        ]
                        if own
                        else [],
                    )
                if isinstance(value, rules.Obsession):
                    data.update(
                        can_tag=not value.ended_event
                        and resolve(
                            state, value.target, profiles(c, self.store.campaign_id)
                        ).controller
                        == viewer.user_id
                    )
                if isinstance(value, rules.Encounter):
                    data.update(
                        can_tag=value.kind == "spy"
                        and value.thinks_private
                        and resolve(
                            state, value.actor, profiles(c, self.store.campaign_id)
                        ).controller
                        == viewer.user_id
                    )
                if isinstance(value, rules.TagUse):
                    data.update(
                        can_npc_off_duty=value.kind == "symptom"
                        and not value.ended_event
                        and value.target.kind == "npc"
                    )
                if isinstance(value, (rules.FeedbackSequence, rules.FeedbackStep)):
                    from girlframe.services.m3_ankou_feedback_sequences import (
                        projection as feedback_projection,
                    )

                    data.update(feedback_projection(self.game, c, state, value, viewer))
                return data
            raise WorkflowError("Recover the actual original private Ankou record")

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        rows = []
        for cls in (
            rules.Relay,
            rules.Task,
            rules.FeedbackSequence,
            rules.FeedbackStep,
            rules.Processor,
            rules.Delivery,
            rules.Obsession,
            rules.Encounter,
            rules.TagUse,
        ):
            for value in rules.records(state, cls):
                if viewer.user_id not in _viewers(self.game, c, state, value):
                    continue
                pending = False
                if isinstance(value, rules.Relay):
                    pending = (
                        value.consequence is None and viewer.user_id == value.handler_controller
                    )
                elif isinstance(value, rules.Task):
                    pending = not value.completed_event and viewer.user_id == value.controller
                elif isinstance(value, rules.FeedbackStep):
                    pending = viewer.user_id == (
                        value.target_controller
                        if value.phase == "purpose"
                        else int(value.actor.entity)
                    ) and value.phase not in ("complete", "ended")
                elif isinstance(value, rules.Delivery):
                    pending = viewer.user_id == value.target_controller and not value.saved_event
                elif isinstance(value, rules.FeedbackSequence):
                    pending = (
                        not value.completed_event
                        and not value.terminal_event
                        and value.venue is None
                        and viewer.user_id == int(value.actor.entity)
                    )
                rows.append(
                    dict(
                        id=value.model_dump()["id"],
                        revision=state.revision,
                        label="Ankou — "
                        + rules.KINDS[cls].removeprefix("ankou_").replace("_", " "),
                        phase="pending"
                        if pending
                        or isinstance(value, rules.Task)
                        and not value.completed_event
                        or isinstance(value, rules.Relay)
                        and not value.consequence
                        or isinstance(value, rules.FeedbackStep)
                        and value.phase not in ("complete", "ended")
                        else "history",
                        pending=pending,
                    )
                )
        return rows


def _viewers(game: GameService, c: Connection, state: GameState, value: Model) -> set[int]:
    if isinstance(value, rules.Obsession):
        return {
            int(value.actor.entity),
            resolve(
                state,
                value.target,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            ).controller,
        }
    if isinstance(value, rules.TagUse):
        return {
            resolve(
                state, ref, profiles(c, game.store.campaign_id), require_current_profile=False
            ).controller
            for ref in (value.actor, value.target)
        }
    if isinstance(value, rules.Encounter):
        return {
            value.author,
            resolve(
                state,
                value.actor,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            ).controller,
        }
    if isinstance(value, rules.Delivery):
        return {value.author_controller, value.target_controller}
    if isinstance(value, rules.Task):
        source = next((x for x in rules.records(state, rules.Relay) if x.id == value.source), None)
        return {
            value.controller,
            *(
                {int(source.actor.entity), source.handler_controller}
                if source
                else {
                    resolve(
                        state,
                        value.target,
                        profiles(c, game.store.campaign_id),
                        require_current_profile=False,
                    ).controller
                }
                if value.target
                else set()
            ),
        }
    if isinstance(value, rules.FeedbackStep):
        return {
            int(value.actor.entity),
            *({value.target_controller} if value.target_controller else set()),
        }
    if isinstance(value, rules.Processor):
        return {int(value.actor.entity), value.handler_controller}
    if isinstance(value, rules.Relay):
        return {int(value.actor.entity), value.handler_controller}
    if isinstance(value, rules.FeedbackSequence):
        return {int(value.actor.entity)}
    actor = getattr(value, "actor", None)
    return (
        {
            resolve(
                state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
            ).controller
        }
        if actor
        else set()
    )


def _task(
    game: GameService,
    c: Connection,
    state: GameState,
    source: str,
    actor: ActorRef,
    kind: Any,
    cast: SceneCast,
    event: str,
    *,
    target: ActorRef | None = None,
    options: tuple[str, ...] = (),
    source_action: str | None = None,
    source_asset: str | None = None,
) -> rules.Task:
    value = rules.Task(
        id=rules.identity("task", source, actor.token, kind, event),
        source=source,
        actor=actor,
        controller=resolve(
            state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
        ).controller,
        kind=kind,
        cast=cast,
        event=event,
        target=target,
        options=options,
        source_action=source_action,
        source_asset=source_asset,
    )
    rules.put(state, value)
    return value


def prove_task(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Task:
    value = rules.get(state, rules.Task, identity)
    born = rules.get(_history(c, game, value.event), rules.Task, identity)
    if any(
        getattr(value, k) != getattr(born, k)
        for k in (
            "id",
            "source",
            "actor",
            "controller",
            "kind",
            "cast",
            "event",
            "target",
            "source_action",
            "source_asset",
        )
    ):
        raise WorkflowError("Preserve the genuine original consequence and actual source chooser")
    if value.selected_event:
        selected = rules.get(_history(c, game, value.selected_event), rules.Task, value.id)
        if any(
            getattr(value, k) != getattr(selected, k)
            for k in ("choice", "account", "source_tag", "options", "selected_event")
        ):
            raise WorkflowError("Preserve the actual canonical owned task selection and cost")
    if value.kind == "fight_fawn":
        from girlframe.engine.m3_appearance_matrix import damages

        actual = next(
            (x for x in damages(_history(c, game, value.event)) if x.id == value.source), None
        )
        if (
            actual is None
            or actual.target != value.actor
            or actual.damager != value.target
            or actual.asset != value.source_asset
        ):
            raise WorkflowError("Prove the actual newly damaged Asset and original damager")
    return value


def prove_encounter(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Encounter:
    value = rules.get(state, rules.Encounter, identity)
    born = support.prove_birth(
        game,
        c,
        value.event,
        "m3.ankou_task_answered" if value.request else "m3.ankou_encounter",
        value.author,
    )
    if value.request:
        request = prove_task(game, c, state, value.request)
        if (
            request.kind != "spy_context"
            or request.actor != value.target
            or request.target != value.actor
            or request.controller != value.author
        ):
            raise WorkflowError("Preserve the actual target-authored spying context request")
    if rules.get(born, rules.Encounter, identity) != value:
        raise WorkflowError("Preserve the actual original human factual encounter")
    bound = profiles(c, game.store.campaign_id)
    if _positions(game, c, state, (value.actor, value.target)) != {
        value.actor.token: value.actor_position,
        value.target.token: value.target_position,
    }:
        raise WorkflowError("Refresh the changed actual bodies/contact before using this source")
    if value.author not in (
        resolve(born, value.actor, bound, require_current_profile=False).controller,
        resolve(born, value.target, bound, require_current_profile=False).controller,
    ):
        raise WorkflowError("Only the original actual observer/target authored this source fact")
    return value


def validate_pending_touch(
    game: GameService, c: Connection, state: GameState, identity: str, event: str
) -> rules.Touch:
    value = rules.get(state, rules.Touch, identity)
    relay = prove_relay(game, c, state, value.relay)
    contact = prove_encounter(game, c, state, value.encounter)
    view = resolve(state, value.actor, profiles(c, game.store.campaign_id))
    if (
        value.event != event
        or value.completed_event
        or value.actor != relay.actor
        or value.target != contact.target
        or relay.ended_event
        or "touch" not in relay.benefits
        or not any(
            x.id == value.asset and not x.damaged for x in state.sheets[value.actor.entity].assets
        )
        or (
            value.frame is not None
            and (
                value.frame != relay.frame
                or view.frame_instance != value.frame
                or view.cell is None
                or view.cell != view.frame_cell
            )
        )
    ):
        raise WorkflowError("Use this exact staged active relay self-damage and true touch source")
    return value


def prove_touch(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Touch:
    value = rules.get(state, rules.Touch, identity)
    born = _history(c, game, value.event)
    if rules.get(born, rules.Touch, identity) != value:
        raise WorkflowError("Preserve the genuine source-owned damaged Asset and touch effect")
    from girlframe.services.m3_asset_loss import snapshots

    before, _ = snapshots(game, c, value.event)
    validate_pending_touch(
        game,
        c,
        before.model_copy(
            update={
                "facts": [
                    *before.facts,
                    dict(
                        kind="ankou_touch",
                        id=value.id,
                        body=value.model_copy(
                            update={"completed_event": None, "work": ()}
                        ).model_dump_json(),
                    ),
                ]
            }
        ),
        identity,
        value.event,
    )
    return value


def _period(
    game: GameService, c: Connection, state: GameState, identity: str, actor: ActorRef
) -> dict[str, Any]:
    table = t.m3["m3_off_duty"]
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
    body = json.loads(row["body_json"]) if row else {}
    if (
        row is None
        or str(actor.entity) not in {str(x) for x in body.get("pilots", ())}
        or current_ref(state, int(actor.entity)) != actor
        or body.get("character_ids", {}).get(actor.entity) != actor.incarnation
        or body.get("phase") != "active"
        or actor.entity in body.get("ended_characters", {})
    ):
        raise WorkflowError("Use the actual original participant's real OffDuty period")
    return dict(row)


def _owner_channel(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> int:
    casts = [x for x in state.scene_casts if x.open and any(r.actor == actor for r in x.roles)]
    if len(casts) != 1:
        raise WorkflowError("Use one actual current original participant scene")
    return casts[0].channel


def disclosed_sources(
    game: GameService, c: Connection, state: GameState, viewer: GuildViewer, person: ActorRef
) -> list[dict[str, str]]:
    from girlframe.engine.m3_mockingbird import actor_tags

    bound = profiles(c, game.store.campaign_id)
    other = resolve(state, person, bound)
    if other.controller == viewer.user_id:
        return [dict(id=x.id, label=x.name) for x in other.identities] + [
            dict(id=x.id, label=x.label) for x in actor_tags(state, person)
        ]
    result = []
    for fact in state.facts:
        if fact.get("kind") != "ankou_disclosure":
            continue
        body = json.loads(fact["body"])
        if (
            body["recipient"] == viewer.user_id
            and ActorRef.model_validate(body["person"]) == person
        ):
            born = support.prove_birth(
                game,
                c,
                body["event"],
                "m3.ankou_task_answered" if body.get("request") else "m3.ankou_disclosed",
                other.controller,
            )
            if fact not in born.facts:
                raise WorkflowError("Preserve the actual source-person private disclosure")
            result.append(
                dict(
                    id=body["resource"],
                    label=body["label"],
                    kind=body.get("resource_kind", "identity"),
                )
            )
    return result


def observe(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    event: str,
    metadata: dict[str, Any],
) -> None:
    """Source facts only: no nested event or fabricated performance during a real trigger."""
    registry = Access(game.store).registry
    if registry is None or game.store.policy.m3_approval is None:
        return
    from girlframe.engine.m3_appearance_matrix import damages

    for damage in damages(after):
        if damage.event != event or any(
            x.source == damage.id and x.kind == "fight_fawn"
            for x in rules.records(after, rules.Task)
        ):
            continue
        try:
            eligible = bool(rules.held(before, damage.target, rules.FIGHT))
        except ValueError:
            eligible = False
        if not eligible:
            continue
        registry.require_available(rules.FIGHT)
        cast = next((x for x in before.scene_casts if x.id == damage.scene), None)
        if cast is None:
            # A legacy cast is source-backed in the actual producer's bound scene.
            scenes = t.m2["m2_scenes"]
            channel = c.scalar(
                sa.select(scenes.c.channel_id).where(
                    scenes.c.campaign_id == game.store.campaign_id, scenes.c.id == damage.scene
                )
            )
            if channel is None:
                raise WorkflowError("Recover the actual source damage scene")
            cast = _cast(game, c, before, int(channel))
        _task(
            game,
            c,
            after,
            damage.id,
            damage.target,
            "fight_fawn",
            cast,
            event,
            target=damage.damager,
            source_action=damage.action,
            source_asset=damage.asset,
        )
    old_npcs = {x.id: x for x in before.world.npcs} if before.world else {}
    dead = (
        [x for x in after.world.npcs if x.id in old_npcs and old_npcs[x.id].alive and not x.alive]
        if after.world
        else []
    )
    for obsession in rules.records(before, rules.Obsession):
        if obsession.ended_event:
            continue
        bound = profiles(c, game.store.campaign_id)
        try:
            if rules.frame(before, obsession.actor) != obsession.frame:
                continue
        except ValueError:
            continue
        was = resolve(before, obsession.target, bound, require_current_profile=False)
        archived = any(
            x.actor == obsession.target and x.source_event == event for x in after.career_archives
        )
        died = (
            archived
            or not resolve(after, obsession.target, bound, require_current_profile=False).alive
        )
        if was.alive and died:
            from girlframe.services.m3_ankou_feedback_sequences import start

            cast = next(
                (
                    x
                    for x in before.scene_casts
                    if x.open and any(r.actor == obsession.actor for r in x.roles)
                ),
                None,
            )
            if cast is None:
                # Source venue is historical; no physical join or pause is invented.
                cast = next(
                    (
                        x
                        for x in before.scene_casts
                        if any(r.actor == obsession.actor for r in x.roles)
                    ),
                    None,
                )
            sequence = start(
                game,
                c,
                after,
                obsession.actor,
                cast,
                obsession.id,
                event,
                count=5,
                reason="obsession",
            )
            rules.put(
                after, obsession.model_copy(update={"sequence": sequence.id, "ended_event": event})
            )
    for relay in rules.active_relays(before):
        if relay.consequence != "death":
            continue
        for npc in dead:
            source = rules.identity("npc-death", relay.id, npc.id, event)
            if any(x.source == source for x in rules.records(after, rules.Task)):
                continue
            own = resolve(
                after,
                relay.actor,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            )
            if own.inside_frame:
                _task(
                    game,
                    c,
                    after,
                    source,
                    relay.actor,
                    "death_identity",
                    relay.cast,
                    event,
                    target=ActorRef(kind="npc", entity=npc.id),
                )
            else:
                # Physiology is unconditional; it does not invent the dead NPC as an opponent.
                after.facts.append(
                    dict(
                        kind="ankou_death_helpless",
                        source=source,
                        actor=relay.actor.model_dump_json(),
                        event=event,
                    )
                )
    for linked in rules.records(before, rules.Processor):
        if linked.unlinked_event:
            continue
        bound = profiles(c, game.store.campaign_id)
        own = resolve(after, linked.actor, bound, require_current_profile=False)
        broken = not own.alive or own.offstage_source is not None
        if not broken and own.cell is not None:
            broken = any(
                not resolve(after, x, bound, require_current_profile=False).alive
                or (
                    resolve(after, x, bound, require_current_profile=False).cell is not None
                    and resolve(after, x, bound, require_current_profile=False).cell != own.cell
                )
                for x in linked.minds
            )
        if broken:
            support.unlink(game, c, after, rules.get(after, rules.Processor, linked.id), event)


def helpless(state: GameState, actor: ActorRef, foe: ActorRef | None = None) -> bool:
    return rules.helpless(state, actor, foe)


def on_play(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    """Actual hostile Play admission, before effects; never triggered by readback."""
    if not rules.active_relays(state):
        return
    actor = support.actual_action_actor(action)
    meta = action["data"]
    raw = meta.get("tag_context", {}).get("target") or meta.get("prepared", {}).get("target_actor")
    target = ActorRef.model_validate(raw) if raw else None
    if target is None:
        uid = meta.get("prepared", {}).get("target")
        cid = meta.get("character_ids", {}).get(str(uid)) if uid else None
        if uid and cid:
            target = ActorRef(kind="pilot", entity=str(uid), incarnation=cid)
    for relay in rules.active_relays(state):
        if (
            relay.actor == actor
            or "interrupt" not in relay.benefits
            or relay.cast.id != action["scene_id"]
        ):
            continue
        if any(
            x.kind == "interrupt" and x.source_action == action["id"] and x.source == relay.id
            for x in rules.records(state, rules.Task)
        ):
            continue
        _task(
            game,
            c,
            state,
            relay.id,
            relay.actor,
            "interrupt",
            relay.cast,
            event,
            target=actor,
            source_action=action["id"],
        )
    if target is None or actor == target:
        return
    for relay in rules.active_relays(state, target):
        if "emotion" not in relay.benefits:
            continue
        prove_relay(game, c, state, relay.id)
        if any(
            x.source == relay.id and x.kind == "emotion" and x.actor == actor
            for x in rules.records(state, rules.Task)
        ):
            continue
        _task(
            game,
            c,
            state,
            relay.id,
            actor,
            "emotion",
            relay.cast,
            event,
            target=target,
            source_action=action["id"],
        )


def consume_roll_modifiers(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> list[dict[str, Any]]:
    if not any(not x.used_action for x in rules.records(state, rules.FightFawn)):
        return []
    actor = support.actual_action_actor(action)
    data = action["data"]
    raw = data.get("tag_context", {}).get("target") or data.get("prepared", {}).get("target_actor")
    target = ActorRef.model_validate(raw) if raw else None
    if target is None:
        uid = data.get("prepared", {}).get("target")
        cid = data.get("character_ids", {}).get(str(uid)) if uid else None
        if cid:
            target = ActorRef(kind="pilot", entity=str(uid), incarnation=cid)
    result = []
    for value in rules.records(state, rules.FightFawn):
        if (
            value.actor != actor
            or value.target != target
            or value.play != data["play"]
            or value.used_action
        ):
            continue
        task = prove_task(game, c, state, value.task)
        selected = rules.get(_history(c, game, value.event), rules.FightFawn, value.id)
        if selected != value or not task.completed_event:
            raise WorkflowError("Preserve the original source-owned accumulated Fight/Fawn bonus")
        rules.put(
            state, value.model_copy(update={"used_action": action["id"], "used_event": event})
        )
        result.append(dict(source=value.id, amount=1))
    return result


def prove_roll_modifiers(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> list[dict[str, Any]]:
    result = []
    if not any(x.used_action == action["id"] for x in rules.records(state, rules.FightFawn)):
        return []
    actor = support.actual_action_actor(action)
    for value in rules.records(state, rules.FightFawn):
        if value.used_action != action["id"]:
            continue
        prove_task(game, c, state, value.task)
        if not value.used_event or value.actor != actor or value.play != action["data"]["play"]:
            raise WorkflowError("Recover the genuine consumed Fight/Fawn roll source")
        born = rules.get(_history(c, game, value.used_event), rules.FightFawn, value.id)
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.used_event
            )
        ).first()
        receipt = action["data"].get("receipt", {})
        payload = json.loads(audit.payload_json) if audit else {}
        if (
            born != value
            or audit is None
            or audit.kind not in ("m2.rolled", "m3.rolled")
            or payload.get("action_id") != action["id"]
            or payload.get("receipt_id") != receipt.get("id")
        ):
            raise WorkflowError("Prove the actual canonical raw receipt and source modifier use")
        result.append(dict(source=value.id, amount=1))
    return result


def expire_scene(
    game: GameService, c: Connection, state: GameState, scene: str, event: str
) -> bool:
    changed = False
    for value in rules.active_relays(state):
        if value.cast.id == scene:
            if value.consequence is None:
                raise WorkflowError("The actual Handler still owes the Relay consequence")
            rules.put(state, value.model_copy(update={"ended_event": event}))
            changed = True
    return changed


def off_duty_start(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, period: str, event: str
) -> bool:
    from girlframe.engine.m3_mockingbird import actor_tags

    changed = False
    for use in rules.records(state, rules.TagUse):
        if use.kind == "symptom" and use.target == actor and not use.ended_event:
            if any(x.id == use.tag for x in actor_tags(state, actor)):
                support.remove_tag(state, actor, use.tag)
            rules.put(state, use.model_copy(update={"ended_event": event}))
            changed = True
    return changed


def off_duty_complete(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, period: str, event: str
) -> bool:
    changed = False
    for value in rules.records(state, rules.Obsession):
        if value.actor != actor or value.ended_event:
            continue
        if any(
            x.actor == actor
            and x.target == value.target
            and x.period == period
            and x.kind == "seen"
            for x in rules.records(state, rules.Encounter)
        ):
            continue
        scene = next((x for x in state.scene_casts if any(r.actor == actor for r in x.roles)), None)
        if scene is None:
            raise WorkflowError("Recover the original actor's actual period source venue")
        _task(
            game,
            c,
            state,
            value.id,
            actor,
            "missed_obsession",
            scene,
            event,
            target=value.target,
            options=(period,),
        )
        changed = True
    return changed


def synchronize_events(game: GameService, c: Connection, event: str) -> None:
    from girlframe.services.m3_ankou_feedback_sequences import materialize

    materialize(game, c, event)
    support.materialize_unlinks(game, c, event)
    state = load_state(c, game.store.campaign_id)
    from girlframe.services.m3_ankou_feedback_sequences import complete_child

    for step in rules.records(state, rules.FeedbackStep):
        if step.phase == "child" and step.child:
            complete_child(game, c, state, game.action(c, step.child), event)
    # Only actual new original death archives require career synchronization.
    state = load_state(c, game.store.campaign_id)
    for archive in state.career_archives:
        if archive.source_event == event:
            from girlframe.services.m3_careers import synchronize_end

            synchronize_end(c, game, archive)


def stalker_view(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, target: ActorRef
) -> dict[str, Any]:
    require_rule(game, c, state, actor, rules.STALKER)
    if not rules.effective_intense(state, actor, target):
        raise WorkflowError(
            "Only this actual directional Intense source authorizes Stalker knowledge"
        )
    view = resolve(state, target, profiles(c, game.store.campaign_id))
    if view.cell is None:
        raise WorkflowError("SOURCE_POSITION_REQUIRED: actual location remains unknown")
    candidates = [x for x in rules.records(state, rules.Company) if x.actor == target]
    company = None
    for source in reversed(candidates):
        born = support.prove_birth(game, c, source.event, "m3.ankou_task_answered", source.author)
        if rules.get(born, rules.Company, source.id) != source:
            raise WorkflowError("Preserve the original actual authored companion fact")
        task = prove_task(game, c, state, source.request)
        if task.kind != "company" or task.actor != target or task.target != actor:
            continue
        if _positions(game, c, state, (target, *source.companions)) != source.positions:
            continue
        company = [
            dict(
                ref=x.model_dump(mode="json"),
                label=resolve(state, x, profiles(c, game.store.campaign_id)).label,
            )
            for x in source.companions
        ]
        break
    return dict(
        target=target.model_dump(mode="json"),
        cell=view.cell,
        vessel=view.vessel_id,
        company=company,
        company_known=company is not None,
    )


def disclose(
    game: GameService,
    viewer: GuildViewer,
    key: str,
    revision: int,
    person: ActorRef,
    recipient: ActorRef,
    resource: str,
    account: str,
) -> dict[str, Any]:
    def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
        from girlframe.engine.m3_mockingbird import actor_tags

        bound = profiles(c, game.store.campaign_id)
        own = resolve(state, person, bound)
        other = resolve(state, recipient, bound)
        if (
            own.controller != viewer.user_id
            or not own.alive
            or not other.alive
            or person == recipient
        ):
            raise WorkflowError(
                "Only the actual original source person privately discloses their real resource"
            )
        rules.frame(state, recipient)
        label = next((x.name for x in own.identities if x.id == resource), None)
        if label is None:
            label = next((x.label for x in actor_tags(state, person) if x.id == resource), None)
        if label is None:
            raise WorkflowError("Choose an actual currently owned original Identity or Tag")
        body = dict(
            person=person.model_dump(mode="json"),
            recipient=other.controller,
            recipient_actor=recipient.model_dump(mode="json"),
            resource=resource,
            resource_kind="identity" if any(x.id == resource for x in own.identities) else "tag",
            label=label,
            account=support.text(account),
            event=event,
        )
        state.facts.append(
            dict(kind="ankou_disclosure", id=event, body=json.dumps(body, sort_keys=True))
        )
        return dict(id=event)

    return AnkouService(game)._write(
        viewer,
        key,
        revision,
        "m3.ankou_disclosed",
        dict(
            person=person.model_dump(mode="json"),
            recipient=recipient.model_dump(mode="json"),
            resource=resource,
            account=account,
        ),
        operation,
    )


def npc_off_duty(
    game: GameService, viewer: GuildViewer, key: str, revision: int, actor: ActorRef, account: str
) -> dict[str, Any]:
    def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
        actual = resolve(state, actor, profiles(c, game.store.campaign_id))
        handler = active_handler(state)
        handler_controller = (
            resolve(state, handler, profiles(c, game.store.campaign_id)).controller
            if handler
            else None
        )
        if (
            actor.kind != "npc"
            or not actual.alive
            or viewer.user_id not in (actual.controller, handler_controller)
        ):
            raise WorkflowError(
                "Only its original controller or actual Handler records NPC GoOffDuty"
            )
        support.text(account)
        off_duty_start(game, c, state, actor, "npc-duty:" + event, event)
        state.facts.append(
            dict(
                kind="ankou_npc_off_duty",
                id=event,
                actor=actor.model_dump_json(),
                account=account,
                event=event,
            )
        )
        return dict(id=event)

    return AnkouService(game)._write(
        viewer,
        key,
        revision,
        "m3.ankou_npc_off_duty",
        dict(actor=actor.model_dump(mode="json"), account=account),
        operation,
    )


def pulse_options(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> list[dict[str, str]]:
    from girlframe.engine.m3_mockingbird import actor_tags

    actor = support.actual_action_actor(action)
    try:
        if not rules.held(state, actor, rules.PULSE):
            return []
    except ValueError:
        return []
    if action["data"]["play"] not in ("all_out_assault", "engage", "put_someone_beneath_you"):
        return []
    require_rule(game, c, state, actor, rules.PULSE)
    return [dict(id=x.id, label=x.label) for x in actor_tags(state, actor)]


def apply_pulse(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    tag: str,
    target: ActorRef,
    event: str,
) -> None:
    actor = support.actual_action_actor(action)
    if tag not in {x["id"] for x in pulse_options(game, c, state, action)}:
        raise WorkflowError("Move an actual owned Tag only on a genuine supported Amygdala Play")
    raw = action["data"].get("tag_context", {}).get("target")
    actual = ActorRef.model_validate(raw) if raw else None
    if actual is None:
        prepared = action["data"].get("prepared", {})
        raw = prepared.get("target_actor")
        if raw:
            actual = ActorRef.model_validate(raw)
        elif prepared.get("target"):
            uid = str(prepared["target"])
            cid = action["data"].get("character_ids", {}).get(uid)
            if cid:
                actual = ActorRef(kind="pilot", entity=uid, incarnation=cid)
    if actual != target or actor == target:
        raise WorkflowError("Move the Tag only to this real Play's actual original target")
    if any(
        x.kind == "pulse" and x.source == action["id"] for x in rules.records(state, rules.TagUse)
    ):
        raise WorkflowError("This actual Play already moved its one Amygdala Tag")
    support.move_tag(state, actor, target, tag)
    rules.put(
        state,
        rules.TagUse(
            id=rules.identity("pulse", action["id"]),
            source=action["id"],
            actor=actor,
            target=target,
            tag=tag,
            scene=action["scene_id"],
            event=event,
            kind="pulse",
        ),
    )


def _interrupt_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    task = prove_task(game, c, state, json.loads(row["body_json"])["task"])
    if (
        task.kind != "interrupt"
        or task.source_action != action["id"]
        or task.controller != int(row["actor_id"])
        or task.completed_event
    ):
        raise WorkflowError(
            "Use the actual original owned interruption on this genuine incoming Play"
        )
    if row["kind"] == "ankou_interrupt_child":
        raise WorkflowError(
            "Complete the actual interruption Play; an acknowledgment cannot close it"
        )
    event = action["data"]["response_event"]
    if answer.flag is False:
        if answer.options or answer.fields:
            raise WorkflowError("Decline without erasing a Tag or inventing a performance")
        rules.put(state, task.model_copy(update={"completed_event": event, "choice": "declined"}))
        return True
    if (
        answer.flag is not True
        or len(answer.options) != 1
        or answer.options[0]
        not in (
            "keep_your_head",
            "check_sensors",
            "flirt",
            "all_out_assault",
            "engage",
            "put_someone_beneath_you",
        )
        or set(answer.fields) != {"tag"}
        or task.target is None
    ):
        raise WorkflowError(
            "Erase one actual acting-person Tag and choose a genuine interruption Play"
        )
    relay = prove_relay(game, c, state, task.source)
    if relay.ended_event or "interrupt" not in relay.benefits:
        raise WorkflowError("The actual relay interruption source has ended")
    support.remove_tag(state, task.target, answer.fields["tag"])
    request = game.request(c, action, task.controller, "ankou_interrupt_child", dict(task=task.id))
    rules.put(
        state,
        task.model_copy(
            update={
                "source_tag": answer.fields["tag"],
                "options": answer.options,
                "choice": "interrupt",
                "selected_event": event,
                "account": support.text(answer.text),
                "request": request,
            }
        ),
    )
    return True


def require_source_tasks(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    if any(
        x.source_action == action["id"] and x.kind == "emotion" and not x.completed_event
        for x in rules.records(state, rules.Task)
    ):
        raise WorkflowError(
            "The actual first-against person still owes their dominant-emotion answer"
        )


def prove_tag(
    game: GameService, c: Connection, state: GameState, owner: ActorRef, tag: str
) -> rules.TagUse:
    value = next(
        (x for x in rules.records(state, rules.TagUse) if x.tag == tag and x.target == owner), None
    )
    if value is None or value.ended_event:
        raise WorkflowError("Recover the genuine active Ankou source Tag")
    born = rules.get(_history(c, game, value.event), rules.TagUse, value.id)
    if born != value:
        raise WorkflowError(
            "Preserve this actual original source Tag giver, recipient and lifetime"
        )
    if value.kind in ("symptom", "champion"):
        processor = prove_source(game, c, state, value.source)
        if value.kind == "symptom" and owner not in processor.minds:
            raise WorkflowError("Only the actual linked processor receives these symptoms")
    elif value.kind == "emotion":
        prove_relay(game, c, state, value.source)
    elif value.kind == "obsession":
        obsession = rules.get(state, rules.Obsession, value.source)
        proof = prove_obsession(
            game, c, _history(c, game, value.event), obsession.actor, obsession.target
        )
        if proof is None:
            raise WorkflowError("Prove the actual original Obsession Tag source")
    elif value.kind == "spy":
        prove_encounter(game, c, _history(c, game, value.event), value.source)
    elif value.kind == "pulse":
        action = game.action(c, value.source)
        actor = support.actual_action_actor(action)
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        ).first()
        payload = json.loads(audit.payload_json) if audit else {}
        receipt = action["data"].get("receipt", {})
        if (
            actor != value.actor
            or audit is None
            or audit.kind not in ("m2.rolled", "m3.rolled")
            or payload.get("action_id") != action["id"]
            or payload.get("receipt_id") != receipt.get("id")
        ):
            raise WorkflowError("Prove the actual Amygdala move at its canonical real roll/receipt")
    return value


def self_tag(game: GameService, c: Connection, state: GameState, owner: ActorRef, tag: str) -> bool:
    value = next((x for x in rules.records(state, rules.TagUse) if x.tag == tag), None)
    if value is None or value.kind != "champion" or value.actor != owner or value.target != owner:
        return False
    prove_tag(game, c, state, owner, tag)
    return True


def request_source(
    game: GameService,
    viewer: GuildViewer,
    key: str,
    revision: int,
    channel: int,
    person: ActorRef,
    kind: Literal["disclosure", "spy_context", "company"],
    account: str,
) -> dict[str, Any]:
    def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
        actor = current_ref(state, viewer.user_id)
        require_rule(
            game, c, state, actor, rules.QUICKCHANGE if kind == "disclosure" else rules.STALKER
        )
        cast = _cast(game, c, state, channel)
        support.cast_actor(game, c, state, cast, actor)
        actual = resolve(state, person, profiles(c, game.store.campaign_id))
        if actor == person or not actual.alive:
            raise WorkflowError("Address an actual other original source person")
        if kind == "spy_context" and person not in support.range_people(game, c, state, actor):
            raise WorkflowError(
                "Use an actual current physical spying source, not invented remote observation"
            )
        support.text(account)
        options: tuple[str, ...] = ()
        if kind == "company":
            options = tuple(
                x.model_dump_json() for x in support.range_people(game, c, state, person)
            )
        task = _task(
            game, c, state, event, person, kind, cast, event, target=actor, options=options
        )
        return dict(id=task.id)

    return AnkouService(game)._write(
        viewer,
        key,
        revision,
        "m3.ankou_source_requested",
        dict(channel=channel, person=person.model_dump(mode="json"), kind=kind, account=account),
        operation,
    )


def sense_view(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, relay_id: str
) -> list[dict[str, Any]]:
    source = prove_relay(game, c, state, relay_id)
    if source.actor != actor or source.ended_event or "sense" not in source.benefits:
        raise WorkflowError("Use the actual owned active scene's vague-location benefit")
    own = resolve(state, actor, profiles(c, game.store.campaign_id))
    # Vague sensing grants no hidden names or thoughts.
    known = {current_ref(state, x.owner) for x in state.sheets.values() if x.character_id}
    if state.world:
        known.update(ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.revealed)
    return [
        dict(
            id=rules.identity("sense", source.id, x.token),
            label=resolve(state, x, profiles(c, game.store.campaign_id)).label
            if x in known
            else "An unidentified person",
            vague_cell=own.cell,
        )
        for x in support.range_people(game, c, state, actor)
    ]


def save_notice(
    game: GameService, viewer: GuildViewer, key: str, revision: int, identity: str
) -> dict[str, Any]:
    def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
        value = rules.get(state, rules.Delivery, identity)
        born = rules.get(_history(c, game, value.event), rules.Delivery, identity)
        if (
            value.model_copy(update={"saved_event": None}) != born
            or viewer.user_id != value.target_controller
            or value.saved_event
        ):
            raise WorkflowError(
                "Only the actual addressed original recipient saves this notice to history"
            )
        rules.put(state, value.model_copy(update={"saved_event": event}))
        return dict(id=value.id)

    return AnkouService(game)._write(
        viewer, key, revision, "m3.ankou_notice_saved", dict(id=identity), operation
    )


def require_free(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, source: str | None = None
) -> None:
    """Actual new-action timing; root passes only a positively prepared child source ID."""
    required = [
        x
        for x in rules.records(state, rules.Task)
        if x.actor == actor
        and not x.completed_event
        and x.kind in ("fight_fawn", "death_identity", "missed_obsession", "perform")
    ]
    if any(x.id != source for x in required):
        raise WorkflowError(
            "Resolve this original actor's actual outstanding Ankou choice/performance first"
        )
    for sequence in rules.records(state, rules.FeedbackSequence):
        if sequence.actor != actor or sequence.completed_event or sequence.terminal_event:
            continue
        step = next(
            (
                x
                for x in rules.records(state, rules.FeedbackStep)
                if x.sequence == sequence.id and x.id == source and x.phase == "child"
            ),
            None,
        )
        if step is None:
            raise WorkflowError(
                "Complete the actual original Feedback sequence before a new unrelated Play"
            )
