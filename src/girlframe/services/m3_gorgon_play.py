"""Actual no-dice Gorgon scene intents use the existing locks, events and owned choices."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_gorgon_frame_contact as frame_contact
from girlframe.engine import m3_grow_unreal as unreal
from girlframe.engine import m3_growth as growth
from girlframe.engine import m3_hallucinations as hallucinations
from girlframe.engine import m3_incubus_conditioning as incubus
from girlframe.engine import m3_jackdaw as jackdaw
from girlframe.engine import m3_mother_hazard as hazard
from girlframe.engine import m3_mother_sprite as mother_sprite
from girlframe.engine import m3_parasite as parasite
from girlframe.engine import m3_parasite_infection as infection
from girlframe.engine import m3_sentinel_shell as shell
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, ActorView, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_gorgon_type_tags import RULES as TYPE_TAG_RULES
from girlframe.engine.m3_gorgon_type_tags import TYPES as TAG_TYPES
from girlframe.engine.m3_gorgon_type_tags import present as tag_target_present
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_sentinel import RULE as corrupt_rule
from girlframe.engine.m3_sentinel import already_corrupted
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_gorgon_contact import PLAY as contact_play
from girlframe.services.m3_gorgon_contact import PLAYS as contact_plays
from girlframe.services.m3_gorgon_contact import RULE as contact_rule
from girlframe.services.m3_gorgon_contact import eligible as contact_eligible
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULES: dict[str, str] = {
    "attack": "gorgon.gorgon.attack",
    contact_play: contact_rule,
    frame_contact.PLAY: frame_contact.RULE,
    "collateral": "gorgon.gorgon.collateral-damage",
    "warp": "gorgon.gorgon.warp",
    "corrupt": corrupt_rule,
    shell.PLAY: shell.RULE,
    incubus.PLAY: incubus.RULE,
    hazard.PLAY: hazard.RULE,
    shell.RELEASE: shell.RULE,
    unreal.PLAY: unreal.RULE,
    infection.PLAY: infection.RULE,
    "growth_adapt": growth.RULE,
    "growth_regrow": growth.RULE,
    "mother_sprite": mother_sprite.RULE,
    "jackdaw_jam": jackdaw.RULE,
    "jackdaw_catatonia": jackdaw.RULE,
    **dict.fromkeys(hallucinations.PLAYS, hallucinations.RULE),
    **dict.fromkeys(parasite.PLAYS, parasite.RULE),
    **{str(kind): rule for kind, rule in TYPE_TAG_RULES.items()},
}


PRIVATE_PLAYS = (*contact_plays, incubus.PLAY, infection.PLAY, hazard.PLAY)


class GorgonPlayService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _attack_target(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        actor: ActorView,
        target: ActorView,
        bound: tuple[ProfileBinding, ...],
    ) -> None:
        from girlframe.engine.m3_battle import assets
        from girlframe.engine.m3_janus_pandora import require_can_harm
        from girlframe.services.m3_battle import _visible

        if (
            target.ref == actor.ref
            or target.offstage_source
            or not _visible(state, target.ref, actor.controller)
            or not any(
                x.actor == target.ref and x.controller == target.controller for x in cast.roles
            )
        ):
            raise WorkflowError("Use an actual visible original target in this Gorgon's scene")
        require_can_harm(state, actor.ref, target.ref)
        assert state.world is not None
        if target.ref.kind == "external_pilot":
            from girlframe.engine.m3_harpy_defeat import harpy

            if not (
                any(item.id == target.ref.entity for item in state.harpy_states)
                or any(
                    item.id == target.ref.entity and item.kind == "harpy"
                    for item in state.world.pilots
                )
            ):
                raise WorkflowError(
                    "This original external Pilot needs its actual resource and Defeat port"
                )
            harpy(state, target.ref)
        if target.rules in ("girl_frame", "handler_girl") and target.inside_frame is None:
            raise WorkflowError(
                "Record the original body's actual cockpit/occupancy facts before an Attack"
            )
        if target.ref.kind == "gorgon" and any(
            item.id == target.ref.entity and item.gorgon_class == "dormant"
            for item in state.world.gorgons
        ):
            from girlframe.services.m3_gorgon_dormant import awakened_source

            # Check existing provenance. A new attack stages awakening after the lock.
            awakened_source(self.game, c, state, target.ref)
        available = assets(state, target.ref, bound)
        if target.ref.kind in ("gorgon", "external_pilot") and not available:
            raise WorkflowError(
                "This original target needs an actual physically available Asset to pit"
            )
        if target.rules in ("girl_frame", "handler_girl") and not any(
            not item.damaged for item in available
        ):
            raise WorkflowError("This exhausted original needs its actual source consequence first")

    def authorize(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
    ) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        if action is not None:
            approval = self.store.policy.m3_approval
            assert approval is not None
            if action["data"]["gorgon_play"]["registry"] != approval.registry_sha256:
                raise WorkflowError("M3_POLICY_CHANGED: recover the original Gorgon Play approval")
            if viewer.user_id not in (
                action["data"].get("private_audience") or action["data"]["participants"]
            ):
                raise WorkflowError("Only an original source-table human owns this response")
            gm, appointment = MedicalService(self.store)._handler(c)
            meta = action["data"]["gorgon_play"]
            if (gm, appointment) != (meta["procedural_gm"], meta["appointment"]):
                raise WorkflowError("Recover the original Gorgon adjudicator appointment")
            self.source(c, action)

    def preview(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        from girlframe.engine.m3_janus_pandora import vicious
        from girlframe.services.m3_battle import _cast, _visible
        from girlframe.services.m3_hallucinations import daily_case, next_day
        from girlframe.services.m3_hallucinations import eligible as isolated

        with self.store.engine.connect() as c:
            self.authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            bound = profiles(c, self.store.campaign_id)
            rows = []
            visible: dict[str, ActorView] = {}
            owned_gorgons: set[ActorRef] = set()
            can_corrupt = False
            can_grow: dict[str, list[str]] = {}
            can_birth: list[str] = []
            can_jam: list[str] = []
            for role in cast.roles:
                actual = resolve(state, role.actor, bound, require_current_profile=False)
                if not _visible(state, role.actor, viewer.user_id):
                    continue
                visible[role.actor.token] = actual
                owned = actual.controller == role.controller == viewer.user_id and not (
                    role.actor.kind == "gorgon"
                    and infection.inhabits_original_body(state, role.actor)
                )
                if (
                    owned
                    and role.actor.kind == "gorgon"
                    and actual.cell is not None
                    and state.world
                ):
                    body = next(x for x in state.world.gorgons if x.id == role.actor.entity)
                    if body.alive and "jackdaw" in body.types and not actual.offstage_source:
                        can_jam.append(role.actor.token)
                    if body.alive and "growth" in body.types and not actual.offstage_source:
                        can_grow[role.actor.token] = [
                            k
                            for k, available in (
                                ("growth_adapt", not body.exposed and bool(body.assets)),
                                ("growth_regrow", any(x.damaged for x in body.assets)),
                            )
                            if available
                        ]
                    if (
                        body.alive
                        and "mother" in body.types
                        and not actual.offstage_source
                        and any(not x.damaged for x in body.assets)
                    ):
                        can_birth.append(role.actor.token)
                if (
                    owned
                    and role.actor.kind == "gorgon"
                    and actual.cell is not None
                    and not actual.offstage_source
                    and state.world is not None
                    and not already_corrupted(state.world, actual.cell)
                    and any(
                        x.id == role.actor.entity and "sentinel" in x.types
                        for x in state.world.gorgons
                    )
                ):
                    can_corrupt = True
                if owned and role.actor.kind == "gorgon":
                    owned_gorgons.add(role.actor)
                rows.append(
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        token=role.actor.token,
                        label=actual.label,
                        source_sha256=actual.source_sha256,
                        owned=owned,
                        assets=[asset.model_dump(mode="json") for asset in actual.assets]
                        if owned and role.actor.kind == "gorgon"
                        else [],
                    )
                )
            typed_targets: dict[str, dict[str, list[str]]] = {}
            attack_targets: dict[str, dict[str, str]] = {}
            parasite_choices: dict[str, dict[str, list[str]]] = {}
            exposure_days: dict[str, dict[str, int]] = {}
            conditioning_tags: dict[str, dict[str, list[tuple[str, str]]]] = {}
            shed_assets: dict[str, tuple[str, ...]] = {}
            hazard_tags: dict[str, dict[str, list[tuple[str, str]]]] = {}
            if state.world is not None:
                for actor in state.world.gorgons:
                    token = ActorRef(kind="gorgon", entity=actor.id).token
                    caster = visible.get(token)
                    if caster is None or caster.ref not in owned_gorgons:
                        continue
                    if (
                        not caster.offstage_source
                        and caster.assets
                        and (actor.gorgon_class != "benevolent" or vicious(state, caster.ref))
                    ):
                        valid = {}
                        for target in visible.values():
                            try:
                                self._attack_target(c, state, cast, caster, target, bound)
                            except (ValueError, WorkflowError):
                                continue
                            valid[target.ref.token] = (
                                "same_cell"
                                if caster.cell is not None and caster.cell == target.cell
                                else "requires_judge"
                            )
                        if valid:
                            attack_targets[token] = valid
                    if actor.alive and "parasite" in actor.types and not caster.offstage_source:
                        if parasite.active(state, caster.ref):
                            parasite_choices[token] = {"parasite_detach": []}
                        else:
                            hosts = [
                                host.ref.token
                                for host in visible.values()
                                if parasite.present(state, caster, host)
                            ]
                            if hosts:
                                parasite_choices[token] = {"parasite_hitch": hosts}
                    options: dict[str, list[str]] = {
                        kind: [
                            target.ref.token
                            for target in visible.values()
                            if target.ref != caster.ref and tag_target_present(kind, caster, target)
                        ]
                        for kind, gorgon_type in TAG_TYPES.items()
                        if gorgon_type in actor.types
                        and (kind != "doppleganger_bond" or actor.revealed)
                    }
                    if "jackdaw" in actor.types:
                        options["jackdaw_hallucinations"] = [
                            girl.ref.token
                            for girl in visible.values()
                            if isolated(c, self.store.campaign_id, state, caster.ref, girl, cast.id)
                        ]
                        days = {
                            girl.ref.token: next_day(state, case)
                            for girl in visible.values()
                            if (
                                case := daily_case(
                                    c, self.store.campaign_id, state, caster.ref, girl, cast.id
                                )
                            )
                            is not None
                        }
                        exposure_days[token] = days
                        options["jackdaw_hallucinations_day"] = list(days)
                    options[contact_play] = [
                        girl.ref.token
                        for girl in visible.values()
                        if contact_eligible(state, caster, girl)
                    ]
                    options[frame_contact.PLAY] = [
                        girl.ref.token
                        for girl in visible.values()
                        if contact_eligible(state, caster, girl, in_frame=True)
                    ]
                    if (
                        actor.alive
                        and "sentinel" in actor.types
                        and not shell.shell_intact(actor)
                        and not any(x.source == caster.ref for x in shell.active(state))
                    ):
                        options[shell.PLAY] = [
                            target.token
                            for target in shell.nearest(caster, tuple(visible.values()))
                        ]
                    options[shell.RELEASE] = [
                        x.girl.token
                        for x in shell.active(state)
                        if x.source == caster.ref and x.scene == cast.id and x.girl.token in visible
                    ]
                    if actor.alive and "incubus" in actor.types:
                        known = {
                            girl.ref.token: [(x.id, x.label) for x in tags]
                            for girl in visible.values()
                            if (tags := incubus.available(state, caster, girl))
                        }
                        conditioning_tags[token] = known
                        options[incubus.PLAY] = list(known)
                    if actor.alive and "mother" in actor.types:
                        exposures = {
                            girl.ref.token: [(x.id, x.label) for x in tags]
                            for girl in visible.values()
                            if (tags := hazard.available(state, caster, girl))
                        }
                        hazard_tags[token] = exposures
                        options[hazard.PLAY] = list(exposures)
                    if actor.alive and "growth" in actor.types and unreal.available_assets(actor):
                        shed_assets[token] = unreal.available_assets(actor)
                        options[unreal.PLAY] = [
                            girl.ref.token
                            for girl in visible.values()
                            if unreal.original_target(caster, girl)
                        ]
                    if actor.alive and "parasite" in actor.types:
                        # Do not use other bodies' actual corruption to discover targets.
                        options[infection.PLAY] = [
                            girl.ref.token
                            for girl in visible.values()
                            if infection.reachable(state, caster, girl)
                        ]
                    typed_targets[token] = {
                        kind: targets for kind, targets in options.items() if targets
                    }
            access = Access(self.store)
            assert access.registry is not None
            plays = []
            for kind, identity in RULES.items():
                if kind == "attack" and not attack_targets:
                    continue
                if kind == "corrupt" and not can_corrupt:
                    continue
                if (
                    kind in TAG_TYPES
                    or kind in hallucinations.PLAYS
                    or kind in contact_plays
                    or kind
                    in (
                        shell.PLAY,
                        shell.RELEASE,
                        incubus.PLAY,
                        unreal.PLAY,
                        infection.PLAY,
                        hazard.PLAY,
                    )
                ) and not any(kind in x for x in typed_targets.values()):
                    continue
                if kind in parasite.PLAYS and not any(kind in x for x in parasite_choices.values()):
                    continue
                if kind in growth.KINDS and not any(kind in x for x in can_grow.values()):
                    continue
                if kind == "mother_sprite" and not can_birth:
                    continue
                if kind in jackdaw.EFFECTS and not can_jam:
                    continue
                try:
                    access.registry.require_available(identity)
                except ValueError:
                    continue
                plays.append(kind)
            return dict(
                revision=state.revision,
                channel=channel,
                cast_revision=cast.revision,
                actors=rows,
                plays=plays,
                typed_targets=typed_targets,
                attack_targets=attack_targets if "attack" in plays else {},
                growth=can_grow,
                sprite_birth=can_birth,
                jam=can_jam,
                parasite=parasite_choices,
                exposure_days=exposure_days,
                conditioning_tags=conditioning_tags,
                hazard_tags=hazard_tags,
                shed_assets=shed_assets,
            )

    def begin(
        self, viewer: GuildViewer, key: str, channel: int, expected: int, declaration: Declaration
    ) -> dict[str, Any]:
        declaration = Declaration.model_validate_json(declaration.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_battle import _cast, _scene_judge, _visible
            from girlframe.services.m3_hallucinations import daily_case, next_day
            from girlframe.services.m3_hallucinations import eligible as isolated
            from girlframe.services.m3_scene_requisitions import guard

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected:
                raise WorkflowError(
                    "STALE_GORGON_PLAY: refresh the actual scene and declared Assets"
                )
            access = Access(self.store)
            assert access.registry is not None
            access.registry.require_available(RULES[declaration.kind])
            cast = _cast(self.game, c, state, channel)
            bound = profiles(c, self.store.campaign_id)
            actual = resolve(state, declaration.actor, bound, require_current_profile=False)
            guard(c, self.store, cast.id, declaration.actor)
            if (
                actual.controller != viewer.user_id
                or actual.source_sha256 != declaration.actor_sha256
                or actual.offstage_source
            ):
                raise WorkflowError(
                    "Use the actual owned present Gorgon and unchanged physical resources"
                )
            assert state.world is not None
            gorgon = next(
                item for item in state.world.gorgons if item.id == declaration.actor.entity
            )
            from girlframe.engine.m3_janus_pandora import require_can_harm, vicious

            if infection.inhabits_original_body(state, actual.ref):
                raise WorkflowError(
                    "The original Parasite is folded inside its host until excision"
                )
            if declaration.kind in parasite.PLAYS:
                riding = parasite.active(state, actual.ref) is not None
                if (
                    not gorgon.alive
                    or "parasite" not in gorgon.types
                    or riding != (declaration.kind == "parasite_detach")
                ):
                    raise WorkflowError(
                        "Use the original Parasite with the matching current host state"
                    )
            if declaration.kind == "corrupt" and (
                "sentinel" not in gorgon.types
                or actual.cell is None
                or already_corrupted(state.world, actual.cell)
            ):
                raise WorkflowError("Use the actual Sentinel standing in a clear map square")
            if declaration.kind in growth.KINDS:
                if actual.cell is None:
                    raise WorkflowError("Use the actual original Growth's established map square")
                if declaration.adaptation is not None:
                    growth.adapt(gorgon, declaration.adaptation, "preview")
                if declaration.regrowth is not None:
                    growth.regrow(gorgon, declaration.regrowth, "preview")
            if declaration.birth is not None:
                if actual.cell is None:
                    raise WorkflowError("Use this actual Mother's established map square")
                mother_sprite.check(gorgon, declaration.birth)
            if declaration.interference is not None:
                jackdaw.check(state, declaration.actor, actual.cell, declaration.interference)
                if declaration.kind == "jackdaw_catatonia":
                    from girlframe.services.m3_jackdaw import targets

                    if not targets(state, cast, bound, declaration.interference):
                        raise WorkflowError("An actual non-Pilot must be present within this range")

            if (
                gorgon.gorgon_class == "benevolent"
                and not vicious(state, declaration.actor)
                and declaration.kind in ("attack", "collateral")
            ):
                raise WorkflowError(
                    "A Benevolent Gorgon will not Attack or cause Collateral Damage"
                )
            if declaration.target is not None and declaration.kind != "attack":
                require_can_harm(state, declaration.actor, declaration.target)
            if not any(
                role.actor == actual.ref and role.controller == viewer.user_id
                for role in cast.roles
            ):
                raise WorkflowError("Join this actual Gorgon to the original source scene")
            if not set(declaration.assets) <= {asset.id for asset in actual.assets}:
                raise WorkflowError("Declare actual currently owned Gorgon Assets")
            target_view = None
            if declaration.target is not None:
                target = resolve(state, declaration.target, bound, require_current_profile=False)
                target_view = target
                if (
                    target.source_sha256 != declaration.target_sha256
                    or target.offstage_source
                    or not any(role.actor == target.ref for role in cast.roles)
                ):
                    raise WorkflowError(
                        "Use the actual present original target and source resources"
                    )
                if declaration.kind == "jackdaw_hallucinations" and not isolated(
                    c, self.store.campaign_id, state, actual.ref, target, cast.id
                ):
                    raise WorkflowError("The actual Girl must be Isolated by this original Jackdaw")
                if declaration.day is not None:
                    case = daily_case(c, self.store.campaign_id, state, actual.ref, target, cast.id)
                    if case is None or declaration.day != next_day(state, case):
                        raise WorkflowError(
                            "Use the next fictional day with the original Girl still in range"
                        )
                if declaration.kind == unreal.PLAY and (
                    "growth" not in gorgon.types
                    or declaration.shed not in unreal.available_assets(gorgon)
                    or not unreal.original_target(actual, target)
                ):
                    raise WorkflowError("Use an actual Growth Asset and an actual reachable Girl")
                if declaration.kind == infection.PLAY and (
                    "parasite" not in gorgon.types or not infection.reachable(state, actual, target)
                ):
                    raise WorkflowError("Use the actual local Parasite and original Girl")
                if declaration.kind == hazard.PLAY and not any(
                    x.id == declaration.tag for x in hazard.available(state, actual, target)
                ):
                    raise WorkflowError("Choose one actual unmarked Tag known to this Mother")
                if declaration.kind == incubus.PLAY and not any(
                    x.id == declaration.tag for x in incubus.available(state, actual, target)
                ):
                    raise WorkflowError("Choose one actual unmarked Tag this Incubus gave the Girl")
                if declaration.kind == shell.PLAY:
                    present = tuple(
                        resolve(state, role.actor, bound, require_current_profile=False)
                        for role in cast.roles
                        if role.actor.kind == "pilot"
                    )
                    if (
                        "sentinel" not in gorgon.types
                        or any(x.source == actual.ref for x in shell.active(state))
                        or shell.shell_intact(gorgon)
                        or target.ref not in shell.nearest(actual, present)
                    ):
                        raise WorkflowError(
                            "Choose the closest original Girl to this actual Sentinel"
                        )
                if declaration.kind == shell.RELEASE and not any(
                    x.source == actual.ref and x.girl == target.ref and x.scene == cast.id
                    for x in shell.active(state)
                ):
                    raise WorkflowError(
                        "Choose the actual Sentinel's original captive in this scene"
                    )
                if declaration.kind in contact_plays and not contact_eligible(
                    state, actual, target, in_frame=declaration.kind == frame_contact.PLAY
                ):
                    raise WorkflowError("Use the free original Girl in the actual cockpit context")
                if declaration.kind == "parasite_hitch" and (
                    not _visible(state, target.ref, viewer.user_id)
                    or not parasite.present(state, actual, target)
                ):
                    raise WorkflowError("Choose an actual living ordinary NPC in your square")
                if declaration.kind in (
                    "incubus_inflict",
                    "mother_mutation",
                    "doppleganger_bond",
                ) and (
                    TAG_TYPES[declaration.kind] not in gorgon.types
                    or not tag_target_present(declaration.kind, actual, target)
                    or declaration.kind == "doppleganger_bond"
                    and not gorgon.revealed
                ):
                    raise WorkflowError(
                        "Use a real body in this revealed type's actual local reach"
                    )
            if declaration.kind == "attack" and target_view is not None:
                self._attack_target(c, state, cast, actual, target_view, bound)
            from girlframe.services.m3_gorgon_dormant import require_clear

            require_clear(self.game, c, declaration.actor)
            if self.game.pending_actions(c):
                raise WorkflowError("SCENE_BUSY: finish or recover the original held Play first")
            lock = self.game.lock(c, channel)
            if lock is not None and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: restore the existing scene lock first")
            judge, judge_human, judge_source = _scene_judge(self.game, c, state, cast)
            gm, appointment = MedicalService(self.store)._handler(c)
            identity, event = str(uuid4()), str(uuid4())
            participants = sorted(
                {role.controller for role in cast.roles}
                | ({cast.facilitator} if cast.facilitator else set())
            )
            approval = self.store.policy.m3_approval
            assert approval is not None
            reach_required = (
                actual.cell is None
                or target_view is not None
                and target_view.cell != actual.cell
                and declaration.kind not in hallucinations.PLAYS
                or declaration.interference is not None
                and len(declaration.interference.cells) > 1
            )
            meta: dict[str, Any] = dict(
                declaration=declaration.model_dump(mode="json"),
                actor=declaration.actor.model_dump(mode="json"),
                target=declaration.target.model_dump(mode="json") if declaration.target else None,
                kind=declaration.kind,
                assets=list(declaration.assets),
                controller=viewer.user_id,
                cast=cast.model_dump(mode="json"),
                cast_sha256=fingerprint(cast),
                judge=judge_human,
                judge_actor=judge.model_dump(mode="json") if judge else None,
                adjudicator=judge.model_dump(mode="json") if judge else None,
                judge_source=judge_source,
                procedural_gm=gm,
                appointment=appointment,
                registry=approval.registry_sha256,
                source_event=event,
                started=False,
                followups=[],
                phase="confirmed",
                capability_required=any(
                    asset.damaged for asset in actual.assets if asset.id in declaration.assets
                )
                or reach_required,
                capability_approved=False,
                reach_required=reach_required,
            )
            handler = active_handler(state)
            data = dict(
                gorgon_play=meta,
                play="gorgon_" + declaration.kind,
                context=declaration.account,
                handler=gm,
                participants=participants,
                character_ids={
                    role.actor.entity: role.actor.incarnation
                    for role in cast.roles
                    if role.actor.kind == "pilot"
                },
                receipt=None,
                modifiers=[],
                result={},
                choices={},
                m3_shared=dict(registry=approval.registry_sha256),
                tag_context=dict(
                    actor=meta["actor"],
                    handler=handler.model_dump(mode="json") if handler else None,
                    gm_controller=gm,
                    table=participants,
                    cast=meta["cast"],
                    cast_sha256=meta["cast_sha256"],
                ),
            )
            if declaration.kind in PRIVATE_PLAYS and target_view is not None:
                audience = sorted({viewer.user_id, target_view.controller, gm})
                meta["private_audience"] = data["private_audience"] = audience
            state.facts.append(
                dict(
                    kind="gorgon_play_intent",
                    action=identity,
                    event=event,
                    body=json.dumps(meta, sort_keys=True),
                )
            )
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(viewer.user_id),
                    channel_id=str(channel),
                    scene_id=cast.id,
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data, sort_keys=True),
                )
            )
            values = dict(
                action_id=identity,
                state="acquiring",
                body_json="{}",
                lease_until=0,
                claim_token=None,
            )
            locks = t.m2["m2_locks"]
            if lock:
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id,
                        locks.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    locks.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.gorgon_play_confirmed",
                state,
                event_id=event,
                action_id=identity,
                play_kind=declaration.kind,
            )
            return dict(action_id=identity, state="acquiring")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.gorgon_play_confirmed",
                dict(
                    channel=channel,
                    expected=expected,
                    declaration=declaration.model_dump(mode="json"),
                ),
                operation,
                auto_audit=False,
                authorize=lambda c: self.authorize(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid source state; refresh the actual Gorgon declaration"
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def source(self, c: Connection, action: dict[str, Any]) -> dict[str, Any]:
        meta = action["data"]["gorgon_play"]
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == meta["source_event"],
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        fact = (
            next(
                (
                    item
                    for item in proof.facts
                    if item.get("kind") == "gorgon_play_intent"
                    and item.get("action") == action["id"]
                    and item.get("event") == meta["source_event"]
                ),
                None,
            )
            if proof
            else None
        )
        original = json.loads(fact["body"]) if fact else None
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == meta["source_event"],
            )
        ).first()
        keys = (
            "declaration",
            "actor",
            "target",
            "kind",
            "assets",
            "controller",
            "cast",
            "cast_sha256",
            "judge",
            "judge_actor",
            "adjudicator",
            "judge_source",
            "procedural_gm",
            "appointment",
            "registry",
            "source_event",
            "capability_required",
            "reach_required",
            "private_audience",
        )
        if (
            not isinstance(original, dict)
            or event is None
            or event.kind != "m3.gorgon_play_confirmed"
            or event.actor_id != str(meta["controller"])
            or json.loads(event.payload_json).get("action_id") != action["id"]
            or any(meta.get(key) != original.get(key) for key in keys)
        ):
            raise WorkflowError(
                "SOURCE_GORGON_PLAY_MISSING: recover the actual immutable original intent"
            )
        source_cast = SceneCast.model_validate_json(json.dumps(original["cast"]))
        source_table = sorted(
            {role.controller for role in source_cast.roles}
            | ({source_cast.facilitator} if source_cast.facilitator else set())
        )
        if (
            action["scene_id"] != source_cast.id
            or int(action["channel_id"]) != source_cast.channel
            or action["actor_id"] != str(original["controller"])
            or action["data"]["participants"] != source_table
            or action["data"].get("private_audience") != original.get("private_audience")
            or action["data"]["character_ids"]
            != {
                role.actor.entity: role.actor.incarnation
                for role in source_cast.roles
                if role.actor.kind == "pilot"
            }
        ):
            raise WorkflowError("The original Gorgon body, scene or human table changed")
        return dict(original)

    def advance(
        self, c: Connection, viewer: GuildViewer, key: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        from girlframe.services import m3_gorgon_runtime
        from girlframe.services.m3_battle import _cast

        self.authorize(c, viewer, action)
        self.game.unpaused(c)
        meta = action["data"]["gorgon_play"]
        if viewer.user_id != meta["controller"] or meta["started"]:
            raise WorkflowError(
                "Only the original actual Gorgon controller advances its unstarted Play"
            )
        state = load_state(c, self.store.campaign_id)
        cast = _cast(self.game, c, state, int(action["channel_id"]))
        if fingerprint(cast) != meta["cast_sha256"]:
            raise WorkflowError("STALE_GORGON_CAST: recover the actual original scene roles")
        lock = self.game.lock(c, action["channel_id"])
        if not lock or lock["state"] != "held":
            raise WorkflowError("LOCK_NOT_ACKNOWLEDGED: no Gorgon effect has occurred")
        declaration = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        for ref, expected in (
            (declaration.actor, declaration.actor_sha256),
            (declaration.target, declaration.target_sha256),
        ):
            if ref is not None:
                current_actor = resolve(
                    state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
                )
                if (
                    current_actor.source_sha256 != expected
                    or ref == declaration.actor
                    and current_actor.controller != meta["controller"]
                ):
                    raise WorkflowError(
                        "STALE_GORGON_RESOURCES: refresh the original unstarted declaration"
                    )
        event = str(uuid4())
        meta.update(started=True, phase="active", advance_event=event)
        action["state"] = "awaiting_choices"
        action["data"]["response_event"] = event
        if meta["capability_required"]:
            self.game.request(c, action, meta["judge"], "gorgon_asset_capability")
            meta["phase"] = "capability_review"
        else:
            m3_gorgon_runtime.start(self.game, c, state, action)
        self.game.save_action(c, action)
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.gorgon_play_advanced",
            state,
            event_id=event,
            action_id=action["id"],
        )
        self.synchronize(c, action, event, viewer, key)
        return dict(action_id=action["id"], receipt=None)

    def apply(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
    ) -> None:
        from girlframe.services import m3_gorgon_runtime

        self.source(c, action)
        if row["kind"] == "gorgon_asset_capability":
            meta = action["data"]["gorgon_play"]
            if (
                int(row["actor_id"]) != meta["judge"]
                or meta["phase"] != "capability_review"
                or answer.flag is None
                or not answer.text.strip()
                or answer.options
                or answer.denied
                or answer.fields
                or answer.number is not None
                or answer.member is not None
            ):
                raise WorkflowError(
                    "The original judge must confirm or deny the actual capability and reach"
                )
            meta.update(
                capability_approved=answer.flag,
                capability_account=answer.text,
                phase="active" if answer.flag else "ineligible",
            )
            if answer.flag:
                m3_gorgon_runtime.start(self.game, c, state, action)
        else:
            m3_gorgon_runtime.apply(self.game, c, state, action, row, answer)

    def decision(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any], row: dict[str, Any]
    ) -> dict[str, Any]:
        from girlframe.services import m3_gorgon_runtime

        self.authorize(c, viewer, action)
        state = load_state(c, self.store.campaign_id)
        return dict(row) | dict(
            body=json.loads(row["body_json"]),
            gorgon_play=True,
            parent=action["id"],
            channel=int(action["channel_id"]),
            detail=dict(kind="capability", account=action["data"]["context"])
            if row["kind"] == "gorgon_asset_capability"
            else m3_gorgon_runtime.projection(self.game, c, state, action, row),
        )

    def synchronize(
        self,
        c: Connection,
        action: dict[str, Any],
        event: str,
        viewer: GuildViewer | None,
        key: str,
    ) -> None:
        from girlframe.services import m3_gorgon_runtime

        current = self.game.action(c, action["id"])
        if current["state"] in ("complete", "aborted"):
            return
        phase = current["data"]["gorgon_play"]["phase"]
        if phase == "capability_review":
            return
        ready = phase == "ineligible" or m3_gorgon_runtime.synchronize(
            self.game, c, current, event, viewer, key
        )
        current = self.game.action(c, action["id"])
        if ready and not self.game.pending(c, current["id"]):
            current["state"] = "complete"
            current["data"]["gorgon_play"]["phase"] = "complete"
            self.game.queue(
                c,
                current,
                "outcome",
                dict(
                    play=current["data"]["play"],
                    callsign="Gorgon",
                    receipt=None,
                    total=None,
                    tier=None,
                ),
            )
            self.game.save_action(c, current)


def complete_damage_work(
    game: GameService,
    c: Connection,
    row: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    source = json.loads(row["body_json"]).get("source_action")
    if source:
        GorgonPlayService(game).synchronize(c, game.action(c, source), event, viewer, key)


def apply_fatal(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
    *,
    allow_sprite: bool = False,
) -> None:
    from girlframe.services import m3_gorgon_runtime

    GorgonPlayService(game).source(c, action)
    m3_gorgon_runtime.apply_fatal(game, c, action, event, viewer, key, allow_sprite=allow_sprite)


def _response(
    game: GameService,
    c: Connection,
    parent: dict[str, Any],
    actor: ActorRef,
) -> dict[str, Any]:
    GorgonPlayService(game).source(c, parent)
    if parent["state"] in ("complete", "aborted"):
        raise WorkflowError("Resume this actual still-held Gorgon response")
    meta = parent["data"]["gorgon_play"]
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    role = next((role for role in cast.roles if role.actor == actor), None)
    if role is None:
        raise WorkflowError("A different role cannot inherit this original response opportunity")
    row = next(
        (
            row
            for row in game.pending(c, parent["id"])
            if row["kind"] == "gorgon_response_play"
            and row["actor_id"] == str(role.controller)
            and json.loads(row["body_json"]).get("actor") == actor.model_dump(mode="json")
            and json.loads(row["body_json"]).get("attacker") == meta["actor"]
        ),
        None,
    )
    if row is None:
        raise WorkflowError("Choose the actual original Girl's pending response Play")
    actions = t.m2["m2_actions"]
    if c.scalar(
        sa.select(actions.c.id).where(
            actions.c.campaign_id == game.store.campaign_id,
            actions.c.parent_id == parent["id"],
            actions.c.state.not_in(("complete", "aborted")),
        )
    ):
        raise WorkflowError("Resume the existing original response before starting another")
    return row


def prepare_response(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    prepared: PlayInput,
    state: GameState,
    channel: int,
) -> dict[str, Any] | None:
    if prepared.parent is None:
        return None
    # Damage Defeat is a separate source-owned child, validated against the
    # original held Battle work by the Defeat adapter.
    if prepared.play == "defeat" and prepared.source_work is not None:
        return None
    parent = game.action(c, prepared.parent)
    source = parent["data"].get("gorgon_play")
    if not source or (
        source["kind"]
        in (
            *hallucinations.PLAYS,
            frame_contact.PLAY,
            shell.PLAY,
            incubus.PLAY,
            unreal.PLAY,
            infection.PLAY,
            hazard.PLAY,
        )
        and prepared.play == "keep_your_head"
        and prepared.source_work is not None
    ):
        return None
    from girlframe.services.m3_battle import _cast

    sheet = state.sheets.get(str(viewer.user_id))
    if sheet is None or sheet.character_id is None:
        raise WorkflowError(
            "Use this original response body's actual role, not another owned character"
        )
    actor = ActorRef(kind="pilot", entity=str(viewer.user_id), incarnation=sheet.character_id)
    row = validate_child(game, c, parent, actor, prepared)
    if int(parent["channel_id"]) != channel:
        raise WorkflowError("Respond in this Gorgon Play's actual original scene")
    cast = _cast(game, c, state, channel)
    if source.get("frame_intervention") and prepared.play not in (
        "engage",
        "all_out_assault",
        "go_for_the_core",
    ):
        raise WorkflowError("The immediate intervention needs its actual combat Play")
    return dict(
        choice=row["id"],
        actor=actor.model_dump(mode="json"),
        attacker=parent["data"]["gorgon_play"]["actor"],
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        private_audience=source.get("private_audience")
        if source.get("frame_intervention") or source["kind"] in (incubus.PLAY, hazard.PLAY)
        else None,
        conditioning_tag=json.loads(row["body_json"]).get("conditioning_tag"),
        table=sorted(
            {role.controller for role in cast.roles}
            | ({cast.facilitator} if cast.facilitator else set())
        ),
    )


def allowed_archived(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> frozenset[tuple[str, str]]:
    from girlframe.services.m3_harpy_defeat import ended_actor_source

    parent, seen = action, set()
    while not parent["data"].get("gorgon_play"):
        if parent["id"] in seen or not parent["parent_id"]:
            raise WorkflowError("Recover the actual original Gorgon response ancestry")
        seen.add(parent["id"])
        parent = game.action(c, parent["parent_id"])
        if parent["scene_id"] != action["scene_id"] or parent["channel_id"] != action["channel_id"]:
            raise WorkflowError("Recover the original Gorgon response scene")
    GorgonPlayService(game).source(c, parent)
    source = SceneCast.model_validate_json(json.dumps(parent["data"]["gorgon_play"]["cast"]))
    return frozenset(
        (role.actor.entity, str(role.actor.incarnation))
        for role in source.roles
        if role.actor.kind == "pilot" and ended_actor_source(game, c, state, role.actor) is not None
    )


def recovery_cast(
    game: GameService, c: Connection, state: GameState, parent: dict[str, Any]
) -> None:
    """Retain each original role; only proved original endings may remove a body."""
    from girlframe.services.m3_battle import _cast
    from girlframe.services.m3_harpy_defeat import ended_actor_source, ended_director_judge

    source = GorgonPlayService(game).source(c, parent)
    original = SceneCast.model_validate_json(json.dumps(source["cast"]))
    current = _cast(game, c, state, int(parent["channel_id"]))
    if fingerprint(current) == fingerprint(original):
        return
    judge = original.adjudicator
    if judge is not None and ended_director_judge(
        game, c, state, original, current, judge, source["judge"]
    ):
        return
    if (
        current.id != original.id
        or current.channel != original.channel
        or not current.open
        or current.revision < original.revision
        or current.facilitator != original.facilitator
        or current.facilitator_source != original.facilitator_source
    ):
        raise WorkflowError("Recover the original Gorgon scene and human facilitator")
    expected = tuple(
        role for role in original.roles if ended_actor_source(game, c, state, role.actor) is None
    )
    adjudicator = (
        None
        if judge is not None and ended_actor_source(game, c, state, judge) is not None
        else judge
    )
    if current.roles != expected or current.adjudicator != adjudicator:
        raise WorkflowError("Only proved original body endings may change this saved scene cast")


def validate_child(
    game: GameService,
    c: Connection,
    parent: dict[str, Any],
    actor: ActorRef,
    prepared: PlayInput,
) -> dict[str, Any]:
    row = _response(game, c, parent, actor)
    if prepared.parent != parent["id"]:
        raise WorkflowError("Use this exact held source parent for the response")
    if parent["data"]["gorgon_play"]["kind"] == hazard.PLAY:
        from girlframe.services.m3_mother_hazard import SUPPORTED_PLAY

        case = hazard.get(load_state(c, game.store.campaign_id), parent["id"])
        if (
            case is None
            or case.completed
            or case.girl != actor
            or case.requested_play != prepared.play
            or prepared.play != SUPPORTED_PLAY
        ):
            raise WorkflowError("Use the actual original Mother's selected supported Play")
    if prepared.play in (
        "engage",
        "all_out_assault",
        "go_for_the_core",
    ) and prepared.target_actor != ActorRef.model_validate(parent["data"]["gorgon_play"]["actor"]):
        raise WorkflowError("This response must address the actual original attacking Gorgon")
    return row


def counter_declaration(
    game: GameService, c: Connection, parent: dict[str, Any], declaration: Any
) -> dict[str, Any]:
    row = _response(game, c, parent, declaration.actor)
    if declaration.target.model_dump(mode="json") != parent["data"]["gorgon_play"]["actor"]:
        raise WorkflowError("Declare this response against the actual original attacking Gorgon")
    return row


def complete_response(
    game: GameService,
    c: Connection,
    child: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.services import m3_gorgon_runtime

    source = child["data"].get("gorgon_counter_source")
    if child["state"] != "complete" or not child.get("parent_id") or source is None:
        raise WorkflowError("Finish the actual original Gorgon response Play first")
    parent = game.action(c, child["parent_id"])
    GorgonPlayService(game).source(c, parent)
    actor = child["data"].get("actor_basic", {}).get("ref")
    if actor is None:
        incarnation = child["data"].get("character_ids", {}).get(child["actor_id"])
        actor = (
            ActorRef(kind="pilot", entity=child["actor_id"], incarnation=incarnation).model_dump(
                mode="json"
            )
            if incarnation
            else None
        )
    if (
        actor != source.get("actor")
        or source.get("attacker") != parent["data"]["gorgon_play"]["actor"]
    ):
        raise WorkflowError(
            "A successor or different body cannot satisfy this original Gorgon response"
        )
    row = next(
        (
            row
            for row in game.pending(c, parent["id"])
            if row["id"] == source.get("choice")
            and row["kind"] == "gorgon_response_play"
            and json.loads(row["body_json"]).get("actor") == actor
        ),
        None,
    )
    if row is None:
        return
    m3_gorgon_runtime.complete_response(game, c, parent, child, event, viewer, key)
    GorgonPlayService(game).synchronize(c, game.action(c, parent["id"]), event, viewer, key)
