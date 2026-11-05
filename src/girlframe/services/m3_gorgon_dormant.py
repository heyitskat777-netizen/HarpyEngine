"""Original Gorgon counter-Void is real World corruption before its attack continues."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_gorgon_dormant as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Required
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_collateral import append, latest
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

KIND = "gorgon_dormant_void"


def _history(game: "GameService", c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover this actual awakening's immutable source history")
    return GameState.model_validate_json(raw)


def awakened_source(
    game: "GameService", c: Connection, state: GameState, dormant: ActorRef
) -> str | None:
    """Prove the persistent actual marker, including existing Pilot/Harpy Battle sources."""
    markers = [
        x
        for x in state.facts
        if x.get("kind") == "dormant_awakening" and x.get("gorgon") == dormant.entity
    ]
    if not markers:
        return None
    if dormant.kind != "gorgon":
        raise WorkflowError("The actual awakened body is a Gorgon")
    marker = markers[-1]
    event = marker.get("event", "")
    proof = _history(game, c, event)
    if marker not in proof.facts or (
        not marker.get("source_action") and marker.get("cause") != "own_type_play"
    ):
        raise WorkflowError("A declaration flag or rewritten marker is not actual awakening proof")
    body = (
        next((x for x in proof.world.gorgons if x.id == dormant.entity), None)
        if proof.world
        else None
    )
    actor = ActorRef.model_validate_json(marker.get("actor", "{}"))
    if body is None or body.gorgon_class != "dormant":
        raise WorkflowError("Recover the original Dormant body at its actual awakening")
    event_row = c.execute(
        sa.select(t.events.c.kind, t.events.c.payload_json, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if event_row is None or event_row.kind not in (
        "m3.battle_dormant_awakened",
        "m3.gorgon_play_advanced",
        "m2.choice_resolved",
        "m3.choice_resolved",
        "m3.leviathan_layers_raised",
        "m3.leviathan_obsessed_tag_given",
        "m3.leviathan_obsession_trigger_paid",
    ):
        raise WorkflowError("Recover the actual committed attack/capability awakening source")
    if marker.get("cause") == "own_type_play":
        if event_row.kind in ("m3.leviathan_obsessed_tag_given", "m3.leviathan_obsession_trigger_paid"):
            from girlframe.services.m3_leviathan_obsession import ObsessionService

            if actor != dormant or marker.get("source_type") not in (
                "gorgon-type.leviathan.leviathan-type", "gorgon-type.leviathan.succumb-to-obsession"
            ):
                raise WorkflowError("The awakening must belong to this actual original Type actor")
            ObsessionService(game).prove_type_event(c, proof, event, dormant)
            return event
        from girlframe.engine.m3_leviathan import LayerSource

        source = next(
            (
                x
                for x in proof.facts
                if x.get("kind") == "leviathan_layers"
                and x.get("event") == event
                and x.get("actor") == dormant.model_dump_json()
            ),
            None,
        )
        layers = LayerSource.model_validate_json(source["body"]) if source else None
        if (
            event_row.kind != "m3.leviathan_layers_raised"
            or actor != dormant
            or marker.get("source_type") != "gorgon-type.leviathan.leviathan-type"
            or json.loads(event_row.payload_json).get("actor_ref")
            != dormant.model_dump(mode="json")
            or event_row.actor_id != str(resolve(proof, dormant, ()).controller)
            or layers is None
            or layers.actor != dormant
            or layers.event != event
            or body.flesh_layers != layers.layers
            or body.flesh_layers_event != event
        ):
            raise WorkflowError("Prove the actual original Dormant's owned Type Play effect")
        return event
    if json.loads(event_row.payload_json).get("action_id") != marker["source_action"]:
        raise WorkflowError("The awakening event belongs to another original source action")
    if marker.get("cause") == "own_play":
        from girlframe.services.m3_gorgon_play import GorgonPlayService

        action = game.action(c, marker["source_action"])
        original = GorgonPlayService(game).source(c, action)
        if (
            actor != dormant
            or original["actor"] != dormant.model_dump(mode="json")
            or original["kind"] not in ("attack", "collateral", "warp")
            or marker.get("source_intent") != original["source_event"]
        ):
            raise WorkflowError("Prove the actual original Dormant's own declared basic Play")
        if event_row.kind == "m3.gorgon_play_advanced":
            if event_row.actor_id != str(original["controller"]):
                raise WorkflowError("Only the actual declared controller advanced this own Play")
        elif event_row.kind in ("m2.choice_resolved", "m3.choice_resolved"):
            request_id = json.loads(event_row.payload_json).get("choice_id")
            choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
            request = (
                c.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == game.store.campaign_id, choices.c.id == request_id
                    )
                )
                .mappings()
                .first()
            )
            response = c.scalar(
                sa.select(responses.c.answer_json).where(
                    responses.c.campaign_id == game.store.campaign_id,
                    responses.c.choice_id == request_id,
                    responses.c.actor_id == str(original["judge"]),
                    responses.c.event_id == event,
                )
            )
            if (
                request is None
                or request["kind"] != "gorgon_asset_capability"
                or request["action_id"] != action["id"]
                or request["actor_id"] != str(original["judge"])
                or event_row.actor_id != request["actor_id"]
                or response is None
                or json.loads(response).get("flag") is not True
            ):
                raise WorkflowError("Prove the actual frozen judge's capability approval")
        else:
            raise WorkflowError("An unstarted menu/declaration cannot awaken this actual creature")
        return event
    candidates: list[tuple[str, Required]] = []
    for fact in proof.facts:
        if fact.get("event") != event:
            continue
        if fact.get("kind") == "gorgon_dormant_stage":
            staged = json.loads(fact["body"])
            required = Required.model_validate_json(json.dumps(staged["requirement"]))
            candidates.append((fact["id"], required))
        elif fact.get("kind") == "battle_damage_stage" and fact.get("requirement"):
            required = Required.model_validate_json(fact["requirement"])
            candidates.append((fact["id"], required))
    matched = [
        identity
        for identity, requirement in candidates
        if requirement.kind == "dormant_void"
        and requirement.target == actor
        and requirement.opponent == dormant
        and requirement.source_pdf == 165
    ]
    work = t.m3["m3_required_work"]
    for identity in matched:
        first = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == game.store.campaign_id, work.c.id == identity)
                .order_by(work.c.revision)
                .limit(1)
            )
            .mappings()
            .first()
        )
        original = json.loads(first["body_json"]) if first else {}
        if (
            first is not None
            and first["event_id"] == event
            and first["kind"] in ("dormant_void", KIND)
            and original.get("owner") == actor.model_dump(mode="json")
            and original.get("source_action") == marker["source_action"]
        ):
            return event
    raise WorkflowError(
        "The actual persistent awakening needs its original required counter source"
    )


def record_own_wake(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    """An actual advanced own basic Play wakes this same creature, not merely a menu."""
    meta = action["data"]["gorgon_play"]
    actor = ActorRef.model_validate(meta["actor"])
    body = (
        next((x for x in state.world.gorgons if x.id == actor.entity), None)
        if state.world
        else None
    )
    if body is None or body.gorgon_class != "dormant":
        return
    if awakened_source(game, c, state, actor) is not None:
        return
    state.facts.append(
        dict(
            kind="dormant_awakening",
            cause="own_play",
            gorgon=actor.entity,
            actor=actor.model_dump_json(),
            event=action["data"]["response_event"],
            source_action=action["id"],
            source_choice="",
            source_intent=meta["source_event"],
        )
    )


def stage(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> bool:
    meta = action["data"]["gorgon_play"]
    actor = ActorRef.model_validate(meta["actor"])
    target = ActorRef.model_validate(meta["target"])
    if target.kind != "gorgon":
        return False
    creature = (
        next((x for x in state.world.gorgons if x.id == target.entity), None)
        if state.world
        else None
    )
    if creature is None or creature.gorgon_class != "dormant":
        return False
    previous = awakened_source(game, c, state, target)
    if previous is not None:
        meta["dormant_prior_awakening"] = previous
        return False
    identity = str(uuid5(NAMESPACE_URL, "actual-gorgon-dormant:" + action["id"]))
    if meta.get("dormant_work") or any(x.get("id") == identity for x in state.facts):
        raise WorkflowError(
            "Resume the actual original Gorgon's existing counter, not a second cost"
        )
    actual = resolve(state, actor, ())
    if actor.kind != "gorgon" or actual.controller != meta["controller"] or not actual.assets:
        raise WorkflowError("The actual Gorgon attacker needs its original owned World resources")
    event = action["data"]["response_event"]
    required = Required(
        kind="dormant_void",
        target=actor,
        opponent=target,
        source_pdf=165,
        details=dict(source_kind="gorgon_attack", dive="not_a_frame_actor"),
    )
    choice = game.request(
        c,
        action,
        meta["controller"],
        KIND,
        dict(
            work_id=identity,
            actor=actor.model_dump(mode="json"),
            dormant=target.model_dump(mode="json"),
        ),
    )
    body = dict(
        owner=actor.model_dump(mode="json"),
        source_action=action["id"],
        requirement=required.model_dump(mode="json"),
        continuation=choice,
        source_event=event,
        source_kind="gorgon_attack",
        controller=meta["controller"],
        immediate=True,
        phase="void",
        dive_applicable=False,
    )
    state.facts.extend(
        (
            dict(
                kind="gorgon_dormant_stage",
                id=identity,
                event=event,
                body=json.dumps(body, sort_keys=True),
            ),
            dict(
                kind="dormant_awakening",
                gorgon=target.entity,
                actor=actor.model_dump_json(),
                source_action=action["id"],
                source_choice=choice,
                event=event,
                work=identity,
            ),
        )
    )
    meta.update(phase="awaiting_dormant_void", dormant_work=identity)
    meta.setdefault("followups", []).append(identity)
    return True


def materialize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    proof = _history(game, c, event)
    work = t.m3["m3_required_work"]
    for fact in proof.facts:
        if fact.get("kind") != "gorgon_dormant_stage" or fact.get("event") != event:
            continue
        body = json.loads(fact["body"])
        if body["source_action"] != action["id"]:
            continue
        if c.scalar(
            sa.select(work.c.id).where(
                work.c.campaign_id == game.store.campaign_id, work.c.id == fact["id"]
            )
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            fact["id"],
            body["controller"],
            body["controller"],
            KIND,
            body,
            event,
        )


class GorgonDormantService:
    def __init__(self, store: OnboardingStore, game: "GameService | None" = None):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, game or GameService(store)

    def _source(self, c: Connection, identity: str) -> tuple[dict[str, Any], dict[str, Any]]:
        row = latest(self.game, c, identity)
        if row["kind"] != KIND:
            raise WorkflowError("Open the original actual Gorgon counter-Void source")
        table = t.m3["m3_required_work"]
        first = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision)
                .limit(1)
            )
            .mappings()
            .one()
        )
        initial, body = json.loads(first["body_json"]), json.loads(row["body_json"])
        proof = _history(self.game, c, first["event_id"])
        stage_fact = next(
            (
                x
                for x in proof.facts
                if x.get("kind") == "gorgon_dormant_stage" and x.get("id") == identity
            ),
            None,
        )
        if stage_fact is None or json.loads(stage_fact["body"]) != initial:
            raise WorkflowError("Recover this exact original canonical Gorgon counter stage")
        frozen = (
            "owner",
            "source_action",
            "requirement",
            "continuation",
            "source_event",
            "source_kind",
            "controller",
            "dive_applicable",
        )
        if any(body.get(key) != initial.get(key) for key in frozen):
            raise WorkflowError("A different actor/source cannot inherit this counter obligation")
        required = Required.model_validate_json(json.dumps(initial["requirement"]))
        if required.target.kind != "gorgon" or required.opponent is None:
            raise WorkflowError("Use the actual Gorgon body, not its controller's Pilot")
        from girlframe.services.m3_gorgon_play import GorgonPlayService

        action = self.game.action(c, initial["source_action"])
        GorgonPlayService(self.game).source(c, action)
        meta = action["data"]["gorgon_play"]
        if (
            meta["kind"] != "attack"
            or meta["actor"] != initial["owner"]
            or meta["target"] != required.opponent.model_dump(mode="json")
            or meta.get("dormant_work") != identity
            or meta["controller"] != initial["controller"]
        ):
            raise WorkflowError("Recover the real original declared Gorgon attack/counter binding")
        if awakened_source(self.game, c, proof, required.opponent) != first["event_id"]:
            raise WorkflowError("Recover this exact first actual persistent awakening")
        if (
            str(body["controller"]) != first["owner_id"]
            or first["subject_id"] != first["owner_id"]
            or first["scene_id"] != action["scene_id"]
            or any(
                row[key] != first[key]
                for key in ("owner_id", "subject_id", "scene_id", "mission_id", "off_duty_id")
            )
        ):
            raise WorkflowError("Recover the original actual cost's human/context binding")
        if row["state"] == "resolved":
            if body.get("phase") == "paid":
                _payment_event(self.game, c, action, identity, body)
            elif body.get("phase") == "original_ended":
                ended_proof = _history(self.game, c, body.get("ended_state_event", ""))
                ended_body = (
                    next(
                        (
                            x
                            for x in ended_proof.world.gorgons
                            if x.id == required.target.entity and not x.alive
                        ),
                        None,
                    )
                    if ended_proof.world
                    else None
                )
                if ended_body is None or ended_body.model_dump_json() != body.get(
                    "actual_ended_body"
                ):
                    raise WorkflowError(
                        "Prove the exact original ended creature, not a resolved flag"
                    )
            else:
                raise WorkflowError("This actual counter has no proved terminal effect")
        elif body.get("phase") != "void":
            raise WorkflowError("Recover the original still-owed actual counter")
        return row, body

    def _view(self, c: Connection, human: int, identity: str) -> dict[str, Any]:
        row, body = self._source(c, identity)
        if row["owner_id"] != str(human) or body["controller"] != human:
            raise WorkflowError("Only the actual original Gorgon controller reads/chooses its cost")
        state = load_state(c, self.store.campaign_id)
        actor = ActorRef.model_validate(body["owner"])
        actual = resolve(state, actor, (), require_alive=False)
        if actual.controller != human:
            raise WorkflowError(
                "Recover this source Gorgon's actual controller; no current-PC alias"
            )
        assert state.world is not None
        creature = next(x for x in state.world.gorgons if x.id == actor.entity)
        available = [x.model_dump(mode="json") for x in creature.assets if not x.void]
        return dict(
            id=identity,
            revision=row["revision"],
            game_revision=state.revision,
            state=row["state"],
            actor=actor.model_dump(mode="json"),
            source_action=body["source_action"],
            assets=available,
            already_fully_void=bool(creature.assets) and all(x.void for x in creature.assets),
            can_act=actual.alive and bool(creature.assets) and row["state"] != "resolved",
            dive_applicable=False,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return self._view(c, viewer.user_id, identity)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        latest_rows = {
            x["id"]: x
            for x in c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == KIND)
                .order_by(table.c.revision)
            ).mappings()
        }
        return [
            dict(
                id=x["id"],
                revision=x["revision"],
                state=x["state"],
                incoming=True,
                label="Your actual Gorgon's Dormant counter-Void",
            )
            for x in latest_rows.values()
            if x["state"] != "resolved" and x["owner_id"] == str(viewer.user_id)
        ]

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        asset: str | None,
        description: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            access = Access(self.store)
            access.authorize(c, viewer, "world", director_response=True)
            access.authorize(c, viewer, "plays", director_response=True)
            data = self._view(c, viewer.user_id, identity)
            from girlframe.services.m3_gorgon_play import GorgonPlayService

            GorgonPlayService(self.game).authorize(
                c, viewer, self.game.action(c, data["source_action"])
            )

        def apply(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            data = self._view(c, viewer.user_id, identity)
            row, body = self._source(c, identity)
            if (
                revision != row["revision"]
                or game_revision != data["game_revision"]
                or not data["can_act"]
            ):
                raise WorkflowError("STALE_GORGON_VOID: reopen this actual original body/cost")
            state = load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate(body["owner"])
            required = Required.model_validate_json(json.dumps(body["requirement"]))
            assert required.opponent is not None
            event = str(uuid4())
            changed = rules.inflict(
                state, actor, required.opponent, identity, asset, description, event
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.gorgon_dormant_void_paid",
                changed,
                event_id=event,
                work_id=identity,
                source_action=body["source_action"],
            )
            append(c, row, event, body | dict(phase="paid", payment_event=event), "resolved")
            _complete(self.game, c, identity, event, viewer, key)
            return dict(
                id=identity,
                state="resolved",
                game_revision=load_state(c, self.store.campaign_id).revision,
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.gorgon_dormant_void_paid",
                dict(
                    id=identity,
                    revision=revision,
                    game_revision=game_revision,
                    asset=asset,
                    description=description,
                ),
                apply,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def _complete(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    row, body = GorgonDormantService(game.store, game)._source(c, identity)
    if row["state"] != "resolved":
        raise WorkflowError("Apply the actual counter-Void before resuming the original attack")
    choices = t.m2["m2_choices"]
    choice = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == body["continuation"],
            )
        )
        .mappings()
        .first()
    )
    if (
        choice is None
        or choice["action_id"] != body["source_action"]
        or choice["kind"] != KIND
        or json.loads(choice["body_json"]).get("work_id") != identity
    ):
        raise WorkflowError("Recover the exact original Gorgon counter choice")
    if choice["state"] == "pending":
        c.execute(
            choices.update()
            .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == choice["id"])
            .values(
                state=(
                    "completed_original_ended"
                    if body.get("phase") == "original_ended"
                    else "completed_by_work"
                ),
                revision=choices.c.revision + 1,
            )
        )
    action = game.action(c, body["source_action"])
    if action["state"] not in ("complete", "aborted"):
        from girlframe.services.m3_gorgon_play import GorgonPlayService
        from girlframe.services.m3_gorgon_runtime import resume_after_dormant

        if body.get("phase") == "paid":
            resume_after_dormant(
                game, c, load_state(c, game.store.campaign_id), action, identity, event
            )
            game.save_action(c, action)
        GorgonPlayService(game).synchronize(c, action, event, viewer, key)


def require_clear(game: "GameService", c: Connection, actor: ActorRef | None = None) -> None:
    table = t.m3["m3_required_work"]
    rows = {
        x["id"]: x
        for x in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.kind == KIND)
            .order_by(table.c.revision)
        ).mappings()
    }
    for row in rows.values():
        body = json.loads(row["body_json"])
        if actor is None or body["owner"] == actor.model_dump(mode="json"):
            GorgonDormantService(game.store, game)._source(c, row["id"])
            if row["state"] != "resolved":
                raise WorkflowError(
                    "Finish this actual Gorgon's immediate Dormant counter-Void first"
                )


def _payment_event(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    identity: str,
    body: dict[str, Any],
) -> str:
    event = str(body.get("payment_event", ""))
    proof = _history(game, c, event)
    fact = next(
        (
            x
            for x in proof.facts
            if x.get("kind") == "gorgon_dormant_void_paid"
            and x.get("work") == identity
            and x.get("event") == event
        ),
        None,
    )
    payment = rules.Payment.model_validate_json(fact["body"]) if fact else None
    owner = ActorRef.model_validate(body["owner"])
    source_event = c.execute(
        sa.select(
            t.events.c.seq, t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json
        ).where(t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event)
    ).first()
    if (
        payment is None
        or payment.dormant != Required.model_validate_json(json.dumps(body["requirement"])).opponent
        or payment.actor != owner
        or payment.work != identity
        or payment.event != event
        or body["source_action"] != action["id"]
        or source_event is None
        or source_event.kind != "m3.gorgon_dormant_void_paid"
        or source_event.actor_id != str(body["controller"])
        or json.loads(source_event.payload_json).get("work_id") != identity
        or json.loads(source_event.payload_json).get("source_action") != action["id"]
    ):
        raise WorkflowError("A resolved flag cannot substitute for the actual original Void effect")
    history = t.m2["m2_state_history"]
    preceding = c.scalar(
        sa.select(history.c.body_json)
        .join(
            t.events,
            sa.and_(
                t.events.c.campaign_id == history.c.campaign_id, t.events.c.id == history.c.event_id
            ),
        )
        .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < source_event.seq)
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    before = GameState.model_validate_json(preceding) if preceding else None
    actor_before = (
        next((x for x in before.world.gorgons if x.id == owner.entity), None)
        if before and before.world
        else None
    )
    actor_after = (
        next((x for x in proof.world.gorgons if x.id == owner.entity), None)
        if proof.world
        else None
    )
    if (
        before is None
        or actor_before is None
        or actor_after is None
        or tuple(x.model_dump_json() for x in actor_before.assets) != payment.before_assets
    ):
        raise WorkflowError("Recover the sole actual original World resources before this payment")
    expected = rules.inflict(
        before, owner, payment.dormant, identity, payment.asset, payment.description, event
    )
    assert expected.world is not None
    expected_actor = next(x for x in expected.world.gorgons if x.id == owner.entity)
    if actor_after != expected_actor:
        raise WorkflowError(
            "This counter cannot repair, duplicate or rewrite unrelated Gorgon resources"
        )
    return event


def paid_source(game: "GameService", c: Connection, action: dict[str, Any], identity: str) -> str:
    row, body = GorgonDormantService(game.store, game)._source(c, identity)
    if row["state"] != "resolved" or body.get("phase") != "paid":
        raise WorkflowError("The source contest needs its real completed Gorgon Void payment")
    return _payment_event(game, c, action, identity, body)


def synchronize_endings(
    game: "GameService", c: Connection, event: str, viewer: GuildViewer | None, key: str
) -> None:
    """A genuinely ended original pays no invented Void to a replacement/controller body."""
    proof = _history(game, c, event)
    table = t.m3["m3_required_work"]
    rows = {
        x["id"]: dict(x)
        for x in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.kind == KIND)
            .order_by(table.c.revision)
        ).mappings()
    }
    for row in rows.values():
        if row["state"] == "resolved":
            continue
        actual, body = GorgonDormantService(game.store, game)._source(c, row["id"])
        owner = ActorRef.model_validate(body["owner"])
        ended = (
            next((x for x in proof.world.gorgons if x.id == owner.entity and not x.alive), None)
            if proof.world
            else None
        )
        if ended is None:
            continue
        append(
            c,
            actual,
            event,
            body
            | dict(
                phase="original_ended",
                ended_state_event=event,
                actual_ended_body=ended.model_dump_json(),
            ),
            "resolved",
        )
        _complete(game, c, row["id"], event, viewer, key)
