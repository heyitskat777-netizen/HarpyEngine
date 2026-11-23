"""Read explicitly reported canon through the Activity's current consent boundary."""

from typing import TYPE_CHECKING

from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.scenes.canon import KnowledgeGrant, ShadowConsent
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.onboarding import OnboardingStore, WorkflowError

if TYPE_CHECKING:
    from girlframe.services.director_context import DirectorContextService


def capture_consent(
    store: OnboardingStore, c: Connection, scene: str, *, allow_closed: bool = False
) -> ShadowConsent | None:
    observer = DirectorObservationService(store, synthetic=True, activity_shadow=True)
    state = observer._state(c, scene)
    if state.activity_epoch is None or state.policy.mode != "shadow":
        return None
    try:
        observer.game.scene_unpaused(c, scene)
    except WorkflowError:
        return None
    try:
        row = observer._scene(c, scene, allow_closed=allow_closed)
    except WorkflowError as error:
        if not allow_closed or not str(error).startswith("SCENE_UNAVAILABLE: use the actual"):
            return None
        from girlframe.services.director_closeout import closed_scene_audience

        row = {"participants": closed_scene_audience(store, c, scene)}
    if not observer._consented(c, row, state):
        return None
    return ShadowConsent(
        activity_epoch=state.activity_epoch, consent_generation=state.consent_generation
    )


def handler_canon(
    context: "DirectorContextService",
    c: Connection,
    scene: str,
    actor: ActorRef,
    handler: int,
    *,
    closed_only: bool = False,
) -> tuple[KnowledgeReference, ...]:
    from girlframe.services import canon_history
    from girlframe.services.canon import CanonService
    from girlframe.services.director_closeout import authorized_closed_scenes

    store = context.store
    if store.policy.canon_facilitator_id is None or capture_consent(store, c, scene) is None:
        return ()
    canon = CanonService(store)
    principal = canon.principal(c, handler)
    if principal is None:
        return ()
    grants = [
        (row, grant)
        for row, grant in canon._grants_for(c, handler, principal)
        if grant.method == "reported"
        and grant.window is not None
        and grant.shadow_consent
        and (grant.window.scene_id != scene) == closed_only
    ]
    if not grants:
        return ()
    closed = authorized_closed_scenes(context, c, actor)
    stamps = {scene: capture_consent(store, c, scene)}
    statuses = canon_history.statuses(c, store.campaign_id)

    def authorized(source_scene: str, saved: ShadowConsent | None) -> bool:
        if saved is None or (source_scene != scene and source_scene not in closed):
            return False
        if source_scene not in stamps:
            stamps[source_scene] = capture_consent(store, c, source_scene, allow_closed=True)
        return stamps[source_scene] == saved

    def current_fact(fact_id: str) -> bool:
        pending = [fact_id]
        checked = set()
        while pending:
            identity = pending.pop()
            if identity in checked:
                continue
            if statuses.get(identity) != "current":
                return False
            fact = canon._fact(c, identity)
            if not authorized(fact.window.scene_id, fact.shadow_consent):
                return False
            checked.add(identity)
            pending.extend(fact.depends_on)
        return True

    result = []
    for receipt, grant in grants:
        assert grant.window is not None and grant.source_grant_id is not None
        origin = grant.window.scene_id
        if not authorized(origin, grant.shadow_consent) or not current_fact(grant.fact_id):
            continue
        raw = c.scalar(
            canon_history.grants(store.campaign_id, int(receipt["actor_id"]))
            .where(t.events.c.id == grant.source_grant_id)
            .with_only_columns(t.events.c.payload_json)
        )
        if raw is None:
            continue
        witness = KnowledgeGrant.model_validate_json(raw)
        if (
            witness.method != "witnessed"
            or witness.fact_id != grant.fact_id
            or witness.window is None
            or not authorized(witness.window.scene_id, witness.shadow_consent)
        ):
            continue
        fact = canon._fact(c, grant.fact_id)
        identity = "canon:" + receipt["id"]
        result.append(
            KnowledgeReference(
                id=identity,
                source_id=grant.fact_id,
                source_revision=1,
                order=receipt["seq"],
                classification="established_world",
                text=fact.statement,
                known_by=(actor.token,),
                origin_scene=origin if origin != scene else None,
                origin_reference=identity if origin != scene else None,
            )
        )
    return tuple(result)


def local_canon_citations(
    context: "DirectorContextService",
    c: Connection,
    scene: str,
    recipient: ActorRef,
    refs: tuple[KnowledgeReference, ...],
) -> set[str]:
    """A local canon citation can go back to a Pilot documented as a current witness."""
    from girlframe.services.canon import CanonService

    if recipient.kind != "pilot":
        return set()
    citations = {ref.source_id: ref.id for ref in refs if ref.id.startswith("canon:")}
    if not citations:
        return set()
    canon = CanonService(context.store)
    owner = int(recipient.entity)
    principal = canon.principal(c, owner)
    if principal is None:
        return set()
    consent = capture_consent(context.store, c, scene)
    return {
        citations[grant.fact_id]
        for _, grant in canon._grants_for(c, owner, principal)
        if grant.fact_id in citations
        and grant.method == "witnessed"
        and grant.window is not None
        and grant.window.scene_id == scene
        and consent is not None
        and grant.shadow_consent == consent
    }
