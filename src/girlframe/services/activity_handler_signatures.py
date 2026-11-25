"""Source-bound Activity access to native Handler signature work."""

import json
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.activity_batch import NativeHandlerSignature, NativeSignatureOpportunity
from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Context, Declaration
from girlframe.engine.m3_handler_character import BOOK_RULES
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_trainer_phrases import PHRASE_LABELS, sitting
from girlframe.services import m3_insurgent_loyalty as loyalty
from girlframe.services import m3_mistress_rewards as honey
from girlframe.services import m3_scientist_lab as lab
from girlframe.services import m3_trainer_phrases as training
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_handler_book_orders import active_book, direct_order_source
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

CHOICES = frozenset(
    (
        honey.OFFER,
        honey.REPLY,
        honey.REJECTION,
        loyalty.WATCH,
        loyalty.REVEAL,
        *training.RESPONSE_CHOICES,
        training.FLIRT,
        training.HUNT,
    )
)
ORDERS = frozenset(("order_response", "order_disobey"))
DIRECT_BOOKS = (("Mistress", honey.RULE), ("Insurgent", loyalty.RULE))
CHILD_CHOICES = frozenset(
    (
        "tag_window",
        "actor_disobey",
        "handler_disobey",
        "follow_disobey",
        "actor_flirt",
        "target_flirt",
        "actor_flirt_answer",
        "flirt_escape",
        "flirt_owe_tag",
        "engage_assault_extra",
        "battle_assault_table",
        "battle_handler",
        "battle_counter",
        "battle_low_damage",
        "battle_actor_damage",
        "battle_target_damage",
        "battle_trainer_protect",
    )
)


def conditioning_targets(
    game: GameService, c: Connection, state: GameState, scene: dict[str, Any], issuer: int
) -> list[dict[str, Any]]:
    lock = game.lock(c, scene["channel_id"])
    if (lock and lock["state"] != "released") or not active_book(
        game, c, state, book="Trainer", rule=training.RULE
    ):
        return []
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_battle import _cast

    targets = []
    for uid in scene["participants"]:
        if str(uid) not in state.sheets or not higher(state, issuer, uid):
            continue
        target = current_ref(state, uid)
        phrases = [
            (key, label)
            for key, label in PHRASE_LABELS.items()
            if issuer != state.handler
            or training._installation(game, c, state, target, key) is not None
        ]
        actors: dict[str, list[tuple[str, str]]] = {}
        if {key for key, _ in phrases}.intersection(("hunt", "protect")):
            try:
                cast = _cast(game, c, state, scene["channel_id"])
            except WorkflowError:
                cast = None
            if cast:
                bound = profiles(c, game.store.campaign_id)
                for key, _ in phrases:
                    if key not in ("hunt", "protect"):
                        continue
                    select = training._hunt_target if key == "hunt" else training._protected_target
                    for role in cast.roles:
                        try:
                            actor = select(game, c, state, scene, target, issuer, role.actor.token)
                            if actor:
                                name = resolve(state, actor, bound).label
                                actors.setdefault(key, []).append((actor.token, name))
                        except (ValueError, WorkflowError):
                            continue
        phrases = [
            (key, label)
            for key, label in phrases
            if key not in ("hunt", "protect") or actors.get(key)
        ]
        if phrases:
            targets.append(
                {
                    "id": str(uid),
                    "name": state.sheets[str(uid)].callsign,
                    "phrases": phrases,
                    "actors": actors,
                }
            )
    return targets


