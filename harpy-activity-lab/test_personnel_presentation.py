"""Source-verified labels preserve native choices; private portraits use participant identity."""

from rulebook_text import BOND_PROMPTS, BOOK, printed_fields
from test_campaign_role_access import CONFIG, request, role_activity
from test_handler_pilot_view import login

from girlframe.engine.bonds import PROMPTS
from girlframe.engine.m2 import SENSOR_QUESTION_TEXT
from girlframe.engine.m3_red_queen import QUESTIONS as QUEEN_QUESTIONS
from girlframe.engine.m3_wyvern import QUESTIONS as WYVERN_QUESTIONS


def test_bond_prompt_indices_and_native_question_ids_are_preserved():
    assert {girl: len(prompts) for girl, prompts in BOND_PROMPTS.items()} == {
        girl: len(prompts) for girl, prompts in PROMPTS.items()
    }
    assert BOOK["questions"]["sensors"]["text"] == SENSOR_QUESTION_TEXT
    assert BOOK["questions"]["red_queen"]["text"] == QUEEN_QUESTIONS
    assert BOOK["questions"]["wyvern"]["text"] == WYVERN_QUESTIONS
    schema = [
        {
            "key": "options",
            "options": [
                ("hurt", "Who would you like me to hurt?"),
                ("intimacy", "Do you want to be intimate with me?"),
            ],
            "minimum": 1,
            "maximum": 1,
        }
    ]
    rewritten = printed_fields(schema, "actor_flirt")
    assert [key for key, label in rewritten[0]["options"]] == ["hurt", "intimacy"]
    assert rewritten[0]["options"][0][1] == "Who do you want me to hurt?"
    assert rewritten[0]["options"][1][1] == BOOK["questions"]["flirt"]["text"]["intimacy"]
    assert rewritten[0]["minimum"] == rewritten[0]["maximum"] == 1


def test_remaining_printed_choices_preserve_native_slots_and_fixed_questions():
    from rulebook_text import DESIRES, MAXIMS, STANDARDS, sensor_question_text

    from girlframe.engine.creation_details import DESIRES as native_desires
    from girlframe.engine.creation_details import MAXIMS as native_maxims
    from girlframe.engine.creation_details import STANDARDS as native_standards
    from girlframe.engine.m3_void import QUESTIONS

    assert (len(STANDARDS), len(MAXIMS), len(DESIRES)) == (
        len(native_standards),
        len(native_maxims),
        len(native_desires),
    )
    assert STANDARDS[-1] == native_standards[-1]  # Custom wording remains the owner's.
    assert STANDARDS[0] == "Report on your cadremates behaviour and activities."
    assert MAXIMS[7] == "Never piss off your engineer."
    assert DESIRES[5] == "A fucktoy"
    assert tuple(BOOK["questions"]["void_threshold"]["text"].values()) == QUESTIONS
    assert sensor_question_text("What can I smell?") == "what can I smell?"
    assert sensor_question_text("A player's own question?") == "A player's own question?"
    fields = [
        {
            "key": "options",
            "options": [("consume_smell", "What can I smell?")],
            "minimum": 2,
            "maximum": 2,
        }
    ]
    assert printed_fields(fields, "actor_sensors")[0]["options"] == [
        ("consume_smell", "what can I smell?")
    ]
    assert fields[0]["minimum"] == fields[0]["maximum"] == 2


def test_private_portraits_follow_ids_even_when_both_callsigns_match(tmp_path):
    from activity_artwork import CATALOG
    from test_campaign_role_access import TESTER

    pictures = [row["id"] for row in CATALOG if row["kind"] == "pilot"][:2]
    assert len(pictures) == 2
    with role_activity(tmp_path) as host:
        one = login(host, "role-pilot")
        two = login(host, "invited")
        campaign = request(host, "/api/campaigns", one)["campaigns"][0]["id"]
        query = "?campaign=" + campaign
        for token, owner, picture in (
            (one, TESTER, pictures[0]),
            (two, CONFIG.invited_user_id, pictures[1]),
        ):
            current = request(host, "/api/player-setup" + query, token)
            request(
                host,
                "/api/player-setup/profile" + query,
                token,
                {"revision": current["revision"], "callsign": "SHARED CALLSIGN"},
            )
            request(
                host,
                "/api/player-setup/artwork" + query,
                token,
                {"kind": "pilot", "target": owner, "artwork": picture, "previous": None},
            )
        a = request(host, "/api/player-setup" + query, one)
        b = request(host, "/api/player-setup" + query, two)
        assert a["options"]["bond_prompts"][0] == "When I was a Harpy, I was obsessed with you."
        assert (
            a["creation_choices"]["standards"][0]
            == BOOK["choices"]["princess_standards"]["text"][0]
        )
        assert a["creation_choices"]["desires"][5] == BOOK["choices"]["investor_desires"]["text"][5]
        target = next(row for row in a["communications"] if row["portrait"] == pictures[1])
        source = next(row for row in b["communications"] if row["portrait"] == pictures[0])
        request(
            host, "/api/communications/" + target["id"] + query, one, {"text": "First principal."}
        )
        request(
            host, "/api/communications/" + source["id"] + query, two, {"text": "Second principal."}
        )
        thread = request(host, "/api/communications/" + target["id"] + query, one)
        assert (
            thread["sender"]["portrait"] == pictures[0]
            and thread["recipient"]["portrait"] == pictures[1]
        )
        assert [entry["portrait"] for entry in thread["entries"]] == pictures
        assert len({entry["author_id"] for entry in thread["entries"]}) == 2
        reopened = login(host, "role-pilot")
        assert (
            request(host, "/api/communications/" + target["id"] + query, reopened)["entries"]
            == thread["entries"]
        )
        third = login(host, "other")
        outsider = request(host, "/api/player-setup" + query, third)
        contact = next(row for row in outsider["communications"] if row["portrait"] == pictures[1])
        assert request(host, "/api/communications/" + contact["id"] + query, third)["entries"] == []
