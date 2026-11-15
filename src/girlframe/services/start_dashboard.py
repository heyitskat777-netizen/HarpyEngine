"""Owner-scoped, read-only setup progress derived from existing saved authorities."""

from typing import Any, Literal

import sqlalchemy as sa

from girlframe.database import tables as t
from girlframe.engine.creation_review import ReviewIssue
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.inbox import InboxService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore
from girlframe.services.provisioning import TEMPLATE
from girlframe.services.read_only_bot import GuildViewer

Route = Literal[
    "join",
    "profile",
    "build",
    "bond",
    "requests",
    "status",
    "creation_rules",
    "handler",
    "review",
    "activate",
    "ready",
    "server",
    "create",
    "court",
    "mentor_callsign",
    "pair_assets",
    "history",
    "girl_setup",
    "frame_details",
]


def _step(key: str, label: str, status: str, route: Route) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "route": route}


def _route(issue: ReviewIssue) -> Route:
    """Map the existing readiness authority to an existing editor, never revalidate it."""
    routes: dict[str, Route] = {
        "handler": "handler",
        "status": "status",
        "princess_ace": "status",
        "initial_conditions": "creation_rules",
        "starting_resources": "creation_rules",
        "starting_requisition": "creation_rules",
        "starting_bond": "bond",
        "additional_starting_bond": "bond",
        "princess_peer": "requests",
        "princess_handler": "requests",
        "handler_investor": "requests",
        "cadre_history": "history",
        "cadre_discussion": "history",
        "maxims": "girl_setup",
        "own_standard": "girl_setup",
        "npc_investors": "girl_setup",
    }
    return routes.get(issue.code, "build")