def native_signature(
    game: GameService, c: Connection, scene: dict[str, Any], handler: ActorRef, girl: ActorRef
) -> tuple[NativeSignatureOpportunity, ...]:
    state = load_state(c, game.store.campaign_id)
    persona = state.handler_persona
    if persona is None or persona.playbook is None:
        return ()
    book = persona.playbook
    play: NativeHandlerSignature
    result = next(rule for rule in BOOK_RULES[book] if rule.kind == "Signature Play")
    if book in ("Mistress", "Insurgent"):
        kind = honey.OFFER if book == "Mistress" else loyalty.WATCH
        choices, actions = t.m2["m2_choices"], t.m2["m2_actions"]
        bound = c.execute(
            sa.select(actions.c.id, choices.c.id.label("choice_id"), choices.c.body_json)
            .join(
                choices,
                (choices.c.campaign_id == actions.c.campaign_id)
                & (choices.c.action_id == actions.c.id),
            )
            .where(
                actions.c.campaign_id == game.store.campaign_id,
                actions.c.scene_id == scene["id"],
                actions.c.actor_id == girl.entity,
                choices.c.actor_id == handler.entity,
                choices.c.kind == kind,
                choices.c.state == "pending",
            )
        ).all()
        control = None
        for action_id, choice_id, body in bound:
            action = game.action(c, action_id)
            original = (honey._source if book == "Mistress" else loyalty._source)(
                game, c, state, action
            )
            saved = json.loads(body)
            if original and original == (saved["source"] if book == "Mistress" else saved):
                control = choice_id
                break
        if not control:
            return ()
        destination: Literal["signature_choice", "conditioning_phrase", "off_duty_signature"]
        destination = "signature_choice"
        play = "catch_more_flies_with_honey" if book == "Mistress" else "rebel_sympathizers"
    elif book in ("Scientist", "Trainer"):
        periods = t.m3["m3_off_duty"]
        raw = c.scalar(
            sa.select(periods.c.body_json).where(
                periods.c.campaign_id == game.store.campaign_id,
                periods.c.phase == "active",
            )
        )
        control = None
        destination = "off_duty_signature"
        if raw:
            period = Period.model_validate_json(raw)
            if (
                str(period.handler) == handler.entity
                and period.handler_scene is None
                and period.character_ids.get(girl.entity) == girl.incarnation
                and girl.entity not in period.ended_characters
            ):
                people = (period.handler, int(girl.entity))
                try:
                    if book == "Scientist":
                        lab.scope(game, c, state, period, people)
                        control = period.id
                    else:
                        for phrase in PHRASE_LABELS:
                            try:
                                training.training_target(game, c, state, period, people, phrase)
                            except WorkflowError:
                                continue
                            control = period.id
                            break
                except WorkflowError:
                    pass
        if not control and book == "Trainer":
            if any(
                row["id"] == girl.entity
                for row in conditioning_targets(game, c, state, scene, int(handler.entity))
            ):
                control = girl.entity
                destination = "conditioning_phrase"
        if not control:
            return ()
        play = "head_to_the_lab" if book == "Scientist" else "conditioning_phrases"
    else:
        return ()
    return (
        NativeSignatureOpportunity(
            play=play,
            title=result.title,
            trigger=result.trigger,
            control=control,
            destination=destination,
        ),
    )


def _conditioning_action(action: dict[str, Any]) -> bool:
    return isinstance(action["data"].get("conditioning_phrase"), dict)


