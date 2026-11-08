"""Merge-safe permission ownership; Discord-independent bit operations."""

from typing import Any

SEND_MASK = (1 << 11) | (1 << 38)
LOCK_MASK = SEND_MASK | (1 << 35) | (1 << 36)


def records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    existing = {(x["kind"], str(x["id"])): x for x in snapshot["overwrites"]}
    keys = set(existing) | {
        ("role", str(snapshot["everyone_id"])),
        ("member", str(snapshot["bot_id"])),
    }
    if len(keys) > 100:
        raise ValueError("The channel has no room for safe lock overwrites")
    result = []
    for kind, identity in sorted(keys):
        original = existing.get((kind, identity))
        allow, deny = (int(original["allow"]), int(original["deny"])) if original else (0, 0)
        bot = kind == "member" and identity == str(snapshot["bot_id"])
        mask = SEND_MASK if bot else LOCK_MASK
        after = {
            "allow": (allow | mask) if bot else (allow & ~mask),
            "deny": (deny & ~mask) if bot else (deny | mask),
        }
        result.append(
            {
                "kind": kind,
                "id": identity,
                "mask": mask,
                "original": None if original is None else {"allow": allow, "deny": deny},
                "applied": after,
            }
        )
    return result


def merge(
    record: dict[str, Any], current: dict[str, int] | None, *, restore: bool
) -> dict[str, int] | None:
    original = record["original"] or {"allow": 0, "deny": 0}
    applied = record["applied"]
    mask = int(record["mask"])
    now = current or {"allow": 0, "deny": 0}
    owned = (now["allow"] & mask, now["deny"] & mask)
    before = (original["allow"] & mask, original["deny"] & mask)
    after = (applied["allow"] & mask, applied["deny"] & mask)
    if owned not in (before, after):
        raise ValueError("Staff permission edits conflict with the lock-owned bits")
    desired = original if restore else applied
    result = {key: (now[key] & ~mask) | (desired[key] & mask) for key in ("allow", "deny")}
    if (
        restore
        and result == {"allow": 0, "deny": 0}
        and (record["original"] is None or current is None)
    ):
        return None
    return result