class StartDashboardService:
    """Readiness is guidance, not authorization to run any returned route.

    Actual forms continue to recheck ownership, revisions, consent and release
    scope. Looking at this projection never joins, provisions, saves or activates.
    """

    def __init__(self, store: OnboardingStore):
        self.store = store

    def snapshot(self, viewer: GuildViewer) -> dict[str, Any]:
        self.store.guild_member(viewer)
        handler = HandlerService(self.store)
        admin = viewer.is_administrator and self.store.policy.allow_guild_administrators
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            bound = self.store._binding_matches(connection)
            initialized = bool(
                connection.scalar(
                    sa.select(t.campaigns.c.initialized).where(
                        t.campaigns.c.id == self.store.campaign_id
                    )
                )
            )
            membership = connection.execute(
                sa.select(t.members.c.active).where(
                    t.members.c.campaign_id == self.store.campaign_id,
                    t.members.c.user_id == str(viewer.user_id),
                )
            ).first()
            joined = membership is not None and bool(membership.active)
            inactive = membership is not None and not bool(membership.active)
            _, setup = handler.current(connection)
            handler_active = setup.handler_id is not None and handler._member(
                connection, setup.handler_id
            )
            is_handler = joined and setup.handler_id == viewer.user_id
            resources_ready = int(
                connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(t.resources)
                    .where(
                        t.resources.c.campaign_id == self.store.campaign_id,
                        t.resources.c.key.in_([x.key for x in TEMPLATE]),
                        t.resources.c.state == "ready",
                        t.resources.c.discord_id.is_not(None),
                    )
                )
                or 0
            )
            campaign: dict[str, Any] = {
                "bound": bound,
                "initialized": initialized,
                "handler_id": setup.handler_id if joined or admin else None,
                "handler_active": handler_active,
                "status_current": False,
                "rulings_ready": False,
                "pilot_count": 0,
                "resources_ready": resources_ready,
                "resources_total": len(TEMPLATE),
                "steps": [],
            }
            character: dict[str, Any] = {
                "exists": False,
                "callsign": None,
                "girl": None,
                "frame": None,
                "creation_revision": 0,
                "saved_current": False,
                "review_ready": False,
                "release_enabled": False,
                "next_route": "join",
                "issues": [],
                "steps": [],
                "requests": {"actionable": 0, "waiting": 0, "stale": 0},
            }
            activated = False
            if joined:
                # This existing projection owns freshness, all roster revisions
                # and the Handler/Pilot distinction. Return counts, not peer drafts.
                current_setup = handler.view(viewer)
                roster = handler._roster(connection)
                rulings = handler.effective_rulings(connection)
                campaign.update(
                    status_current=not current_setup["status_stale"]
                    and len(current_setup["status_order"]) >= 2,
                    rulings_ready=rulings is not None
                    and rulings.requisition_mode == "long_game"
                    and self.store.policy.owner_initial_conditions is not None,
                    pilot_count=len(roster),
                )
                profile = connection.execute(
                    sa.select(t.characters.c.public_json).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == str(viewer.user_id),
                    )
                ).first()
                state = load_state(connection, self.store.campaign_id)
                own = state.sheets.get(str(viewer.user_id))
                activated = own is not None
                if activated:
                    assert own is not None
                    character.update(
                        exists=True,
                        callsign=own.callsign,
                        girl=own.girl,
                        frame=own.frame,
                        creation_revision=own.review.creation_revision,
                        saved_current=True,
                        review_ready=True,
                        next_route="ready",
                    )
                elif profile is None:
                    character["next_route"] = "profile"
                else:
                    current = CreationReviewService(self.store)._current(connection, viewer)
                    own_creation = current.sheet.creation
                    issues = [x for x in current.sheet.issues if x.category != "review"]
                    projected = [
                        {
                            "code": x.code,
                            "message": x.message,
                            "route": _route(x),
                            "waiting": (
                                _route(x) == "handler"
                                and not admin
                                or _route(x) in ("status", "creation_rules")
                                and not is_handler
                                or x.code in ("princess_handler", "handler_investor")
                                and not is_handler
                                or x.code == "initial_conditions"
                            ),
                        }
                        for x in issues
                    ]
                    primary = current.sheet.primary_starting_bond
                    for issue in projected:
                        if issue["code"] == "additional_starting_bond" and any(
                            x.depth == "Personal"
                            and (primary is None or x.counterpart != primary.counterpart)
                            for x in current.sheet.bonds
                        ):
                            issue["route"] = "review"
                    character.update(
                        exists=True,
                        callsign=current.sheet.callsign,
                        girl=own_creation.girl_playbook,
                        frame=own_creation.frame_playbook,
                        creation_revision=current.sheet.creation_revision,
                        saved_current=current.saved_current,
                        review_ready=current.sheet.ready_for_rules_review,
                        issues=projected,
                        # Only the fingerprint is exposed, not the private review
                        # body. Existing save/activation paths still recheck it.
                        review_fingerprint=current.fingerprint,
                    )
                    character["next_route"] = (
                        projected[0]["route"]
                        if projected
                        else "activate"
                        if current.saved_current
                        else "review"
                    )
            approval = self.store.policy.m2_approval
            character["release_enabled"] = (
                approval is not None
                and approval.registry_sha256 == registry_digest()
                and self.store.policy.owner_intense_tag_bonus is not None
            )
            if character["next_route"] == "activate" and not character["release_enabled"]:
                character["next_route"] = "review"
        if joined:
            # Retain the Inbox's existing visible/you/waiting distinction. It
            # already understands sources beyond creation and never grants consent.
            inbox = InboxService(self.store)
            page = inbox.page(viewer)
            own_items = inbox.items(viewer) if page.counts["pending"] else ()
            pending = [x for x in own_items if x.state == "pending"]
            character["requests"] = {
                "actionable": page.counts["you"],
                "waiting": page.counts["waiting"],
                "stale": sum(x.stale for x in pending),
            }
            for issue in character["issues"]:
                if (
                    issue["code"] in ("starting_bond", "additional_starting_bond")
                    and issue["route"] != "review"
                ):
                    relevant = [x for x in pending if x.source == "bond"]
                    if relevant:
                        issue["route"] = "requests"
                        issue["waiting"] = not any(x.incoming or x.stale for x in relevant)
            if character["issues"]:
                character["next_route"] = character["issues"][0]["route"]
        if inactive:
            character["issues"] = [
                {
                    "code": "membership",
                    "message": (
                        "Campaign membership is inactive. Ask the administrator to review it."
                    ),
                    "route": "join",
                    "waiting": True,
                }
            ]
        campaign["steps"] = [
            _step(
                "server",
                "Saved server resources",
                "complete" if resources_ready == len(TEMPLATE) else "next" if admin else "waiting",
                "server",
            ),
            _step(
                "campaign",
                "Campaign initialized",
                "complete" if initialized else "next" if admin else "waiting",
                "create",
            ),
            _step(
                "handler",
                "Appointed Handler",
                "complete" if handler_active else "next" if admin else "waiting",
                "handler",
            ),
            _step(
                "roster",
                "At least two Pilot profiles",
                "complete" if campaign["pilot_count"] >= 2 else "waiting",
                "profile",
            ),
            _step(
                "status",
                "Current confirmed Status order",
                "complete" if campaign["status_current"] else "next" if is_handler else "waiting",
                "status",
            ),
            _step(
                "rulings",
                "Starting resource settings",
                "complete" if campaign["rulings_ready"] else "next" if is_handler else "waiting",
                "creation_rules",
            ),
        ]
        routes = {x["route"] for x in character["issues"]}
        build_routes = {"build", "girl_setup", "history", "frame_details"}
        coordination_routes = {"bond", "requests", "court", "mentor_callsign", "pair_assets"}
        character["steps"] = [
            _step(
                "join",
                "Campaign membership",
                "complete" if joined else "waiting" if inactive else "next",
                "join",
            ),
            _step(
                "profile",
                "Callsign and playbooks",
                "complete" if character["exists"] else "next" if joined else "blocked",
                "profile",
            ),
            _step(
                "build",
                "Assets and character details",
                "complete"
                if activated or character["exists"] and not routes & build_routes
                else "next"
                if character["exists"]
                else "blocked",
                "build",
            ),
            _step(
                "coordination",
                "Bonds and shared starting choices",
                "complete"
                if activated
                or character["exists"]
                and not routes & coordination_routes
                and not any(
                    x["code"] in ("starting_bond", "additional_starting_bond")
                    for x in character["issues"]
                )
                else "waiting"
                if character["requests"]["waiting"] and not character["requests"]["actionable"]
                else "next"
                if character["exists"]
                else "blocked",
                "requests",
            ),
            _step(
                "review",
                "Complete saved review",
                "complete"
                if character["saved_current"] and character["review_ready"]
                else "next"
                if character["review_ready"]
                else "blocked",
                "review",
            ),
            _step(
                "activate",
                "Explicit playable activation",
                "complete"
                if activated
                else "next"
                if character["saved_current"]
                and character["review_ready"]
                and character["release_enabled"]
                else "blocked",
                "activate",
            ),
        ]
        return {
            "owner": viewer.user_id,
            "joined": joined,
            "membership_inactive": inactive,
            "is_admin": admin,
            "is_handler": is_handler,
            "activated": activated,
            "character": character,
            "campaign": campaign,
        }
