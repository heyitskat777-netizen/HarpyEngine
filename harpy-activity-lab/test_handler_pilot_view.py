"""Own-account presentation and saved cosmetic draft recovery, isolated campaign only."""
import json
import sqlite3
from http import HTTPStatus
from test_campaign_role_access import CONFIG, TESTER, request, role_activity

def login(host, code):
    nonce=request(host,"/api/discord/challenge",data={})["nonce"]
    return request(host,"/api/discord/session",data={"nonce":nonce,"code":code,"guild_id":CONFIG.guild_id})["session"]

def test_handler_own_draft_view_and_roster_callsign(tmp_path):
    with role_activity(tmp_path) as host:
        token=login(host,"handler")
        campaign=request(host,"/api/campaigns",token)["campaigns"][0]["id"]
        route="/api/player-setup?campaign="+campaign
        desk=request(host,route,token)
        assert desk["stage"]=="handler" and desk["handler_account"]
        own=request(host,route+"&perspective=pilot",token)
        assert own["stage"]=="profile"
        assert own["enrollment"]["owner_id"]==CONFIG.handler_user_id
        assert "native dual-role support" in own["handler_pilot_notice"]
        request(host,"/api/player-setup/profile?campaign="+campaign+"&perspective=pilot",token,
                {"revision":own["revision"],"callsign":"HANDLER PILOT"})
        draft=request(host,route+"&perspective=pilot",token)
        assert draft["stage"]=="draft" and draft["callsign"]=="HANDLER PILOT"
        assert any("Handler account" in issue for issue in draft["review"]["issues"])
        again=request(host,route,token)
        assert again["stage"]=="handler" and again["callsign"]=="HANDLER PILOT"
        members=request(host,"/api/presence?campaign="+campaign,token)["members"]
        assert any(p["name"]=="HANDLER PILOT" and p["handler"] for p in members)
        peer=login(host,"invited")
        record=request(host,route+"&perspective=pilot",peer)
        assert not record["handler_account"] and record["stage"]!="handler"
        request(host,"/api/player-setup/handler-play-start?campaign="+campaign+"&perspective=pilot",peer,{},status=HTTPStatus.FORBIDDEN)
        reopened=login(host,"handler")
        assert request(host,route+"&perspective=pilot",reopened)["callsign"]=="HANDLER PILOT"

def test_retired_frame_draft_requires_owner_confirmation_without_losing_notes(tmp_path):
    with role_activity(tmp_path) as host:
        token=login(host,"role-pilot")
        campaign=request(host,"/api/campaigns",token)["campaigns"][0]["id"]
        route="/api/player-setup?campaign="+campaign
        current=request(host,route,token)
        request(host,"/api/player-setup/profile?campaign="+campaign,token,{"revision":current["revision"],"callsign":"SAVED CALLSIGN"})
        database=tmp_path/"role-runtime/playtest-campaigns"/("activity-"+campaign.replace("-",""))/"missions.sqlite3"
        with sqlite3.connect(database) as db:
            uid,raw=db.execute("SELECT user_id,public_json FROM characters WHERE user_id=?",(TESTER,)).fetchone()
            public=json.loads(raw)
            public["frame_playbook"]="JANUS-B"
            db.execute("UPDATE characters SET public_json=?,private_json=? WHERE user_id=?",(json.dumps(public),json.dumps({"notes":"Retain these owner notes."}),uid))
        recovered=request(host,route,token)
        assert recovered["stage"]=="profile"
        assert recovered["callsign"]=="SAVED CALLSIGN"
        assert recovered["options"]["frame"]=="JANUS" and recovered["recovery_notice"]
        with sqlite3.connect(database) as db:
            assert json.loads(db.execute("SELECT public_json FROM characters WHERE user_id=?",(uid,)).fetchone()[0])["frame_playbook"]=="JANUS-B"
        request(host,"/api/player-setup/profile?campaign="+campaign,token,{"revision":recovered["revision"],"callsign":recovered["callsign"],"girl_playbook":recovered["options"]["girl"],"frame_playbook":"JANUS"})
        assert request(host,route,token)["stage"]=="draft"
        with sqlite3.connect(database) as db:
            assert json.loads(db.execute("SELECT private_json FROM characters WHERE user_id=?",(uid,)).fetchone()[0])["notes"]=="Retain these owner notes."
        members=request(host,"/api/presence?campaign="+campaign,token)["members"]
        assert any(p["name"]=="SAVED CALLSIGN" and not p["enrolled"] for p in members)
