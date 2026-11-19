"""Scoped post-roll Gorgon Tags in real opposing battle Plays."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Gorgon, WorldTag
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "core.core.gorgon-tags"
SELECT = "gorgon_tag_selection"
REMOVE = "gorgon_tag_removal"
DISCLOSED = "gorgon_tag_disclosed"


class Disclosure(Model):
    ref: ActorRef
    tag: str
    recipients: tuple[ActorRef, ...]
    scene: str
    event: str
    account: str


def _enabled(game: "GameService") -> bool:
    approval = game.store.policy.m3_approval
    registry = Access(game.store).registry
    return bool(
        approval
        and registry
        and "plays" in approval.subsystems
        and approval.registry_sha256 == digest(registry)
        and registry.entry(RULE).verified
    )


def original(state: GameState, action: dict[str, Any]) -> tuple[ActorRef, Gorgon] | None:
    data = action["data"]
    source = data.get("battle") or data.get("engage")
    if (
        source is None
        or state.world is None
        or data["play"] not in ("engage", "all_out_assault", "go_for_the_core")
    ):
        return None
    actor = ActorRef.model_validate(source["actor"])
    target = ActorRef.model_validate(source["target"])
    if actor.kind != "pilot" or target.kind != "gorgon" or actor.entity != action["actor_id"]:
        return None
    gorgon = next((x for x in state.world.gorgons if x.id == target.entity and x.alive), None)
    return (actor, gorgon) if gorgon else None


def _known(state: GameState, actor: ActorRef, target: Gorgon) -> tuple[WorldTag, ...]:
    originals = {actor.token, actor.model_dump_json()}
    heard = set()
    for fact in state.facts:
        if fact.get("kind") == DISCLOSED:
            disclosure = Disclosure.model_validate_json(fact["body"])
            if disclosure.ref.entity == target.id and actor in disclosure.recipients:
                heard.add(disclosure.tag)
    return tuple(tag for tag in target.tags if tag.giver_entity in originals or tag.id in heard)


def _source(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorRef, Gorgon, int]:
    from girlframe.engine.m3_actors import fingerprint, resolve
    from girlframe.services.m3_battle import _cast

    actual = original(state, action)
    if actual is None:
        raise WorkflowError("Recover the exact original Gorgon and acting Girl")
    actor, target = actual
    ref = ActorRef(kind="gorgon", entity=target.id)
    cast = _cast(game, c, state, int(action["channel_id"]))
    meta = action["data"].get("battle") or action["data"]["engage"]
    if (
        current_ref(state, int(actor.entity)) != actor
        or fingerprint(cast) != meta["cast_sha256"]
        or not any(x.actor == ref for x in cast.roles)
        or not any(x.actor == actor and str(x.controller) == actor.entity for x in cast.roles)
    ):
        raise WorkflowError("Recover the actual original battle cast for this Gorgon Tag roll")
    controller = resolve(state, ref, profiles(c, game.store.campaign_id)).controller
    if controller is None or controller not in action["data"]["participants"]:
        raise WorkflowError("Recover the Gorgon's actual current controller")
    return actor, target, controller


def stage(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> bool:
    data = action["data"]
    if status := data.get("gorgon_tags"):
        return bool(status != "complete")
    actual = original(state, action)
    if actual is None or not _known(state, *actual):
        return False
    if not _enabled(game):
        return False
    actor, _, _ = _source(game, c, state, action)
    data["gorgon_tags"] = "selecting"
    action["state"] = "awaiting_choices"
    game.request(c, action, int(actor.entity), SELECT)
    return True


def _owner(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    kind: str,
    owner: int,
) -> tuple[Gorgon, int, tuple[WorldTag, ...]]:
    if not _enabled(game):
        raise WorkflowError("Gorgon Tags require their original reviewed rules scope")
    actor, target, controller = _source(game, c, state, action)
    if (
        kind == SELECT
        and (owner != int(actor.entity) or action["data"].get("gorgon_tags") != "selecting")
        or kind == REMOVE
        and (owner != controller or action["data"].get("gorgon_tags") != "removing")
    ):
        raise WorkflowError(
            "Only the original acting Girl or Gorgon controller owns their response"
        )
    return target, controller, _known(state, actor, target) if kind == SELECT else target.tags


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    kind: str,
    owner: int,
) -> list[dict[str, str]]:
    _, _, selectable = _owner(game, c, state, action, kind, owner)
    return [dict(id=tag.id, name=tag.label) for tag in selectable]


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    kind: str,
    owner: int,
    answer: ChoiceAnswer,
) -> bool:
    target, controller, selectable = _owner(game, c, state, action, kind, owner)
    allowed = {x.id for x in selectable}
    if (
        answer.fields
        or answer.number is not None
        or answer.flag is not None
        or answer.member is not None
        or not set((*answer.options, *answer.denied)) <= allowed
        or bool(set(answer.options) & set(answer.denied))
    ):
        raise WorkflowError("Use distinct original Gorgon Tags with a supported direction")
    data = action["data"]
    if kind == SELECT:
        if bool(answer.options or answer.denied) != bool(answer.text.strip()):
            raise WorkflowError("Record why the actual Gorgon Tags apply, or leave them unused")
        for amount, picks in ((1, answer.options), (-1, answer.denied)):
            for tag in picks:
                data["modifiers"].append(
                    dict(
                        source="gorgon_tag",
                        actor=owner,
                        tag=tag,
                        target=target.id,
                        amount=amount,
                        text=answer.text.strip(),
                    )
                )
        if len(answer.denied) + len(answer.options) >= 2:
            data["gorgon_tags"] = "removing"
            game.request(c, action, controller, REMOVE)
            return False
    else:
        if answer.denied or answer.text or len(answer.options) > 1:
            raise WorkflowError("The Gorgon may remove exactly one Tag or leave its Tags in place")
        if answer.options:
            assert state.world is not None
            changed = target.model_copy(
                update=dict(tags=tuple(x for x in target.tags if x.id != answer.options[0]))
            )
            state.world = update(
                state.world,
                gorgons=tuple(changed if x.id == target.id else x for x in state.world.gorgons),
            )
            data["gorgon_tag_removed"] = answer.options[0]
    data["gorgon_tags"] = "complete"
    return True


class GorgonTagService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _options(
        self, c: Connection, viewer: GuildViewer, channel: int
    ) -> tuple[GameState, SceneCast, dict[str, Gorgon], dict[str, ActorRef]]:
        from girlframe.engine.m3_actors import resolve
        from girlframe.services.m3_battle import _cast

        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.authorize(c, viewer, "world", director_response=True)
        if not _enabled(self.game):
            raise WorkflowError("Gorgon Tags need their reviewed rules scope")
        state = load_state(c, self.store.campaign_id)
        cast = _cast(self.game, c, state, channel)
        gorgons = (
            {
                x.id: x
                for x in state.world.gorgons
                if x.alive
                and x.tags
                and any(
                    role.actor.kind == "gorgon"
                    and role.actor.entity == x.id
                    and role.controller == viewer.user_id
                    and resolve(state, role.actor, ()).controller == viewer.user_id
                    for role in cast.roles
                )
            }
            if state.world
            else {}
        )
        girls = {
            role.actor.entity: role.actor
            for role in cast.roles
            if role.actor.kind == "pilot" and current_ref(state, role.controller) == role.actor
        }
        return state, cast, gorgons, girls

    def view(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, _, gorgons, girls = self._options(c, viewer, channel)
            return dict(
                revision=state.revision,
                gorgons={
                    key: dict(name=x.name, tags=tuple((t.id, t.label) for t in x.tags))
                    for key, x in gorgons.items()
                },
                girls=tuple((key, state.sheets[key].callsign) for key in girls),
            )

    def disclose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        gorgon: str,
        tag: str,
        recipients: tuple[str, ...],
        account: str,
    ) -> dict[str, Any]:
        if (
            not recipients
            or len(set(recipients)) != len(recipients)
            or not 0 < len(account.strip()) <= 1200
        ):
            raise WorkflowError(
                "Record the actual Tag disclosure to its distinct original witnesses"
            )

        def authorize(c: Connection) -> None:
            self.game.unpaused(c)
            _, _, gorgons, _ = self._options(c, viewer, channel)
            if gorgon not in gorgons:
                raise WorkflowError("Choose the controlled Gorgon's actual Tag")

        def operation(c: Connection) -> dict[str, Any]:
            state, cast, gorgons, girls = self._options(c, viewer, channel)
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError(
                    "STALE_GORGON_TAG: reopen this actual scene after pending Plays"
                )
            target = gorgons.get(gorgon)
            if (
                target is None
                or not any(x.id == tag for x in target.tags)
                or not set(recipients) <= girls.keys()
            ):
                raise WorkflowError(
                    "Choose the controlled Gorgon's actual Tag and current original witnesses"
                )
            event = str(uuid4())
            record = Disclosure(
                ref=ActorRef(kind="gorgon", entity=gorgon),
                tag=tag,
                recipients=tuple(girls[x] for x in recipients),
                scene=cast.id,
                event=event,
                account=account.strip(),
            )
            state.facts.append(dict(kind=DISCLOSED, id=event, body=record.model_dump_json()))
            self.game.event(
                c, viewer.user_id, key, "m3.gorgon_tag_disclosed", state, event_id=event
            )
            return dict(event=event, recipients=len(recipients))

        return self.store._write(
            viewer,
            key,
            "m3.gorgon_tag_disclosed",
            dict(
                channel=channel,
                expected=expected,
                gorgon=gorgon,
                tag=tag,
                recipients=recipients,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