class ActivitySignatureChoices:
    def __init__(self, session: DirectorSessionService):
        self.game, self.observer = session.game, session.observer
        self.store = session.store

    def _choice(
        self, c: Connection, viewer: GuildViewer, scene: str, identity: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self.observer._scene(c, scene, viewer)
        choices = t.m2["m2_choices"]
        row = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == self.store.campaign_id,
                    choices.c.id == identity,
                    choices.c.actor_id == str(viewer.user_id),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This signature decision belongs to its original controller.")
        action = self.game.action(c, row["action_id"])
        if action["scene_id"] != scene:
            raise WorkflowError("Recover the original signature decision and scene.")
        kind = row["kind"]
        if kind in CHOICES:
            state = load_state(c, self.store.campaign_id)
            body = json.loads(row["body_json"])
            if kind in (honey.OFFER, honey.REPLY, honey.REJECTION):
                source = honey._source(self.game, c, state, action)
                valid = bool(source and source == body.get("source"))
            elif kind in (loyalty.WATCH, loyalty.REVEAL):
                source = loyalty._source(self.game, c, state, action)
                valid = bool(source and source == body)
            else:
                proved = training._original(self.game, c, state, action)
                valid = bool(proved and proved[1] == body.get("source"))
            if not valid:
                raise WorkflowError("Recover the original signature participants and result.")
        else:
            root = self.game.action(c, action["parent_id"]) if action["parent_id"] else action
            child = bool(
                action["parent_id"]
                and action["data"]["play"]
                in (
                    "disobey_orders",
                    "flirt",
                    "all_out_assault",
                )
            )
            if not (
                (kind in ORDERS or (child and kind in CHILD_CHOICES))
                and self._signature_order(c, root)
            ):
                raise WorkflowError("Recover the original signature decision and scene.")
        return dict(row), action

    def _signature_order(self, c: Connection, root: dict[str, Any]) -> bool:
        if _conditioning_action(root):
            state = load_state(c, self.store.campaign_id)
            return training._original(self.game, c, state, root) is not None
        orders = t.m2["m2_orders"]
        current = c.scalar(
            sa.select(orders.c.state).where(
                orders.c.campaign_id == self.store.campaign_id,
                orders.c.id == root["data"].get("order_id"),
            )
        )
        if not current:
            return False
        state = load_state(c, self.store.campaign_id)
        return any(
            direct_order_source(
                self.game,
                c,
                state,
                root,
                book=book,
                rule=rule,
                order_state=current,
            )
            for book, rule in DIRECT_BOOKS
        )

    def read(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            native = self.observer._scene(c, scene, viewer)
            state = load_state(c, self.store.campaign_id)
            choices = []
            for item in self.game.pending_choices(c, viewer):
                if item["kind"] not in CHOICES | ORDERS | CHILD_CHOICES:
                    continue
                try:
                    _, action = self._choice(c, viewer, scene, item["id"])
                    data = self.game.decision(viewer, item["id"])
                except WorkflowError:
                    continue
                kind = item["kind"]
                card = {key: data[key] for key in ("id", "kind", "revision")}
                if kind == honey.REPLY:
                    reward = data["body"]
                    card["reward"] = {
                        "label": honey.LABELS[reward["reward"]],
                        "account": reward.get("account"),
                        "tag": reward.get("tag"),
                    }
                if text := data.get("conditioning_text"):
                    card["text"] = text
                if kind in ORDERS:
                    card["text"] = action["data"].get("order_text")
                if kind in (training.FLIRT, training.HUNT, "order_disobey"):
                    card["action_id"] = item["action_id"]
                    card["sheet_revision"] = state.sheets[str(viewer.user_id)].revision
                if kind in CHILD_CHOICES:
                    card["show_form"] = True
                if not _conditioning_action(action) and kind in ORDERS:
                    card["direct_order"] = True
                choices.append(card)
            targets = conditioning_targets(self.game, c, state, native, viewer.user_id)
            lock = self.game.lock(c, native["channel_id"])
            present = [
                [str(uid), state.sheets[str(uid)].callsign]
                for uid in native["participants"]
                if str(uid) in state.sheets
            ]
            direct = (
                present
                if viewer.user_id == state.handler
                and (not lock or lock["state"] == "released")
                and any(
                    active_book(self.game, c, state, book=book, rule=rule)
                    for book, rule in DIRECT_BOOKS
                )
                else []
            )
            try:
                issuer = current_ref(state, viewer.user_id)
            except ValueError:
                issuer = None
            seated = [
                (uid, name)
                for uid, name in present
                if (record := sitting(state, current_ref(state, int(uid))))
                and record.issuer == issuer
            ]
            used = {row["context"] for row in state.facts if row["kind"] == "battle_context_used"}
            hunts = [
                {
                    "id": value.id,
                    "status": value.state,
                    "text": value.declaration.account,
                    "can_confirm": value.state == "proposed"
                    and viewer.user_id == value.adjudicator,
                    "can_roll": value.state == "confirmed" and viewer.user_id == value.owner,
                    "sheet_revision": state.sheets[str(value.owner)].revision
                    if viewer.user_id == value.owner
                    else None,
                    "choice": value.source_choice,
                }
                for value in self._hunt_contexts(c, viewer, scene)
                if value.state in ("proposed", "confirmed") and value.id not in used
            ]
        return {
            "choices": choices,
            "handler": viewer.user_id == state.handler,
            "targets": targets,
            "present": present,
            "seated": seated,
            "direct_targets": direct,
            "hunts": hunts,
            "game_revision": state.revision,
        }

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        revision: int,
        answer: ChoiceAnswer,
    ) -> dict[str, Any]:
        def guard(c: Connection) -> None:
            row, _ = self._choice(c, viewer, scene, identity)
            self.game.scene_unpaused(c, scene)
            if row["kind"] in (training.FLIRT, training.HUNT, "order_disobey"):
                raise WorkflowError("Continue through this original Play's native controls.")

        return self.game.respond(viewer, key, identity, revision, answer, source_authorize=guard)

    def _order_guard(
        self, c: Connection, viewer: GuildViewer, scene: str, key: str, expected: int
    ) -> None:
        self.observer._scene(c, scene, viewer)
        self.game.scene_unpaused(c, scene)
        commands = t.commands
        replay = c.scalar(
            sa.select(commands.c.interaction_key).where(
                commands.c.campaign_id == self.store.campaign_id,
                commands.c.interaction_key == key,
            )
        )
        if replay is None and load_state(c, self.store.campaign_id).revision != expected:
            raise WorkflowError("Refresh the original scene and current Status.")

    def issue(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        expected: int,
        target: int,
        phrase: str | None,
        text: str,
        counterpart: int | None,
        actor: str | None,
    ) -> dict[str, Any]:
        if phrase is not None and phrase not in PHRASE_LABELS:
            raise ValueError("Choose a printed Conditioning Phrase.")
        with self.store.engine.connect() as c:
            channel = int(self.observer._scene(c, scene, viewer)["channel_id"])

        def guard(c: Connection) -> None:
            self._order_guard(c, viewer, scene, key, expected)
            if phrase is None:
                state = load_state(c, self.store.campaign_id)
                if viewer.user_id != state.handler or not any(
                    active_book(self.game, c, state, book=book, rule=rule)
                    for book, rule in DIRECT_BOOKS
                ):
                    raise WorkflowError("Only the original Mistress or Insurgent can issue here.")

        with self.store.source_guard(guard):
            return self.game.issue_order(
                viewer,
                key,
                channel,
                target,
                text,
                conditioning_phrase=phrase,
                phrase_target=counterpart,
                phrase_actor=actor,
            )

    def child(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        revision: int,
        sheet_revision: int,
        account: str,
        heat: int,
        witnessed: bool,
    ) -> dict[str, Any]:
        def source(c: Connection) -> tuple[dict[str, Any], dict[str, Any]]:
            row, parent = self._choice(c, viewer, scene, identity)
            self.game.scene_unpaused(c, scene)
            if row["revision"] != revision or row["kind"] not in (training.FLIRT, "order_disobey"):
                raise WorkflowError("Choose your actual current signature follow-up.")
            return row, parent

        with self.store.engine.connect() as c:
            row, parent = source(c)
        refusal = row["kind"] == "order_disobey"
        if not refusal and witnessed:
            raise ValueError("Choose witness status only for refusal.")
        play = PlayInput(
            play="disobey_orders" if refusal else "flirt",
            order_id=parent["data"]["order_id"] if refusal else None,
            target=None if refusal else int(json.loads(row["body_json"])["target"]),
            parent=parent["id"],
            context=account,
            heat=heat,
            witnessed=witnessed,
            trigger_confirmed=True,
        )

        def guard(c: Connection) -> None:
            source(c)

        with self.store.source_guard(guard):
            return self.game.begin(viewer, key, int(parent["channel_id"]), sheet_revision, play)

    def hunt_preview(self, viewer: GuildViewer, scene: str, choice: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, action = self._choice(c, viewer, scene, choice)
            if row["kind"] != training.HUNT:
                raise WorkflowError("Choose the original Hunt decision.")
        decision = self.game.decision(viewer, choice)
        before = BattleService(self.store).preview(viewer, int(action["channel_id"]))
        actor, target = decision["body"]["actor"], decision["body"]["target"]
        selected = [
            next((x for x in before["actors"] if x["ref"] == ref), None) for ref in (actor, target)
        ]
        if any(x is None for x in selected):
            raise WorkflowError("Recover both original visible bodies for Hunt.")
        return {
            "revision": before["revision"],
            "choice_revision": decision["revision"],
            "channel": int(action["channel_id"]),
            "parent": action["id"],
            "actors": [
                {key: actor[key] for key in ("ref", "name", "sha256", "assets")}
                for actor in selected
                if actor is not None
            ],
        }

    def _hunt_contexts(self, c: Connection, viewer: GuildViewer, scene: str) -> list[Context]:
        self.observer._scene(c, scene, viewer)
        state = load_state(c, self.store.campaign_id)
        current: dict[str, Context] = {}
        for fact in state.facts:
            if fact["kind"] != "battle_context":
                continue
            value = Context.model_validate_json(fact["body"])
            if (
                value.scene == scene
                and value.source_choice
                and viewer.user_id
                in (
                    value.owner,
                    value.adjudicator,
                )
            ):
                current[value.id] = value
        choices = t.m2["m2_choices"]
        actual = (
            set(
                c.scalars(
                    sa.select(choices.c.id).where(
                        choices.c.campaign_id == self.store.campaign_id,
                        choices.c.id.in_({x.source_choice for x in current.values()}),
                        choices.c.kind == training.HUNT,
                    )
                )
            )
            if current
            else set()
        )
        return [value for value in current.values() if value.source_choice in actual]

    def hunt_declare(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        choice: str,
        expected: int,
        source: str,
        target: str,
        account: str,
    ) -> dict[str, Any]:
        before = self.hunt_preview(viewer, scene, choice)
        actor, opponent = before["actors"]
        selected = Declaration(
            play="all_out_assault",
            actor=ActorRef.model_validate(actor["ref"]),
            target=ActorRef.model_validate(opponent["ref"]),
            attacking_asset=source,
            target_asset=target,
            actor_sha256=actor["sha256"],
            target_sha256=opponent["sha256"],
            account=account,
        )

        def guard(c: Connection) -> None:
            self.game.scene_unpaused(c, scene)
            row, _ = self._choice(c, viewer, scene, choice)
            if row["kind"] != training.HUNT:
                raise WorkflowError("Choose the actual Hunt decision.")

        with self.store.source_guard(guard):
            return BattleService(self.store).propose(
                viewer, key, expected, before["channel"], selected, parent=before["parent"]
            )

    def hunt_continue(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        expected: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        def find(c: Connection) -> Context:
            ctx = next((x for x in self._hunt_contexts(c, viewer, scene) if x.id == identity), None)
            if ctx is None:
                raise WorkflowError("Recover the original open Hunt declaration.")
            return ctx

        def guard(c: Connection) -> None:
            self.game.scene_unpaused(c, scene)
            find(c)

        with self.store.engine.connect() as c:
            saved = find(c)
            channel = int(self.observer._scene(c, scene, viewer)["channel_id"])
        with self.store.source_guard(guard):
            if data["action"] == "hunt-confirm":
                return BattleService(self.store).confirm(
                    viewer,
                    key,
                    expected,
                    identity,
                    opening=data["opening"],
                    reach=data["reach"],
                    outside_permission=data["outside_permission"],
                    indirect=data["indirect"],
                    evidence=data["text"],
                )
            declaration = saved.declaration
            return self.game.begin(
                viewer,
                key,
                channel,
                data["sheet_revision"],
                PlayInput(
                    play="all_out_assault",
                    context=declaration.account,
                    heat=data["heat"],
                    target_actor=declaration.target,
                    attacking_asset=declaration.attacking_asset,
                    target_asset=declaration.target_asset,
                    battle_context=saved.id,
                    parent=saved.source_action,
                    trigger_confirmed=True,
                    piloting=data["piloting"],
                ),
            )

    def leave(
        self, viewer: GuildViewer, key: str, scene: str, expected: int, target: int
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            channel = int(self.observer._scene(c, scene, viewer)["channel_id"])

        def guard(c: Connection) -> None:
            self._order_guard(c, viewer, scene, key, expected)

        with self.store.source_guard(guard):
            return training.grant_leave(self.game, viewer, key, channel, target)
