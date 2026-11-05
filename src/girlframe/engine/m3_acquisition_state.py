"""Source-bound actual Frame grants and issued physical items, separate from accounts."""

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class FirearmIssue(Model):
    asset: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    action: str | None = None


class PersonalFirearmGrant(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    frame_instance: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    purchase: str | None = None
    issues: tuple[FirearmIssue, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def actual_original(self) -> "PersonalFirearmGrant":
        if self.actor.kind != "pilot" or len({x.asset for x in self.issues}) != len(self.issues):
            raise ValueError("An original Girl's entitlement keeps distinct actual issued items")
        return self
