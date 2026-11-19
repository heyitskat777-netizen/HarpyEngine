"""Optional Ancillary playbook creation and its independent character resources."""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import GameState, IdentityState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "optional.ancillary.shared-rules"
SOLDIER_SIMPLIFICATION = "ancillary.soldier.simplification-surgery"

Book = Literal[
    "SOLDIER",
    "MERCENARY",
    "PRODIGY",
    "REVOLUTIONARY IDEALIST",
    "ANGEL-WIFE",
    "CHAINED DARLING",
    "WARBOY",
    "ABYSSAL ACOLYTE",
]
Affiliation = Literal["foundation", "rebel"]


@dataclass(frozen=True)
class Starter:
    rule: str
    affiliation: Affiliation
    identities: tuple[str, ...]
    assets: tuple[str, ...]


STARTERS: dict[Book, Starter] = {
    "SOLDIER": Starter(
        "ancillary.soldier.soldier",
        "foundation",
        ("Dangerous", "Programmed"),
        (
            "Nice Jacket",
            "Freshly-Healed Link",
            "Hyperreflex Implant",
            "Excursion Lobotomy",
            "Taser",
        ),
    ),
    "MERCENARY": Starter(
        "ancillary.mercenary.mercenary",
        "foundation",
        ("Dangerous", "Desperate", "Programmed", "Wired"),
        (
            "Falcon-Eyes",
            "Illegal Neural Implant",
            "Obeisance Uniform",
            "Thick Skin",
            "Debtor Implant",
        ),
    ),
    "PRODIGY": Starter(
        "ancillary.prodigy.prodigy",
        "foundation",
        ("Dangerous", "Just Better", "Programmed", "Wired"),
        ("High Collar", "Wireless Link", "Nice Hair", "Containment Suit", "Patrician Chip"),
    ),
    "REVOLUTIONARY IDEALIST": Starter(
        "ancillary.revolutionary-idealist.revolutionary-idealist",
        "rebel",
        ("Dangerous", "Malfunctioning", "Amateur", "Wired"),
        (
            "Maximal Feedback Link",
            "Stimjector Implant",
            "Jacket with Pins",
            "Radio Clicker",
            "Wireless Brainchip",
        ),
    ),
    "ANGEL-WIFE": Starter(
        "ancillary.angel-wife.angel-wife",
        "rebel",
        ("Wife", "Malfunctioning", "Programmed", "Wired"),
        ("Embed Ring", "Seraphim Core", "Restriction Belt", "Praise Earbud", "Pretty Dress"),
    ),
    "CHAINED DARLING": Starter(
        "ancillary.chained-darling.chained-darling",
        "rebel",
        ("Dangerous", "Malfunctioning", "Taken Apart", "Wired"),
        (
            "Repression Conditioning",
            "Lifeline",
            "Virility Implant",
            "Heart Exploder",
            "Rugged Pants",
        ),
    ),
    "WARBOY": Starter(
        "ancillary.warboy.warboy",
        "rebel",
        ("Dangerous", "Man", "Programmed", "Wired"),
        ("Gun (dad’s)", "Beast Conditioning", "Encryption Link", "Box of Secrets", "Nice Belt"),
    ),
    "ABYSSAL ACOLYTE": Starter(
        "ancillary.abyssal-acolyte.abyssal-acolyte",
        "rebel",
        ("Dangerous", "Malfunctioning", "Devoted", "Wired"),
        ("Devotee Lenses", "Girlcatcher", "Ripped-Out Link", "Sharp Knife", "Worship Rod"),
    ),
}

SOLDIER_FRAME_ASSETS = ("Assault Rifle", "Laser Sword", "Armour Plating")


def frame_assets(book: Book, catalogue: str) -> tuple[str, ...]:
    if book == "SOLDIER":
        return SOLDIER_FRAME_ASSETS if catalogue == "SOLDIER_3" else ()
    source = CATALOG.get(catalogue)
    return tuple(source["assets"]) if source is not None and source["family"] == "frame" else ()


class NamedAsset(Model):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)


class Draft(Model):
    name: str = Field(min_length=1, max_length=120)
    book: Book
    girl_assets: tuple[NamedAsset, NamedAsset]
    frame_catalogue: str
    frame_assets: tuple[NamedAsset, NamedAsset]
    bond: ActorRef | None = None
    patron: ActorRef | None = None
    wanted: ActorRef | None = None

    @model_validator(mode="after")
    def exact_choices(self) -> "Draft":
        choices = STARTERS[self.book]
        if (
            not self.name.strip()
            or (self.bond is None) != (self.book in ("CHAINED DARLING", "WARBOY"))
            or (self.patron is not None) != (self.book == "MERCENARY")
            or (self.wanted is not None and self.book != "WARBOY")
            or any(not x.description.strip() for x in (*self.girl_assets, *self.frame_assets))
        ):
            raise ValueError("Record the actual original playbook's starting choices")
        for picks, available in (
            (self.girl_assets, choices.assets),
            (self.frame_assets, frame_assets(self.book, self.frame_catalogue)),
        ):
            if len({x.name for x in picks}) != 2 or not {x.name for x in picks} <= set(available):
                raise ValueError("Choose two distinct actual Assets from the printed sources")
        return self


class Character(Model):
    actor: ActorRef
    controller: int = Field(gt=0)
    event: str
    draft: Draft
    heat: int = Field(default=0, ge=0)
    identities: tuple[IdentityState, ...]
    tags: tuple[TagState, ...] = Field(default=(), exclude_if=lambda value: not value)


class Offer(Model):
    id: str
    source_event: str
    sponsor: ActorRef
    controller: int = Field(gt=0)
    site: str
    faction: str | None
    books: tuple[Book, ...]
    contacts: tuple[ActorRef, ...] = ()
    phase: Literal["offered", "accepted", "declined"] = "offered"
    decision_event: str | None = None


def offers(state: GameState) -> tuple[Offer, ...]:
    return tuple(
        Offer.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "ancillary_offer"
    )


def put_offer(state: GameState, value: Offer) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != ("ancillary_offer", value.id)
    ] + [dict(kind="ancillary_offer", id=value.id, body=value.model_dump_json())]


def records(state: GameState) -> tuple[Character, ...]:
    return tuple(
        Character.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "ancillary_character"
    )


def find(state: GameState, actor: ActorRef) -> Character | None:
    if actor.kind != "external_pilot" or not actor.entity.startswith("ancillary:"):
        return None
    return next((x for x in records(state) if x.actor == actor), None)


def put(state: GameState, value: Character) -> None:
    state.facts = [
        x
        for x in state.facts
        if (x.get("kind"), x.get("id")) != ("ancillary_character", value.actor.entity)
    ] + [dict(kind="ancillary_character", id=value.actor.entity, body=value.model_dump_json())]
