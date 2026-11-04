"""Private standing rules and their actual recorded breach provenance."""

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model


class Breach(Model):
    source_event: str = Field(min_length=1)
    evidence: str = Field(min_length=1, max_length=1200)
    handler: ActorRef
    obligation: str = Field(min_length=1)


class Regulation(Model):
    id: str = Field(min_length=1)
    subject: ActorRef
    inflictor: ActorRef
    knowing_handler: ActorRef
    rule: str = Field(min_length=1, max_length=1200)
    disclosed: bool
    source_event: str = Field(min_length=1)
    breaches: tuple[Breach, ...] = ()

    @model_validator(mode="after")
    def actual_parties(self) -> "Regulation":
        if (
            self.subject.kind != "pilot"
            or self.inflictor.kind not in ("pilot", "handler")
            or self.knowing_handler.kind != "handler"
            or self.knowing_handler.incarnation is not None
            or not self.rule.strip()
        ):
            raise ValueError("A regulation needs its actual Girl, inflictor and informed Handler")
        return self
