"""The actual Gorgon response's combat declaration and assigned adjudication."""

from battlefield import Battlefield

from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle import resource_sha
from girlframe.engine.m3_battle_state import Context, Declaration
from girlframe.engine.m3_mother_hazard import PLAY as HAZARD
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import BattleService
from girlframe.services.onboarding import WorkflowError

RESPONSE = "gorgon_response_play"
PLAYS = (("all_out_assault", "All-Out Assault"), ("go_for_the_core", "Go for the Core"))


class GorgonCounterWork:
    def __init__(self, game):
        self.game, self.store = game, game.store
        self.battle = BattleService(self.store)

    def declaration(self, viewer, identity):
        choice = self.game.decision(viewer, identity)
        if choice["kind"] != RESPONSE or choice["state"] != "pending":
            raise WorkflowError("Open your pending response to the original Gorgon.")
        actor = ActorRef.model_validate(choice["body"]["actor"])
        target = ActorRef.model_validate(choice["body"]["attacker"])
        preview = self.battle.preview(viewer, int(choice["channel"]))
        with self.store.engine.connect() as c:
            parent = self.game.action(c, choice["parent"])
            source = parent["data"]["gorgon_play"]
            state = load_state(c, self.store.campaign_id)
            bound = profiles(c, self.store.campaign_id)
            view = resolve(state, actor, bound, require_current_profile=False)
            if state.revision != preview["revision"] or view.controller != viewer.user_id:
                raise WorkflowError("Recover the original Gorgon response.")
            plays = {}
            if (
                not source.get("frame_intervention")
                and source["kind"] != HAZARD
                and view.piloting
                and (
                    actor.kind == "pilot" or actor.kind == "external_pilot" and view.girl == "harpy"
                )
            ):
                for play, label in PLAYS:
                    options = Battlefield.declared_options(
                        state,
                        bound,
                        preview,
                        play,
                        actor_token=actor.token,
                    )
                    if options is None:
                        continue
                    actual = next(
                        (row for row in options["targets"] if row["id"] == target.token), None
                    )
                    if actual is not None:
                        plays[play] = (label, options["attacking_assets"], actual["assets"])
            return dict(
                revision=state.revision,
                actor=actor,
                target=target,
                parent=choice["parent"],
                channel=int(choice["channel"]),
                plays=plays,
                actor_sha256=resource_sha(state, actor, bound),
                target_sha256=resource_sha(state, target, bound),
            )

    def context(self, viewer, identity):
        result = self.battle.context(viewer, identity)
        context = Context.model_validate(result["context"])
        if not context.source_action:
            raise WorkflowError("Choose a declaration attached to the original Gorgon.")
        with self.store.engine.connect() as c:
            if not self.game.action(c, context.source_action)["data"].get("gorgon_play"):
                raise WorkflowError("Choose a declaration attached to the original Gorgon.")
            state = load_state(c, self.store.campaign_id)
            actor = resolve(
                state,
                context.declaration.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
        return result | {"decision": context, "heat": actor.heat, "actor": actor}

    def start(self, viewer, key, identity, data, heat):
        context = data["decision"]
        move = context.declaration
        if not (context.owner == viewer.user_id and context.opening and context.reach):
            raise WorkflowError("The assigned judge must approve opening and reach.")
        prepared = PlayInput(
            play=move.play,
            heat=heat,
            context=move.account,
            trigger_confirmed=True,
            parent=context.source_action,
            target_actor=move.target,
            piloting=True,
            attacking_asset=move.attacking_asset,
            target_asset=move.target_asset,
            battle_context=identity,
        )
        channel = int(data["channel"])
        if move.actor.kind == "pilot":
            return self.game.begin(
                viewer, key, channel, self.game.sheet(viewer)["revision"], prepared
            )
        service = ActorPlayService(self.game)
        menu = service.preview(viewer, channel, move.actor)
        judge = menu["adjudicator"]["ref"]
        return service.begin(
            viewer,
            key,
            channel,
            move.actor,
            data["actor"].source_sha256,
            ActorRef.model_validate(judge) if judge else None,
            menu["cast_revision"],
            prepared,
        )

    def file(self, viewer, key, data, verb, account, weapon, asset):
        return self.battle.propose(
            viewer,
            key,
            data["revision"],
            data["channel"],
            Declaration(
                play=verb,
                actor=data["actor"],
                target=data["target"],
                attacking_asset=weapon,
                target_asset=asset,
                actor_sha256=data["actor_sha256"],
                target_sha256=data["target_sha256"],
                account=account,
            ),
            parent=data["parent"],
        )
