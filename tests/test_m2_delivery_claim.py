"""A stale pending job cannot publish after a different worker owns its claim."""

import asyncio

import sqlalchemy as sa
from test_ledger import ledger as ledger
from test_m2_game import setup_game, start

from girlframe.database import tables as t


def test_stale_delivery_claim_does_not_publish_or_mutate_new_owner(ledger):
    game, worker, gateway, dice = setup_game(ledger)
    publications = []
    original_publish = gateway.publish

    async def publish(channel, payload, nonce):
        publications.append(nonce)
        return await original_publish(channel, payload, nonce)

    gateway.publish = publish
    identity = start(game)
    table = t.m2["m2_outbox"]
    with ledger.transaction() as connection:
        game.queue(connection, game.action(connection, identity), "synthetic_delivery")
    stale = worker.claim("m2_outbox", ("pending",))
    assert stale is not None
    with ledger.transaction() as connection:
        connection.execute(
            table.update()
            .where(table.c.campaign_id == ledger.campaign_id, table.c.id == stale["id"])
            .values(lease_until=0)
        )
    current = worker.claim("m2_outbox", ("pending",))
    assert current is not None and current["id"] == stale["id"]
    assert current["claim_token"] != stale["claim_token"]

    def saved():
        with ledger.engine.connect() as connection:
            return dict(
                connection.execute(
                    sa.select(table).where(
                        table.c.campaign_id == ledger.campaign_id, table.c.id == stale["id"]
                    )
                )
                .mappings()
                .one()
            )

    before = saved()
    asyncio.run(worker.deliver(stale, gateway))
    assert publications == [] and gateway.messages == {} and saved() == before
    asyncio.run(worker.deliver(current, gateway))
    assert len(publications) == 1 and len(gateway.messages) == 1
    delivered = saved()
    assert delivered["state"] == "sent" and delivered["attempts"] == 1
    assert delivered["claim_token"] is None
    # Replaying the old pending dict must not publish again after completion.
    asyncio.run(worker.deliver(current, gateway))
    assert saved() == delivered and len(publications) == 1 and len(gateway.messages) == 1
    assert dice.calls == 0
