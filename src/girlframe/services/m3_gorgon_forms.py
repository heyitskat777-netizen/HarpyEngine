"""Activity form projection for existing native Gorgon declarations."""

from typing import Any

from girlframe.engine.m3_gorgon_play_state import Declaration
from girlframe.engine.m3_gorgon_type_tags import LABELS
from girlframe.engine.m3_growth import KINDS as GROWTH
from girlframe.engine.m3_jackdaw import EFFECTS as JACKDAW
from girlframe.services.native_form_fields import Field, form_fields
from girlframe.services.onboarding import WorkflowError


def jackdaw_cells(raw: str) -> tuple[tuple[int, int], ...]:
    try:
        return tuple((int(x), int(y)) for x, y in (line.split(",") for line in raw.splitlines()))
    except ValueError:
        raise WorkflowError("Enter the original range as one x,y grid square per line.") from None


def _targets(view: dict[str, Any], token: str, kind: str) -> tuple[str | None, ...]:
    if kind in view["environment"]:
        return (None,) if token in view["environment"][kind] else ()
    if kind in GROWTH:
        return (None,) if kind in view["growth"].get(token, ()) else ()
    if kind == "mother_sprite":
        return (None,) if token in view["sprite_birth"] else ()
    if kind in JACKDAW:
        return (None,) if token in view["jam"] else ()
    if kind in ("parasite_hitch", "parasite_detach"):
        choices = view["parasite"].get(token, {})
        if kind not in choices:
            return ()
        return (None,) if kind == "parasite_detach" else tuple(choices[kind])
    return tuple(view["typed_targets"].get(token, {}).get(kind, ()))


def _fields(
    view: dict[str, Any], kind: str, actor: dict[str, Any], target: str | None
) -> tuple[Field, ...]:
    owned = actor["assets"]
    assets = tuple((x["id"], x["name"]) for x in owned)
    if kind == "collateral":
        return (Field("assets", "Actual destructive Assets", assets, maximum=len(assets)),)
    if kind in LABELS:
        return (Field("tag", "Printed effect", LABELS[kind]),)
    if kind == "doppleganger_bond":
        return (Field("tag", "Tag earned in the actual interaction"),)
    if kind == "growth_adapt":
        return (
            Field("guards", "Actual Core-protecting Assets", assets, maximum=min(2, len(assets))),
            Field("weakness", "New Core weakness", paragraph=True),
            Field("tag", "Tag the Growth takes"),
        )
    if kind == "growth_regrow":
        return (
            Field(
                "eaten",
                "Damaged Asset to consume",
                tuple((x["id"], x["name"]) for x in owned if x["damaged"]),
            ),
            Field("replacement", "Replacement Asset name"),
            Field("description", "Describe the new Asset", paragraph=True),
        )
    if kind == "mother_sprite":
        return (
            Field(
                "payment",
                "Intact Asset the Mother damages",
                tuple((x["id"], x["name"]) for x in owned if not x["damaged"]),
            ),
            Field("name", "The Sprite's name"),
            Field("asset", "The Sprite's original Asset"),
            Field("weakness", "The Sprite's Core weakness", paragraph=True),
        )
    if kind in JACKDAW:
        return (Field("audible_range", "One affected x,y square per line", paragraph=True),)
    if kind == "grow_unreal":
        shed = view["shed_assets"].get(actor["token"], ())
        return (
            Field("shed", "Original Asset to sacrifice", tuple(x for x in assets if x[0] in shed)),
        )
    if kind in ("incubus_conditioning", "mother_hazard"):
        names = "conditioning_tags" if kind == "incubus_conditioning" else "hazard_tags"
        tags = tuple(view[names][actor["token"]][target])
        return (Field("tag", "Actual known unmarked Tag", tags),)
    return ()


def declarations(view: dict[str, Any], actor: str) -> tuple[dict[str, Any], ...]:
    """Expand the engine's per-actor targets and environment options into exact forms."""
    rows = {row["token"]: row for row in view["actors"]}
    current = rows.get(actor)
    if not current or not current["owned"]:
        return ()
    options = []
    for kind in view["plays"]:
        if kind == "attack":  # The existing Activity Attack keeps its own saved shape.
            continue
        for target in _targets(view, actor, kind):
            opponent = rows.get(target)
            options.append(
                dict(
                    kind=kind,
                    target_token=target or "environment",
                    target=opponent["ref"] if opponent else None,
                    target_sha256=opponent["source_sha256"] if opponent else None,
                    target_name=opponent["label"] if opponent else "",
                    fields=form_fields(_fields(view, kind, current, target)),
                    day=view["exposure_days"].get(actor, {}).get(target)
                    if kind == "jackdaw_hallucinations_day"
                    else None,
                )
            )
    return tuple(options)


def declaration(
    actor: dict[str, Any], binding: dict[str, Any], account: str, values: dict[str, Any]
) -> Declaration:
    kind = binding["kind"]
    details: dict[str, Any] = {}
    if kind in LABELS or kind in ("incubus_conditioning", "mother_hazard"):
        details["tag"] = values["tag"][0]
    if kind == "doppleganger_bond":
        details["tag"] = values["tag"]
    if kind == "growth_adapt":
        details["adaptation"] = dict(
            guards=dict(assets=values["guards"], weakness=values["weakness"]), tag=values["tag"]
        )
    if kind == "growth_regrow":
        details["regrowth"] = dict(
            asset=values["eaten"][0], name=values["replacement"], description=values["description"]
        )
    if kind == "mother_sprite":
        details["birth"] = dict(
            payment=values["payment"][0],
            name=values["name"],
            asset=values["asset"],
            weakness=values["weakness"],
        )
    if kind in JACKDAW:
        details["interference"] = dict(cells=jackdaw_cells(values["audible_range"]))
    if kind == "grow_unreal":
        details["shed"] = values["shed"][0]
    if kind == "jackdaw_hallucinations_day":
        details["day"] = binding["day"]
    return Declaration.model_validate(
        dict(
            kind=kind,
            actor=actor,
            actor_sha256=binding["actor_sha256"],
            target=binding["target"],
            target_sha256=binding["target_sha256"],
            assets=values.get("assets", ()),
            account=account,
            reach_confirmed=True,
            **details,
        )
    )
