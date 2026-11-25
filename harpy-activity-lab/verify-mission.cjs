const assert = require("node:assert/strict");
const { spawn, spawnSync } = require("node:child_process");
const { once } = require("node:events");
const path = require("node:path");
const readline = require("node:readline");
const { randomUUID } = require("node:crypto");
const { chromium } = require(process.env.HARPY_ACTIVITY_TEST_PLAYWRIGHT ??
  "playwright-core");

const app = path.dirname(__dirname);
const engine = path.resolve(process.env.HARPY_ACTIVITY_ENGINE_ROOT ?? app);
const python = process.env.HARPY_ACTIVITY_TEST_PYTHON ??
  (process.platform === "win32" ? path.join(engine, ".venv", "Scripts", "python.exe")
    : path.join(engine, ".venv", "bin", "python"));
const main = path.join(__dirname, "mission_lab.py");
const dmOffline = process.argv.includes("--discord-offline-dm");
const sceneCheck = dmOffline && process.argv.includes("--scene-check");
const offDutyCase = process.argv.find(argument => argument.startsWith("--off-duty-test="))?.split("=")[1];
const relayPlaysCheck = process.argv.includes("--relay-plays-check");
const roomPlaysCheck = process.argv.includes("--room-plays-check");
const relayTier = process.argv.find(argument => argument.startsWith("--relay-tier="))?.split("=")[1] ?? "mid";
const communicationsCheck = process.argv.includes("--communications-check");
const artworkCheck = process.argv.includes("--artwork-check");
const playRailCheck = process.argv.includes("--play-rail-check");
const rosterBattlefieldCheck = process.argv.includes("--private-battlefield-check");
const campaignSwitchCheck = process.argv.includes("--campaign-switch-check");
const campaignDmCheck = process.argv.includes("--campaign-dm-check");
const handlerPlaysCheck = process.argv.includes("--handler-plays-check");
const missionDeskCheck = process.argv.includes("--mission-desk-check");
const sceneOrdersCheck = process.argv.includes("--scene-orders-check");
const directorTrialCheck = process.argv.includes("--director-trial-check");
const rehearsalCheck = process.argv.includes("--director-rehearsal-check");
const archiveCheck = process.argv.includes("--scene-archive-check");
const intelCheck = process.argv.includes("--scene-intel-check");
const sceneArtworkCheck = process.argv.includes("--scene-artwork-stability-check");
const p2BattlefieldCheck = process.argv.includes("--p2-battlefield-check");
const playParityCheck = process.argv.includes("--play-parity-check");
const p2Facility = process.argv.includes("--outpost") ? "outpost" : "hangar";
const directorDiscordCheck = archiveCheck || intelCheck || sceneArtworkCheck || p2BattlefieldCheck || playParityCheck || rehearsalCheck || process.argv.includes("--director-discord-check");
const enrollmentDraftCheck = process.argv.includes("--enrollment-draft-check");
const boundRosterCheck = enrollmentDraftCheck || sceneOrdersCheck || missionDeskCheck || rosterBattlefieldCheck || campaignSwitchCheck || campaignDmCheck || handlerPlaysCheck || process.argv.includes("--bound-roster-check");
const discordOffline = directorDiscordCheck || dmOffline || boundRosterCheck || process.argv.includes("--discord-offline");
const chromePath = process.argv.slice(2).find(argument => !argument.startsWith("--"));
const tacticalTier = process.argv.slice(2).find(argument => argument.startsWith("--tactical-tier="))?.split("=")[1];
const coreCase = process.argv.slice(2).find(argument => argument.startsWith("--core-case="))?.split("=")[1];
const orderCheck = dmOffline && process.argv.includes("--order-check");
const flirtCheck = discordOffline && !dmOffline && process.argv.includes("--flirt-check");
const beneathCheck = discordOffline && !dmOffline && process.argv.includes("--beneath-check");
const beneathExtra = process.argv.slice(2).find(argument => argument.startsWith("--beneath-extra="))?.split("=")[1] ?? "pin";
const defeatCase = process.argv.slice(2).find(argument => argument.startsWith("--defeat-case="))?.split("=")[1];
const flirtExtra = process.argv.slice(2).find(argument => argument.startsWith("--flirt-extra="))?.split("=")[1] ?? "owe";
const followthroughCheck = flirtCheck && process.argv.includes("--followthrough-check");
const handlerEffect = process.argv.slice(2).find(argument => argument.startsWith("--handler-effect="))?.split("=")[1] ?? (followthroughCheck ? "expectation" : "brief");
const campaign = (discordOffline ? "discord-offline-" : "smoke-") + randomUUID();
const args = ["-B", main, "--campaign", campaign];
const directorName = "browser-" + randomUUID();
const directorArgs = ["-B", main, "--p2-trial", directorName];
const savedLabel = "Response saved · Accepted";
const discordUsers = {invited:"333333333333333333",other:"444444444444444444",handler:"555555555555555555","role-pilot":"666666666666666666"};

async function startServer() {
  const command = discordOffline
    ? ["-B", path.join(__dirname, "discord_test_host.py"), "--campaign", campaign, ...(dmOffline ? ["--dm"] : []),
        ...(directorDiscordCheck ? ["--p2-trial", directorName] : []),
        ...(rehearsalCheck || (p2BattlefieldCheck && process.argv.includes("--rehearsal-copy")) ? ["--copy-p2-rehearsal"] : []),
        ...(boundRosterCheck ? ["--bound-roster"] : []),
        ...(campaignSwitchCheck || campaignDmCheck ? ["--managed-campaigns"] : []),
        ...(campaignDmCheck ? ["--allow-dm"] : []),
        ...(tacticalTier ? ["--tactical-tier", tacticalTier] : []),
        ...(handlerPlaysCheck ? ["--scene-tier","high"] : relayPlaysCheck || roomPlaysCheck ? ["--scene-tier", relayTier] : []),
        ...(offDutyCase ? ["--off-duty-test", offDutyCase, "--scene-tier", "mid"] : []),
        ...(defeatCase ? ["--defeat-test", defeatCase] : []),
        ...(coreCase === "high" ? ["--core-test-heat"] : [])]
    : [...(directorTrialCheck ? directorArgs : args), "--port", "0", "--stop-on-input-close"];
  const child = spawn(python, command, { cwd: app, windowsHide: true });
  let stderr = "";
  child.stderr.on("data", chunk => { stderr += chunk; });
  const lines = readline.createInterface({ input: child.stdout });
  try {
    const config = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Mission lab startup timed out.")), 40000);
      child.once("error", error => { clearTimeout(timeout); reject(error); });
      child.once("exit", code => {
        clearTimeout(timeout);
        reject(new Error(`Mission lab exited (${code}). ${stderr}`));
      });
      lines.once("line", line => {
        clearTimeout(timeout);
        try { resolve(JSON.parse(line)); } catch (error) { reject(error); }
      });
    });
    return { child, diagnostics: () => stderr, ...config };
  } catch (error) {
    child.stdin.end();
    throw error;
  } finally {
    lines.close();
  }
}

async function stopServer(server) {
  if (!server || server.child.exitCode !== null || server.child.signalCode !== null) return;
  const exit = once(server.child, "exit");
  server.child.stdin.end();
  await exit;
}

async function verifyDirectorTrial(browser, server, previous = null) {
  const route = server.origin + "/api/director-trial";
  assert.equal((await fetch(route)).status, 401);
  async function enter(label, role) {
    const connection = directorDiscordCheck ? await openPilot(browser, server, role) : null;
    const page = connection?.page ?? await browser.newPage();
    const view = connection?.view ?? page;
    page.setDefaultTimeout(10000);
    if (!connection) await page.goto(server.pilots[label]);
    try {
      const closeInbox = view.getByRole("button",{name:"Close inbox",exact:true});
      if (await closeInbox.isVisible()) await closeInbox.click();
      await view.getByRole("button", {name:"Training terminal",exact:true}).click();
    } catch (error) {
      throw new Error(label + " could not open the trial. " + await view.locator("#status").textContent(), {cause:error});
    }
    return {page, session:connection?.session, dialog:view.getByRole("dialog", {name:"Training terminal"})};
  }
  function request(person, path, data, key = randomUUID(), origin = server.discord_activity_origin ?? server.origin) {
    const headers = {Origin:origin, "Idempotency-Key":key};
    if (person.session) headers.Authorization = "Bearer " + person.session;
    return person.page.request.fetch(server.origin + path, {method:data ? "POST" : "GET", data, headers});
  }
  const post = (person, data, key, origin) => request(person, "/api/director-trial", data, key, origin);
  const pilot = await enter("Invited pilot", "invited");
  if (rehearsalCheck) {
    const sheet = await (await request(pilot, "/api/player-setup")).json();
    assert.equal(sheet.profile.frame, "JANUS");
    assert.equal(sheet.cadre.length, 2);
    assert(sheet.cadre.every(item => item.frame === "JANUS"));
  }
  if (previous) {
    if (directorDiscordCheck) {
      const reopened = [pilot, await enter("Other pilot", "other"), await enter("GM and Handler", "handler")];
      for (const saved of previous.saved) {
        const own = await request(reopened[saved.owner], saved.path, structuredClone(saved.data), saved.key);
        assert.equal(own.status(), 200, await own.text());
        assert.deepEqual(await own.json(), saved.receipt);
        const other = await request(reopened[(saved.owner + 1) % 3], saved.path, structuredClone(saved.data), randomUUID());
        assert.equal(other.ok(),false);
      }
      const pilotState = await (await request(pilot, "/api/player-setup")).json();
      const initial = pilotState.scene_mail.find(item => item.id === previous.original);
      assert.deepEqual(initial.roll.faces, [4,5]);
      assert.equal(initial.state, "complete");
      for (const [owner, id] of previous.pending.entries()) {
        const response = await request(reopened[owner], "/api/director-trial");
        const own = (await response.json()).work.native.choices;
        assert(own.some(item => item.id === id));
        assert(!own.some(item => previous.pending.some((other, index) => index !== owner && other === item.id)));
      }
    }
    await pilot.dialog.getByText("Play request · awaiting gm review").waitFor();
    await pilot.dialog.getByRole("button", {name:"Safety pause",exact:true}).click();
    await pilot.dialog.getByText("PAUSED", {exact:true}).waitFor();
    assert.equal(await pilot.dialog.getByLabel("Pilot transmission").count(), 0);
    await pilot.dialog.getByRole("button", {name:"Lift my safety pause",exact:true}).click();
    await pilot.dialog.getByText("Play request · awaiting gm review").waitFor();
    await pilot.dialog.getByRole("button", {name:"Withdraw my consent"}).click();
    await pilot.dialog.getByText("AWAITING CONSENT", {exact:true}).waitFor();
    assert.equal(await pilot.dialog.getByLabel("Pilot transmission").count(), 0);
    return;
  }
  const other = await enter("Other pilot", "other");
  const gm = await enter("GM and Handler", "handler");
  const consent = "I consent to use invented dialogue in this trial";
  for (const person of [pilot, other, gm]) {
    await person.dialog.getByText("AWAITING CONSENT", {exact:true}).waitFor();
    await person.dialog.getByRole("button", {name:consent,exact:true}).click();
    await person.dialog.getByRole("button", {name:"Withdraw my consent"}).waitFor();
  }
  await pilot.dialog.getByRole("button", {name:"Refresh training record"}).click();
  const greeting = "GM, I choose Keep Your Head to hold the calibration needle steady.";
  await pilot.dialog.getByLabel("Pilot transmission").fill(greeting);
  await pilot.dialog.getByRole("button", {name:"File transmission",exact:true}).click();
  await pilot.dialog.getByText("Transmission filed.", {exact:true}).waitFor();
  await pilot.dialog.getByText("Play request · awaiting gm review").waitFor();
  assert.equal((await post(other, {operation:"gm-work"})).ok(), false);
  assert.equal((await post(other, {operation:"memory"})).ok(), false);
  assert.equal((await post(other, {operation:"gm-work"}, randomUUID(), "http://invalid.test")).status(),403);
  const current = await (await request(other, "/api/director-trial")).json();
  assert.deepEqual(current.work.declarations,[]);
  await gm.dialog.getByRole("button", {name:"Open private GM desk"}).click();
  await gm.dialog.getByText("Private GM review", {exact:true}).waitFor();
  const privateView = await post(gm, {operation:"gm-work"});
  assert.equal(privateView.status(),200);
  assert.equal((await privateView.json()).declarations.length,1);
  const command = {operation:"submit",revision:current.status.scene_revision,
    text:"An out-of-character trial note",classification:"ooc"};
  const key = randomUUID();
  const first = await post(other, command, key);
  const retry = await post(other, command, key);
  assert.equal(first.status(),200);
  assert.deepEqual(await retry.json(), await first.json());
  if (directorDiscordCheck) return saveDiscordTrialChoices(request, [pilot, other, gm]);
  return [];
}

async function saveDiscordTrialChoices(request, people) {
  const setup = "/api/player-setup";
  const director = "/api/director-trial";
  const saved = [];
  async function json(owner, path, data) {
    const response = await request(people[owner], path, data);
    assert.equal(response.status(),200,await response.text());
    return response.json();
  }
  async function waitFor(owner, path, select) {
    for (let n = 0; n < 65; n++) {
      const result = select(await json(owner,path));
      if (result) return result;
      await new Promise(resolve => setTimeout(resolve,120));
    }
    throw new Error("Timed out waiting for the original participant's choice.");
  }
  async function record(owner, path, data) {
    const key = randomUUID();
    const response = await request(people[owner], path, data, key);
    assert.equal(response.status(), 200, await response.text());
    saved.push({owner,path,data,key,receipt:await response.json()});
  }
  const original = await json(0, setup);
  const context = "GM, I choose Keep Your Head to hold the calibration needle steady.";
  await json(0, setup + "/keep-start", {context,confirmed:true,character_revision:original.scene.keep.character_revision});
  const choice = (owner, kind) => waitFor(owner,director,view => view.work?.native.choices.find(item => item.kind === kind));
  const answer = async (owner, kind, answer) => {
    const assigned = await choice(owner,kind);
    await record(owner,setup + "/keep-choice", {
      id:assigned.id,revision:assigned.revision,role:owner === 2 ? "handler" : "pilot",answer,
    });
  };
  for (const owner of [0,1,2]) await answer(owner,"tag_window",{options:["pass"]});
  await answer(0,"actor_keep",{options:["tough","in_control"],denied:["desperate"]});
  const ruling = await choice(2,"handler_keep");
  const open = {operation:"open",kind:"choice",source:ruling.id,
    frame:{stakes:"Hold the calibration needle on its mark.",demands:[
      {id:"steady",question:"Can the pilot hold the mark?"}
    ]}};
  assert.equal((await request(people[0],director,open)).ok(),false);
  const packet = await json(2,director,open);
  const filed = await json(2,director,{operation:"propose",request:packet.request,proposal:{
    request_id:packet.packet.request_id,
    decision:{kind:"keep",verdict:"enough",narration:"The pilot holds the calibration mark.",
      assessments:[{demand_id:"steady",sufficient:true,evidence_ids:["source","native","traits"],
        traits:[{trait:"in_control",polarity:"are"}],private_reason:"PRIVATE_ASSESSMENT_CANARY"}]},
    cited_evidence:["source","native"],private_reasoning:"PRIVATE_GM_CANARY",
  }});
  const review = {operation:"review",proposal:filed.id};
  assert.equal((await request(people[1],director,review)).ok(),false);
  const intended = await json(2,director,review);
  assert(!JSON.stringify(intended).includes("PRIVATE_"));
  await record(2,director,{operation:"confirm",proposal:filed.id,approved:true});
  const resolved = await waitFor(0,setup,data => data.scene.keep.current?.state === "complete" && data.scene.keep.current);
  const second = await waitFor(1,setup,data => data.scene.keep.can_start && data);
  await json(1, setup + "/keep-start", {
    context:"Hold steady in the mock relay chamber.",confirmed:true,
    character_revision:second.scene.keep.character_revision,
  });
  const pending = [];
  for (const owner of [0,1,2]) pending.push((await choice(owner,"tag_window")).id);
  return {saved,original:resolved.id,pending};
}

async function verifySceneArtworkStability(browser, server) {
  const {page,view} = await openPilot(browser,server,"invited");
  await view.getByRole("button",{name:"Close inbox",exact:true}).click();
  await view.getByRole("button",{name:"Open Relay operations",exact:true}).click();
  const artwork = view.locator("#room-artwork");
  const figure = artwork.locator("figure");
  const dialog = view.getByRole("dialog",{name:/^Artwork/});
  const frame = await (await page.locator("iframe").elementHandle()).contentFrame();
  const refresh = view.locator("#refresh");
  async function select(id, label) {
    await view.getByRole("button",{name:/^(Select|Change) scene artwork$/}).click();
    await dialog.getByLabel("Artwork selection").selectOption(id);
    await dialog.getByRole("img",{name:label,exact:true}).waitFor();
  }
  async function save() {
    await dialog.getByRole("button",{name:"Save artwork",exact:true}).click();
    await dialog.waitFor({state:"hidden"});
  }
  async function refreshScene() {
    const data = page.waitForResponse(response => new URL(response.url()).pathname === "/api/player-setup");
    await refresh.evaluate(button => button.click());
    assert.equal((await data).status(),200);
    await view.locator("#refresh:enabled").waitFor();
  }
  async function holdDecode(label) {
    await frame.evaluate(alt => {
      const decode = HTMLImageElement.prototype.decode;
      const release = new Promise(resolve => { window.releaseSceneArtwork = resolve; });
      window.sceneArtworkDecoding = false;
      HTMLImageElement.prototype.decode = async function () {
        if (this.alt === alt) {
          window.sceneArtworkDecoding = true;
          await release;
        }
        return decode.call(this);
      };
      window.finishSceneArtwork = () => {
        HTMLImageElement.prototype.decode = decode;
        window.releaseSceneArtwork();
      };
    },label);
  }

  await select("scene-polar-ruins","Polar Ruins");
  await save();
  const ruins = artwork.getByRole("img",{name:"Polar Ruins",exact:true});
  const original = await ruins.elementHandle();
  const height = (await figure.boundingBox()).height;
  await refreshScene();
  await refreshScene();
  assert(await original.evaluate(img => img.isConnected && img.complete && img.naturalWidth > 0));
  assert.equal((await figure.boundingBox()).height,height);

  await select("scene-snowbound-transit-checkpoint","Snowbound Transit Checkpoint");
  await holdDecode("Snowbound Transit Checkpoint");
  await save();
  await frame.waitForFunction(() => window.sceneArtworkDecoding);
  await refreshScene();
  assert(await original.evaluate(img => img.isConnected));
  assert.equal((await figure.boundingBox()).height,height);
  await frame.evaluate(() => window.finishSceneArtwork());
  const checkpoint = artwork.getByRole("img",{name:"Snowbound Transit Checkpoint",exact:true});
  await checkpoint.waitFor();
  assert.equal(await original.evaluate(img => img.isConnected),false);
  assert.equal((await figure.boundingBox()).height,height);
  const replacement = await checkpoint.elementHandle();
  await refreshScene();
  assert(await replacement.evaluate(img => img.isConnected));

  await select("scene-empty-hangar","Empty Hangar");
  await holdDecode("Empty Hangar");
  await save();
  await frame.waitForFunction(() => window.sceneArtworkDecoding);
  await view.locator('[data-folder="scenes"]').click();
  await view.getByRole("button",{name:"Start Scene",exact:true}).click();
  const start = view.getByRole("dialog",{name:"Start Scene",exact:true});
  await start.getByLabel("Scene name").fill("Unillustrated room");
  await start.getByRole("button",{name:"Create room",exact:true}).click();
  await view.getByRole("heading",{name:"Unillustrated room",exact:true}).waitFor();
  await frame.evaluate(() => window.finishSceneArtwork());
  await refreshScene();
  assert.equal(await artwork.locator("img").count(),0);
  assert.equal(await replacement.evaluate(img => img.isConnected),false);
}

async function verifySceneIntel(browser, server, previous) {
  const recipient = await openPilot(browser, server, "other");
  const setup = "/api/player-setup";
  const share = setup + "/share-intel";
  const discovery = "The K-12 relay is jammed.\nPreferred route: <west stairs>.";
  const privateDialogue = "Private source dialogue. The recovery key is LANTERN.";
  const name = "Sealed intercept";
  const inbox = recipient.view.locator("#mail-entries");
  function api(person, route, data, key = randomUUID()) {
    return person.page.request.fetch(server.origin + route, {
      method:data ? "POST" : "GET", data,
      headers:{Authorization:"Bearer " + person.session, Origin:server.discord_activity_origin,
        "Idempotency-Key":key},
    });
  }
  if (previous) {
    const state = await (await api(recipient,setup)).json();
    assert.deepEqual(state.intel_mail,[previous.report]);
    assert(!state.directory.rooms.some(room => room.name === name));
    assert.equal((await api(recipient,previous.transcript)).status(),403);
    const link = inbox.locator(`[data-mail-id="intel:${previous.report.id}"]`);
    await link.click();
    const card = recipient.view.locator(`[data-mail-file="intel:${previous.report.id}"]`);
    await card.getByRole("heading",{name:"Intel from " + previous.report.callsign}).waitFor();
    assert.equal(await card.locator(".intel-report-body").textContent(),discovery);
    assert.equal(await card.locator(".intel-report-body *").count(),0);
    assert.equal(await card.locator("a, button").count(),0);
    assert(!((await card.textContent()).includes(name)));
    return;
  }

  const owner = await openPilot(browser, server, "invited");
  const handler = await openPilot(browser, server, "handler");
  await owner.view.getByRole("button",{name:"Close inbox",exact:true}).click();
  await owner.view.getByRole("button",{name:"Start Scene",exact:true}).click();
  const start = owner.view.getByRole("dialog",{name:"Start Scene",exact:true});
  await start.getByLabel("Scene name").fill(name);
  await start.getByRole("button",{name:"Create room",exact:true}).click();
  await owner.view.getByRole("heading",{name,exact:true}).waitFor();
  const ownerState = await (await api(owner,setup)).json();
  const recipientState = await (await api(recipient,setup)).json();
  const room = ownerState.directory.rooms.find(item => item.name === name).id;
  const transcript = "/api/rooms/" + room + "/transcript";
  const target = ownerState.intel_targets.find(item => item.callsign === recipientState.callsign);
  const ownerTarget = recipientState.intel_targets.find(item => item.callsign === ownerState.callsign);
  assert.deepEqual(ownerState.intel_targets,[target]);
  assert.equal((await api(recipient,transcript)).status(),403);
  const post = await api(owner,setup + "/room-post",{target:room,text:privateDialogue});
  assert.equal(post.status(),200,await post.text());
  assert.equal((await api(recipient,share,{room,recipients:[ownerTarget.id],text:"Forged discovery"})).status(),409);
  assert.equal((await api(owner,share,{room,recipients:[target.id,ownerTarget.id],text:"Invalid selection"})).status(),409);
  assert.equal((await (await api(recipient,setup)).json()).intel_mail.length,0);

  await owner.view.getByRole("button",{name:"Share Intel",exact:true}).click();
  const dialog = owner.view.getByRole("dialog",{name:"Share Intel",exact:true});
  await dialog.getByLabel("Discovery").fill(discovery);
  await dialog.getByRole("button",{name:"Send Intel",exact:true}).click();
  await dialog.getByText("Choose at least one recipient.",{exact:true}).waitFor();
  await dialog.getByRole("checkbox",{name:target.callsign,exact:true}).check();
  const sent = owner.page.waitForResponse(response => new URL(response.url()).pathname === share);
  await dialog.getByRole("button",{name:"Send Intel",exact:true}).click();
  const response = await sent;
  assert.equal(response.status(),200,await response.text());
  const {report:id} = await response.json();
  const key = response.request().headers()["idempotency-key"];
  const command = {room,recipients:[target.id],text:discovery};
  assert.deepEqual(await (await api(owner,share,command,key)).json(),{report:id});
  assert.equal((await api(owner,share,{...command,text:"Changed discovery"},key)).status(),409);
  await owner.view.getByText("Intel sent.",{exact:true}).waitFor();
  await recipient.view.getByRole("button",{name:"Close inbox",exact:true}).click();
  await recipient.view.locator("#inbox-toggle").click();
  await inbox.locator(`[data-mail-id="intel:${id}"]`).waitFor();
  const [report, ...extra] = (await (await api(recipient,setup)).json()).intel_mail;
  assert.deepEqual(extra,[]);
  assert.deepEqual(report,{id,callsign:ownerState.callsign,body:discovery,created:report.created});
  assert.equal((await (await api(owner,setup)).json()).intel_mail.length,0);
  assert.equal((await (await api(handler,setup)).json()).intel_mail,undefined);
  assert.equal((await api(recipient,transcript)).status(),403);
  const end = await api(owner,setup + "/room-end",{room});
  assert.equal(end.status(),200,await end.text());
  assert.equal((await api(owner,share,command)).status(),409);
  const archived = await (await api(owner,transcript)).json();
  assert(archived.archived_at);
  assert.deepEqual(archived.entries.map(entry => entry.body),[privateDialogue]);
  return {report,transcript};
}

async function verifySceneArchive(browser, server, previous) {
  const owner = await openPilot(browser, server, "invited");
  const closeInbox = owner.view.getByRole("button", {name:"Close inbox",exact:true});
  if (await closeInbox.isVisible()) await closeInbox.click();
  const name = "After-action archive";
  const archive = owner.view.getByRole("button",{name:"Scene Archive",exact:true});
  function api(person, route, data) {
    return person.page.request.fetch(server.origin + route, {
      method:data ? "POST" : "GET", data,
      headers:{Authorization:"Bearer " + person.session, Origin:server.discord_activity_origin,
        "Idempotency-Key":randomUUID()},
    });
  }
  const setup = "/api/player-setup";
  const privateName = "Supply seal inspection";
  if (previous) {
    await archive.click();
    const search = owner.view.getByRole("searchbox",{name:"Search archive"});
    const mainEntry = owner.view.getByRole("button",{name:"Open " + name,exact:true});
    const privateEntry = owner.view.getByRole("button",{name:"Open " + privateName,exact:true});
    await mainEntry.waitFor();
    await privateEntry.waitFor();
    const ended = new Date(previous.snapshot.archived_at * 1000).toISOString();
    const entryTime = owner.view.locator(".scene-directory-entry").filter({has:mainEntry}).locator("time");
    assert.equal(await entryTime.getAttribute("datetime"), ended);
    assert.match(await entryTime.textContent(), /^Ended /);
    for (const query of ["AFTER-ACTION", "hangar deck", previous.peerCallsign.toLowerCase()]) {
      await search.fill(query);
      await mainEntry.waitFor();
      await privateEntry.waitFor({state:"hidden"});
    }
    await search.fill("outpost k-12");
    await privateEntry.waitFor();
    await mainEntry.waitFor({state:"hidden"});
    await search.fill("nothing by this name");
    await owner.view.getByText("No archived scene files match this search.",{exact:true}).waitFor();
    await search.fill("hangar " + previous.peerCallsign);
    const refreshed = owner.page.waitForResponse(response => new URL(response.url()).pathname === setup);
    await owner.view.locator("#refresh").evaluate(button => button.click());
    await refreshed;
    assert.equal(await search.inputValue(),"hangar " + previous.peerCallsign);
    assert(await search.evaluate(input => input === document.activeElement));
    await mainEntry.click();
    await owner.view.getByText("Archived · Read-only",{exact:true}).waitFor();
    assert.equal(await owner.view.locator("#room-actions time").getAttribute("datetime"), ended);
    assert.equal(await owner.view.getByLabel("Dialogue or narration").count(),0);
    assert.deepEqual(await (await api(owner, previous.route)).json(), previous.snapshot);
    await owner.view.locator('[data-folder="profile"]').click();
    const mailbox = (await (await api(owner,setup)).json()).scene_mail;
    for (const receipt of previous.snapshot.receipts.slice().reverse()) {
      const filed = mailbox.filter(entry => entry.id === receipt.id);
      assert.deepEqual(filed, [{...receipt, archived_at:previous.snapshot.archived_at}]);
      await owner.view.locator("#inbox-toggle").click();
      const link = owner.view.locator(`#mail-entries [data-mail-id="receipt:${receipt.id}"]`);
      await link.getByText("Archived",{exact:true}).waitFor();
      await link.click();
      await owner.view.getByRole("heading",{name,exact:true}).waitFor();
      const entry = owner.view.locator(`#dialogue-entries [data-scene-receipt="${receipt.id}"]:focus`);
      await entry.getByText(receipt.result.ruling,{exact:true}).waitFor();
      await entry.getByText("Original roll · " + receipt.roll.faces.join(" + ") + " · Total " + receipt.roll.pre_total,
        {exact:true}).waitFor();
      assert.equal(await entry.getByRole("button").count(),0);
      assert.equal(await owner.view.getByLabel("Dialogue or narration").count(),0);
    }
    return;
  }
  await owner.view.getByRole("button",{name:"Start Scene",exact:true}).click();
  const start = owner.view.getByRole("dialog",{name:"Start Scene",exact:true});
  await start.getByLabel("Scene name").fill(name);
  const refreshed = owner.page.waitForResponse(response => new URL(response.url()).pathname === setup);
  await start.getByLabel("Location (optional)").fill("Hangar Deck");
  await owner.view.locator("#refresh").evaluate(button => button.click());
  await refreshed;
  await start.getByLabel("Scene name").press("End");
  assert.equal(await start.getByLabel("Scene name").inputValue(),name);
  await start.getByRole("button",{name:"Create room",exact:true}).click();
  await owner.view.getByRole("heading",{name,exact:true}).waitFor();
  const scene = (await (await api(owner,setup)).json()).directory.rooms.find(room => room.name === name);
  const route = "/api/rooms/" + scene.id + "/transcript";
  const other = await openPilot(browser, server, "other");
  assert(!((await api(other,setup + "/room-end",{room:scene.id})).ok()));
  assert(!((await api(other,route)).ok()));
  const issued = await api(owner,setup + "/invite-issue",{target:scene.id});
  assert.equal(issued.status(),200,await issued.text());
  const redeemed = await api(other,setup + "/invite-redeem",{code:(await issued.json()).code});
  assert.equal(redeemed.status(),200,await redeemed.text());
  const line = "The crew logs the final relay reading.";
  await owner.view.getByLabel("Dialogue or narration").fill(line);
  await owner.view.getByRole("button",{name:"File transmission",exact:true}).click();
  await owner.view.getByText(line,{exact:true}).waitFor();
  const handler = await openPilot(browser, server, "handler");
  async function waitFor(person, pick) {
    for (let attempt = 0; attempt < 60; attempt++) {
      const response = await api(person, setup);
      assert.equal(response.status(), 200, await response.text());
      const value = pick(await response.json());
      if (value) return value;
      await new Promise(resolve => setTimeout(resolve, 120));
    }
    throw new Error("The expected scene state did not load.");
  }
  const answer = async (person, role, kind, choice) => {
    const assigned = await waitFor(person, data => role === "handler"
      ? data.handler_choices?.find(card => card.room === scene.id && card.choice.kind === kind)?.choice
      : data.active_scene?.keep?.choices.find(card => card.kind === kind));
    const saved = await api(person,setup + "/keep-choice",{
      room:scene.id,id:assigned.id,revision:assigned.revision,role,answer:choice,
    });
    assert.equal(saved.status(),200,await saved.text());
  };
  for (const [context, ruling] of [
    ["Hold the relay steady.", "The relay holds."],
    ["Wait for the last transmission.", "The last transmission gets through."],
  ]) {
    const current = await waitFor(owner, data => data.active_scene?.id === scene.id && data.active_scene.keep);
    const roll = await api(owner,setup + "/keep-start",{
      room:scene.id, context, confirmed:true, character_revision:current.character_revision,
    });
    assert.equal(roll.status(),200,await roll.text());
    const {action_id:id} = await roll.json();
    const busy = await api(owner,setup + "/room-end",{room:scene.id});
    assert.equal(busy.status(),409,await busy.text());
    assert.match((await busy.json()).error,/pending action/i);
    if (context === "Hold the relay steady.") {
      const tag = await waitFor(owner,data => data.scene_mail.find(entry => entry.id === id)?.pending.find(choice => choice.kind === "tag_window"));
      assert.equal(tag.owner,"viewer");
      await owner.view.locator("#inbox-toggle").click();
      await owner.view.locator("#dispatch-decisions").click();
      const dispatch = owner.view.locator(`#mail-entries [data-mail-id="choice:${tag.id}:${tag.revision}"]`);
      await dispatch.getByText("RESPONSE REQUIRED",{exact:true}).waitFor();
      const profile = await (await api(owner,setup)).json();
      assert((await dispatch.getAttribute("aria-description")).includes("Assigned to " + profile.callsign));
      const count = await owner.view.locator("#decision-count").textContent();
      assert(Number(count) > 0);
      await dispatch.click();
      const play = owner.view.getByRole("dialog",{name:/Keep Your Head/i});
      await play.locator("#scene-action-record").getByText("Action required",{exact:true}).waitFor();
      await play.locator("#scene-action-record").getByText(name,{exact:true}).waitFor();
      await play.getByRole("button",{name:"Close scene Play",exact:true}).click();
      await owner.view.locator("#inbox-toggle").click();
      await dispatch.waitFor();
      assert.equal(await dispatch.locator("..").getAttribute("data-unread"),"false");
      assert.equal(await owner.view.locator("#decision-count").textContent(),count);
      await owner.view.getByRole("button",{name:"Close inbox",exact:true}).click();
    }
    await answer(owner,"pilot","tag_window",{options:["pass"]});
    await answer(handler,"handler","tag_window",{options:["pass"]});
    await answer(owner,"pilot","actor_keep",{options:["tough","in_control"],denied:["desperate"]});
    await answer(handler,"handler","handler_keep",{flag:true,text:ruling});
    await waitFor(owner,data => {
      const play = data.active_scene?.keep?.current;
      return play?.id === id && play.state === "complete" && !data.active_scene.locked;
    });
    if (context === "Hold the relay steady.") {
      await owner.view.locator("#inbox-toggle").click();
      await owner.view.locator("#dispatch-decisions").click();
      await owner.view.locator("#mail-entries").getByText("NO RESPONSE ASSIGNED",{exact:true}).waitFor();
      await owner.view.getByRole("button",{name:"Close inbox",exact:true}).click();
      await owner.view.locator('#scene-play-options button[data-play="keep_your_head"]').click();
      const filed = owner.view.getByRole("dialog",{name:/Keep Your Head/i});
      await filed.locator("#scene-action-record").getByText("Filed",{exact:true}).waitFor();
      await filed.getByRole("button",{name:"Close scene Play",exact:true}).click();
      await owner.view.locator('[data-folder="frame"]').click();
      await owner.view.locator("#notice").filter({hasText:"Log equipment variances before handover."}).waitFor();
      await owner.view.getByRole("button",{name:"Back",exact:true}).click();
    }
  }
  await owner.view.getByRole("button",{name:"End Scene",exact:true}).click();
  const end = owner.view.getByRole("dialog",{name:"End Scene",exact:true});
  await end.getByRole("button",{name:"End and archive scene",exact:true}).click();
  await owner.view.getByText("Archived · Read-only",{exact:true}).waitFor();
  assert.equal(await owner.view.getByLabel("Dialogue or narration").count(),0);
  const snapshot = await (await api(owner,route)).json();
  assert(snapshot.archived_at);
  assert.equal(snapshot.entries.at(-1).body,line);
  assert.equal(snapshot.receipts.length,2);
  assert.deepEqual(snapshot.receipts[0].roll.faces,[4,5]);
  const participant = await (await api(other,route)).json();
  assert.deepEqual(participant.entries,snapshot.entries);
  assert.equal(participant.receipts.length,0);
  assert.deepEqual(await (await api(owner,setup + "/room-end",{room:scene.id})).json(),
    {room:scene.id,archived_at:snapshot.archived_at});
  for (const [step, data] of [
    ["room-post",{target:scene.id,text:"Late write"}],
    ["enter-scene",{room:scene.id}],
    ["invite-issue",{target:scene.id}],
  ]) {
    const blocked = await api(owner,setup + "/" + step,data);
    assert.equal(blocked.status(),409,await blocked.text());
  }
  const created = await api(owner,setup + "/room-create",{name:privateName,location:"outpost"});
  assert.equal(created.status(),200,await created.text());
  const {room:privateRoom} = await created.json();
  const privateArchive = await api(owner,setup + "/room-end",{room:privateRoom});
  assert.equal(privateArchive.status(),200,await privateArchive.text());
  const otherSetup = await (await api(other,setup)).json();
  assert(!otherSetup.scene_mail.some(receipt => receipt.room === scene.id));
  const peerCallsign = otherSetup.callsign;
  assert(otherSetup.directory.rooms.find(room => room.id === scene.id).archived_pilots.includes(peerCallsign));
  assert(!otherSetup.directory.rooms.some(room => room.id === privateRoom));
  assert.equal((await api(other,"/api/rooms/" + privateRoom + "/transcript")).status(),403);
  return {route,snapshot,peerCallsign};
}

async function openPilot(browser, server, role, failFirstMissionPost = false, campaignId, channelId, options = {}) {
  const page = await browser.newPage();
  page.setDefaultTimeout(8000);
  if (!discordOffline) {
    await page.goto(server.pilots[role === "invited" ? "Invited pilot" : "Other pilot"]);
    assert.equal(new URL(page.url()).pathname, "/activity");
    await page.locator("#inbox-toggle").click();
    return {page, view:page};
  }

  const proxy = server.discord_activity_origin;
  const guild = "222222222222222222";
  const launch = new URL(proxy);
  if (!dmOffline && !options.dm) launch.searchParams.set("guild_id", guild);
  if (campaignId) launch.searchParams.set("campaign", campaignId);
  if (channelId) launch.searchParams.set("channel_id", channelId);
  const discordUser = discordUsers[role];
  const failingReads = new Set(dmOffline && !failFirstMissionPost
    ? ["/api/discord/challenge", "/api/mission-offers"]
    : []);
  let losePlayStartResponse = dmOffline && failFirstMissionPost;
  let session;
  let assetVersion;
  await page.route("https://offline-discord.test/", route => route.fulfill({
    contentType:"text/html",
    body:`<style>body{margin:0} iframe{display:block;width:100vw;height:100vh;border:0}</style><iframe title="Activity" src="${launch.href}"></iframe>`,
  }));
  await page.route(proxy + "/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const file = url.pathname;
    if (/^\/(?:(?:foundation|artwork)\.css|(?:foundation-ui|artwork-ui|player-setup|battlefield-ui|communications-ui|discord-sdk)\.js)$/.test(file)) {
      const version = url.searchParams.get("v");
      assert.match(version ?? "", /^[a-f0-9]{16}$/);
      assetVersion ??= version;
      assert.equal(version,assetVersion);
    }
    const fail = failFirstMissionPost && request.method() === "POST" && /^\/api\/mission-offers\/.+\/response$/.test(file);
    const gatewayError = {
      status:502, contentType:"text/html",
      body:"<!DOCTYPE html><title>Temporary gateway error</title>",
    };
    if (failingReads.delete(file)) return route.fulfill(gatewayError);
    const loseStartedPlay = losePlayStartResponse && file === "/api/player-setup/keep-start";
    if (fail) {
      failFirstMissionPost = false;
      if (!dmOffline) return route.fulfill(gatewayError);
    }
    if (file === "/discord-sdk.js") {
      return route.fulfill({
        contentType:"text/javascript",
        body:`export class DiscordSDK {
          guildId = new URLSearchParams(location.search).get("guild_id");
          channelId = new URLSearchParams(location.search).get("channel_id");
          ready = async () => {};
          commands = {
            openInviteDialog: async () => { document.documentElement.dataset.nativeInviteOpened = "true"; },
            authorize: async options => {
              if (!options.state || !options.scope.includes("guilds.members.read")) throw new Error("Expected scoped OAuth.");
              return {code:${JSON.stringify(role)}};
            },
            authenticate: async ({access_token}) => {
              if (access_token !== ${JSON.stringify(role)}) throw new Error("Unexpected test token.");
              return {user:{id:${JSON.stringify(discordUser)}}};
            },
          };
        }`,
      });
    }
    const post = request.method() === "POST";
    const headers = request.headers();
    delete headers.host;
    delete headers["content-length"];
    if (post) headers.origin = proxy;
    let upstream;
    let body;
    try {
      upstream = await fetch(server.origin + file + url.search, {
        method:request.method(), headers, body:post ? request.postData() : undefined,
        signal:AbortSignal.timeout(8000),
      });
      body = Buffer.from(await upstream.arrayBuffer());
    } catch {
      if (page.isClosed()) return;
      return route.fulfill({
        status:503, contentType:"application/json",
        body:JSON.stringify({error:"The offline Activity host was unreachable."}),
      }).catch(() => {});
    }
    if (fail || loseStartedPlay) {
      if (loseStartedPlay) losePlayStartResponse = false;
      assert.equal(upstream.status, 200);
      return route.fulfill(gatewayError);
    }
    if (file === "/api/discord/session" && upstream.ok) {
      const authorization = JSON.parse(body);
      assert.equal(authorization.discord_user_id, discordUser);
      assert(!("refresh_token" in authorization));
      session = authorization.session;
    }
    return route.fulfill({
      status:upstream.status, contentType:upstream.headers.get("content-type"), body,
    });
  });
  await page.goto("https://offline-discord.test/");
  const view = page.frameLocator("iframe");
  const auth = view.locator("#auth-dialog");
  await auth.getByRole("heading", {name:"Foundation access terminal", exact:true}).waitFor();
  try {
    await auth.waitFor();
  } catch (error) {
    const message = await view.locator("#status").textContent({timeout:1000}).catch(() => "");
    throw new Error(`Discord fixture as ${role} did not open sign-in: ${message}\n${server.diagnostics()}`, {cause:error});
  }
  if (process.env.HARPY_AUTH_CAPTURE && failFirstMissionPost) {
    await page.locator("iframe").screenshot({path:process.env.HARPY_AUTH_CAPTURE});
  }
  await auth.locator("#sign-in").click();
  if (options.pickCampaign) {
    const picker = view.getByRole("dialog",{name:"Choose a campaign"});
    await picker.getByLabel("Campaign",{exact:true}).selectOption({label:options.pickCampaign});
    await picker.getByRole("button",{name:"Open campaign"}).click();
  }
  try {
    await view.locator("#pilot[data-ready]").waitFor();
  } catch (error) {
    const status = await view.locator("#status").textContent();
    const authStatus = await view.locator("#auth-status").textContent();
    const setupStatus = await view.locator("#setup").textContent();
    throw new Error(`Discord fixture sign-in as ${role} did not load: ${status || authStatus || setupStatus}`, {cause:error});
  }
  await auth.waitFor({state:"hidden"});
  if (!await view.locator("#enrollment-dialog").isVisible()) await view.locator("#inbox-toggle").click();
  assert(session);
  return {page, view, get session() { return session; }};
}

async function selectPlayCategory(scope, category) {
  await scope.getByRole("group", {name:"Play categories", exact:true})
    .getByRole("button", {name:category, exact:true}).click();
}

async function verifyOrders(pilot, request, origin) {
  const {view, page} = pilot;
  const closeInbox = view.getByRole("button", {name:"Close inbox", exact:true});
  if (await closeInbox.isVisible()) await closeInbox.click();
  await view.getByRole("button", {name:"Battlefield", exact:true}).click();
  const load = async () => {
    const response = await request(pilot, "/api/battlefield");
    assert.equal(response.status,200);
    return response.json();
  };
  const send = (path, data, key = randomUUID()) => request(pilot, "/api/battlefield/" + path, {
    method:"POST", headers:{Origin:origin,"Content-Type":"application/json","Idempotency-Key":key},
    body:JSON.stringify(data),
  });
  const plays = view.getByRole("dialog", {name:"Choose a Play"});
  const playMenu = view.getByRole("button", {name:"Play", exact:true});
  const receive = plays.getByRole("button", {name:"Receive Orders", exact:true});
  const disobey = plays.getByRole("button", {name:"Disobey Orders", exact:true});
  const receiving = view.getByLabel("Respond to the direct order", {exact:true});
  const saveResponse = view.getByRole("button",{name:"Save order response",exact:true});
  const issue = async text => {
    await view.getByText("Test Handler · Issue drill order", {exact:true}).click();
    await view.getByLabel("Direct order to your pilot", {exact:true}).fill(text);
    await view.getByRole("button",{name:"Issue drill order",exact:true}).click();
    await playMenu.click();
    await selectPlayCategory(plays, "Talk");
    await receive.waitFor();
  };
  const assertNoOrder = async () => {
    await playMenu.click();
    assert.equal(await receive.count(),0);
    assert.equal(await disobey.count(),0);
    await plays.getByRole("button", {name:"Close Play menu"}).click();
  };
  await assertNoOrder();
  const fake = {choice:randomUUID(), revision:1, sheet_revision:(await load()).sheet_revision, account:"No source", heat:0, witnessed:false, confirmed:true};
  assert.equal((await send("disobey_orders", fake)).status,409);

  await issue("Hold the relay perimeter until the all-clear.");
  const issued = await load();
  assert.deepEqual(issued.actions.map(item => item.id),["receive_orders"]);
  const opponent = issued.roster.find(character => !character.controlled);
  if (opponent) {
    await plays.getByLabel("Character",{exact:true}).selectOption(opponent.id);
    assert.equal(await receive.count(),0);
    assert.equal(await plays.getByText("Receive Orders",{exact:true}).count(),0);
    await plays.getByLabel("Character",{exact:true}).selectOption(issued.roster.find(character => character.controlled).id);
  }
  await receive.click();
  await plays.getByRole("button", {name:"Open Play", exact:true}).click();
  await receiving.selectOption("obedient");
  await saveResponse.click();
  await view.getByText("Response · Obedient",{exact:true}).waitFor();
  const followed = await load();
  assert.equal(followed.play.result.response,"obedient");
  assert.equal(followed.play.receipt,null);
  await assertNoOrder();

  await issue("Stand down and turn over the relay console.");
  await receive.click();
  await plays.getByRole("button", {name:"Open Play", exact:true}).click();
  await receiving.selectOption("disobey");
  await saveResponse.click();
  await saveResponse.waitFor({state:"hidden"});
  await playMenu.click();
  await disobey.waitFor();
  assert.equal(await receive.count(),0);
  const staged = await load();
  assert.deepEqual(staged.actions.map(item => item.id),["disobey_orders"]);
  const requestChoice = staged.actions[0].order.choice;
  assert.equal((await send("choice", {role:"opponent",id:requestChoice.id,revision:requestChoice.revision,answer:{options:["pass"]}})).status,409);
  await disobey.click();
  await plays.getByRole("button", {name:"Open Play", exact:true}).click();
  await view.getByLabel("Describe the refusal",{exact:true}).fill("I keep the console under my control.");
  await view.getByLabel("Did a Foundation member witness the refusal?").selectOption("no");
  const roll = page.waitForResponse(response => response.url().endsWith("/api/battlefield/disobey_orders"));
  await view.getByRole("button",{name:"Roll Disobey Orders",exact:true}).click();
  const started = await roll;
  assert.equal(started.status(),200);
  const original = await started.json();
  const posted = started.request();
  const repeat = await send("disobey_orders", posted.postDataJSON(), posted.headers()["idempotency-key"]);
  assert.equal(repeat.status,200);
  assert.deepEqual(await repeat.json(),original);
  for (const role of ["Pilot","Test Handler",...(opponent ? ["Drill opponent"] : [])]) {
    await view.getByRole("button",{name:role + " · Pass Tag window",exact:true}).click();
  }
  const actorChoice = view.locator('#tactical-controls article[data-role="pilot"]');
  const handlerChoice = view.locator('#tactical-controls article[data-role="handler"]');
  const pending = actorChoice.or(handlerChoice).first();
  await pending.getByRole("button",{name:"Save refusal choice",exact:true}).waitFor();
  const initial = (await load()).choices.find(choice => choice.kind === "actor_disobey");
  if (initial?.schema.some(field => field.key === "options")) {
    await actorChoice.getByLabel("Choose the refusal branch").selectOption(opponent ? "follow" : "tag_heat");
    if (opponent) {
      const target = initial.schema.find(field => field.key === "member").options[0];
      assert.equal(target[1],opponent.label);
      await actorChoice.getByLabel("Pilot to follow you").selectOption(target[0]);
    } else {
      await actorChoice.getByLabel("New Tag (Tag + Heat branch)").fill("Defiant");
      await actorChoice.getByLabel("Heat gained (Tag branch)").selectOption("1");
    }
    await actorChoice.getByRole("button",{name:"Save refusal choice",exact:true}).click();
    if (opponent) {
      const follower = view.locator('#tactical-controls article[data-role="opponent"]');
      await follower.getByLabel("Follow immediately without thinking?").selectOption("yes");
      await follower.getByRole("button",{name:"Save refusal choice",exact:true}).click();
    }
  } else if (initial) {
    await actorChoice.getByLabel("Act immediately without thinking?").selectOption("yes");
    await actorChoice.getByRole("button",{name:"Save refusal choice",exact:true}).click();
  }
  await handlerChoice.getByLabel("Does the Handler find out?").selectOption("yes");
  await handlerChoice.getByRole("button",{name:"Save refusal choice",exact:true}).click();
  await view.getByText("Handler discovered the refusal",{exact:true}).waitFor();
  const saved = await load();
  assert.equal(saved.play.result.response,"disobey");
  assert.equal(saved.play.result.response_play,saved.refusal.id);
  assert.equal(saved.refusal.result.handler_knows,true);
  if (tacticalTier) assert.equal(saved.refusal.result.tier,tacticalTier);
  assert.equal(saved.refusal.result.can_disobey,saved.refusal.result.tier !== "low");
  assert.equal((await send("disobey_orders", posted.postDataJSON())).status,409);
  await assertNoOrder();
  return {play:saved.play, refusal:saved.refusal, followed:followed.play};
}

async function verifyHud({view, page}) {
  const originalSize = page.viewportSize();
  const header = view.locator(".activity-header");
  const inbox = view.getByRole("region",{name:"Inbox",exact:true});
  const inboxButton = view.locator("#inbox-toggle");
  const theme = view.getByRole("button",{name:"Toggle light and dark mode"});
  const present = view.getByRole("region",{name:"Present Pilots",exact:true});
  const closeInbox = view.getByRole("button",{name:"Close inbox",exact:true});
  const folder = label => view.getByRole("navigation",{name:"Campaign folders"}).getByRole("button",{name:label,exact:true});
  await closeInbox.click();
  const priorTheme = await theme.getAttribute("aria-pressed");
  await theme.click();
  const newTheme = priorTheme === "true" ? "light" : "dark";
  for (const [label, context] of [["Scenes","Scenes / Hangar Deck"],["Battlefield","Battlefield"]]) {
    await folder(label).click();
    assert.equal(await folder(label).getAttribute("aria-current"),"page");
    assert.equal(await view.locator("#desk-context").textContent(),context);
    assert.equal(await view.locator("html").getAttribute("data-theme"),newTheme);
    await present.getByRole("button",{name:/^SYNTH \| /}).waitFor();
    await inboxButton.click();
    await inbox.waitFor();
    await inbox.getByText("Response saved · Accepted",{exact:true}).waitFor();
    await closeInbox.click();
    assert(await inboxButton.evaluate(button => document.activeElement === button));
  }
  await folder("Scenes").click();
  assert.equal(await header.evaluate(node => getComputedStyle(node).position),"sticky");
  assert.match(await folder("Scenes").evaluate(node => getComputedStyle(node).fontFamily),/monospace/);
  assert.equal(await view.locator("main").evaluate(node => getComputedStyle(node).backgroundImage),"none");
  assert.match(await view.locator(".masthead").evaluate(node => getComputedStyle(node).backgroundImage),/repeating-linear-gradient/);
  const activity = await (await page.locator("iframe").elementHandle()).contentFrame();
  for (const width of [1024,736,480,320]) {
    await page.setViewportSize({width,height:720});
    await activity.waitForFunction(expected => innerWidth === expected,width);
    assert(await header.evaluate(node => Array.from(node.querySelectorAll("button"))
      .filter(button => button.getClientRects().length).every(button => {
        const rect = button.getBoundingClientRect();
        return rect.left >= 0 && rect.right <= document.documentElement.clientWidth + 1;
      })),`Header controls overflow at ${width}px`);
    if (width === 320) assert((await header.boundingBox()).height <= 150, "Narrow masthead is taller than it needs to be");
    const {locations, work, communications} = await view.locator(".layout").evaluate(layout => {
      const bounds = selector => layout.querySelector(selector).getBoundingClientRect().toJSON();
      return {locations:bounds(".locations"), work:bounds("main"), communications:bounds("#desk-rail")};
    });
    const aligned = width === 1024 ? locations.right <= work.left + 1 && work.right <= communications.left + 1
      : width === 736 ? locations.bottom <= work.top + 1 && work.right <= communications.left + 1
      : locations.bottom <= work.top + 1 && work.bottom <= communications.top + 1;
    assert(aligned,`Desk panels overlap at ${width}px: ${JSON.stringify({locations, work, communications})}`);
  }
  await inboxButton.click();
  await inbox.waitFor();
  assert(await inbox.evaluate(node => {
    const rect = node.getBoundingClientRect();
    return rect.left >= 0 && rect.right <= document.documentElement.clientWidth + 1 && rect.bottom <= innerHeight + 1;
  }));
  await closeInbox.click();
  if (originalSize) await page.setViewportSize(originalSize);
  await theme.click();
  await view.locator("#location-list").getByRole("button",{name:/Outpost K-12/}).click();
  await view.getByRole("heading",{name:"Outpost K-12",exact:true}).waitFor();
  assert.equal(await present.locator("#presence-context").textContent(),"Outpost K-12");
  await present.getByText("No pilots present.",{exact:true}).waitFor();
  await view.locator("#location-list").getByRole("button",{name:/Hangar Deck/}).click();
  await present.getByRole("button",{name:/^SYNTH \| /}).waitFor();
  await folder("Cadre Status").click();
  await view.locator("#cadre-data").getByRole("button",{name:/^SYNTH \| /}).click();
  await view.locator("#profile-pane").getByText("SYNTH",{exact:true}).waitFor();
  await view.getByRole("button",{name:"Back",exact:true}).click();
  await view.getByRole("heading",{name:"Cadre Status",exact:true}).waitFor();
  await folder("Scenes").click();
}

async function verifyArtwork({view}) {
  const folder = label => view.getByRole("navigation",{name:"Campaign folders"}).getByRole("button",{name:label,exact:true});
  await view.getByRole("button",{name:"Close inbox",exact:true}).click();
  const dialog = view.locator("#artwork-dialog");
  const theme = view.getByRole("button", {name:"Toggle light and dark mode"});
  const panelColor = () => dialog.locator(".terminal-panel").evaluate(panel => getComputedStyle(panel).backgroundColor);
  const image = async (container, label) => {
    const picture = container.getByRole("img", {name:label,exact:true});
    await picture.waitFor();
    for (let attempt = 0; attempt < 40; attempt++) {
      if (await picture.evaluate(item => item.complete && item.naturalWidth > 0)) return;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.fail(label + " did not decode");
  };
  async function choose(kind, id, label) {
    await view.getByRole("button",{name:"Select " + kind + " artwork",exact:true}).click();
    await dialog.getByLabel("Artwork selection").selectOption(id);
    assert.equal(await dialog.locator("#artwork-state").textContent(), "READY TO FILE");
    await image(dialog, label);
    await dialog.getByRole("button",{name:"Save artwork",exact:true}).click();
    await dialog.waitFor({state:"hidden"});
    await image(view.locator(".record-artwork--" + kind), label);
  }
  await view.getByRole("button",{name:"Open Relay operations",exact:true}).click();
  await choose("scene", "scene-empty-hangar", "Empty Hangar");
  const priorColor = await panelColor();
  await theme.click();
  await folder("Pilot Profile").click();
  await choose("pilot", "pilot-sorrow", "SORROW");
  assert.notEqual(await panelColor(), priorColor);
  await theme.click();
  await folder("Frame Status").click();
  await choose("frame", "frame-janus", "JANUS");
  await view.getByRole("button",{name:"Change frame artwork",exact:true}).click();
  await dialog.getByLabel("Artwork selection").selectOption("");
  await dialog.getByRole("button",{name:"Save artwork",exact:true}).click();
  await dialog.waitFor({state:"hidden"});
  await view.getByRole("button",{name:"Select frame artwork",exact:true}).waitFor();
  assert.equal(await view.locator(".record-artwork--frame img").count(), 0);
  await folder("Scenes").click();
  await view.getByRole("button",{name:"Open Relay operations",exact:true}).click();
  await image(view.locator(".record-artwork--scene"), "Empty Hangar");
  const line = "Reporting from the relay with portrait on file.";
  await view.getByLabel("Dialogue or narration").fill(line);
  await view.getByRole("button", {name:"File transmission",exact:true}).click();
  const post = view.locator(".dialogue-entry").filter({hasText:line});
  const portrait = post.locator(".dialogue-portrait img");
  await portrait.waitFor();
  assert.equal(await portrait.getAttribute("alt"), "");
  assert(await portrait.evaluate(item => item.complete && item.naturalWidth > 0));
  await folder("Pilot Profile").click();
  await image(view.locator(".record-artwork--pilot"), "SORROW");
  await folder("Scenes").click();
  if (!(await post.isVisible())) await view.getByRole("button",{name:"Open Relay operations",exact:true}).click();
  await portrait.waitFor();
}

async function verifyPlayRail({page, view}) {
  const inventory = spawnSync(python, ["-B", "-c", `
import json
import os
from types import SimpleNamespace
import mission_lab
from girlframe.engine.creation import official_frame
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.services.m3_access import load_registry
from play_catalog import character_plays

os.environ["GIRLFRAME_RULES_REGISTRY"] = str(mission_lab.ENGINE / "rules" / "registry.json")
registry = load_registry()
catalogs = {}
for girl, frame in zip(GIRL_TYPES, FRAME_TYPES, strict=True):
    sheet = SimpleNamespace(girl=girl, frame=frame, frame_runtime=None,
                            blocked_plays=[], frame_scrapped=False)
    catalogs[girl + " / " + frame] = character_plays(registry, sheet, owns_sheet=True)
    upgrades = [rule.id for rule in registry.entries
                if rule.frame_playbook == official_frame(frame) and rule.frame_rule == "requisition"]
    sheet.frame_runtime = SimpleNamespace(acquired_rules=upgrades)
    catalogs[frame + " / upgraded"] = character_plays(registry, sheet, owns_sheet=True)
    assert character_plays(registry, sheet, owns_sheet=False) == catalogs[girl + " / " + frame]
print(json.dumps(catalogs))
`], {cwd:__dirname, encoding:"utf8"});
  assert.equal(inventory.status, 0, inventory.stderr || String(inventory.error));
  const catalogs = JSON.parse(inventory.stdout);
  const extras = group => new Set(Object.values(catalogs).flat().filter(play => play.group === group).map(play => play.id));
  assert.equal(Object.keys(catalogs).length, 20);
  assert(extras("girl").has("mockingbird_person"));
  assert(extras("frame").has("ankou_processor"));
  assert(extras("frame").has("pandora_birth"));

  const folder = name => view.getByRole("navigation",{name:"Campaign folders"})
    .getByRole("button",{name,exact:true});
  const closeInbox = view.getByRole("button",{name:"Close inbox",exact:true});
  if (await closeInbox.isVisible()) await closeInbox.click();
  await folder("Pilot Profile").click();
  const profile = view.locator("#profile-pane");
  const talk = profile.getByRole("group",{name:"Talk Plays",exact:true});
  const recover = profile.getByRole("group",{name:"Recover Plays",exact:true});
  await profile.getByText("Girl and Frame Plays",{exact:true}).click();
  await selectPlayCategory(profile, "Talk");
  await talk.getByRole("button",{name:"Bad at Being a Person",exact:true}).click();
  const picker = view.getByRole("dialog",{name:"Bad at Being a Person",exact:true});
  await picker.getByRole("heading",{name:"Which scene is this Play for?",exact:true}).waitFor();
  await picker.getByRole("button",{name:"Close scene picker",exact:true}).click();
  await selectPlayCategory(profile, "Recover");
  await recover.getByRole("button",{name:"Living Battery",exact:true}).waitFor();
  assert(!await talk.isVisible());
  const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === "/api/player-setup");
  await view.getByRole("button",{name:"Check for updates",exact:true}).click();
  assert.equal((await refreshed).status(), 200);
  await recover.getByRole("button",{name:"Living Battery",exact:true}).waitFor();

  const mismatch = await profile.locator(".play-rail").evaluate(async (_, catalogs) => {
    const asset = performance.getEntriesByType("resource")
      .find(({name}) => new URL(name).pathname === "/foundation-ui.js");
    const {playRail, playCard} = await import(asset.name);
    for (const [name, plays] of Object.entries(catalogs)) {
      const entries = plays.map(play => ({play, row:playCard(play)}));
      const rail = playRail(entries);
      for (const {play,row} of entries) {
        if (!["talk","fight","scan","recover"].includes(play.category)) return name + " / uncategorized: " + play.id;
        rail.querySelector(`[data-play-category="${play.category}"]`).click();
        const panel = row.closest("[data-play-panel]");
        if (panel?.hidden !== false || panel.dataset.playPanel !== play.category ||
            row.querySelector("strong").textContent !== play.label) return name + " / " + play.id;
      }
      if (rail.querySelectorAll(".play-card").length !== new Set(plays.map(play => play.id)).size) return name;
    }
    return null;
  }, catalogs);
  assert.equal(mismatch, null);

  await folder("Scenes").click();
  await view.getByRole("button",{name:"Open Relay operations",exact:true}).click();
  const scene = view.locator("#scene-play-options");
  const popup = view.locator("#scene-action-dialog");
  await selectPlayCategory(scene, "Recover");
  await scene.locator('button[data-play="keep_your_head"]').click();
  await popup.getByLabel("What are you trying to endure?",{exact:true}).waitFor();
  await popup.getByRole("button",{name:"Close scene Play",exact:true}).click();
  await selectPlayCategory(scene, "Scan");
  await scene.getByRole("group",{name:"Scan Plays",exact:true}).getByText("Check Sensors",{exact:true}).waitFor();
  await selectPlayCategory(scene, "Talk");
  await scene.getByRole("group",{name:"Talk Plays",exact:true}).getByText("Bad at Being a Person",{exact:true}).waitFor();
  await selectPlayCategory(scene, "Fight");
  await scene.locator('button[data-play="go_for_the_core"]').click();
  await popup.getByRole("button",{name:"Open on Battlefield",exact:true}).waitFor();
  await popup.getByRole("button",{name:"Close scene Play",exact:true}).click();
  await view.getByLabel("Dialogue or narration").fill("/play Keep Your Head");
  await view.getByRole("button",{name:"File transmission",exact:true}).click();
  await popup.getByLabel("What are you trying to endure?",{exact:true}).waitFor();
  await popup.getByRole("button",{name:"Close scene Play",exact:true}).click();

  await folder("Battlefield").click();
  await view.getByRole("button",{name:"Play",exact:true}).click();
  const menu = view.getByRole("dialog",{name:"Choose a Play",exact:true});
  await selectPlayCategory(menu, "Talk");
  const battlefieldTalk = menu.getByRole("group",{name:"Talk Plays",exact:true});
  await battlefieldTalk.getByText("Bad at Being a Person",{exact:true}).waitFor();
  assert.equal(await battlefieldTalk.getByRole("button",{name:"Bad at Being a Person",exact:true}).count(), 0);
  await selectPlayCategory(menu, "Scan");
  await menu.getByRole("button",{name:"Check Sensors",exact:true}).click();
  await menu.getByRole("button",{name:"Open Play",exact:true}).click();
  const tactical = view.getByRole("dialog",{name:"Check Sensors",exact:true});
  await tactical.getByRole("button",{name:"Roll Check Sensors",exact:true}).waitFor();
  await tactical.getByRole("button",{name:"Close Battlefield Play",exact:true}).click();

  await page.setViewportSize({width:390,height:700});
  await folder("Pilot Profile").click();
  assert(await profile.locator(".play-rail").evaluate(rail => rail.scrollWidth <= rail.clientWidth));
  console.log(`Command rail surfaces and all 10 Girl and 10 Frame labels passed. Categorized ${extras("girl").size} Girl Plays and ${extras("frame").size} Frame Plays, including upgrades.`);
}

async function verifySceneOrders(browser, server, postSetup, loadSetup) {
  const handler = await openPilot(browser, server, "handler");
  const pilot = await openPilot(browser, server, "invited");
  const close = connection => connection.view.getByRole("button",{name:"Close inbox",exact:true}).click();
  const refresh = connection => connection.view.getByRole("button",{name:"Check for updates",exact:true}).click();
  const receiptText = "Report the relay status to the Handler.";
  await close(handler);
  await close(pilot);
  const joined = await postSetup(pilot, "enter-scene", {room:"relay"});
  assert.equal(joined.status,200,await joined.text());
  await refresh(handler);
  await handler.view.getByRole("button",{name:"Orders and scene cast · Relay operations",exact:true}).click();
  const source = handler.view.locator("#scene-action-dialog");
  const summary = source.locator("summary").filter({hasText:"Issue a direct order"});
  if (await summary.count()) await summary.click();
  await source.getByLabel("Original pilot",{exact:true}).selectOption(discordUsers.invited);
  await source.getByLabel("Direct order",{exact:true}).fill(receiptText);
  const filed = handler.page.waitForResponse(response =>
    new URL(response.url()).pathname === "/api/player-setup/scene-orders");
  await source.getByRole("button",{name:"Issue a direct order",exact:true}).click();
  const response = await filed;
  const body = await response.json();
  assert.equal(response.status(),200,JSON.stringify(body));
  await source.waitFor({state:"hidden"});
  let assigned;
  for (let i = 0; i < 8 && !assigned; i++) {
    const data = await loadSetup(pilot);
    assigned = data.scene_mail.find(row => row.id === body.action_id)?.pending[0];
    if (!assigned) await new Promise(resolve => setTimeout(resolve,300));
  }
  assert.equal(assigned?.kind,"order_response");
  await refresh(pilot);
  await pilot.view.getByRole("button",{name:"Inbox",exact:true}).click();
  await pilot.view.getByRole("button",{name:/Receive Orders · Answer the order/}).click();
  const decision = pilot.view.locator("#scene-action-dialog");
  await decision.getByText(receiptText,{exact:true}).waitFor();
  await decision.getByLabel("Respond to the direct order",{exact:true}).selectOption("obedient");
  await decision.getByRole("button",{name:"Answer the original order",exact:true}).click();
  await decision.getByText("Receive Orders resolved",{exact:true}).waitFor();
  console.log("The Handler filed a direct order, and its pilot opened the exact scene decision from Inbox and answered it.");
}

async function verifyMissionDesk(browser, server) {
  const label = "Inspect the relay mast";
  async function control(role) {
    const connection = await openPilot(browser, server, role);
    const close = connection.view.getByRole("button", {name:"Close inbox",exact:true});
    if (await close.isVisible()) await close.click();
    await connection.view.getByRole("button", {name:"Missions",exact:true}).click();
    return {
      ...connection,
      desk:connection.view.locator("#mission-desk"),
      refresh:() => connection.view.getByRole("button", {name:"Check for updates",exact:true}).click(),
    };
  }
  const handler = await control("handler");
  await handler.desk.getByText("New mission offer",{exact:true}).click();
  await handler.desk.getByLabel("Mission objective").fill(label);
  await handler.desk.getByRole("checkbox",{name:"NIGHT RAIL"}).check();
  await handler.desk.getByRole("checkbox",{name:"CONTOUR"}).check();
  const filed = handler.page.waitForResponse(response =>
    new URL(response.url()).pathname === "/api/mission-desk" && response.request().method() === "POST");
  await handler.desk.getByRole("button",{name:"File mission offer"}).click();
  const response = await filed;
  assert.equal(response.status(),200,await response.text());
  const record = connection => connection.desk.locator("article").filter({hasText:label});
  await record(handler).getByText("0/2 responses",{exact:false}).waitFor();
  for (const role of ["invited","other"]) {
    const pilot = await control(role);
    await record(pilot).getByRole("button",{name:"Accept mission"}).click();
    await record(pilot).getByText("Response saved · Accepted",{exact:true}).waitFor();
    await pilot.page.context().close();
  }
  await handler.refresh();
  await record(handler).getByRole("button",{name:"Dispatch accepted pilots"}).click();
  await record(handler).getByText("Dispatched",{exact:true}).waitFor();
  await record(handler).getByText("File debrief",{exact:true}).click();
  await record(handler).getByLabel("Mission outcome").selectOption("success");
  await record(handler).getByLabel("Debrief (visible to invited pilots)").fill("The relay mast is transmitting.");
  await record(handler).getByRole("button",{name:"Record outcome"}).click();
  await record(handler).getByText("The relay mast is transmitting.",{exact:true}).waitFor();
  assert.equal(await record(handler).getByRole("button",{name:"Close debrief"}).count(),0);
  const reopened = await control("invited");
  await record(reopened).getByText("The relay mast is transmitting.",{exact:true}).waitFor();
  assert.equal(await reopened.desk.getByText("New mission offer",{exact:true}).count(),0);
  await reopened.page.context().close();
  await record(handler).getByRole("button",{name:"Open assigned follow-ups"}).click();
  const punishment = handler.view.locator("#punishment-cases article").filter({hasText:"Dog's Punishment"});
  await punishment.getByLabel("Punishment",{exact:true}).selectOption("stimulant_injection");
  await punishment.getByRole("button",{name:"Apply the assigned Punishment"}).click();
  await punishment.waitFor({state:"hidden"});
  await handler.view.getByRole("button", {name:"Missions",exact:true}).click();
  await record(handler).getByRole("button",{name:"Close debrief"}).click();
  await record(handler).getByText("Debrief filed",{exact:true}).waitFor();
  await handler.desk.getByRole("button",{name:"Prepare Off-Duty"}).click();
  await handler.view.locator("#off-duty-panel").getByText("Set initial Strain",{exact:true}).waitFor();
  console.log("Two pilots answered and the Handler dispatched, filed a debrief, resolved the required Punishment, and prepared Off-Duty through the Activity. A reopened pilot view preserved the outcome.");
  return label;
}

async function verifyBoundRoster(browser, server, owner, other, loadSetup, postSetup, campaignInfo) {
  const handler = await openPilot(browser, server, "handler", false, campaignInfo?.id);
  const handlerBook = handler.view.locator("#handler-playbook");
  const openHandlerPlays = () => handler.view.getByRole("button",{name:"Open Handler Plays",exact:true}).click();
  const closeHandlerPlays = () => handler.view.getByRole("button",{name:"Close Handler Plays",exact:true}).click();
  const dismiss = handler.view.getByRole("button", {name:"Close inbox",exact:true});
  if (await dismiss.isVisible()) await dismiss.click();
  await handler.view.getByRole("button", {name:"Handler desk",exact:true}).click();
  await openHandlerPlays();
  await handlerBook.getByText("Handler rulebook",{exact:true}).waitFor();
  await handlerBook.getByText("Introduce the support",{exact:true}).waitFor();
  await closeHandlerPlays();
  const pilots = [
    {connection:owner, role:"invited", callsign:"NIGHT RAIL", frame:"Switchback", description:"Private northbound fixture", portrait:"pilot-sorrow"},
    {connection:other, role:"other", callsign:"CONTOUR", frame:"Level Crossing", description:"Private southbound fixture", portrait:"pilot-mockingbird"},
  ];
  if (campaignInfo?.name === "Southern Signal") {
    Object.assign(pilots[0], {callsign:"DAYBREAK",frame:"Southbound",description:"Separate southern campaign fixture"});
    Object.assign(pilots[1], {callsign:"HAWK",frame:"Low Water",description:"Separate southern counterpart fixture"});
  }
  const control = (connection, name) => connection.view.getByRole("button", {name,exact:true});
  const closeInbox = async connection => {
    if (await control(connection, "Close inbox").isVisible()) await control(connection, "Close inbox").click();
  };
  const enrollment = connection => connection.view.getByRole("dialog", {name:"Pilot enrollment"});
  const goStep = (connection, label) => enrollment(connection).getByRole("button", {name:label,exact:true}).click();
  const update = async connection => {
    await goStep(connection, "Bond");
    const loaded = connection.page.waitForResponse(response =>
      new URL(response.url()).pathname === "/api/player-setup" && response.request().method() === "GET");
    await goStep(connection, "Synchronize terminal");
    assert.equal((await loaded).status(), 200);
  };

  await closeInbox(handler);
  assert.equal((await loadSetup(handler)).stage, "handler");
  assert.equal(await handler.view.getByRole("heading", {name:"Create pilot",exact:true}).count(), 0);
  assert.equal((await postSetup(handler, "profile", {revision:0,callsign:"HANDLER SPOOF"})).status, 403);

  for (const {connection, callsign} of pilots) {
    await closeInbox(connection);
    await enrollment(connection).waitFor();
    if (connection === owner) {
      const originalSize = connection.page.viewportSize();
      await connection.page.setViewportSize({width:390,height:650});
      assert(await enrollment(connection).evaluate(dialog => {
        const box = dialog.getBoundingClientRect();
        return box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight;
      }), "Enrollment dialog fits a narrow Activity window.");
      await goStep(connection, "Close pilot enrollment");
      await enrollment(connection).waitFor({state:"hidden"});
      await control(connection, "Create pilot").click();
      await enrollment(connection).waitFor();
      if (originalSize) await connection.page.setViewportSize(originalSize);
    }
    await connection.view.getByRole("heading", {name:"Create pilot",exact:true}).waitFor();
    const initial = await loadSetup(connection);
    assert.equal(initial.stage, "profile");
    assert.equal(initial.revision, 0);
    const field = connection.view.getByLabel("Callsign", {exact:true});
    assert.equal(await field.inputValue(), "");
    await field.fill(callsign);
    await control(connection, "File callsign").click();
    await enrollment(connection).locator("#enrollment-identity").getByRole("heading", {name:callsign,exact:true}).waitFor();
    if (connection === owner) {
      await goStep(connection, "Close pilot enrollment");
      await control(connection, "Pilot Profile").click();
      await connection.view.locator("#profile-pane").getByText("Enrollment pending", {exact:true}).waitFor();
      await connection.view.locator("#profile-pane").getByRole("button", {name:"Resume enrollment"}).click();
      await enrollment(connection).locator("#enrollment-identity").getByRole("heading", {name:callsign,exact:true}).waitFor();
    }
  }
  for (const {connection, frame, description, portrait} of pilots) {
    await update(connection);
    await goStep(connection, "Dossier");
    const draft = await loadSetup(connection);
    assert.equal(draft.stage, "draft");
    assert.equal(draft.review.ready, false);
    const {options} = draft;
    const field = label => connection.view.getByLabel(label, {exact:true});
    await field("Frame name").fill(frame);
    if (connection === owner) {
      assert.equal((await postSetup(other, "artwork", {
        kind:"pilot", target:discordUsers.invited, artwork:portrait, previous:null,
      })).status, 409);
    }
    await goStep(connection, "Select profile picture");
    const picker = connection.view.locator("#artwork-dialog");
    await picker.getByLabel("Artwork selection").selectOption(portrait);
    await picker.getByRole("button", {name:"File artwork"}).click();
    await picker.waitFor({state:"hidden"});
    assert.equal(await field("Frame name").inputValue(), frame);
    assert.equal((await loadSetup(connection)).enrollment.portrait, portrait);
    await enrollment(connection).locator(".enrollment-portrait img[src^='blob:']").waitFor();
    await field("Pilot appearance").fill("Grey visor");
    await field("Frame appearance").fill("Ceramic shell");
    await field("NPC name").fill("Iris");
    for (const [family, available] of [["Pilot", options.girl_assets], ["Frame", options.frame_assets]]) {
      for (const index of [0, 1]) {
        const asset = `${family} asset ${index + 1}`;
        await field(asset).selectOption(available[index]);
        await field(asset + " description").fill(description);
      }
    }
    await field("Void-altered pilot asset").selectOption(options.girl_assets[0]);
    const saved = connection.page.waitForResponse(response =>
      new URL(response.url()).pathname === "/api/player-setup" && response.request().method() === "GET");
    await control(connection, "File enrollment draft").click();
    assert.equal((await (await saved).json()).draft.frame_name, frame);
  }
  await enrollment(owner).getByLabel("Recipient", {exact:true}).selectOption(discordUsers.other);
  await control(owner, "Propose starting Bond").click();
  await enrollment(owner).getByText("COUNTERSIGNATURE PENDING", {exact:true}).waitFor();
  const pending = (await loadSetup(owner)).bonds.find(bond => !bond.incoming && bond.state === "pending");
  assert(pending, "The starting Bond awaits the target player's decision.");
  assert.equal((await postSetup(owner, "bond-decision", {
    id:pending.id, revision:pending.revision, decision:"accept",
  })).status, 409);
  await update(other);
  await goStep(other, "Accept Bond");
  await enrollment(other).getByText("Countersigned", {exact:true}).waitFor();
  await goStep(other, "Use as starting Bond");
  await enrollment(other).getByRole("heading", {name:"Activation review"}).waitFor();
  for (const {connection, callsign} of pilots) {
    await update(connection);
    await goStep(connection, "Review");
    const {review} = await loadSetup(connection);
    assert.equal(review.ready, true, JSON.stringify(review.issues));
    await control(connection, "File activation review").click();
    await control(connection, "Activate pilot").click();
    await connection.view.locator("#pilot").filter({hasText:new RegExp("^" + callsign + " \\| ")}).waitFor();
  }
  await Promise.all(pilots.map(({connection}) => connection.page.context().close()));

  for (const {role, callsign, frame, description, portrait} of pilots) {
    const rival = pilots.find(pilot => pilot.role !== role);
    const connection = await openPilot(browser, server, role, false, campaignInfo?.id);
    await closeInbox(connection);
    const active = await loadSetup(connection);
    assert.equal(active.stage, "active");
    assert.equal(active.callsign, callsign);
    assert.equal(active.profile.frame_name, frame);
    assert(active.profile.assets.some(asset => asset.description === description));
    assert(!JSON.stringify(active).includes(rival.description));
    assert.deepEqual(active.cadre.filter(pilot => pilot.own).map(pilot => pilot.id), [discordUsers[role]]);
    assert.equal(active.cadre.find(pilot => pilot.own).artwork, portrait);
    assert(active.cadre.some(pilot => pilot.id === discordUsers[rival.role] && !pilot.own && pilot.callsign === rival.callsign));
    assert.equal((await postSetup(connection, "artwork", {
      kind:"pilot", target:discordUsers[rival.role], artwork:"pilot-sorrow", previous:null,
    })).status, 409);
    await control(connection, "Pilot Profile").click();
    await connection.view.locator("#profile-pane").getByText(callsign, {exact:true}).waitFor();
    assert.equal(await connection.view.locator("#profile-pane").getByText(rival.callsign, {exact:true}).count(), 0);
    await connection.page.context().close();
  }
  await closeInbox(handler);
  await handler.view.getByRole("button",{name:"Synchronize terminal",exact:true}).click();
  await openHandlerPlays();
  await handlerBook.getByLabel(pilots[0].callsign,{exact:true}).check();
  await handlerBook.getByRole("button",{name:"Start Handler Play",exact:true}).click();
  await handlerBook.getByLabel("Handler Play",{exact:true}).selectOption("brief");
  await handlerBook.getByLabel("Information or consequence to communicate",{exact:true}).fill("The west relay has lost power.");
  await handlerBook.getByRole("button",{name:"File effect",exact:true}).click();
  await handler.view.locator("#handler-play-feedback").getByText("Effect filed.",{exact:true}).waitFor();
  await closeHandlerPlays();
  if (handlerPlaysCheck) {
    await control(handler, "Battlefield").click();
    await handler.view.getByLabel("Private Class 0 name",{exact:true}).fill("Synthetic Class 0");
    await handler.view.getByLabel("Two Class 0 Assets, one per line",{exact:true}).fill("Screen\nGuard");
    await handler.view.getByLabel("Class 0 Core weakness",{exact:true}).fill("Resolve the actual briefing.");
    await handler.view.getByLabel("Class 0 type",{exact:true}).selectOption("sentinel");
    await handler.view.getByLabel("Class 0 starting base",{exact:true}).selectOption("0");
    await control(handler, "Open Battlefield").click();
    await control(handler, "Open Battlefield").waitFor({state:"hidden"});
    await control(handler, "Scenes").click();
    const subject = await openPilot(browser, server, "invited");
    let executor = await openPilot(browser, server, "other");
    const refresh = async pilot => {
      await closeInbox(pilot);
      const response = pilot.page.waitForResponse(answer => new URL(answer.url()).pathname === "/api/player-setup" && answer.request().method() === "GET");
      await control(pilot, "Synchronize terminal").click();
      assert.equal((await response).status(),200);
    };
    const start = async play => {
      if (await handlerBook.isVisible()) await closeHandlerPlays();
      await refresh(handler);
      await openHandlerPlays();
      await handlerBook.getByLabel(pilots[0].callsign,{exact:true}).check();
      await handlerBook.getByRole("button",{name:"Start Handler Play",exact:true}).click();
      await handlerBook.getByLabel("Handler Play",{exact:true}).selectOption(play);
      await handlerBook.getByLabel("Information or consequence to communicate",{exact:true}).fill("Synthetic Handler Play briefing.");
    };
    await start("support");
    await handlerBook.getByLabel("Employee name",{exact:true}).fill("Technician Finch");
    await handlerBook.getByLabel("Department",{exact:true}).selectOption("mechanic");
    await handlerBook.getByLabel("Campaign location",{exact:true}).selectOption({index:1});
    await handlerBook.getByLabel("Employee description",{exact:true}).fill("A Foundation field technician.");
    const submitted = handler.page.waitForResponse(response => response.url().endsWith("/api/player-setup/handler-play-submit"));
    await handlerBook.getByRole("button",{name:"File effect",exact:true}).click();
    const response = await submitted;
    const post = response.request();
    const replay = await fetch(server.origin + "/api/player-setup/handler-play-submit", {
      method:"POST", body:post.postData(),
      headers:{
        Authorization:`Bearer ${handler.session}`, Origin:server.discord_activity_origin,
        "Content-Type":"application/json", "Idempotency-Key":await post.headerValue("idempotency-key"),
      },
    });
    assert.equal(replay.status,200);
    assert.deepEqual(await replay.json(),await response.json());
    await handler.view.locator("#handler-play-feedback").getByText("Effect filed.",{exact:true}).waitFor();
    const actors = await fetch(server.origin + "/api/battlefield",{headers:{Authorization:`Bearer ${handler.session}`}});
    assert.equal(actors.status,200);
    assert.equal((await actors.json()).encounter.enemies.filter(npc => npc.label === "Technician Finch").length,1);
    const support = (await loadSetup(subject)).handler_notices.find(notice => notice.play === "support");
    assert.equal(support.employee.name,"Technician Finch");
    assert.equal((await loadSetup(executor)).handler_notices.some(notice => notice.play === "support"),false);
    const dispatch = (await loadSetup(handler)).handler_playbook;
    assert.equal(dispatch.tasks.length,0);

    await start("punish");
    await handlerBook.getByLabel("Affected original",{exact:true}).selectOption({label:pilots[0].callsign});
    await handlerBook.getByLabel("Original executor",{exact:true}).selectOption({label:pilots[1].callsign});
    await handlerBook.getByRole("button",{name:"File effect",exact:true}).click();
    await handler.view.locator("#handler-play-feedback").getByText("Effect filed. Follow-up assigned.",{exact:true}).waitFor();
    await closeHandlerPlays();
    const punishment = handler.view.locator("#punishment-work");
    await punishment.getByLabel("Punishment",{exact:true}).selectOption("stimulant_injection");
    await control(handler, "File Punishment instruction").click();
    await handler.view.locator("#punishment-feedback").getByText("Punishment step filed.",{exact:true}).waitFor();
    const caseID = (await loadSetup(handler)).handler_punishments[0].id;
    const pending = async pilot => (await loadSetup(pilot)).handler_punishments.find(item => item.id === caseID);
    assert.equal((await pending(subject)).action,null);
    assert.equal((await pending(executor)).action,"scene");
    await executor.page.context().close();
    executor = await openPilot(browser, server, "other");
    assert.equal((await pending(executor)).action,"scene");
    const scene = {id:caseID,revision:(await pending(executor)).revision,action:"scene",answer:"The executor played the assigned scene."};
    assert.equal((await postSetup(subject,"handler-punishment",scene)).status,409);
    await closeInbox(executor);
    await executor.view.getByLabel("Describe the scene you played",{exact:true}).fill(scene.answer);
    await control(executor,"Record Punishment scene").click();
    await executor.view.locator("#punishment-feedback").getByText("Punishment step filed.",{exact:true}).waitFor();
    const assigned = await pending(subject);
    assert.equal(assigned.action,"attest");
    assert.equal((await pending(executor)).action,null);
    const attest = {id:caseID,revision:assigned.revision,action:"attest",answer:true};
    assert.equal((await postSetup(handler,"handler-punishment",attest)).status,409);
    await refresh(subject);
    await control(subject,"Inbox").click();
    await control(subject,"Confirm my attendance").first().click();
    await subject.view.locator("#punishment-work").getByRole("button",{name:"Confirm my attendance",exact:true}).click();
    await subject.view.locator("#punishment-feedback").getByText("Punishment step filed.",{exact:true}).waitFor();
    await refresh(executor);
    assert.equal((await pending(executor)).action,"execute");
    await executor.view.getByLabel("Describe your actual execution",{exact:true}).fill("The executor carried out the saved instruction in the scene.");
    await control(executor,"File Punishment execution").click();
    await executor.view.locator("#punishment-work").waitFor({state:"hidden"});
    assert.equal((await loadSetup(subject)).profile.heat,7);
    assert.equal((await loadSetup(handler)).handler_playbook.tasks.length,0);
    await start("mess");
    await handlerBook.getByLabel("Affected original",{exact:true}).selectOption({label:pilots[0].callsign});
    await handlerBook.getByLabel("Change",{exact:true}).selectOption("tag");
    await handlerBook.getByLabel("New Tag",{exact:true}).fill("Under review");
    await handlerBook.getByRole("button",{name:"File effect",exact:true}).click();
    await handler.view.locator("#handler-play-feedback").getByText("Effect filed.",{exact:true}).waitFor();
    assert((await loadSetup(subject)).profile.tags.includes("Under review"));
    await handlerBook.getByRole("button",{name:"Prepare Off-Duty",exact:true}).click();
    await handler.view.locator("#handler-play-feedback").getByText("Off-Duty preparation filed.",{exact:true}).waitFor();
    assert.equal((await loadSetup(handler)).handler_playbook.off_duty_phase,"preparing");
    await start("off_duty");
    await handlerBook.getByRole("button",{name:"File effect",exact:true}).click();
    await handler.view.locator("#handler-play-feedback").getByText("Effect filed. Follow-up assigned.",{exact:true}).waitFor();
    assert.equal((await loadSetup(handler)).handler_playbook.tasks[0].state,"awaiting_effect");
    await closeHandlerPlays();
    const preparation = handler.view.locator("#off-duty-options");
    await preparation.getByLabel("Starting scenario",{exact:true}).selectOption("business_as_usual");
    await preparation.getByRole("button",{name:"Save starting Strain",exact:true}).click();
    await preparation.getByRole("button",{name:"File trigger review",exact:true}).waitFor();
    assert.equal((await loadSetup(handler)).off_duty.closing.strain.cards[0].action,"strain_prepare");
    assert.equal((await loadSetup(subject)).off_duty,null);
    for (const [pilot, text] of [[subject,"First transmission"],[executor,"Newest transmission"]]) {
      assert.equal((await postSetup(pilot,"room-post",{target:"relay",text})).status,200);
      assert.equal((await loadSetup(pilot)).active_scene.id,"relay");
    }
    await refresh(subject);
    await control(subject,"Scenes").click();
    const relay = subject.view.getByRole("button",{name:"Open Relay operations",exact:true});
    if (await relay.isVisible()) await relay.click();
    const entries = subject.view.locator("#dialogue-entries .dialogue-entry");
    await entries.first().getByText("Newest transmission",{exact:true}).waitFor();
    const beneath = subject.view.locator("#scene-play-options button[data-play='put_someone_beneath_you']");
    const category = await beneath.locator("xpath=ancestor::*[@data-play-panel][1]").getAttribute("data-play-panel");
    await subject.view.locator(`#scene-play-options [data-play-category='${category}']`).click();
    await beneath.click();
    const action = subject.view.getByRole("dialog",{name:/put someone beneath you/i});
    await action.getByLabel("Pilot",{exact:true}).selectOption(discordUsers.other);
    const heat = (await loadSetup(subject)).active_scene.options.put_someone_beneath_you.heat_options[0];
    await action.getByLabel("Heat to spend",{exact:true}).selectOption(String(heat));
    await action.locator("#scene-action-fields input").fill("I confront the other pilot at the relay.");
    const started = subject.page.waitForResponse(response => response.url().endsWith("/api/player-setup/scene-start"));
    await action.getByRole("button",{name:/^roll put someone beneath you$/i}).click();
    assert.equal((await started).status(),200);
    const getAssigned = async (connection, kind, role = "pilot") => {
      for (let attempt = 0; attempt < 35; attempt++) {
        const record = await loadSetup(connection);
        const choice = role === "handler"
          ? record.handler_choices.find(card => card.play === "put_someone_beneath_you" && card.choice.kind === kind)?.choice
          : record.active_scene?.options.put_someone_beneath_you.choices.find(card => card.kind === kind);
        if (choice) return choice;
        await new Promise(resolve => setTimeout(resolve,100));
      }
      throw new Error("No assigned scene choice appeared for " + kind);
    };
    for (const [connection,role] of [[executor,"pilot"],[subject,"pilot"]]) {
      const tag = await getAssigned(connection,"tag_window",role);
      assert.equal((await postSetup(connection,"scene-choice",{
        room:"relay",id:tag.id,revision:tag.revision,role,answer:{options:["pass"]},
      })).status,200);
    }
    await getAssigned(handler,"tag_window","handler");
    await refresh(handler);
    await handler.view.getByRole("button",{name:"Relay operations · Put Someone Beneath You",exact:true}).click();
    const handlerDialog = handler.view.getByRole("dialog",{name:"Put Someone Beneath You"});
    await handlerDialog.getByRole("button",{name:"Handler · Pass Tag window",exact:true}).click();
    await handlerDialog.getByText("No further decisions are assigned to you.",{exact:true}).waitFor();
    await handlerDialog.getByRole("button",{name:"Close scene Play",exact:true}).click();
    await getAssigned(subject,"beneath_select");
    await action.getByRole("button",{name:"Check for scene updates",exact:true}).click();
    await action.getByLabel("Choose printed effects",{exact:true}).selectOption("tag");
    await action.getByLabel("Choose one extra effect",{exact:true}).selectOption("punish");
    await action.getByLabel("Describe the actual confrontation",{exact:true}).fill("File the confrontation in the relay log.");
    await action.getByLabel("New Tag label (Tag effect only)",{exact:true}).fill("Severe");
    await action.getByRole("button",{name:"Save confrontation effects",exact:true}).click();
    await action.getByLabel("Punishment",{exact:true}).selectOption("quality_time");
    const assignedPunishment = (await loadSetup(subject)).scene_beneath_work.find(row => row.action === "apply_scene_punishment");
    assert(assignedPunishment);
    assert(!(await loadSetup(executor)).scene_beneath_work.some(row => row.id === assignedPunishment.id));
    await action.getByLabel("Inflicted Tag",{exact:true}).fill("On review");
    await action.getByRole("button",{name:"Apply assigned Punishment",exact:true}).click();
    await action.getByRole("heading",{name:/beneath you resolved/i}).waitFor();
    assert((await loadSetup(executor)).profile.tags.includes("On review"));
    await action.getByRole("button",{name:"Close scene Play",exact:true}).click();
    // Exercise the Inbox and modal against an assigned specialty projection.
    // The native two-pilot ledger tests generate and resolve the actual choices.
    const feedback = {
      id:"fixture-feedback", revision:1, action:"feedback_purpose",
      instruction:"Ankou Feedback",
      fields:[
        {key:"given", label:"Provide a purpose?", options:[["yes","Yes"],["no","No"]], required:true},
        {key:"account", label:"Scene account", required:true},
      ],
    };
    let filed = false;
    await subject.page.route("**/api/player-setup", async route => {
      const request = new URL(route.request().url());
      const response = await route.fetch({url:server.origin + request.pathname + request.search});
      const data = await response.json();
      if (!filed) {
        data.handler_punishments.push(feedback);
        data.scene_beneath_work.push({...feedback, specialty:true, room:"relay",
          room_name:"Relay operations", root:assignedPunishment.root});
      }
      await route.fulfill({response,json:data});
    });
    await subject.page.route("**/api/player-setup/scene-beneath-work", async route => {
      const body = route.request().postDataJSON();
      assert.deepEqual(body,{
        id:feedback.id, revision:1, root:assignedPunishment.root, action:feedback.action,
        answer:{given:"yes",account:"Hold the western relay."},
      });
      filed = true;
      await route.fulfill({json:{state:"complete"}});
    });
    await refresh(subject);
    await control(subject,"Inbox").click();
    const mail = subject.view.getByRole("region",{name:"Inbox",exact:true});
    const link = mail.getByRole("button",{name:"Answer the request for purpose",exact:true});
    await link.waitFor();
    assert.equal(await link.getAttribute("data-mail-id"),"punishment:fixture-feedback:feedback_purpose");
    await link.click();
    await action.getByLabel("Provide a purpose?",{exact:true}).selectOption("yes");
    await action.getByLabel("Scene account",{exact:true}).fill("Hold the western relay.");
    await action.getByRole("button",{name:"Answer the request for purpose",exact:true}).click();
    await action.getByText("Decision filed.",{exact:true}).waitFor();
    assert(filed);
    await Promise.all([subject.page.context().close(),executor.page.context().close()]);
    console.log("Support replay created one canonical NPC and a private notice. Punishment resumed on reopen, denied cross-owner actions, and completed through the chooser, subject, and executor. Tag and Off-Duty handoff were filed through HarpyEngine.");
  }
  await handler.page.context().close();
  console.log("Two signed-in pilots created distinct HarpyEngine sheets, reopened their own records, and could not edit one another's artwork. The Handler received its separate desk.");
}

async function verifyCampaignSwitch(browser, server, owner, other, request, playerSetup, setupPost) {
  const response = await request(owner, "/api/campaigns");
  assert.equal(response.status,200);
  const {campaigns} = await response.json();
  const north = campaigns.find(campaign => campaign.name === "Northern Reach");
  const south = campaigns.find(campaign => campaign.name === "Southern Signal");
  assert(north && south && north.id !== south.id);
  await Promise.all([owner.page.context().close(), other.page.context().close()]);
  for (const campaignInfo of [north, south]) {
    const first = await openPilot(browser, server, "invited", false, campaignInfo.id);
    const second = await openPilot(browser, server, "other", false, campaignInfo.id);
    await verifyBoundRoster(browser, server, first, second, playerSetup, setupPost, campaignInfo);
  }
  const pilot = await openPilot(browser, server, "invited", false, north.id);
  const switcher = pilot.view.locator("#campaign-switch");
  const access = pilot.view.locator("#auth-dialog");
  const storageAvailable = await pilot.view.locator("html").evaluate(() => {
    try {
      return typeof sessionStorage.length === "number";
    } catch (error) {
      if (error.name === "SecurityError") return false;
      throw error;
    }
  });
  const visit = async (entry, callsign, frame) => {
    if (await switcher.inputValue() !== entry.id) {
      const closeInbox = pilot.view.getByRole("button",{name:"Close inbox",exact:true});
      if (await closeInbox.isVisible()) await closeInbox.click();
      await switcher.selectOption(entry.id);
      if (!storageAvailable) {
        // A blocked embedded store must fall back to fresh Discord authorization.
        await access.locator("#sign-in").click();
        await access.waitFor({state:"hidden"});
      }
    }
    try {
      await pilot.view.locator("#campaign-name").filter({hasText:entry.name}).waitFor();
    } catch (error) {
      const state = await pilot.view.locator("html").evaluate(() => ({
        campaign: new URL(location.href).searchParams.get("campaign"),
        status: document.getElementById("status")?.textContent,
        signingIn: document.getElementById("auth-dialog")?.open,
      }));
      throw new Error("Campaign switch did not open the selected file. " + JSON.stringify(state), {cause:error});
    }
    await pilot.view.locator("#pilot[data-ready]").filter({hasText:callsign}).waitFor();
    assert.equal(await access.isVisible(),false);
    const data = await playerSetup(pilot);
    assert.equal(data.stage,"active");
    assert.equal(data.callsign,callsign);
    assert.equal(data.profile.frame_name,frame);
    assert.equal(data.cadre.find(item => item.own).id,discordUsers.invited);
    assert.equal(data.directory.can_invite_campaign,false);
    return data.mailbox;
  };
  const first = await visit(north, "NIGHT RAIL", "Switchback");
  const second = await visit(south, "DAYBREAK", "Southbound");
  assert.notEqual(first, second);
  assert.equal(await visit(north, "NIGHT RAIL", "Switchback"),first);
  const fromChannel = await openPilot(browser, server, "invited", false, undefined, "888888888888888892");
  assert.equal(await fromChannel.view.locator("#campaign-name").textContent(), "Southern Signal");
  assert.equal((await playerSetup(fromChannel)).mailbox, second);
  console.log("The same Discord pilot switched between two active HarpyEngine sheets with separate callsigns, Frames and mailboxes. Launching from the bound channel selected its campaign. " +
    (storageAvailable ? "The existing session survived each switch." : "Blocked storage required fresh authorization at each switch."));
}

async function verifyP2Battlefield(browser, server, previous) {
  const open = async role => {
    const pilot = await openPilot(browser,server,role);
    const close = pilot.view.getByRole("button",{name:"Close inbox",exact:true});
    if (await close.isVisible()) await close.click();
    await pilot.view.getByRole("button",{name:"Battlefield",exact:true}).click();
    return pilot;
  };
  const api = (pilot, operation, data, key = randomUUID()) =>
    pilot.page.request.fetch(server.origin + "/api/battlefield" + (operation ? "/" + operation : ""), {
      method:data ? "POST" : "GET", data,
      headers:{Authorization:"Bearer " + pilot.session, Origin:server.discord_activity_origin, "Idempotency-Key":key},
    });
  const send = async (pilot, operation, data, expected = 200, key) => {
    const response = await api(pilot,operation,data,key);
    assert.equal(response.status(),expected,await response.text());
    return response.json();
  };
  async function waitFor(pilot, predicate) {
    for (let attempt = 0; attempt < 60; attempt++) {
      const response = await api(pilot);
      if (response.status() !== 503) {
        assert.equal(response.status(),200,await response.text());
        const data = await response.json();
        if (predicate(data)) return data;
      }
      await new Promise(resolve => setTimeout(resolve,180));
    }
    assert.fail("P2 Battlefield did not reach the expected state.");
  }
  const roomLabel = p2Facility === "hangar" ? "Maintenance" : "Inspection bay";
  const boardName = p2Facility === "hangar" ? "Hangar Deck" : "Outpost K-12";
  if (previous) {
    const pilot = await open(previous.role);
    if (previous.blocked) {
      const saved = await waitFor(pilot,data => data.facility?.name === boardName && data.encounter.entry_blocker);
      assert(!saved.encounter.joined && !saved.encounter.can_join);
      return;
    }
    const current = await waitFor(pilot, data => data.play?.receipt && data.encounter.turn === previous.turn);
    assert.equal(current.facility.name,boardName);
    assert.deepEqual(current.actors.find(actor => actor.controlled).cell,previous.destination);
    assert.deepEqual(current.play.receipt,previous.receipt);
    await pilot.view.locator("#tactical-grid").getByText(roomLabel,{exact:true}).waitFor();
    const pending = current.choices.find(choice => choice.kind === "tag_window");
    assert(pending && pending.role === "pilot");
    await pilot.view.getByRole("button",{name:"Open assigned choices",exact:true}).click();
    await pilot.view.getByRole("button",{name:"Pilot · Pass Tag window",exact:true}).click();
    const optional = pilot.view.getByRole("button",{name:"Decline optional Risk Factor",exact:true});
    const resolve = pilot.view.getByRole("button",{name:"Resolve Engage",exact:true});
    await resolve.or(optional).first().waitFor();
    if (await optional.isVisible()) await optional.click();
    const owned = await waitFor(pilot,data => data.choices.some(choice => choice.kind === "engage_maneuvers"));
    const fields = owned.choices.find(choice => choice.kind === "engage_maneuvers").fields;
    const asset = fields.assets[0].id;
    for (let index = 0; index < fields.minimum; index++) {
      await pilot.view.getByLabel("Maneuver " + (index + 1),{exact:true}).selectOption(fields.maneuvers[index]);
      await pilot.view.getByLabel("Asset for maneuver " + (index + 1),{exact:true}).selectOption(asset);
    }
    if (fields.damage) await pilot.view.getByLabel("Damage a used Asset",{exact:true}).selectOption(asset);
    await pilot.view.getByLabel("Resulting circumstances",{exact:true}).fill("The pilot secures the relay approach.");
    await resolve.click();
    const done = await waitFor(pilot,data => data.play?.state === "complete");
    assert.deepEqual(done.play.receipt,previous.receipt);
    return;
  }
  const handler = await open("handler");
  const first = await open("invited");
  const second = await open("other");
  const initial = await waitFor(handler,data => data.encounter.can_open);
  assert.deepEqual(initial.encounter.facility_options.map(site => site.id),["hangar","outpost"]);
  await send(first,"open",{revision:initial.revision,facility:p2Facility},409);
  await handler.view.getByRole("button",{name:"Open Battlefield",exact:true}).click();
  const battlefieldSetup = handler.view.locator("#utility-dialog");
  await battlefieldSetup.getByLabel("Facility plan",{exact:true}).selectOption(p2Facility);
  await battlefieldSetup.getByRole("button",{name:"Open Battlefield",exact:true}).click();
  const opened = await waitFor(handler,data => data.facility?.name === boardName && data.encounter.joined);
  assert.deepEqual(opened.board,{minimum:[-1,-1],maximum:[10,5]});
  assert.equal(opened.facility.floor.length,7);
  await handler.view.locator("#tactical-grid").getByText(roomLabel,{exact:true}).waitFor();
  if (process.argv.includes("--rehearsal-copy")) {
    const retained = await waitFor(first,data => data.facility?.name === boardName);
    if (retained.encounter.entry_blocker) {
      await first.view.getByText(retained.encounter.entry_blocker,{exact:true}).waitFor();
      await send(first,"join",{},409);
      return {blocked:true,role:"invited"};
    }
  }
  for (const pilot of [first,second]) {
    const entering = pilot.page.waitForResponse(response => response.url().endsWith("/api/battlefield/join"));
    await pilot.view.getByRole("button",{name:"Enter Battlefield",exact:true}).click();
    const response = await entering;
    assert.equal(response.status(),200,await response.text());
    const joined = await waitFor(pilot,data => data.encounter.joined);
    assert.deepEqual(joined.actors.find(actor => actor.controlled).cell,[0,0]);
    assert(joined.roster.find(actor => actor.controlled).profile);
    assert.equal(joined.roster.find(actor => !actor.controlled)?.profile ?? null,null);
  }
  const deployment = {name:"Relay sentry",account:"The sentry enters the marked bay.",cell:[2,1],
    revision:(await waitFor(handler,() => true)).revision};
  await send(handler,"create-enemy",{...deployment,cell:[4,0]},409);
  await send(handler,"create-enemy",deployment);
  await handler.view.locator(".encounter-status").filter({hasText:"Relay sentry"}).waitFor();
  const starting = handler.page.waitForResponse(response => response.url().endsWith("/api/battlefield/start-turns"));
  await handler.view.getByRole("button",{name:"Start turns",exact:true}).click();
  const startedRequest = await starting;
  assert.equal(startedRequest.status(),200,await startedRequest.text());
  const started = await waitFor(first,data => data.encounter.running);
  const active = started.encounter.yours ? first : second;
  const waiting = active === first ? second : first;
  let now = await waitFor(active,data => data.encounter.yours && data.actions.some(action => action.id === "move"));
  assert.equal((await waitFor(waiting,() => true)).actions.length,0);
  const move = now.actions.find(action => action.id === "move");
  const destination = [1,1];
  const movement = {actor:move.actor, frame:move.frame, turn:now.encounter.turn, revision:now.revision,
    destination, account:"Cross to the adjacent diagonal square."};
  await send(waiting,"move",movement,409);
  await send(waiting,"end-turn",{revision:now.revision},409);
  await send(active,"move",{...movement,destination:[4,0]},409);
  await send(active,"move",{...movement,destination:[0,7]},409);
  await active.view.getByRole("button",{name:"Move",exact:true}).click();
  assert(await active.view.getByRole("button",{name:/^Cell 4, 0 · Wall/}).isDisabled());
  await active.view.getByRole("button",{name:/^Cell 1, 1/}).click();
  await active.view.getByLabel("Describe the movement",{exact:true}).fill(movement.account);
  await active.view.getByRole("button",{name:"Confirm move",exact:true}).click();
  now = await waitFor(active,data => data.actors.some(actor => actor.controlled && actor.cell?.join() === destination.join()));
  await active.view.locator("#tactical-turn-strip").getByText(/Round 1.*Your turn/).waitFor();
  // Cycle through the other pilot and the Handler's enemy before starting the Play.
  const key = randomUUID();
  const end = {revision:now.revision};
  const ended = await send(active,"end-turn",end,200,key);
  assert.deepEqual(await send(active,"end-turn",end,200,key),ended);
  const next = await waitFor(waiting,data => data.encounter.yours);
  await send(waiting,"end-turn",{revision:next.revision});
  const enemy = await waitFor(handler,data => data.encounter.enemy_turn && data.encounter.yours);
  assert.equal(enemy.encounter.active,"Relay sentry");
  const enemyMove = enemy.actions.find(action => action.id === "move");
  const advance = {actor:enemyMove.actor,frame:false,turn:enemy.encounter.turn,revision:enemy.revision,
    destination:[3,1],account:"The sentry advances across the open floor."};
  await send(waiting,"move",advance,409);
  await send(handler,"move",advance);
  const advanced = await waitFor(handler,data => data.actors.some(actor => actor.enemy && actor.cell.join() === "3,1"));
  await send(handler,"end-turn",{revision:advanced.revision});
  now = await waitFor(active,data => data.encounter.yours && data.encounter.round === 2);
  await active.view.locator("#tactical-turn-strip").getByText(/Round 2.*Your turn/).waitFor();
  const engage = now.actions.find(action => action.id === "engage");
  const target = engage.targets.find(actor => actor.label === "Relay sentry");
  assert(engage.range.label && target);
  await active.view.locator('[data-tactical-play="engage"]').click();
  await active.view.getByLabel("Target",{exact:true}).selectOption(target.id);
  await active.view.getByLabel(engage.trigger,{exact:true}).fill("Engage the sentry in the maintenance area.");
  await active.view.getByRole("button",{name:"Roll Engage",exact:true}).click();
  const rolled = await waitFor(active,data => data.play?.play === "engage" && data.play.receipt);
  assert.deepEqual(rolled.play.receipt.faces,[4,5]);
  await send(active,"end-turn",{revision:rolled.revision},409);
  const review = await waitFor(handler,data => data.choices.some(choice => choice.kind === "tag_window"));
  const choice = review.choices.find(choice => choice.kind === "tag_window");
  const answer = {id:choice.id,revision:choice.revision,role:"handler",answer:{options:["pass"]}};
  await send(active,"choice",answer,409);
  await send(handler,"choice",answer);
  const peerReview = await waitFor(waiting,data => data.choices.some(choice => choice.kind === "tag_window"));
  const peerChoice = peerReview.choices.find(choice => choice.kind === "tag_window");
  await send(waiting,"choice",{id:peerChoice.id,revision:peerChoice.revision,role:"pilot",answer:{options:["pass"]}});
  // Leave the pilot-owned follow-up pending for the reopening check.
  return {role:active === first ? "invited" : "other", destination,
    receipt:rolled.play.receipt, turn:rolled.encounter.turn};
}

async function verifyRosterBattlefield(browser, server, request) {
  const open = async role => {
    const pilot = await openPilot(browser, server, role);
    const close = pilot.view.getByRole("button", {name:"Close inbox", exact:true});
    if (await close.isVisible()) await close.click();
    await pilot.view.getByRole("button", {name:"Battlefield", exact:true}).click();
    return pilot;
  };
  const state = async pilot => {
    for (let attempt = 0; attempt < 4; attempt++) {
      const response = await request(pilot, "/api/battlefield");
      if (response.status === 503 && attempt < 3) {
        await new Promise(resolve => setTimeout(resolve, 100));
        continue;
      }
      assert.equal(response.status, 200, await response.clone().text());
      return response.json();
    }
  };
  const send = (pilot, operation, data, key = randomUUID()) =>
    request(pilot, "/api/battlefield/" + operation, {
      method:"POST", body:JSON.stringify(data),
      headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":key},
    });
  const submit = async (pilot, operation, data, expected = 200, key) => {
    const response = await send(pilot, operation, data, key);
    assert.equal(response.status, expected, await response.clone().text());
    return response.json();
  };
  const waitFor = async (pilot, predicate) => {
    for (let i = 0; i < 35; i++) {
      const value = await state(pilot);
      if (predicate(value)) return value;
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    assert.fail("Battlefield did not reach the expected state.");
  };
  const handler = await open("handler");
  const first = await open("invited");
  const second = await open("other");
  const campaignInvite = await request(first, "/api/player-setup/invite-issue", {
    method:"POST", body:JSON.stringify({target:"campaign"}),
    headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":randomUUID()},
  });
  assert.equal(campaignInvite.status,409);
  assert.equal((await state(first)).board, null);
  await submit(first, "open", {revision:0}, 409);
  await handler.view.getByRole("button",{name:"Open Battlefield",exact:true}).click();
  const battlefieldSetup = handler.view.locator("#utility-dialog");
  for (const [name, value] of [
    ["Private Class 0 name","Private Arclight"], ["Two Class 0 Assets, one per line","Screen\nGuard"],
    ["Class 0 Core weakness","Acknowledge the actual disagreement"],
  ]) await battlefieldSetup.getByLabel(name,{exact:true}).fill(value);
  await battlefieldSetup.getByLabel("Class 0 type",{exact:true}).selectOption("sentinel");
  await battlefieldSetup.getByLabel("Class 0 starting base",{exact:true}).selectOption("0");
  await battlefieldSetup.getByRole("button",{name:"Open Battlefield",exact:true}).click();
  const opened = await waitFor(handler, view => view.encounter.joined && view.board);
  assert.deepEqual(opened.board.maximum,[9,9]);
  assert(!JSON.stringify(await state(first)).includes("Private Arclight"));

  for (const [pilot, cell] of [[first,[1,1]], [second,[4,1]]]) {
    await pilot.view.getByRole("button",{name:"Enter Battlefield",exact:true}).click();
    const joined = await waitFor(pilot, view => view.encounter.can_place);
    const placement = await submit(pilot,"place",{
      revision:joined.revision, cell, mode:"piloting", account:"I start in my actual Frame.",
    });
    const review = {id:placement.id,revision:placement.revision,decision:"accept",account:"I confirm the starting position."};
    await submit(pilot,"review-placement",review,409);
    await submit(handler,"review-placement",review);
    await waitFor(pilot, view => view.actors.some(actor => actor.controlled && actor.cell?.join() === cell.join()));
    if (pilot === first) {
      const revision = (await state(handler)).revision;
      const deployment = {revision,name:"Opposing guard",cell:[6,3],account:"An opposing guard enters the marked square."};
      await submit(pilot,"create-enemy",deployment,409);
      const key = randomUUID();
      const enemy = await submit(handler,"create-enemy",deployment,200,key);
      assert.deepEqual(await submit(handler,"create-enemy",deployment,200,key),enemy);
    }
  }

  const sceneTransfer = await request(second,"/api/player-setup/enter-scene",{
    method:"POST", body:JSON.stringify({room:"relay"}),
    headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":randomUUID()},
  });
  assert.equal(sceneTransfer.status,200,await sceneTransfer.text());
  assert(!(await state(second)).encounter.joined);
  await submit(second,"join",{});
  assert.deepEqual((await state(second)).actors.find(actor => actor.controlled).cell,[4,1]);

  await handler.view.locator(".encounter-status").filter({hasText:/NIGHT RAIL.*CONTOUR|CONTOUR.*NIGHT RAIL/}).waitFor();
  const turnRequest = handler.page.waitForResponse(response => response.url().endsWith("/api/battlefield/start-turns"));
  await handler.view.getByRole("button",{name:"Start turns",exact:true}).click();
  const started = await turnRequest;
  assert.equal(started.status(),200,await started.text());
  const a = await waitFor(first, view => view.encounter.running);
  const active = a.encounter.yours ? first : second;
  const waiting = active === first ? second : first;
  const actorName = active === first ? "NIGHT RAIL" : "CONTOUR";
  const otherName = active === first ? "CONTOUR" : "NIGHT RAIL";
  const current = await state(active);
  assert.equal(current.encounter.active,actorName);
  assert.equal(current.encounter.round,1);
  assert.equal(current.roster.find(pilot => pilot.controlled).label,actorName);
  assert.equal(current.roster.find(pilot => pilot.controlled).profile.frame_name, active === first ? "Switchback" : "Level Crossing");
  assert.equal(current.roster.find(pilot => !pilot.controlled).profile,null);
  assert.deepEqual((await state(waiting)).actions,[]);
  const engageTargets = current.actions.find(play => play.id === "engage").targets.map(target => target.label);
  assert(engageTargets.includes(otherName) && !engageTargets.includes(actorName));
  assert(!current.actions.some(play => play.id === "flirt"));
  const move = current.actions.find(action => action.id === "move");
  const start = current.actors.find(actor => actor.controlled).cell;
  const dest = [start[0]+1,start[1]+1];
  const payload = {actor:move.actor,revision:current.revision,frame:move.frame,destination:dest,account:"Cross to the adjacent square."};
  await submit(waiting,"move",payload,409);
  await submit(waiting,"end-turn",{revision:current.revision},409);
  await active.view.getByRole("button",{name:"Move",exact:true}).click();
  await active.view.getByRole("button",{name:new RegExp(`^Cell ${dest.join(", ")}`)}).click();
  await active.view.getByLabel("Describe the movement",{exact:true}).fill(payload.account);
  await active.view.getByRole("button",{name:"Confirm move",exact:true}).click();
  await waitFor(waiting, view => view.actors.find(actor => actor.label === actorName).cell.join() === dest.join());
  const attacking = await state(active);
  const assault = attacking.actions.find(action => action.id === "all_out_assault");
  assert(assault.targets.some(target => target.label === otherName));
  const opponent = assault.targets.find(target => target.label === otherName);
  const declared = await submit(active,"assault-declare",{
    revision:attacking.revision, turn:attacking.encounter.turn, target:opponent.id,
    attacking_asset:assault.attacking_assets[0].id,target_asset:opponent.assets[0].id,
    account:"I declare the opening from the current position.",
  });
  const pending = await waitFor(handler, view => view.encounter.attack_reviews?.some(review => review.id === declared.id));
  const review = {id:declared.id,revision:pending.revision,opening:true,reach:true,evidence:"I confirm this opening and reach."};
  await submit(active,"assault-review",review,409);
  await submit(handler,"assault-review",review);
  assert.equal((await state(active)).declarations.all_out_assault.state,"confirmed");
  const coreState = await state(active);
  const core = {revision:coreState.revision,turn:coreState.encounter.turn,target:coreState.encounter.expose_core,
    confirmed:true,account:"I voluntarily expose my own occupied Frame’s Core."};
  const otherToken = coreState.actors.find(actor => actor.label === otherName).id;
  await submit(waiting,"core-expose",core,409);
  await submit(active,"core-expose",{...core,target:otherToken},409);
  await active.view.getByText("Voluntary Core exposure",{exact:true}).click();
  await active.view.getByLabel("Describe exposing your Core",{exact:true}).fill(core.account);
  await active.view.getByLabel("I confirm I am exposing my own Frame Core",{exact:true}).check();
  await active.view.getByRole("button",{name:"Expose my Core",exact:true}).click();
  await waitFor(waiting, view => view.actors.some(actor => actor.label === actorName && actor.core_exposed));
  const end = {revision:(await state(active)).revision};
  const endKey = randomUUID();
  const receipt = await submit(active,"end-turn",end,200,endKey);
  assert.deepEqual(await submit(active,"end-turn",end,200,endKey),receipt);
  const next = await state(waiting);
  assert.equal(next.encounter.active,otherName);
  const coreTargets = next.actions.find(action => action.id === "go_for_the_core").targets;
  assert(coreTargets.some(target => target.label === actorName));
  await submit(waiting,"end-turn",{revision:next.revision});
  const foe = await waitFor(handler, view => view.encounter.enemy_turn && view.encounter.yours);
  const foeMove = foe.actions.find(action => action.label === "Move enemy");
  const enemyDest = [7,4];
  await submit(active,"move",{actor:foeMove.actor,revision:foe.revision,turn:foe.encounter.turn,frame:false,
    destination:enemyDest,account:"Forged enemy movement."},409);
  await handler.view.getByRole("button",{name:"Move enemy",exact:true}).click();
  await handler.view.getByRole("button",{name:/^Cell 7, 4/}).click();
  await handler.view.getByLabel("Describe the movement",{exact:true}).fill("The guard moves diagonally.");
  await handler.view.getByRole("button",{name:"Confirm move",exact:true}).click();
  const movedEnemy = await waitFor(handler, view => view.actors.some(actor => actor.enemy && actor.cell?.join() === enemyDest.join()));
  await submit(handler,"end-turn",{revision:movedEnemy.revision});
  await Promise.all([first.page.context().close(), second.page.context().close()]);
  const recreated = await open(active === first ? "invited" : "other");
  const reopened = await state(recreated);
  assert(reopened.encounter.yours);
  assert.equal(reopened.encounter.round,2);
  assert.deepEqual(reopened.actors.find(actor => actor.label === actorName).cell,dest);
  await recreated.view.getByRole("button",{name:"Play",exact:true}).click();
  const menu = recreated.view.getByRole("dialog",{name:"Choose a Play",exact:true});
  await selectPlayCategory(menu,"Fight");
  await menu.getByRole("button",{name:"Engage",exact:true}).click();
  await menu.getByRole("button",{name:"Open Play",exact:true}).click();
  const engage = reopened.actions.find(action => action.id === "engage");
  await recreated.view.getByLabel("Target",{exact:true}).selectOption(engage.targets.find(target => target.label === "Opposing guard").id);
  await recreated.view.getByLabel(engage.trigger,{exact:true}).fill("Engage the opposing guard on the marked square.");
  await recreated.view.getByRole("button",{name:"Roll Engage",exact:true}).click();
  const rolled = await waitFor(recreated, view => view.play?.play === "engage" && view.play.receipt);
  await submit(recreated,"end-turn",{revision:rolled.revision},409);
  const assigned = await waitFor(handler, view => view.choices.some(row => row.kind === "tag_window"));
  assert(assigned.choices.every(choice => choice.role === "handler"));
  const assignedChoice = assigned.choices.find(row => row.kind === "tag_window");
  const answer = {id:assignedChoice.id,revision:assignedChoice.revision,role:"handler",answer:{options:["pass"]}};
  await submit(recreated,"choice",answer,409);
  await submit(handler,"choice",answer);
  console.log("Private Battlefield passed owned pilot movement, Handler-only enemy movement, voluntary Core exposure, mixed-cast transfer, and owned review and Tag responses.");
  return {role:active === first ? "invited" : "other", actorName, dest, enemyDest, receipt:rolled.play.receipt};
}

async function verifyPlayParity(browser, server, saved) {
  const pilot = await openPilot(browser, server, "invited");
  const peer = await openPilot(browser, server, "other");
  const handler = await openPilot(browser, server, "handler");
  const api = async (member, operation = "", data, key = randomUUID(), status = 200) => {
    const response = await member.page.request.fetch(server.origin + "/api/player-setup" + operation, {
      method:data ? "POST" : "GET",
      data,
      headers:{Authorization:"Bearer " + member.session, Origin:server.discord_activity_origin, "Idempotency-Key":key},
    });
    assert.equal(response.status(), status, await response.text());
    return response.json();
  };
  const poll = async check => {
    for (let visit = 0; visit < 55; visit++) {
      const value = await check();
      if (value) return value;
      await new Promise(resolve => setTimeout(resolve,200));
    }
    assert.fail("The isolated Activity did not reach the expected decision.");
  };
  const choice = (member, kind) => poll(async () => {
    const state = await api(member);
    return member === handler ? state.handler_choices.find(item => item.choice.kind === kind)?.choice
      : state.scene.keep.choices.find(item => item.kind === kind);
  });
  const file = (member, row, answer, key, status) => api(member, "/keep-choice", {
    id:row.id, revision:row.revision, role:row.role, answer,
  }, key, status);
  const mine = await api(pilot);
  assert.equal(mine.stage, "active");
  assert.notEqual(mine.callsign, (await api(peer)).callsign);
  assert.equal((await api(handler)).stage, "handler");
  if (saved) {
    const answer = await choice(handler, "handler_keep");
    assert.equal(answer.id, saved.choice);
    assert.deepEqual(mine.scene.keep.current.receipt, saved.roll);
    assert(!mine.scene.keep.choices.some(item => item.id === saved.choice));
    const response = {flag:true, text:"The original pilot held steady."};
    await file(pilot, answer, response, randomUUID(), 409);
    const key = randomUUID();
    const filed = await file(handler, answer, response, key);
    assert.deepEqual(await file(handler, answer, response, key), filed);
    const final = await poll(async () => {
      const play = (await api(pilot)).scene.keep.current;
      return play?.state === "complete" && play;
    });
    assert.deepEqual(final.receipt, saved.roll);
    assert.equal(final.result.ruling, response.text);
    return;
  }
  assert(mine.scene.keep.can_start);
  const payload = {context:"Hold steady through the terminal outage.", confirmed:true,
    character_revision:mine.scene.keep.character_revision};
  const key = randomUUID();
  const started = await api(pilot, "/keep-start", payload, key);
  assert.deepEqual(await api(pilot, "/keep-start", payload, key), started);
  await file(pilot, await choice(pilot, "tag_window"), {options:["pass"]});
  await file(handler, await choice(handler, "tag_window"), {options:["pass"]});
  const peerTag = (await api(peer)).scene.keep.choices.find(row => row.kind === "tag_window");
  if (peerTag) await file(peer, peerTag, {options:["pass"]});
  await file(pilot, await choice(pilot, "actor_keep"),
    {options:["tough", "in_control"], denied:["desperate"]});
  const pending = await choice(handler, "handler_keep");
  const root = (await api(pilot)).scene.keep.current;
  assert.equal(root.id, started.action_id);
  assert.deepEqual(root.receipt.faces, [4,5]);
  return {choice:pending.id, roll:root.receipt};
}

async function verifyPartialEnrollment(browser, server) {
  const dialog = pilot => pilot.view.locator("#enrollment-dialog");
  const field = (pilot, label) => dialog(pilot).getByLabel(label, {exact:true});
  const button = (pilot, label) => dialog(pilot).getByRole("button", {name:label, exact:true});
  const load = async pilot => {
    const response = await fetch(server.origin + "/api/player-setup", {
      headers:{Authorization:"Bearer " + pilot.session}, signal:AbortSignal.timeout(8000),
    });
    assert.equal(response.status, 200);
    return response.json();
  };
  const pilot = await openPilot(browser, server, "invited");
  await pilot.page.setViewportSize({width:390, height:720});
  await field(pilot, "Callsign").fill("TEST RAIL");
  await button(pilot, "File callsign").click();
  const frameName = field(pilot, "Frame name");
  await frameName.fill("First draft");
  const before = await load(pilot);
  const firstAsset = before.options.girl_assets[0];
  await field(pilot, "Pilot asset 1").selectOption(firstAsset);
  await field(pilot, "Pilot asset 1 description").fill("A scratched visor.");
  const filed = pilot.page.waitForResponse(response =>
    new URL(response.url()).pathname === "/api/player-setup/build" &&
    response.request().method() === "POST");
  await button(pilot, "File enrollment draft").click();
  assert.equal((await filed).status(), 200);
  await pilot.view.getByText("ENROLLMENT RECORD FILED", {exact:true}).waitFor();
  await pilot.page.context().close();

  const reopened = await openPilot(browser, server, "invited");
  const restored = await load(reopened);
  assert.equal(restored.revision, before.revision + 1);
  assert.equal(restored.stage, "draft");
  assert.equal(restored.review.ready, false);
  assert.equal(restored.draft.frame_name, "First draft");
  assert.deepEqual(restored.draft.girl_assets, [{name:firstAsset, description:"A scratched visor."}]);
  assert.deepEqual(restored.draft.frame_assets, []);
  assert.equal(await field(reopened, "Frame name").inputValue(), "First draft");
  assert.equal(await field(reopened, "Pilot asset 1 description").inputValue(), "A scratched visor.");
  await button(reopened, "Review").click();
  assert.equal(await button(reopened, "Activate pilot").count(), 0);
  await reopened.page.context().close();
}

async function mainTest() {
  let server;
  let browser;
  try {
    server = await startServer();
    if (discordOffline) {
      const request = (route, options = {}) => fetch(server.origin + route, {
        ...options, signal: AbortSignal.timeout(8000),
        headers: {Origin:server.discord_activity_origin, ...options.headers},
      });
      assert.equal((await request("/api/mission-offers")).status,401);
      const challenge = await request("/api/discord/challenge",{method:"POST"});
      assert.equal(challenge.status,200);
      const {nonce} = await challenge.json();
      const exchange = (guild_id, code = "invited", challengeNonce = nonce) => request("/api/discord/session",{
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({code,nonce:challengeNonce,guild_id}),
      });
      assert.equal((await exchange("555555555555555555")).status,403);
      assert.equal((await exchange("222222222222222222")).status,400);
      const deniedDmUsers = dmOffline ? ["other", "pending-member"] : campaignDmCheck ? ["unapproved"] : ["invited"];
      for (const code of deniedDmUsers) {
        const fresh = await request("/api/discord/challenge",{method:"POST"});
        assert.equal((await exchange(null, code, (await fresh.json()).nonce)).status,403);
      }
    }
    browser = await chromium.launch({
      executablePath: chromePath ?? chromium.executablePath(),
      headless: true, args: ["--disable-background-networking", "--disable-sync"],
    });
    if (enrollmentDraftCheck) {
      await verifyPartialEnrollment(browser, server);
      console.log("Partial enrollment survived a fresh synthetic Discord sign-in and stayed pending.");
      return;
    }
    if (playParityCheck) {
      const pending = await verifyPlayParity(browser, server);
      await Promise.all(browser.contexts().map(context => context.close()));
      await stopServer(server);
      server = await startServer();
      await verifyPlayParity(browser, server, pending);
      console.log("Simulated Discord verified both pilot sheets, the separate Handler ruling, retry, and the original roll after restart.");
      return;
    }
    if (sceneArtworkCheck) {
      await verifySceneArtworkStability(browser,server);
      console.log("P2 scene artwork kept its image and height through refresh, swapped after decode, and cleared on room change.");
      return;
    }
    if (p2BattlefieldCheck) {
      const saved = await verifyP2Battlefield(browser,server);
      await Promise.all(browser.contexts().map(context => context.close()));
      await stopServer(server);
      server = await startServer();
      await verifyP2Battlefield(browser,server,saved);
      console.log(saved.blocked
        ? "Copied P2 rehearsal filed a facility and preserved the unresolved source Play restriction across restart."
        : "P2 " + p2Facility + " passed Handler map selection, wall checks, diagonal pilot movement, enemy movement, turn ownership, and owner-only Engage resolution after restart.");
      return;
    }
    if (intelCheck) {
      const intel = await verifySceneIntel(browser,server);
      await Promise.all(browser.contexts().map(context => context.close()));
      await stopServer(server);
      server = await startServer();
      await verifySceneIntel(browser,server,intel);
      console.log("P2 Share Intel delivered one private Inbox report across retries and reopening. The recipient could not read or join the source transcript through the report.");
      return;
    }
    if (archiveCheck) {
      const archived = await verifySceneArchive(browser,server);
      await Promise.all(browser.contexts().map(context => context.close()));
      await stopServer(server);
      server = await startServer();
      await verifySceneArchive(browser,server,archived);
      console.log("P2 archive search and end times survived restart. Both old Inbox receipts opened their exact read-only entries with original rolls and rulings. A nonparticipant could neither list nor open a private archive.");
      return;
    }
    if (directorTrialCheck || directorDiscordCheck) {
      const saved = await verifyDirectorTrial(browser, server);
      await Promise.all(browser.contexts().map(context => context.close()));
      await stopServer(server);
      server = await startServer();
      await verifyDirectorTrial(browser, server, saved);
      console.log(directorDiscordCheck
        ? "Simulated Discord sign-in, private GM proposal, two pilot choices and the Handler ruling survived reopening and restart."
        : "P2 consent, authenticated private GM desk, declaration isolation, retry and fresh-process recovery passed.");
      return;
    }
    if (campaignDmCheck) {
      const multiple = await openPilot(browser, server, "invited", false, undefined, undefined, {dm:true, pickCampaign:"Southern Signal"});
      assert.equal(await multiple.view.locator("#campaign-name").textContent(), "Southern Signal");
      const single = await openPilot(browser, server, "role-pilot", false, undefined, undefined, {dm:true});
      assert.equal(await single.view.locator("#campaign-name").textContent(), "Northern Reach");
      assert.equal(await single.view.getByRole("dialog",{name:"Choose a campaign"}).isVisible(), false);
      console.log("DM launch offered a campaign picker for two approved bindings, opened the sole binding automatically, and denied a user without a campaign role.");
      return;
    }
    const owner = await openPilot(browser, server, "invited", discordOffline);
    if (rosterBattlefieldCheck) {
      const route = server.origin + "/api/presence";
      assert.equal((await fetch(route)).status,401);
      const result = await fetch(route,{headers:{Authorization:`Bearer ${owner.session}`}});
      assert.equal(result.status,200);
      const roster = (await result.json()).members;
      assert.equal(roster.length,3);
      assert.equal(roster.find(person => person.id === discordUsers.invited).online,true);
      assert.equal(roster.find(person => person.id === discordUsers.other).online,false);
      assert.equal(roster.find(person => person.id === discordUsers.other).enrolled,false);
      await owner.view.locator("#desk-rail")
        .getByText("Offline · Enrollment pending",{exact:true}).waitFor({state:"attached"});
    }
    if (playRailCheck) {
      await verifyPlayRail(owner);
      return;
    }
    if (artworkCheck) {
      await verifyArtwork(owner);
      console.log("Artwork previews, scene and profile persistence, transcript portraits, Frame selection and clearing passed.");
      return;
    }
    const other = dmOffline ? null : await openPilot(browser, server, "other");
    async function request(pilot, route, options = {}) {
      const cookies = await pilot.page.context().cookies(server.origin);
      const cookie = cookies.map(({name,value}) => `${name}=${value}`).join("; ");
      const credentials = pilot.session ? {Authorization:`Bearer ${pilot.session}`} : {Cookie:cookie};
      const target = new URL(route, server.origin);
      if (campaignSwitchCheck && !target.searchParams.has("campaign")) {
        const selected = await pilot.view.locator("html").evaluate(() => new URL(location.href).searchParams.get("campaign"));
        if (selected) target.searchParams.set("campaign", selected);
      }
      return fetch(target, {
        ...options, signal: AbortSignal.timeout(8000),
        headers: {...credentials, ...options.headers},
      });
    }
    const setupRoute = "/api/player-setup";
    const playerSetup = async pilot => {
      const response = await request(pilot, setupRoute);
      assert.equal(response.status, 200);
      return response.json();
    };
    const setupPost = (pilot, step, body) => request(pilot, setupRoute + "/" + step, {
      method:"POST",
      headers: { Origin: server.discord_activity_origin ?? server.origin, "Idempotency-Key": randomUUID(), "Content-Type":"application/json" },
      body: JSON.stringify(body),
    });
    if (boundRosterCheck) {
      if (campaignSwitchCheck) {
        await verifyCampaignSwitch(browser, server, owner, other, request, playerSetup, setupPost);
        return;
      }
      await verifyBoundRoster(browser, server, owner, other, playerSetup, setupPost);
      if (sceneOrdersCheck) await verifySceneOrders(browser, server, setupPost, playerSetup);
      if (missionDeskCheck) {
        const objective = await verifyMissionDesk(browser, server);
        await Promise.all(browser.contexts().map(context => context.close()));
        await stopServer(server);
        server = await startServer();
        const handler = await openPilot(browser, server, "handler");
        const close = handler.view.getByRole("button",{name:"Close inbox",exact:true});
        if (await close.isVisible()) await close.click();
        await handler.view.getByRole("button",{name:"Missions",exact:true}).click();
        const desk = handler.view.locator("#mission-desk");
        await desk.locator("article").filter({hasText:objective}).getByText("Debrief filed",{exact:true}).waitFor();
        await desk.getByRole("button",{name:"Open current Off-Duty"}).click();
        await handler.view.locator("#off-duty-panel").getByText("Set initial Strain",{exact:true}).waitFor();
        console.log("The filed debrief and preparing Off-Duty persisted after restarting the private fixture.");
      }
      if (rosterBattlefieldCheck) {
        const saved = await verifyRosterBattlefield(browser, server, request);
        await Promise.all(browser.contexts().map(context => context.close()));
        await stopServer(server);
        server = await startServer();
        const pilot = await openPilot(browser, server, saved.role);
        const recovered = await request(pilot, "/api/battlefield");
        assert.equal(recovered.status,200);
        const restored = await recovered.json();
        assert.equal(restored.encounter.active,saved.actorName);
        assert.deepEqual(restored.actors.find(actor => actor.label === saved.actorName).cell,saved.dest);
        assert(restored.actors.find(actor => actor.label === saved.actorName).core_exposed);
        assert.deepEqual(restored.actors.find(actor => actor.enemy).cell,saved.enemyDest);
        assert.deepEqual(restored.play.receipt,saved.receipt);
        console.log("Pilot and enemy positions, round, Core exposure and the original roll survived restarting the private lab.");
      }
      return;
    }
    const conversation = "/api/communications/";
    let savedCommunication;
    let savedRelayOptions;
    let savedRoomPlay;
    if (other) {
      assert.notEqual(owner.page.context(), other.page.context());
      await other.view.getByText("No mail filed.").waitFor();
      await owner.view.getByRole("button", {name:"Close inbox"}).click();
      await owner.view.getByRole("button", {name:/Outpost K-12/}).click();
      await owner.view.getByRole("button", {name:"Start scene"}).click();
      await owner.view.getByLabel("Scene name").fill("Signal Watch");
      await owner.view.getByRole("button", {name:"Create room"}).click();
      await owner.view.getByRole("heading", {name:"Signal Watch"}).waitFor();
      assert(await owner.view.getByRole("button", {name:"Enter scene for Plays"}).isVisible());
      assert.equal(await owner.view.locator("#scene-play-options").isVisible(), false);
      await owner.view.getByLabel("Dialogue or narration").fill("SYNTH records a clean signal.");
      await owner.view.getByRole("button", {name:"File transmission"}).click();
      await owner.view.getByText("SYNTH records a clean signal.", {exact:true}).waitFor();
      const room = (await playerSetup(owner)).directory.rooms.find(item => item.name === "Signal Watch");
      const transcript = "/api/rooms/" + room.id + "/transcript";
      assert.equal((await request(other,transcript)).status,403);
      await owner.view.getByRole("button", {name:"Invite to room"}).click();
      if (discordOffline) {
        await owner.view.getByRole("button", {name:"Discord invite"}).click();
        await owner.view.locator("html[data-native-invite-opened='true']").waitFor();
      }
      await owner.view.getByRole("button", {name:"Generate binding code"}).click();
      const hostCode = owner.view.getByRole("dialog").getByLabel("Binding code");
      await hostCode.waitFor();
      const bindingCode = await hostCode.inputValue();
      assert.equal(bindingCode.length, 12);
      await owner.view.getByRole("button", {name:"Close invitation"}).click();
      assert.equal((await setupPost(owner,"invite-redeem",{code:bindingCode})).status,409);
      await other.view.getByRole("button", {name:"Close inbox"}).click();
      await other.view.locator(".campaign-menu summary").click();
      await other.view.getByRole("button", {name:"Join by binding code", exact:true}).click();
      await other.view.getByRole("dialog").getByLabel("Binding code").fill(bindingCode);
      await other.view.getByRole("button", {name:"Redeem binding code"}).click();
      await other.view.getByRole("heading", {name:"Signal Watch"}).waitFor();
      await other.view.locator("#room-access").getByText("Joined",{exact:true}).waitFor();
      assert.equal((await setupPost(other,"invite-issue",{target:"campaign"})).status,409);
      await owner.view.locator("#inbox-toggle").click();
      const recruit = await playerSetup(other);
      assert.equal(recruit.stage, "profile");
      assert.equal((await setupPost(other, "join-scene", {})).status, 409);
      assert.equal((await setupPost(owner, "profile", {revision:recruit.revision,callsign:"FORGED"})).status, 409);
      await other.view.getByLabel("Callsign", {exact:true}).fill("FALLOW");
      await other.view.getByRole("button", {name:"Save callsign"}).click();
      await other.view.getByText("Create pilot · FALLOW").waitFor();
      const incomplete = await playerSetup(other);
      assert.equal(incomplete.review.ready, false);
      assert.equal((await setupPost(other,"activate",{fingerprint:incomplete.review.fingerprint})).status,409);
      const choices = incomplete.options;
      for (const [label, text] of [
        ["Frame name","Watchlight"], ["Pilot appearance","Grey visor"],
        ["Frame appearance","White ceramic shell"], ["NPC name","Iris"],
      ]) await other.view.getByLabel(label, {exact:true}).fill(text);
      for (const [family, options] of [["Pilot", choices.girl_assets], ["Frame", choices.frame_assets]]) {
        for (let index = 0; index < 2; index++) {
          await other.view.getByLabel(`${family} asset ${index+1}`, {exact:true}).selectOption(options[index]);
          await other.view.getByLabel(`${family} asset ${index+1} description`, {exact:true}).fill("Synthetic test fixture");
        }
    }
    await other.view.getByLabel("Void-altered pilot asset").selectOption(choices.girl_assets[0]);
    const draftSaved = other.page.waitForResponse(response => response.url().endsWith(setupRoute) && response.request().method() === "GET");
    await other.view.getByRole("button", {name:"Save character draft"}).click();
    const savedDraft = await draftSaved;
    assert.equal((await savedDraft.json()).draft.frame_name, "Watchlight");
    await other.view.getByRole("button", {name:"Propose starting Bond"}).click();
      await other.view.locator("#inbox-toggle").click();
    await other.view.locator("#mail-entries").getByRole("button", {name:/^Starting Bond/}).click();
    await other.view.getByText("Awaiting a response").waitFor();
    const pendingBond = (await playerSetup(other)).bonds[0];
    assert.equal((await setupPost(other, "bond-decision", {
      id:pendingBond.id, revision:pendingBond.revision, decision:"accept",
    })).status, 409);
    const bondReviewer = await openPilot(browser, server, "invited");
    await bondReviewer.view.locator("#mail-entries").getByRole("button", {name:/^Starting Bond/}).click();
    await bondReviewer.view.getByRole("button", {name:"Accept Bond"}).click();
    await bondReviewer.view.getByText("Bond accepted").waitFor();
    await bondReviewer.page.context().close();
    const refreshedRecruit = await openPilot(browser, server, "other");
    assert.equal((await playerSetup(refreshedRecruit)).draft.frame_name, "Watchlight");
      await refreshedRecruit.view.getByRole("button", {name:"Close inbox"}).click();
    await refreshedRecruit.view.getByRole("button", {name:"Save activation review"}).click();
    await refreshedRecruit.view.getByRole("button", {name:"Activate pilot"}).click();
      await refreshedRecruit.view.getByRole("button", {name:"Open Relay operations"}).click();
    await refreshedRecruit.view.getByRole("button", {name:"Join scene"}).waitFor();
    assert.deepEqual((await playerSetup(refreshedRecruit)).scene.plays, []);
    await refreshedRecruit.view.getByRole("button", {name:"Pilot Profile",exact:true}).click();
    const recruitProfile = refreshedRecruit.view.locator("#profile-pane");
    await selectPlayCategory(recruitProfile, "Recover");
    await recruitProfile.getByRole("button",{name:"Keep Your Head",exact:true}).click();
    const recruitPicker = refreshedRecruit.view.getByRole("dialog",{name:"Keep Your Head",exact:true});
    await recruitPicker.getByRole("radio",{name:"Relay operations",exact:true}).check();
    await recruitPicker.getByRole("button",{name:"Join and open Play",exact:true}).click();
    await refreshedRecruit.view.getByRole("heading", {name:"Scene Plays"}).waitFor();
    await refreshedRecruit.view.getByRole("region", {name:"Scenes", exact:true})
      .getByText("Describe what you are trying to endure", {exact:true}).waitFor();
    await refreshedRecruit.view.getByLabel("What are you trying to endure?",{exact:true}).waitFor();
    const joined = await playerSetup(refreshedRecruit);
    assert.equal(joined.scene.joined, true);
    assert.equal(joined.scene.keep.current, null);
    assert.deepEqual(joined.scene.plays.map(play => play.id),
      ["keep_your_head", "check_sensors", "engage", "flirt"]);
    assert.ok(joined.scene.pilots.includes("FALLOW"));
    if (communicationsCheck || relayPlaysCheck || roomPlaysCheck) {
      const sender = await openPilot(browser, server, "invited");
      await sender.view.getByRole("button", {name:"Close inbox"}).click();
      const openRelay = async pilot => {
        await pilot.view.getByRole("button", {name:"Open Relay operations"}).click();
        await pilot.view.getByRole("heading", {name:"Scene Plays",exact:true}).waitFor();
      };
      if (communicationsCheck) {
        const desk = sender.view.locator("#communications");
        await desk.getByText("Foundation networks are monitored. The Handler may respond to DMs.").waitFor();
        assert.equal(await sender.view.locator("#pilot").textContent(), "SYNTH | Ace");
        assert(await desk.evaluate(node => node.closest("aside").getBoundingClientRect().left >= document.querySelector("main").getBoundingClientRect().right - 1));
        const senderRecord = await playerSetup(sender);
        const toFallow = senderRecord.communications.find(item => item.label === "FALLOW");
        const toSynth = joined.communications.find(item => item.label === "SYNTH");
        const toHandler = senderRecord.communications.find(item => item.label === "Handler");
        const send = (pilot, contact, text, key) => request(pilot, conversation + contact.id, {
          method:"POST", headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":key},
          body:JSON.stringify({text}),
        });
        const read = async (pilot, contact) => {
          const response = await request(pilot, conversation + contact.id);
          assert.equal(response.status,200);
          return (await response.json()).entries;
        };
        assert.equal((await fetch(server.origin + conversation + toFallow.id)).status,401);
        await desk.getByRole("button",{name:/^FALLOW/}).click();
        const dialog = sender.view.getByRole("dialog",{name:"Private communication · FALLOW"});
        await dialog.getByRole("textbox",{name:"Private message",exact:true}).fill("Meet at the observation deck.");
        const posted = sender.page.waitForResponse(response => response.request().method() === "POST" && response.url().includes(conversation));
        await dialog.getByRole("button",{name:"Send message"}).click();
        const sent = await posted;
        assert.equal(sent.status(),200,await sent.text());
        const messageKey = sent.request().headers()["idempotency-key"];
        assert.deepEqual(await (await send(sender,toFallow,"Meet at the observation deck.",messageKey)).json(),await sent.json());
        assert.equal((await send(sender,toFallow,"A different message.",messageKey)).status,409);
        await dialog.getByText("Meet at the observation deck.",{exact:true}).waitFor();
        await dialog.getByRole("button",{name:"Close private communication"}).click();
        const received = await read(refreshedRecruit,toSynth);
        assert.equal(received.length,1);
        assert.equal(received[0].body,"Meet at the observation deck.");
        assert.equal((await request(sender,conversation + toSynth.id)).status,403);
        await refreshedRecruit.view.getByRole("button",{name:"Check for updates"}).click();
        await refreshedRecruit.view.locator("#inbox-toggle").click();
        await refreshedRecruit.view.getByRole("button",{name:"Message from SYNTH",exact:true}).click();
        await refreshedRecruit.view.getByRole("dialog").getByText("Meet at the observation deck.",{exact:true}).waitFor();
        const exactMessage = refreshedRecruit.view.locator(`[data-message="${received[0].id}"]`);
        assert(await exactMessage.evaluate(message => document.activeElement === message));
        await refreshedRecruit.view.getByRole("button",{name:"Close private communication"}).click();
        const handler = await openPilot(browser, server, "handler");
        await handler.view.getByRole("button",{name:"Close inbox"}).click();
        assert.deepEqual(await read(handler,toFallow),[]);
        assert.deepEqual(await read(handler,toSynth),[]);
        assert.equal((await request(handler,"/api/battlefield")).status,403);
        assert.equal((await send(sender,toHandler,"May I review the relay report?",randomUUID())).status,200);
        await handler.view.locator("#communications").getByRole("button",{name:/^SYNTH/}).click();
        const handlerThread = handler.view.getByRole("dialog",{name:"Private communication · SYNTH"});
        await handlerThread.getByText("May I review the relay report?",{exact:true}).waitFor();
        await handlerThread.getByRole("textbox",{name:"Private message",exact:true}).fill("Report access granted.");
        await handlerThread.getByRole("button",{name:"Send message"}).click();
        await handlerThread.getByText("Report access granted.",{exact:true}).waitFor();
        const reply = await read(sender,toHandler);
        assert.deepEqual(reply.map(entry => entry.callsign),["SYNTH","Handler"]);
        assert.deepEqual(await read(refreshedRecruit,toHandler),[]);
        savedCommunication = received;
        await handler.page.context().close();
      }
      if (relayPlaysCheck) {
        await openRelay(sender);
        await sender.view.getByRole("button",{name:"Safety pause",exact:true}).click();
        const resume = sender.view.getByRole("button",{name:"Clear my safety pause",exact:true});
        await resume.waitFor();
        const paused = (await playerSetup(refreshedRecruit)).scene;
        assert.equal(paused.safety.paused,true);
        assert.equal(paused.safety.own,false);
        assert.equal(paused.options.check_sensors.can_start,false);
        await resume.click();
        await sender.view.getByRole("button",{name:"Safety pause",exact:true}).waitFor();
        const waitOptions = async (pilot, play, check) => {
          for (let attempt = 0; attempt < 60; attempt++) {
            const result = (await playerSetup(pilot)).scene.options[play];
            if (check(result)) return result;
            await new Promise(resolve => setTimeout(resolve,125));
          }
          throw new Error("Timed out waiting for relay " + play);
        };
        const postChoice = async (pilot, choice, answer, expected = 200) => {
          const response = await setupPost(pilot,"scene-choice",{id:choice.id,revision:choice.revision,role:choice.role,answer});
          assert.equal(response.status,expected,await response.text());
        };
        const firstChoice = async (pilot, play, kind) =>
          (await waitOptions(pilot,play,state => state.choices.some(choice => choice.kind === kind))).choices.find(item => item.kind === kind);
        const finishTags = async (play, target) => {
          if (target) await postChoice(target,await firstChoice(target,play,"tag_window"),{options:["pass"]});
          for (const role of ["pilot","handler"]) {
            const state = await waitOptions(sender,play,data => data.choices.some(choice => choice.kind === "tag_window" && choice.role === role));
            await postChoice(sender,state.choices.find(choice => choice.kind === "tag_window" && choice.role === role),{options:["pass"]});
          }
        };
        const startPlay = async (play, context, target = null) => {
          const option = await waitOptions(sender,play,state => state.can_start);
          const response = await setupPost(sender,"scene-start",{play,context,target,confirmed:true,character_revision:option.character_revision});
          assert.equal(response.status,200,await response.text());
        };
        const sensors = sender.view.locator("#scene-action-dialog");
        await selectPlayCategory(sender.view.locator("#scene-play-options"), "Scan");
        await sender.view.locator('#scene-play-options button[data-play="check_sensors"]').click();
        await sensors.locator('input[name="context"]').fill("Sweep the relay approach.");
        await sensors.getByRole("button",{name:"Roll Check Sensors",exact:true}).click();
        await finishTags("check_sensors",refreshedRecruit);
        const questions = await firstChoice(sender,"check_sensors","actor_sensors");
        const listed = questions.fields.find(field => field.key === "options");
        await postChoice(sender,questions,{options:listed.options.slice(0,listed.maximum).map(([id]) => id)});
        const answers = await firstChoice(sender,"check_sensors","handler_sensors");
        await postChoice(sender,answers,{fields:Object.fromEntries(answers.fields.map(field => [field.key.slice(7),"Signal confirmed."]))});
        await waitOptions(sender,"check_sensors",state => state.current?.state === "complete");
        await sensors.getByRole("button",{name:"Close scene Play",exact:true}).click();
        await startPlay("engage","Hold the relay approach.");
        await finishTags("engage",refreshedRecruit);
        const engage = await firstChoice(sender,"engage","actor_engage");
        const moves = engage.fields.find(field => field.key === "options");
        const options = moves.options.slice(0,moves.minimum).map(([id]) => id);
        const resources = Object.fromEntries(options.map(id => [id,engage.fields.find(field => field.key === "fields." + id).options[0][0]]));
        const damage = engage.fields.some(field => field.key === "denied") ? {denied:[resources[options[0]]]} : {};
        await postChoice(sender,engage,{options,fields:resources,...damage});
        await waitOptions(sender,"engage",state => state.current?.state === "complete");
        const flirt = await waitOptions(sender,"flirt",state => state.can_start);
        assert.equal(flirt.targets.length,1);
        await startPlay("flirt","Ask what would make the next watch easier.",flirt.targets[0].id);
        await finishTags("flirt",refreshedRecruit);
        const question = await firstChoice(sender,"flirt","actor_flirt");
        const topic = question.fields[0].options.find(([key]) => key !== "intimacy")[0];
        const extra = question.fields.some(field => field.key === "fields.extra")
          ? {fields:{extra:"owe"},text:"I ask for more than the watch handoff."} : {};
        await postChoice(sender,question,{options:[topic],...extra});
        const reply = await firstChoice(refreshedRecruit,"flirt","target_flirt");
        assert(!(await playerSetup(sender)).scene.options.flirt.choices.some(choice => choice.id === reply.id));
        await postChoice(sender,reply,{text:"Forged response."},409);
        const returnTopic = !extra.fields && reply.fields.find(field => field.key === "options")?.options.find(([id]) => id !== "intimacy")?.[0];
        await postChoice(refreshedRecruit,reply,{text:"Give me the next watch.",...(returnTopic ? {options:[returnTopic]} : {})});
        if (extra.fields) {
          const owe = await firstChoice(refreshedRecruit,"flirt","flirt_owe_tag");
          await postChoice(sender,owe,{text:"Forged Tag."},409);
          await postChoice(refreshedRecruit,owe,{text:"Owes a favor"});
        }
        if (returnTopic) {
          const ownAnswer = await firstChoice(sender,"flirt","actor_flirt_answer");
          await postChoice(refreshedRecruit,ownAnswer,{text:"Forged return answer."},409);
          await postChoice(sender,ownAnswer,{text:"I’ll bring the spare receiver."});
        }
        await waitOptions(sender,"flirt",state => state.current?.state === "complete");
        const follow = await waitOptions(sender,"flirt_followthrough",state => state.can_start);
        await startPlay("flirt_followthrough","Swap assignments for the next watch.",follow.targets[0].id);
        const ownFollow = await firstChoice(refreshedRecruit,"flirt_followthrough","followthrough_confirm");
        await postChoice(sender,ownFollow,{flag:true,text:"Forged confirmation."},409);
        await postChoice(refreshedRecruit,ownFollow,{flag:true,text:"The assignment is updated."});
        await waitOptions(sender,"flirt_followthrough",state => state.current?.state === "complete");
        savedRelayOptions = (await playerSetup(sender)).scene.options;
      }
      if (roomPlaysCheck) {
        const shared = (await playerSetup(sender)).directory.rooms.find(item => item.name === "Signal Watch");
        assert(shared.available_play_ids.includes("check_sensors"));
        assert(!shared.available_play_ids.includes("flirt"));
        const privateRoom = await setupPost(sender,"room-create",{name:"East catwalk",location:"hangar"});
        assert.equal(privateRoom.status,200);
        const {room:privateId} = await privateRoom.json();
        const outsiderRoom = (await playerSetup(refreshedRecruit)).directory.rooms.find(item => item.id === privateId);
        assert.equal(outsiderRoom.available_play_ids,undefined);
        assert.equal((await setupPost(refreshedRecruit,"enter-scene",{room:privateId})).status,409);
        await sender.view.getByRole("button",{name:"Pilot Profile",exact:true}).click();
        await selectPlayCategory(sender.view.locator("#profile-pane"), "Scan");
        await sender.view.locator("#profile-pane").getByRole("button",{name:"Check Sensors",exact:true}).click();
        const selection = sender.view.getByRole("dialog",{name:"Check Sensors",exact:true});
        await selection.getByRole("radio",{name:"Signal Watch",exact:true}).check();
        await selection.getByRole("button",{name:"Switch and open Play"}).click();
        await sender.view.getByRole("heading",{name:"Signal Watch",exact:true}).waitFor();
        await sender.view.getByText("SYNTH records a clean signal.",{exact:true}).waitFor();
        const control = sender.view.locator("#scene-action-dialog");
        await control.getByRole("button",{name:"Roll Check Sensors",exact:true}).waitFor();
        assert.equal((await (await request(sender,"/api/rooms/relay/transcript")).json()).entries.length,0);
        await control.locator('input[name="context"]').fill("Check the Signal Watch approaches.");
        assert.equal(await control.locator('input[type="checkbox"]').count(),0);
        await control.getByRole("button",{name:"Roll Check Sensors",exact:true}).click();
        const read = async () => (await playerSetup(sender)).active_scene;
        const waitChoice = async (kind, role) => {
          for (let attempt = 0; attempt < 60; attempt++) {
            const state = await read();
            assert.equal(state.id,shared.id);
            const choice = state.options.check_sensors.choices.find(item => item.kind === kind && item.role === role);
            if (choice) return choice;
            await new Promise(resolve => setTimeout(resolve,125));
          }
          throw new Error("Timed out waiting for created-scene " + kind);
        };
        const answer = async (choice, value, room = shared.id, status = 200) => {
          const response = await setupPost(sender,"scene-choice",{room,id:choice.id,revision:choice.revision,role:choice.role,answer:value});
          assert.equal(response.status,status,await response.text());
        };
        const ownTag = await waitChoice("tag_window","pilot");
        const waitingRooms = (await playerSetup(sender)).directory.rooms;
        assert.equal(waitingRooms.find(item => item.id === shared.id).play_availability.check_sensors.state,"resume");
        assert(waitingRooms.find(item => item.id === "relay").play_availability.check_sensors.reasons.some(reason => reason.code === "switch_busy"));
        assert.equal((await setupPost(sender,"enter-scene",{room:"relay"})).status,409);
        await answer(ownTag,{options:["pass"]},"relay",409);
        await answer(ownTag,{options:["pass"]});
        await answer(await waitChoice("tag_window","handler"),{options:["pass"]});
        const questions = await waitChoice("actor_sensors","pilot");
        const options = questions.fields.find(field => field.key === "options");
        await answer(questions,{options:options.options.slice(0,options.maximum).map(([id]) => id)});
        const answers = await waitChoice("handler_sensors","handler");
        await answer(answers,{fields:Object.fromEntries(answers.fields.map(field => [field.key.slice(7),"Signal Watch is clear."]))});
        await sender.view.getByRole("button",{name:"Check for updates"}).click();
        await sender.view.getByText("Check Sensors resolved",{exact:true}).waitFor();
        for (let attempt = 0; attempt < 40 && (await read()).locked; attempt++) {
          await new Promise(resolve => setTimeout(resolve,125));
        }
        const result = (await read()).options.check_sensors.current;
        assert.equal(result.state,"complete");

        await sender.view.getByRole("button",{name:"Pilot Profile",exact:true}).click();
        await selectPlayCategory(sender.view.locator("#profile-pane"), "Talk");
        await sender.view.locator("#profile-pane").getByRole("button",{name:"Flirt",exact:true}).click();
        const flirtPicker = sender.view.getByRole("dialog",{name:"Flirt",exact:true});
        const catwalk = flirtPicker.getByRole("listitem").filter({hasText:"East catwalk"});
        await catwalk.getByText("Another pilot must enter this scene for Plays.",{exact:true}).waitFor();
        assert.equal(await catwalk.getByRole("radio").count(),0);
        await catwalk.getByRole("button",{name:"Invite another pilot"}).click();
        const invite = sender.view.getByRole("dialog",{name:"Invite · East catwalk"});
        await invite.getByRole("button",{name:"Generate binding code"}).click();
        const field = invite.getByLabel("Binding code");
        await field.waitFor();
        const code = await field.inputValue();
        assert(code);
        assert.equal((await setupPost(refreshedRecruit,"invite-redeem",{code})).status,200);
        assert.equal((await setupPost(refreshedRecruit,"invite-issue",{target:privateId})).status,409);
        await invite.getByRole("button",{name:"Close invitation"}).click();
        await flirtPicker.getByRole("button",{name:"Refresh scene availability"}).click();
        await catwalk.getByText("Another pilot must enter this scene for Plays.",{exact:true}).waitFor();
        assert.equal((await setupPost(refreshedRecruit,"enter-scene",{room:privateId})).status,200);
        await flirtPicker.getByRole("button",{name:"Refresh scene availability"}).click();
        await catwalk.getByRole("radio",{name:"East catwalk",exact:true}).waitFor();
        await flirtPicker.getByRole("button",{name:"Close scene picker"}).click();

        assert.equal((await setupPost(refreshedRecruit,"enter-scene",{room:shared.id})).status,200);
        const current = await playerSetup(sender);
        const now = current.directory.rooms.find(item => item.id === shared.id);
        assert(now.available_play_ids.includes("flirt"));
        await sender.view.getByRole("button",{name:"Back",exact:true}).click();
        await sender.view.getByRole("button",{name:"Check for updates"}).click();
        const cast = sender.view.getByRole("region",{name:"Present Pilots",exact:true});
        const expectedCast = current.cadre.filter(pilot => current.active_scene.pilot_ids.includes(pilot.id));
        assert.equal(expectedCast.length,2);
        for (const pilot of expectedCast) {
          await cast.getByRole("button",{name:pilot.callsign + " | " + pilot.status,exact:true}).waitFor();
        }
        assert.equal((await setupPost(refreshedRecruit,"enter-scene",{room:"relay"})).status,200);
        assert.equal((await setupPost(sender,"enter-scene",{room:"relay"})).status,200);
        assert.equal((await playerSetup(sender)).active_scene.options.check_sensors.current,null);
        assert.equal((await setupPost(sender,"enter-scene",{room:shared.id})).status,200);
        assert.deepEqual((await read()).options.check_sensors.current,result);
        savedRoomPlay = {id:shared.id,result};
      }
      await sender.page.context().close();
    }
    await refreshedRecruit.page.context().close();
    console.log("Verified guided HarpyEngine creation, independent Bond response, activation, scene join, and Play menu.");
    }

    const list = await (await request(owner, "/api/mission-offers")).json();
    const offer = list.offers[0];
    assert.equal(offer.revision, 1);
    assert.equal(offer.needs_response, true);
    const route = `/api/mission-offers/${offer.id}/response`;
    const data = { expected_revision: offer.revision, response: "accept" };
    const post = (page, key, body = data) => request(page, route, {
      method: "POST",
      headers: { Origin: server.discord_activity_origin ?? server.origin, "Idempotency-Key": key, "Content-Type":"application/json" },
      body: JSON.stringify(body),
    });
    if (other) {
      const forbidden = await post(other, randomUUID());
      assert.equal(forbidden.status, 404);
      assert.deepEqual(await forbidden.json(), { error: "Mission offer unavailable." });
    }
    const pending = await (await request(owner, "/api/mission-offers")).json();
    assert.equal(pending.offers[0].needs_response, true);
    assert.equal(pending.offers[0].revision, 1);

    let failedKey;
    if (discordOffline && !dmOffline) {
      const failedSubmit = owner.page.waitForResponse(response => response.url().endsWith(route));
      await owner.view.getByRole("button", {name:"Accept mission"}).click();
      failedKey = (await failedSubmit).request().headers()["idempotency-key"];
      assert.ok(failedKey);
      await owner.view.getByText("The Activity returned an unexpected response (HTTP 502).").waitFor();
      assert.equal((await (await request(owner, "/api/mission-offers")).json()).offers[0].revision, 1);
    }
    const submit = owner.page.waitForResponse(response => response.url().endsWith(route));
    await owner.view.getByRole("button", { name: "Accept mission" }).click();
    const committed = await submit;
    const key = committed.request().headers()["idempotency-key"];
    assert.ok(key);
    if (failedKey) assert.equal(key, failedKey);
    assert.equal(committed.status(), dmOffline ? 502 : 200);
    await owner.view.getByText(savedLabel).waitFor();
    const duplicate = await post(owner, key);
    assert.equal(duplicate.status, 200);
    const receipt = await duplicate.json();
    assert.equal(receipt.revision, 2);
    assert.equal(receipt.response, "accept");
    assert.equal((await post(owner, key, { ...data, response:"decline" })).status, 409);
    assert.equal((await post(owner, randomUUID())).status, 409);
    if (other) assert.equal((await post(other, key)).status, 404);
    console.log("Verified initial response and safe retry.");

    let keepReceipt;
    let offDutyReceipt;
    let tacticalResult;
    let assaultResult;
    let sensorResult;
    let coreResult;
    let counterResult;
    if (dmOffline) {
      await verifyHud(owner);
      await owner.view.getByRole("button", {name:"Pilot Profile", exact:true}).click();
      await owner.view.locator("#profile-pane").getByText("SYNTH", {exact:true}).waitFor();
      assert(await owner.view.locator("#profile-pane").getByRole("heading", {name:"Sheet Plays"}).isVisible());
      assert(await owner.view.locator("#profile-pane .play-card").first().isVisible());
      const profile = owner.view.locator("#profile-pane");
      await selectPlayCategory(profile, "Recover");
      const profileKeep = profile.getByRole("button",{name:"Keep Your Head",exact:true});
      const keepPicker = owner.view.getByRole("dialog",{name:"Keep Your Head",exact:true});
      await profileKeep.click();
      await keepPicker.getByRole("heading",{name:"Which scene is this Play for?"}).waitFor();
      await keepPicker.getByRole("button",{name:"Close scene picker",exact:true}).click();
      assert(await profileKeep.evaluate(button => document.activeElement === button));
      await profileKeep.click();
      await keepPicker.getByRole("button",{name:"Continue in Relay operations",exact:true}).click();
      await owner.view.getByLabel("What are you trying to endure?",{exact:true}).waitFor();
      assert.equal((await playerSetup(owner)).scene.keep.current,null);
      await owner.view.getByRole("button",{name:"Back",exact:true}).click();
      await selectPlayCategory(profile, "Scan");
      await profile.getByRole("button",{name:"Check Sensors",exact:true}).click();
      const sensorsPicker = owner.view.getByRole("dialog",{name:"Check Sensors",exact:true});
      const drill = await (await request(owner,"/api/battlefield")).json();
      await sensorsPicker.getByRole("radio",{name:drill.title,exact:true}).check();
      await sensorsPicker.getByRole("button",{name:"Continue in Battlefield",exact:true}).click();
      await owner.view.locator("#tactical-controls").getByRole("button",{name:"Roll Check Sensors",exact:true}).waitFor();
      assert.equal((await (await request(owner,"/api/battlefield")).json()).play,null);
      await owner.view.getByRole("button",{name:"Back",exact:true}).click();
      const frame = (await playerSetup(owner)).profile;
      const expectedFrame = frame.frame_name || frame.frame;
      await owner.view.locator("#profile-pane").getByRole("button", {name:expectedFrame}).click();
      await owner.view.locator("#frame-data").getByRole("heading", {name:"Upgrades"}).waitFor();
      await owner.view.getByRole("button", {name:frame.assets[0].name, exact:true}).click();
      await owner.view.getByLabel("Description").fill("Operator-authored test description.");
      await owner.view.getByRole("button", {name:"Save description"}).click();
      await owner.view.getByText("Description saved.").waitFor();
      await owner.view.getByRole("button", {name:"Back", exact:true}).click();
      await owner.view.getByRole("button", {name:frame.assets[0].name, exact:true}).waitFor();
      await owner.view.getByRole("button", {name:"Back", exact:true}).click();
      await owner.view.locator("#profile-pane").getByText("SYNTH", {exact:true}).waitFor();
    }
    if (dmOffline && !sceneCheck && !orderCheck) {
      await owner.view.getByRole("button", {name:"Battlefield", exact:true}).click();
      const loadBattlefield = async pilot => {
        const response = await request(pilot, "/api/battlefield");
        assert.equal(response.status, 200);
        return response.json();
      };
      const sendBattlefield = (pilot, action, body) => request(pilot, "/api/battlefield/" + action, {
        method:"POST", headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":randomUUID()},
        body:JSON.stringify(body),
      });
      await owner.view.getByRole("button", {name:"Move", exact:true}).click();
      await owner.view.getByRole("button", {name:"Confirm move"}).waitFor();
      assert.equal(await owner.view.locator("#tactical-grid .tactical-cell").count(),54);
      const before = await loadBattlefield(owner);
      const move = before.actions.find(action => action.id === "move");
      assert.equal((await sendBattlefield(owner,"move",{
        actor:move.actor, frame:move.frame, revision:before.revision, destination:[9,7], account:"Invalid test destination",
      })).status,409);
      assert.equal((await sendBattlefield(owner,"engage",{
        target:move.actor, account:"Invalid self target", sheet_revision:before.sheet_revision, confirmed:true,
      })).status,409);
      await owner.view.getByRole("button", {name:/^Cell 2, 2/}).click();
      await owner.view.getByLabel("Describe the movement").fill("Reposition diagonally along the relay perimeter.");
      const moved = owner.page.waitForResponse(response => response.url().endsWith("/api/battlefield/move"));
      await owner.view.getByRole("button", {name:"Confirm move"}).click();
      assert.equal((await moved).status(), 200);
      await owner.view.getByRole("button", {name:/^Cell 2, 2 .*SYNTH/}).waitFor();
      const positioned = await loadBattlefield(owner);
      assert(positioned.roster.every(pilot => pilot.controlled || pilot.profile === null));
      assert.deepEqual(positioned.actors.find(actor => actor.controlled).cell,[2,2]);
      await owner.view.getByRole("button", {name:"Open pilot file for SYNTH", exact:true}).click();
      await owner.view.locator("#profile-pane").getByText("SYNTH", {exact:true}).waitFor();
      await owner.view.getByRole("button", {name:"Back", exact:true}).click();
      await owner.view.getByRole("button", {name:/^Cell 2, 2 .*SYNTH/}).waitFor();
      const engage = positioned.actions.find(action => action.id === "engage");
      assert.equal(engage.targets.length,1);
      assert.equal(engage.targets[0].separation,2);
      await owner.view.getByRole("button", {name:"Play", exact:true}).click();
      const plays = owner.view.getByRole("dialog", {name:"Choose a Play"});
      const openSelectedPlay = plays.getByRole("button", {name:"Open Play", exact:true});
      assert(await openSelectedPlay.isDisabled());
      await selectPlayCategory(plays, "Fight");
      await plays.getByRole("button", {name:"All-Out Assault"}).waitFor();
      const unlockedCatalog = positioned.roster.find(character => character.controlled);
      assert(unlockedCatalog.plays.some(play => play.id === "go_for_the_core"));
      assert(unlockedCatalog.plays.some(play => play.id === "mockingbird_person"));
      const observed = positioned.roster.find(character => !character.controlled);
      await plays.getByLabel("Character", {exact:true}).selectOption(observed.id);
      await plays.getByText("Sheet reference", {exact:true}).first().waitFor();
      assert.equal(await plays.getByRole("button", {name:"All-Out Assault", exact:true}).count(),0);
      await plays.getByLabel("Character", {exact:true}).selectOption(unlockedCatalog.id);
      if (process.env.HARPY_PLAY_MENU_CAPTURE && !coreCase) {
        await owner.page.locator("iframe").screenshot({path:process.env.HARPY_PLAY_MENU_CAPTURE});
      }
      await selectPlayCategory(plays, "Scan");
      await plays.getByRole("button", {name:"Check Sensors", exact:true}).click();
      assert.equal(await plays.locator("#tactical-play-state").textContent(), "PLAY SELECTED");
      await openSelectedPlay.click();
      const sensors = positioned.actions.find(action => action.id === "check_sensors");
      await owner.view.getByLabel(sensors.trigger, {exact:true}).fill("Take stock of the relay perimeter.");
      await owner.view.getByRole("button", {name:"Roll Check Sensors", exact:true}).click();
      for (const role of ["Pilot", "Test Handler", "Drill opponent"]) {
        await owner.view.getByRole("button", {name:role + " · Pass Tag window"}).click();
      }
      await owner.view.getByRole("button", {name:"Send sensor questions", exact:true}).waitFor();
      const questions = (await loadBattlefield(owner)).choices.find(choice => choice.kind === "actor_sensors").schema[0];
      await owner.view.getByLabel("Listed questions").selectOption(questions.options.slice(0,questions.maximum).map(option => option[0]));
      await owner.view.getByRole("button", {name:"Send sensor questions", exact:true}).click();
      await owner.view.getByRole("button", {name:"Save sensor answers", exact:true}).waitFor();
      const sensorAnswers = (await loadBattlefield(owner)).choices.find(choice => choice.kind === "handler_sensors");
      for (const [index, question] of sensorAnswers.questions.entries()) {
        await owner.view.getByLabel(question, {exact:true}).fill("Test sensor finding " + (index + 1));
      }
      await owner.view.getByRole("button", {name:"Save sensor answers", exact:true}).click();
      await owner.view.getByText("Test sensor finding 1", {exact:true}).waitFor();
      sensorResult = (await loadBattlefield(owner)).play;
      assert.equal(sensorResult.play,"check_sensors");
      assert.equal(sensorResult.state,"complete");
      assert.equal(sensorResult.receipt.faces.length,2);
      await owner.view.getByRole("button", {name:"Play", exact:true}).click();
      await selectPlayCategory(plays, "Fight");
      await plays.getByRole("button", {name:"Engage", exact:true}).click();
      await openSelectedPlay.click();
      await owner.view.getByLabel("Target", {exact:true}).selectOption(engage.targets[0].id);
      await owner.view.getByLabel(engage.trigger, {exact:true}).fill("Hold the relay lane against the opposing Frame.");
      const engaging = owner.page.waitForResponse(response => response.url().endsWith("/api/battlefield/engage"));
      await owner.view.getByRole("button", {name:"Roll Engage"}).click();
      const engaged = await engaging;
      assert.equal(engaged.status(),200,await engaged.text());
      for (const actor of ["Pilot", "Test Handler", "Drill opponent"]) {
        await owner.view.getByRole("button", {name:actor + " · Pass Tag window"}).click();
      }
      const maneuverChoice = owner.view.getByRole("button", {name:"Resolve Engage"});
      const optionalRisk = owner.view.getByRole("button", {name:"Decline optional Risk Factor"});
      await maneuverChoice.or(optionalRisk).first().waitFor();
      if (await optionalRisk.count()) await optionalRisk.click();
      await maneuverChoice.waitFor();
      const pending = (await loadBattlefield(owner)).choices.find(choice => choice.kind === "engage_maneuvers");
      const chosenAsset = pending.fields.assets.find(asset => asset.family === "girl").id;
      for (let index = 0; index < pending.fields.minimum; index++) {
        await owner.view.getByLabel("Maneuver " + (index + 1), {exact:true}).selectOption(pending.fields.maneuvers[index]);
        await owner.view.getByLabel("Asset for maneuver " + (index + 1)).selectOption(chosenAsset);
      }
      if (pending.fields.damage) await owner.view.getByLabel("Damage a used Asset").selectOption(chosenAsset);
      await owner.view.getByLabel("Resulting circumstances").fill("The pilot secures a foothold at the relay.");
      await maneuverChoice.click();
      await owner.view.getByText(/^Resolved · /).waitFor();
      const afterEngage = await loadBattlefield(owner);
      tacticalResult = afterEngage.play;
      assert.equal(tacticalResult.play,"engage");
      assert.equal(tacticalResult.state,"complete");
      assert.equal(tacticalResult.receipt.faces.length,2);
      assert.deepEqual(afterEngage.history[0],sensorResult);
      assert.equal(Object.keys(tacticalResult.result.maneuvers).length, pending.fields.minimum);
      await owner.view.getByRole("button", {name:"Play", exact:true}).click();
      await selectPlayCategory(plays, "Fight");
      await plays.getByRole("button", {name:"All-Out Assault"}).click();
      await openSelectedPlay.click();
      const assault = (await loadBattlefield(owner)).actions.find(action => action.id === "all_out_assault");
      const opponent = assault.targets[0];
      const declarationInput = {
        revision:(await loadBattlefield(owner)).revision,
        target:opponent.id, attacking_asset:assault.attacking_assets[0].id,
        target_asset:opponent.assets[0].id, account:"The drill opponent crosses the unshielded relay approach.",
      };
      assert.equal((await sendBattlefield(owner, "assault-declare", {
        ...declarationInput, target:"absent-opponent",
      })).status,409);
      await owner.view.getByLabel("Target", {exact:true}).selectOption(opponent.id);
      await owner.view.getByLabel("Attacking Asset", {exact:true}).selectOption(assault.attacking_assets[0].id);
      await owner.view.getByLabel("Opposing Asset", {exact:true}).selectOption(opponent.assets[0].id);
      await owner.view.getByLabel("Describe the opening for the assault").fill(declarationInput.account);
      const declarationPost = owner.page.waitForResponse(response => response.url().endsWith("/api/battlefield/assault-declare"));
      await owner.view.getByRole("button", {name:"Declare assault", exact:true}).click();
      const originalDeclaration = await declarationPost;
      assert.equal(originalDeclaration.status(),200);
      const retryBattlefield = async original => {
        const post = original.request();
        const reply = await request(owner, new URL(post.url()).pathname, {
          method:"POST", headers:{
            Origin:server.discord_activity_origin, "Content-Type":"application/json",
            "Idempotency-Key":post.headers()["idempotency-key"],
          },
          body:post.postData(),
        });
        assert.equal(reply.status,200);
        assert.deepEqual(await reply.json(),await original.json());
      };
      await retryBattlefield(originalDeclaration);
      await owner.view.getByRole("heading", {name:"Test Handler review"}).waitFor();
      const proposed = await loadBattlefield(owner);
      assert.equal(proposed.declaration.state,"proposed");
      assert.equal((await sendBattlefield(owner,"assault-roll",{
        id:proposed.declaration.id, sheet_revision:proposed.sheet_revision,
      })).status,409);
      assert.equal((await sendBattlefield(owner,"assault-review",{
        id:proposed.declaration.id, revision:proposed.revision, opening:true, reach:false, evidence:"Still behind cover.",
      })).status,400);
      await owner.view.getByLabel("Confirm the opening").check();
      await owner.view.getByLabel("Confirm the attack can reach").check();
      await owner.view.getByLabel("Evidence of opening and reach").fill("Both drill Frames have a clear line across the approach.");
      await owner.view.getByRole("button", {name:"Confirm assault declaration", exact:true}).click();
      const rollPost = owner.page.waitForResponse(response => response.url().endsWith("/api/battlefield/assault-roll") && response.status() === 200);
      await owner.view.getByRole("button", {name:"Roll All-Out Assault", exact:true}).click();
      const originalRoll = await rollPost;
      await retryBattlefield(originalRoll);
      for (const role of ["Pilot", "Test Handler", "Drill opponent"]) {
        await owner.view.getByRole("button", {name:role + " · Pass Tag window"}).click();
      }
      const ruling = owner.view.getByRole("button", {name:"Save assault table", exact:true});
      const lowDamage = owner.view.getByRole("button", {name:"Save low damage", exact:true});
      await ruling.first().or(lowDamage).waitFor();
      if (await lowDamage.count()) {
        const damage = (await loadBattlefield(owner)).choices.find(choice => choice.kind === "battle_low_damage");
        await owner.view.getByLabel("Asset to damage").selectOption(damage.fields.assets[0].id);
        await lowDamage.click();
      } else {
        for (const role of ["pilot", "handler", "opponent"]) {
          const form = owner.view.locator(`#tactical-controls article[data-role="${role}"]`);
          await form.getByLabel("Vast advantage").selectOption("no");
          await form.getByLabel("Explain the table ruling").fill("This test table finds no vast advantage.");
          await form.getByRole("button", {name:"Save assault table", exact:true}).click();
          await form.getByRole("button", {name:"Save assault table", exact:true}).waitFor({state:"hidden"});
        }
      }
      const complete = owner.view.locator("#tactical-receipt").getByText(/^Resolved · /);
      const highChoice = owner.view.getByRole("button", {name:"Save handler", exact:true});
      const brief = owner.view.getByRole("button", {name:"Save handler play", exact:true});
      await complete.or(highChoice).or(brief).waitFor();
      if (await highChoice.count()) {
        await owner.view.getByLabel("Handler consequence").selectOption("handler_play");
        await owner.view.getByLabel("Second consequence").selectOption("collateral_damage");
        await owner.view.getByLabel("What would be destroyed by collateral damage?").fill("A portable relay signal marker.");
        await highChoice.click();
        await owner.view.getByLabel("Concrete collateral").fill("Portable relay signal marker");
        await owner.view.getByLabel("Resulting damage").fill("The marker's housing cracks.");
        await owner.view.getByLabel("How the attack reached it").fill("The marker stood beside the declared target.");
        await owner.view.getByRole("button", {name:"Save collateral", exact:true}).click();
      }
      if (!await complete.count()) {
        await owner.view.getByLabel("Handler Play", {exact:true}).selectOption("brief");
        await owner.view.getByLabel("Handler’s briefing").fill("The relay has clear access on its western perimeter.");
        await brief.click();
      }
      await complete.waitFor();
      const afterAssault = await loadBattlefield(owner);
      assaultResult = afterAssault.play;
      assert.equal(assaultResult.state,"complete");
      assert.equal(assaultResult.play,"all_out_assault");
      if (tacticalTier) assert.equal(assaultResult.result.tier,tacticalTier);
      assert.equal(afterAssault.impacts[0].actor, assaultResult.result.tier === "low" ? "SYNTH" : opponent.label);
      assert.deepEqual(afterAssault.history[0],tacticalResult);
      assert.deepEqual(afterAssault.history[1],sensorResult);

      if (coreCase) {
        await owner.view.getByRole("button", {name:/^Expose Core · /}).waitFor();
        const readyForCore = await loadBattlefield(owner);
        assert(!afterAssault.actions.some(action => action.id === "go_for_the_core"));
        const exposure = readyForCore.core_exposure_targets[0];
        const hiddenCore = {
          revision:readyForCore.revision, target:exposure.id,
          attacking_asset:readyForCore.actions.find(action => action.id === "all_out_assault").attacking_assets[0].id,
          account:"Strike at the original Core once the opponent exposes it.",
        };
        assert.equal((await sendBattlefield(owner, "core-declare", hiddenCore)).status,409);
        await owner.view.getByRole("button", {name:"Expose Core · " + exposure.label, exact:true}).click();
        const exposeButton = owner.view.getByRole("button", {name:"Expose Core · " + exposure.label, exact:true});
        await exposeButton.waitFor({state:"hidden"});
        await owner.view.getByRole("button", {name:"Play", exact:true}).click();
        await selectPlayCategory(plays, "Fight");
        const coreChoice = plays.getByRole("button", {name:"Go for the Core", exact:true});
        await coreChoice.waitFor();
        if (process.env.HARPY_PLAY_MENU_CAPTURE) {
          await owner.page.locator("iframe").screenshot({path:process.env.HARPY_PLAY_MENU_CAPTURE});
        }
        await coreChoice.click();
        await openSelectedPlay.click();
        const core = (await loadBattlefield(owner)).actions.find(action => action.id === "go_for_the_core");
        assert.equal(core.range.kind,"adjudicated");
        assert.deepEqual(core.targets.map(target => target.id),[exposure.id]);
        await owner.view.getByLabel("Target", {exact:true}).selectOption(exposure.id);
        await owner.view.getByLabel("Attacking Asset", {exact:true}).selectOption(core.attacking_assets.find(asset => !asset.damaged).id);
        await owner.view.getByLabel(core.trigger,{exact:true}).fill(hiddenCore.account);
        await owner.view.getByRole("button", {name:"Declare Core strike", exact:true}).click();
        await owner.view.getByRole("heading", {name:"Test Handler review"}).waitFor();
        const pendingCore = await loadBattlefield(owner);
        const draft = pendingCore.declarations.go_for_the_core;
        assert.equal((await sendBattlefield(owner,"core-roll",{
          id:draft.id, sheet_revision:pendingCore.sheet_revision, heat:0,
        })).status,409);
        assert.equal((await sendBattlefield(owner,"core-review",{
          id:draft.id, revision:pendingCore.revision, opening:true, reach:false,
          capability:false, evidence:"The line is blocked.",
        })).status,400);
        await owner.view.getByLabel("Confirm the opening").check();
        await owner.view.getByLabel("Confirm the attack can reach").check();
        await owner.view.getByLabel("Evidence of opening and reach").fill("A clear line reaches the exposed Core.");
        await owner.view.getByRole("button", {name:"Confirm Core declaration", exact:true}).click();
        if (coreCase === "high") await owner.view.getByLabel("Heat to spend", {exact:true}).selectOption("4");
        const originalCore = owner.page.waitForResponse(response => response.url().endsWith("/api/battlefield/core-roll") && response.status() === 200);
        await owner.view.getByRole("button", {name:"Roll Go for the Core", exact:true}).click();
        await retryBattlefield(await originalCore);
        for (const role of ["Pilot", "Test Handler", "Drill opponent"]) {
          await owner.view.getByRole("button", {name:role + " · Pass Tag window"}).click();
        }
        if (coreCase !== "mid") {
          await owner.view.getByLabel("Core counter", {exact:true}).selectOption(coreCase === "high" ? "make_play_against_actor" : "pass");
          await owner.view.getByRole("button", {name:"Save counter", exact:true}).click();
        }
        if (coreCase === "high") {
          await owner.view.getByLabel("Counter Play", {exact:true}).selectOption("keep_your_head");
          await owner.view.getByLabel("Describe the counter Play").fill("Hold through the shock of the original strike.");
          await owner.view.getByRole("button",{name:"Save counter play", exact:true}).click();
          for (const role of ["Pilot","Test Handler","Drill opponent"]) {
            await owner.view.getByRole("button",{name:role + " · Pass Tag window"}).click();
          }
          const counterPlay = owner.view.getByRole("button",{name:"Save Keep Your Head choice", exact:true});
          const declineRisk = owner.view.getByRole("button",{name:"Decline optional Risk Factor"});
          await counterPlay.or(declineRisk).first().waitFor();
          if (await declineRisk.count()) await declineRisk.click();
          await owner.view.getByLabel("Take a Tag: write its label",{exact:true}).fill("Steady at the exposed Core");
          await counterPlay.click();
          await owner.view.getByLabel("Is it enough?",{exact:true}).selectOption("yes");
          await owner.view.getByLabel("Explain the outcome",{exact:true}).fill("The opponent holds long enough to absorb the strike.");
          await counterPlay.click();
          await owner.view.getByRole("button",{name:"Save target damage", exact:true}).waitFor();
          const damage = (await loadBattlefield(owner)).choices.find(choice => choice.kind === "battle_target_damage");
          await owner.view.getByLabel("Asset to damage").selectOption(damage.fields.assets[0].id);
          await owner.view.getByRole("button",{name:"Save target damage", exact:true}).click();
        }
        await owner.view.getByRole("heading",{name:"Go for the Core receipt",exact:true}).waitFor();
        await owner.view.locator("#tactical-receipt").getByText(/^Resolved · /).waitFor();
        const savedCore = await loadBattlefield(owner);
        coreResult = savedCore.play;
        counterResult = savedCore.counter;
        assert.equal(coreResult.play,"go_for_the_core");
        assert.equal(coreResult.result.tier,coreCase);
        assert.equal(savedCore.actors.some(actor => actor.id === exposure.id),coreCase !== "mid");
        assert.equal(savedCore.target_ended,coreCase === "mid");
        if (coreCase === "high") assert.equal(counterResult.state,"complete");
        assert.deepEqual(savedCore.history.slice(0,3),[assaultResult,tacticalResult,sensorResult]);
      }
    }
    if (dmOffline) {
      await owner.view.getByRole("button", {name:"Scenes", exact:true}).click();
      await owner.view.getByRole("button", {name:"Open Relay operations"}).click();
      await owner.view.getByRole("region",{name:"Present Pilots",exact:true}).getByRole("button", {name:/^SYNTH \| /}).click();
      await owner.view.locator("#profile-pane").getByText("SYNTH", {exact:true}).waitFor();
      await owner.view.getByRole("button", {name:"Back", exact:true}).click();
      await owner.view.getByRole("heading", {name:"Relay operations"}).first().waitFor();
      const dialogue = owner.view.getByLabel("Dialogue or narration");
      const addDialogue = owner.view.getByRole("button", {name:"File transmission"});
      const scenePlayList = owner.view.locator("#scene-play-options");
      await scenePlayList.getByText("Keep your head", {exact:true}).waitFor();
      assert(await scenePlayList.evaluate(element => element.compareDocumentPosition(
        document.getElementById("room-dialogue")) & Node.DOCUMENT_POSITION_PRECEDING));
      const transcriptPath = "/api/rooms/relay/transcript";
      const longEntry = "Relay handoff log.\n".repeat(28) + "End of handoff.";
      assert.equal((await setupPost(owner,"room-post",{target:"relay",text:longEntry})).status,200);
      assert.equal((await setupPost(owner,"room-post",{target:"relay",text:"/play"})).status,200);
      await owner.view.getByRole("button", {name:"Scenes", exact:true}).click();
      await owner.view.getByRole("button", {name:"Open Relay operations"}).click();
      const transcriptPlay = owner.view.getByRole("button", {name:"Open Scene Plays from transcript"});
      await transcriptPlay.waitFor();
      const history = owner.view.locator("#dialogue-entries");
      const atBottom = () => history.evaluate(list => list.scrollTop > 0 &&
        list.scrollHeight - list.scrollTop - list.clientHeight <= 2);
      assert(await atBottom());
      await dialogue.fill("Begin relay watch.");
      await addDialogue.click();
      await history.getByText("Begin relay watch.", {exact:true}).waitFor();
      assert.equal(await owner.view.locator("#room-location").textContent(),"Hangar Deck");
      assert.equal(await owner.view.locator("#room-access").textContent(),"Scene active");
      assert.match(await scenePlayList.locator(".play-rail-layout").evaluate(node => getComputedStyle(node).gridTemplateColumns),/px/);
      if (process.env.HARPY_SCENE_HUD_CAPTURE) {
        await owner.view.locator("html").evaluate(() => window.scrollTo(0,0));
        await owner.page.locator("iframe").screenshot({path:process.env.HARPY_SCENE_HUD_CAPTURE});
      }
      assert(await atBottom());
      await transcriptPlay.click();
      assert.equal(await owner.view.getByRole("heading", {name:"Scene Plays"}).evaluate(node => document.activeElement === node),true);
      const entriesBefore = (await (await request(owner,transcriptPath)).json()).entries;
      await dialogue.fill("/play Keep Your Head");
      await addDialogue.click();
      await owner.view.getByLabel("What are you trying to endure?").waitFor();
      assert.equal(await dialogue.inputValue(),"");
      assert.deepEqual((await (await request(owner,transcriptPath)).json()).entries,entriesBefore);
      await owner.view.getByLabel("What are you trying to endure?").fill("Hold steady through the relay interference.");
      const start = owner.page.waitForResponse(response => response.url().endsWith("/keep-start"));
      await owner.view.getByRole("button", {name:"Roll Keep Your Head"}).click();
      const started = await start;
      assert.equal(started.status(), 502);
      await owner.view.getByRole("button", {name:"Pilot · Pass Tag window"}).click();
      await owner.view.getByRole("button", {name:"Test Handler · Pass Tag window"}).click();
      await owner.view.getByRole("button", {name:"Record pilot choice"}).waitFor();
      const pendingPlay = (await playerSetup(owner)).scene.keep;
      const pilotDecision = pendingPlay.choices.find(choice => choice.kind === "actor_keep");
      const pendingReceipt = history.locator(`[data-scene-receipt="${pendingPlay.current.id}"]`);
      await pendingReceipt.getByRole("button", {name:"Pilot response",exact:true}).waitFor();
      await owner.view.getByRole("button",{name:"Close scene Play",exact:true}).click();
      await owner.view.locator("#inbox-toggle").click();
      await owner.view.locator("#mail-entries").getByRole("button", {name:"Keep Your Head · Pilot response",exact:true}).click();
      const exact = owner.view.locator(`[data-scene-choice="${pilotDecision.id}"]`);
      assert(await exact.evaluate(record => record.contains(document.activeElement)));
      const mid = owner.view.getByLabel("Choose two positive traits", {exact:true});
      const low = owner.view.getByLabel("Choose one positive trait", {exact:true});
      if (await mid.count()) {
        await mid.selectOption(["vicious", "tough"]);
        await owner.view.getByLabel("Choose one distinct negative trait").selectOption("desperate");
      } else if (await low.count()) {
        await low.selectOption("tough");
      } else {
        await owner.view.getByLabel("Take a Tag").fill("Steady under interference");
      }
      await owner.view.getByRole("button", {name:"Record pilot choice"}).click();
      await owner.view.getByLabel("Is it enough?").selectOption("yes");
      await owner.view.getByLabel("Explain the outcome").fill("The pilot holds until the signal clears.");
      await owner.view.getByRole("button", {name:"Record Handler ruling"}).click();
      await owner.view.getByRole("heading", {name:"Keep Your Head resolved"}).waitFor();
      keepReceipt = (await playerSetup(owner)).scene.keep.current;
      assert.equal(keepReceipt.state, "complete");
      assert.equal(keepReceipt.result.ruling, "The pilot holds until the signal clears.");
      assert.equal(keepReceipt.receipt.faces.length, 2);
      const file = history.locator(`[data-scene-receipt="${keepReceipt.id}"]`);
      await file.getByText("Original roll · " + keepReceipt.receipt.faces.join(" + ") + " · Total " + keepReceipt.receipt.pre_total, {exact:true}).waitFor();
      await file.getByText("Ruling · Yes", {exact:true}).waitFor();
      assert.equal(await file.getByRole("button", {name:"Pilot response"}).count(), 0);
      const repeatStart = await request(owner, setupRoute + "/keep-start", {
        method:"POST",
        headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":started.request().headers()["idempotency-key"]},
        body:started.request().postData(),
      });
      assert.equal(repeatStart.status, 200);
      assert.equal((await repeatStart.json()).action_id, keepReceipt.id);
      await owner.view.getByRole("button",{name:"Close scene Play",exact:true}).click();
    }

    if (offDutyCase) {
      const observed = offDutyCase === "observation";
      const play = observed ? "void_observation" : "go_off_duty";
      const alternate = observed ? "go_off_duty" : "void_observation";
      const label = observed ? "Void Observation" : "Go Off-Duty";
      for (let attempt = 0; attempt < 30 && (await playerSetup(owner)).scene.locked; attempt++) {
        await new Promise(resolve => setTimeout(resolve,200));
      }
      const availability = (await playerSetup(owner)).directory.rooms.find(room => room.id === "relay").play_availability[play];
      assert.equal(availability.state,"ready",JSON.stringify(availability.reasons));
      await owner.view.getByRole("button", {name:"Check for updates", exact:true}).click();
      await selectPlayCategory(owner.view.locator("#scene-play-options"), "Recover");
      await owner.view.locator(`#scene-play-options button[data-play="${play}"]`).click();
      const card = owner.view.locator("#scene-action-dialog");
      const before = await playerSetup(owner);
      assert.equal(before.scene.options[alternate].can_start,false);
      assert.equal(before.scene.options[play].current,null);
      const values = {
        play, context:"Spend time at base after the relay watch.",
        period:before.scene.options[play].period,
        character_revision:before.scene.options[play].character_revision, confirmed:true, target:null,
      };
      assert.equal((await setupPost(owner,"scene-start",{...values,play:alternate})).status,409);
      await card.getByLabel("Describe your time at base").fill(values.context);
      const starting = owner.page.waitForResponse(response => response.url().endsWith("/scene-start"));
      await card.getByRole("button", {name:"Roll " + label, exact:true}).click();
      const started = await starting;
      assert.equal(started.status(),200,await started.text());
      await card.getByRole("button", {name:"Pilot · Pass Tag window"}).click();
      await card.getByRole("button", {name:"Test Handler · Pass Tag window"}).click();
      await card.getByRole("heading", {name:label + " resolved"}).waitFor();
      await card.getByRole("button",{name:"Close scene Play",exact:true}).click();
      const result = (await playerSetup(owner)).scene.options[play].current;
      assert.deepEqual(result.receipt.faces,[4,5]);
      assert.equal(result.receipt.modifier_source,observed ? "Void Assets" : "Status");
      const retry = await request(owner, setupRoute + "/scene-start", {
        method:"POST",
        headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":started.request().headers()["idempotency-key"]},
        body:started.request().postData(),
      });
      assert.equal(retry.status,200,await retry.clone().text());
      assert.equal((await retry.json()).action_id,result.id);
      assert.equal((await setupPost(owner,"scene-start",values)).status,409);

      const handler = await openPilot(browser, server, "handler");
      if (await handler.view.getByRole("button", {name:"Close inbox"}).isVisible()) {
        await handler.view.getByRole("button", {name:"Close inbox"}).click();
      }
      const followup = (pilot, name, answer) => playerSetup(pilot).then(({off_duty}) => ({
        period:off_duty.period, revision:off_duty.revision, game_revision:off_duty.game_revision,
        action:name, answer,
      }));
      const panel = pilot => pilot.view.getByRole("region", {name:"Off-Duty follow-ups"});
      const waitFollowupUI = async pilot => {
        const {off_duty:current} = await playerSetup(pilot);
        const revision = current ? `${current.revision}:${current.game_revision}` : "";
        await pilot.view.locator(`#off-duty-options[data-revision="${revision}"]`).waitFor({state:"attached"});
      };
      const refresh = async pilot => {
        await pilot.view.getByRole("button", {name:"Check for updates", exact:true}).click();
        await waitFollowupUI(pilot);
      };
      const command = async (pilot, button) => {
        const pending = pilot.page.waitForResponse(response => response.url().endsWith("/off-duty-followup"));
        await button.click();
        const response = await pending;
        assert.equal(response.status(),200,await response.text());
        await waitFollowupUI(pilot);
        return response.request();
      };

      for (let attempt = 0; attempt < 30 && (await playerSetup(owner)).scene.locked; attempt++) {
        await new Promise(resolve => setTimeout(resolve,200));
      }
      await refresh(owner);
      if (observed) {
        const h = (await playerSetup(handler)).off_duty;
        const p = (await playerSetup(owner)).off_duty;
        assert.equal(p.scene,null);
        assert.equal(p.recovery,null);
        assert.equal(h.work.filter(work => work.kind === "observation_choice").length,1);
        const hWork = h.work.find(work => work.kind === "observation_choice");
        const pWork = p.work.find(work => work.kind === "observation_choice");
        assert.notEqual(hWork.id,pWork.id);
        const forbidden = await followup(owner,"choose_observation",{subject:pWork.subject_id, choices:["hospital_stay","medical_probing"]});
        assert.equal((await setupPost(owner,"off-duty-followup",forbidden)).status,409);
        await panel(owner).getByLabel("Choose 1 consequences").selectOption("hospital_stay");
        await command(owner,panel(owner).getByRole("button",{name:"Save consequence choices"}));
        await panel(owner).getByText("Waiting for the assigned Observation consequence choices.",{exact:true}).waitFor();
        await refresh(handler);
        await panel(handler).getByLabel("Choose 1 consequences").selectOption("medical_probing");
        await command(handler,panel(handler).getByRole("button",{name:"Save consequence choices"}));
        await refresh(owner);
        const handlerWork = (await playerSetup(handler)).off_duty.work.find(work => work.kind === "observation_effect");
        assert(!((await playerSetup(owner)).off_duty.work.some(work => work.id === handlerWork.id)));
        const wrongEffect = await followup(owner,"apply_observation",{id:handlerWork.id,work_revision:handlerWork.revision,details:{account:"Cannot answer for Handler."}});
        assert.equal((await setupPost(owner,"off-duty-followup",wrongEffect)).status,409);
        for (const label of ["An extended hospital stay", "Scientists and Doctors examine you"]) {
          const effect = panel(handler).locator("section").filter({has:handler.view.getByRole("heading",{name:label,exact:true})});
          await effect.getByLabel("What happened?").fill("The Handler records the completed medical review.");
          await command(handler,effect.getByRole("button",{name:"Save consequence",exact:true}));
        }
        await refresh(owner);
      }

      const reward = panel(owner).locator("section").filter({has:owner.view.getByRole("heading",{name:"JANUS Permission review",exact:true})});
      await reward.getByLabel("Did you demonstrate your Core was harmless?").selectOption("no");
      await reward.getByLabel("What happened?").fill("No qualifying demonstration occurred.");
      await command(owner,reward.getByRole("button",{name:"Save Permission review"}));
      await panel(owner).getByLabel("Scene",{exact:true}).selectOption(observed ? "observation:hospital_stay" : "handler_office");
      await panel(owner).getByLabel("Other participants",{exact:true}).selectOption("1");
      await panel(owner).getByLabel("Scene account",{exact:true}).fill("SYNTH and the Handler complete the Off-Duty scene.");
      await command(owner,panel(owner).getByRole("button",{name:"Save scene choice"}));
      await command(owner,panel(owner).getByRole("button",{name:"Confirm my participation"}));
      assert.equal((await playerSetup(owner)).off_duty.recovery,null);
      const earlyRecovery = await followup(owner,"recover",{repair_assets:false});
      assert.equal((await setupPost(owner,"off-duty-followup",earlyRecovery)).status,409);
      await refresh(handler);
      const wrongOwner = await followup(handler,"recover",{repair_assets:false});
      assert.equal((await setupPost(handler,"off-duty-followup",wrongOwner)).status,409);
      await command(handler,panel(handler).getByRole("button",{name:"Confirm my participation"}));
      await refresh(owner);
      const recoveryState = await playerSetup(owner);
      const [identityId, identity] = recoveryState.off_duty.recovery.unmark[0];
      const [damagedAsset] = recoveryState.off_duty.recovery.damaged.frame[0];
      await panel(owner).getByLabel("Identity to unmark").selectOption(identityId);
      await panel(owner).getByLabel("Repair damaged Assets?").selectOption(observed ? "no" : "yes");
      const recoveryRequest = await command(owner,panel(owner).getByRole("button",{name:"Save recovery"}));
      await panel(owner).getByText("Recovery saved.",{exact:true}).waitFor();
      const recoveryRetry = await request(owner, setupRoute + "/off-duty-followup", {
        method:"POST", headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":recoveryRequest.headers()["idempotency-key"]},
        body:recoveryRequest.postData(),
      });
      assert.equal(recoveryRetry.status,200,await recoveryRetry.text());
      await handler.page.context().close();
      offDutyReceipt = {play,result,identity,damagedAsset,observed};
    }

    await owner.page.context().close();
    const reopened = await openPilot(browser, server, "invited");
    await reopened.view.getByText(savedLabel).waitFor();
    if (keepReceipt) {
      await reopened.view.locator("#mail-entries").getByRole("button",{name:"Keep Your Head · Receipt",exact:true}).click();
      const filed = reopened.view.locator(`[data-scene-receipt="${keepReceipt.id}"]`);
      await filed.getByText("The pilot holds until the signal clears.", {exact:true}).waitFor();
      await selectPlayCategory(reopened.view.locator("#scene-play-options"), "Recover");
      await reopened.view.locator('#scene-play-options button[data-play="keep_your_head"]').click();
      await reopened.view.getByRole("heading", {name:"Keep Your Head resolved"}).waitFor();
      await reopened.view.getByRole("button",{name:"Close scene Play",exact:true}).click();
      assert.deepEqual((await playerSetup(reopened)).scene.keep.current, keepReceipt);
    }
    if (assaultResult) {
      await reopened.view.getByRole("button", {name:"Battlefield", exact:true}).click();
      await reopened.view.getByRole("button", {name:/^Cell 2, 2 .*SYNTH/}).waitFor();
      await reopened.view.getByText(/^Resolved · /).waitFor();
      const persisted = await (await request(reopened, "/api/battlefield")).json();
      assert.deepEqual(persisted.play,coreResult ?? assaultResult);
      if (coreCase) assert.deepEqual(persisted.counter,counterResult);
      assert.deepEqual(persisted.history.slice(0,coreResult ? 3 : 2),coreResult ? [assaultResult,tacticalResult,sensorResult] : [tacticalResult,sensorResult]);
    }
    assert.equal(await reopened.view.getByRole("button",{name:"Accept mission"}).count(),0);
    await reopened.page.context().close();
    await other?.page.context().close();
    console.log("Verified the saved response in a fresh browser context.");

    await stopServer(server);
    server = await startServer();
    if (discordOffline) {
      const expiredByRestart = await fetch(server.origin + "/api/mission-offers", {
        headers:{Authorization:`Bearer ${owner.session}`}, signal:AbortSignal.timeout(8000),
      });
      assert.equal(expiredByRestart.status,401);
    }
    const afterRestart = await openPilot(browser, server, "invited");
    await afterRestart.view.getByText(savedLabel).waitFor();
    if (offDutyReceipt) {
      const saved = await playerSetup(afterRestart);
      assert.deepEqual(saved.scene.options[offDutyReceipt.play].current,offDutyReceipt.result);
      assert.equal(saved.off_duty.recovered,true);
      assert.equal(saved.off_duty.invitations[0].remaining,0);
      assert.equal(saved.off_duty.recovery,null);
      assert.equal(saved.profile.identities.find(item => item.name === offDutyReceipt.identity).marked,false);
      assert.equal(saved.profile.assets.find(item => item.id === offDutyReceipt.damagedAsset).damaged,offDutyReceipt.observed);
    }
    if (keepReceipt) {
      await afterRestart.view.getByRole("button", {name:"Close inbox"}).click();
      assert.equal((await playerSetup(afterRestart)).profile.assets[0].description, "Operator-authored test description.");
      await afterRestart.view.getByRole("button", {name:"Open Relay operations"}).click();
      await selectPlayCategory(afterRestart.view.locator("#scene-play-options"), "Recover");
      await afterRestart.view.locator('#scene-play-options button[data-play="keep_your_head"]').click();
      await afterRestart.view.getByRole("heading", {name:"Keep Your Head resolved"}).waitFor();
      await afterRestart.view.getByRole("button",{name:"Close scene Play",exact:true}).click();
      assert.deepEqual((await playerSetup(afterRestart)).scene.keep.current, keepReceipt);
      const reopenedTranscript = await (await request(afterRestart,"/api/rooms/relay/transcript")).json();
      const filed = reopenedTranscript.receipts.find(receipt => receipt.id === keepReceipt.id);
      assert.deepEqual(filed.roll.faces, keepReceipt.receipt.faces);
      assert.equal(filed.result.ruling, keepReceipt.result.ruling);
      assert.deepEqual(filed.pending, []);
    }
    if (assaultResult) {
      await afterRestart.view.getByRole("button", {name:"Battlefield", exact:true}).click();
      await afterRestart.view.getByText(/^Resolved · /).waitFor();
      const persisted = await (await request(afterRestart, "/api/battlefield")).json();
      assert.deepEqual(persisted.actors.find(actor => actor.controlled).cell,[2,2]);
      assert.deepEqual(persisted.play,coreResult ?? assaultResult);
      if (coreCase) assert.deepEqual(persisted.counter,counterResult);
      assert.deepEqual(persisted.history.slice(0,coreResult ? 3 : 2),coreResult ? [assaultResult,tacticalResult,sensorResult] : [tacticalResult,sensorResult]);
    }
    if (other) {
      const pilotAfterRestart = await openPilot(browser, server, "other");
      await pilotAfterRestart.view.getByRole("button", {name:"Close inbox"}).click();
      await pilotAfterRestart.view.getByRole("button", {name:"My scenes", exact:true}).click();
      await pilotAfterRestart.view.getByRole("button", {name:"Open Signal Watch"}).waitFor();
      await pilotAfterRestart.view.getByRole("button", {name:"Open Signal Watch"}).click();
      await pilotAfterRestart.view.getByText("SYNTH records a clean signal.", {exact:true}).waitFor();
      await pilotAfterRestart.view.getByRole("button", {name:"Back", exact:true}).click();
      await pilotAfterRestart.view.getByRole("button", {name:"Open Relay operations"}).click();
      await pilotAfterRestart.view.getByRole("heading", {name:"Scene Plays"}).waitFor();
      const activated = await playerSetup(pilotAfterRestart);
      assert.equal(activated.callsign, "FALLOW");
      assert.equal(activated.scene.joined, true);
      assert(activated.scene.plays.some(play => play.id === "keep_your_head"));
      if (savedCommunication) {
        const contact = activated.communications.find(item => item.label === "SYNTH");
        assert.deepEqual((await (await request(pilotAfterRestart,conversation + contact.id)).json()).entries,savedCommunication);
      }
    }
    if (savedRelayOptions) {
      const options = (await playerSetup(afterRestart)).scene.options;
      for (const [id, result] of Object.entries(savedRelayOptions)) assert.deepEqual(options[id].current,result.current);
    }
    if (savedRoomPlay) {
      const scene = (await playerSetup(afterRestart)).active_scene;
      assert.equal(scene.id,savedRoomPlay.id);
      assert.deepEqual(scene.options.check_sensors.current,savedRoomPlay.result);
      assert.equal((await (await request(afterRestart,"/api/rooms/" + scene.id + "/transcript")).json()).entries[0].body,"SYNTH records a clean signal.");
    }
    const replay = await post(afterRestart, key);
    assert.equal(replay.status, 200);
    assert.deepEqual(await replay.json(), receipt);
    if (beneathCheck) {
      const actor = afterRestart;
      const target = await openPilot(browser,server,"other");
      const openBattlefield = async pilot => {
        const close = pilot.view.getByRole("button",{name:"Close inbox",exact:true});
        if (await close.isVisible()) await close.click();
        await pilot.view.getByRole("button",{name:"Battlefield",exact:true}).click();
      };
      const load = async pilot => {
        for (let attempt=0; ;attempt++) {
          const response = await request(pilot,"/api/battlefield");
          if (response.status === 503 && attempt < 2) continue;
          assert.equal(response.status,200);
          return response.json();
        }
      };
      const sendChoice = async (pilot, choice, answer, role = "pilot", key = randomUUID()) => request(pilot,"/api/battlefield/choice",{
        method:"POST",body:JSON.stringify({role,id:choice.id,revision:choice.revision,answer}),
        headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":key},
      });
      const tryProxy = sendChoice;
      await Promise.all([openBattlefield(actor),openBattlefield(target)]);
      await actor.view.getByRole("button",{name:"Play",exact:true}).click();
      await selectPlayCategory(actor.view.getByRole("dialog", {name:"Choose a Play"}), "Talk");
      await actor.view.getByRole("button",{name:"Put Someone Beneath You",exact:true}).click();
      await actor.view.locator("#tactical-play-open").click();
      const action = (await load(actor)).actions.find(item => item.id === "put_someone_beneath_you");
      assert.equal(action.targets.length,1);
      await actor.view.getByLabel("Target",{exact:true}).selectOption(action.targets[0].id);
      await actor.view.getByLabel("Describe the confrontation",{exact:true}).fill("I confront the other pilot over the incomplete handoff.");
      const roll = actor.page.waitForResponse(response => response.url().endsWith("/api/battlefield/put_someone_beneath_you"));
      await actor.view.getByRole("button",{name:"Roll Put Someone Beneath You",exact:true}).click();
      const started = await roll;
      assert.equal(started.status(),200,await started.text());
      for (const role of ["Pilot","Test Handler"]) {
        await actor.view.getByRole("button",{name:role + " · Pass Tag window",exact:true}).click();
      }
      await target.view.getByRole("button",{name:"Pilot · Pass Tag window",exact:true}).click();
      const low = tacticalTier === "low", high = tacticalTier === "high";
      const selector = low ? target : actor, affected = low ? actor : target;
      await selector.view.getByLabel("Choose printed effects",{exact:true}).selectOption(low ? "damage" : high ? "tag" : ["tag","bond"]);
      const selected = (await load(selector)).choices.find(item => item.kind === "beneath_select");
      assert(!(await load(affected)).choices.some(item => item.id === selected.id));
      assert.equal((await tryProxy(affected,selected,{options:["status"],text:"Attempted proxy"})).status,409);
      assert(!selected.schema.some(field => ["fields.bond","denied"].includes(field.key)));
      await selector.view.getByLabel("Describe the actual confrontation",{exact:true}).fill("Resolve the confrontation at the relay.");
      if (!low) await selector.view.getByLabel("New Tag label (Tag effect only)",{exact:true}).fill("Severe");
      if (high) await selector.view.getByLabel("Choose one extra effect",{exact:true}).selectOption(beneathExtra);
      if (high && beneathExtra === "lock_tag") await selector.view.getByLabel("Tag to lock (lock effect only)",{exact:true}).selectOption("new");
      await selector.view.getByRole("button",{name:"Save confrontation effects",exact:true}).click();
      if (high && beneathExtra === "punish") {
        await selector.view.getByLabel("Punishment",{exact:true}).selectOption("quality_time");
        const work = (await load(selector)).choices.find(item => item.kind === "beneath_punishment");
        const answer = {kind:"quality_time",tag:"On review",revision:work.fields.revision,game_revision:work.fields.game_revision};
        assert.equal((await tryProxy(affected,work,answer)).status,409);
        await selector.view.getByLabel("Inflicted Tag",{exact:true}).fill(answer.tag);
        await selector.view.getByRole("button",{name:"Apply assigned Punishment",exact:true}).click();
      } else if (high && beneathExtra === "pin") {
        await affected.view.getByLabel("Your own response",{exact:true}).selectOption("play");
        const pin = (await load(affected)).choices.find(item => item.kind === "beneath_pin_response");
        assert.equal((await tryProxy(selector,pin,{options:["narrative"],text:"Attempted proxy"})).status,409);
        await affected.view.getByRole("button",{name:"Save your response",exact:true}).click();
        await affected.view.getByLabel("Describe how you keep your head").fill("Hold steady under pressure.");
        await affected.view.getByRole("button",{name:"Roll Keep Your Head",exact:true}).click();
        for (const pilot of [actor,target]) await pilot.view.getByRole("button",{name:"Pilot · Pass Tag window",exact:true}).click();
        await actor.view.getByRole("button",{name:"Test Handler · Pass Tag window",exact:true}).click();
        await target.view.getByLabel("Take a Tag: write its label",{exact:true}).fill("Steady");
        await target.view.getByRole("button",{name:"Save Keep Your Head choice",exact:true}).click();
        await actor.view.getByLabel("Is it enough?",{exact:true}).selectOption("yes");
        await actor.view.getByLabel("Explain the outcome",{exact:true}).fill("The pilot holds steady.");
        await actor.view.getByRole("button",{name:"Save Keep Your Head choice",exact:true}).click();
      } else if (!high) {
        const field = low ? "denied" : "fields.bond";
        const label = low ? "Your actual Asset damaged by the counterattack" : "Your actual Bond to weaken";
        await affected.view.getByLabel(label,{exact:true}).waitFor();
        const choice = (await load(affected)).choices.find(item => item.kind === "beneath_details");
        assert(!(await load(selector)).choices.some(item => item.id === choice.id));
        const options = choice.schema.find(item => item.key === field).options;
        const id = (defeatCase ? options.find(([value]) => value.startsWith("frame:")) : options[0])[0];
        const reply = low ? {denied:[id]} : {fields:{bond:id}};
        assert.equal((await tryProxy(selector,choice,reply)).status,409);
        await affected.view.getByLabel(label,{exact:true}).selectOption(id);
        await affected.view.getByRole("button",{name:"Save your private choice",exact:true}).click();
      }
      if (defeatCase) {
        const formChoice = async (pilot, kind, other) => {
          const choice = (await load(pilot)).choices.find(item => item.kind === kind);
          assert(choice, "Missing choice " + kind);
          assert(!(await load(other)).choices.some(item => item.id === choice.id));
          return choice;
        };
        const press = (pilot, name) => pilot.view.getByRole("button",{name,exact:true}).click();
        await actor.view.getByRole("heading",{name:"Required Defeat",exact:true}).waitFor();
        const handoff = await formChoice(actor,"beneath_defeat",target);
        const start = {account:"Keep the damaged Frame between me and the relay.",sheet_revision:handoff.fields.sheet_revision};
        assert.equal((await tryProxy(target,handoff,start)).status,409);
        assert.equal((await sendChoice(actor,handoff,start,"handler")).status,409);
        await actor.view.getByLabel("Describe the actual Defeat",{exact:true}).fill(start.account);
        const starting = actor.page.waitForResponse(response => response.url().endsWith("/api/battlefield/choice") && response.request().postDataJSON().id === handoff.id);
        await press(actor,"Roll Defeat");
        const started = await starting;
        assert.equal(started.status(),200,await started.text());
        const key = started.request().headers()["idempotency-key"];
        const first = await started.json();
        const retry = await sendChoice(actor,handoff,start,"pilot",key);
        assert.equal(retry.status,200);
        assert.deepEqual(await retry.json(),first);
        for (const role of ["Pilot","Test Handler"]) await press(actor,role + " · Pass Tag window");
        await press(target,"Pilot · Pass Tag window");
        await actor.view.getByLabel("Choose your printed consequences",{exact:true}).waitFor();
        const outcome = await formChoice(actor,"defeat_select",target);
        const choices = defeatCase === "mid" ? ["escape_cockpit_choose_location"]
          : defeatCase === "high" ? ["lower_status","another_girl_gives_tag"]
          : defeatCase === "death" ? ["death"] : ["handler_ruinous_alternative"];
        assert.equal((await tryProxy(target,outcome,{options:choices,text:"Attempted proxy"})).status,409);
        const consequences = actor.view.getByLabel("Choose your printed consequences",{exact:true});
        await consequences.selectOption(defeatCase === "mid" ? choices[0] : choices);
        await actor.view.getByLabel("Describe the selected consequences",{exact:true}).fill("The resulting consequences are recorded in the relay log.");
        if (defeatCase === "high") await actor.view.getByLabel("Invite a Tag giver (Tag option)",{exact:true}).selectOption({index:1});
        await press(actor,"Save Defeat consequences");
        if (defeatCase === "high") {
          await target.view.getByLabel("Offer a Tag",{exact:true}).waitFor();
          const gift = await formChoice(target,"defeat_tag_gift",actor);
          assert.equal((await tryProxy(actor,gift,{options:["give"],text:"Attempted proxy"})).status,409);
          await target.view.getByLabel("Offer a Tag",{exact:true}).selectOption("give");
          await target.view.getByLabel("Tag label (only if giving)",{exact:true}).fill("Survivor");
          await press(target,"Save Tag decision");
        }
        if (defeatCase === "low") {
          const reviewOffer = async (tag, response) => {
            await actor.view.getByLabel("Describe and justify the alternative",{exact:true}).waitFor();
            const offer = await formChoice(actor,"defeat_alternative",target);
            const account = "Remove a permission and record the failed extraction.";
            const answer = {text:account,number:1,flag:true,fields:{tag,frame_context:"unspecified"}};
            assert.equal(offer.role,"handler");
            assert.equal((await sendChoice(target,offer,answer,"handler")).status,409);
            assert.equal((await tryProxy(actor,offer,answer)).status,409);
            await actor.view.getByLabel("Describe and justify the alternative",{exact:true}).fill(account);
            await actor.view.getByLabel("Permissions removed",{exact:true}).selectOption("1");
            await actor.view.getByLabel("Confirm your ruling",{exact:true}).selectOption("yes");
            await actor.view.getByLabel("Inflicted Tag (optional)",{exact:true}).fill(tag);
            await actor.view.getByLabel("Context of last Girl Asset loss",{exact:true}).selectOption("unspecified");
            await press(actor,"Send Handler offer");
            await actor.view.getByText(account,{exact:true}).waitFor();
            const accept = await formChoice(actor,"defeat_accept_alternative",target);
            assert.equal(accept.offer.tag,tag);
            assert.equal(accept.offer.permissions,1);
            assert.equal((await tryProxy(target,accept,{flag:true})).status,409);
            assert.equal((await sendChoice(actor,accept,{flag:true},"handler")).status,409);
            await actor.view.getByLabel("Respond to this exact offer",{exact:true}).selectOption(response);
            await press(actor,"Save your response to the offer");
          };
          await reviewOffer("First offer","no");
          await consequences.selectOption(choices);
          await actor.view.getByLabel("Describe the selected consequences",{exact:true}).fill("Request a revised Handler offer.");
          await press(actor,"Save Defeat consequences");
          await reviewOffer("Failed extraction","yes");
        }
        const tier = defeatCase === "death" ? "low" : defeatCase;
        await actor.view.getByText("Defeat resolved · " + tier[0].toUpperCase() + tier.slice(1),{exact:true}).waitFor();
        assert.equal((await sendChoice(actor,handoff,start)).status,409);
        const afterResolution = await sendChoice(actor,handoff,start,"pilot",key);
        assert.equal(afterResolution.status,200);
        assert.deepEqual(await afterResolution.json(),first);
      }
      await actor.view.locator("#tactical-receipt").getByText("Resolved · " + (low ? "Low" : high ? "High" : "Mid"),{exact:true}).waitFor();
      const saved = await load(actor);
      const targetSaved = await load(target);
      assert.equal(saved.play.result.tier,tacticalTier);
      assert.deepEqual(saved.play.result.beneath_effects,low ? ["damage"] : ["tag",high ? beneathExtra : "bond"]);
      if (defeatCase) {
        const response = saved.beneath_response;
        assert.equal(response.play,"defeat");
        assert.equal(response.state,"complete");
        assert.equal(response.receipt.base_modifier,2);
        assert.equal(response.receipt.modifier_source,"Undamaged Girl Assets");
        assert.deepEqual(response.receipt.faces,defeatCase === "mid" ? [3,3] : defeatCase === "high" ? [6,6] : [1,1]);
        assert.deepEqual(targetSaved.beneath_response.receipt,response.receipt);
        if (defeatCase === "death") {
          assert.equal(saved.sheet_revision,null);
          assert.deepEqual(saved.actions,[]);
        }
      } else if (targetSaved.beneath_response) {
        assert.deepEqual(targetSaved.beneath_response.receipt,saved.beneath_response.receipt);
        assert.equal(targetSaved.beneath_response.result.ruling,"The pilot holds steady.");
        assert.equal(saved.beneath_response.result.ruling,undefined);
      }
      await Promise.all([actor.page.context().close(),target.page.context().close()]);
      await stopServer(server);
      server = await startServer();
      const rejoined = await openPilot(browser,server,"other");
      await openBattlefield(rejoined);
      const restored = await load(rejoined);
      assert.deepEqual(restored.play,saved.play);
      assert.deepEqual(restored.beneath_response,targetSaved.beneath_response);
      if (defeatCase) {
        const originalOwner = await openPilot(browser,server,"invited");
        await openBattlefield(originalOwner);
        const reopened = await load(originalOwner);
        assert.deepEqual(reopened.beneath_response,saved.beneath_response);
        assert.deepEqual(reopened.play,saved.play);
      }
    }
    if (flirtCheck) {
      const showBattlefield = async pilot => {
        const close = pilot.view.getByRole("button",{name:"Close inbox",exact:true});
        if (await close.isVisible()) await close.click();
        await pilot.view.getByRole("button",{name:"Battlefield",exact:true}).click();
      };
      const load = async pilot => {
        const response = await request(pilot,"/api/battlefield");
        assert.equal(response.status,200);
        return response.json();
      };
      const send = (pilot, path, body, key = randomUUID()) => request(pilot,"/api/battlefield/" + path,{
        method:"POST",body:JSON.stringify(body),
        headers:{Origin:server.discord_activity_origin,"Content-Type":"application/json","Idempotency-Key":key},
      });
      const actor = afterRestart;
      let target = await openPilot(browser,server,"other");
      await showBattlefield(actor);
      await showBattlefield(target);
      const opts = await load(actor);
      const action = opts.actions.find(item => item.id === "flirt");
      assert.equal(action.targets.length,1);
      const candidate = action.targets[0];
      const self = (await load(target)).actions.find(item => item.id === "flirt").targets[0].owner;
      assert.equal((await send(actor,"flirt",{
        target:self,account:"Invalid self target",sheet_revision:opts.sheet_revision,confirmed:true,
      })).status,409);
      await actor.view.getByRole("button",{name:"Play",exact:true}).click();
      await selectPlayCategory(actor.view.getByRole("dialog", {name:"Choose a Play"}), "Talk");
      await actor.view.getByRole("button",{name:"Flirt",exact:true}).click();
      await actor.view.locator("#tactical-play-open").click();
      await actor.view.getByLabel("Target",{exact:true}).selectOption(candidate.id);
      await actor.view.getByLabel(action.trigger,{exact:true}).fill("I ask what name the other pilot goes by.");
      await actor.view.getByRole("button",{name:"Roll Flirt",exact:true}).click();
      for (const role of ["Pilot","Test Handler"]) {
        await actor.view.getByRole("button",{name:role + " · Pass Tag window",exact:true}).click();
      }
      try {
        await target.view.getByRole("button",{name:"Pilot · Pass Tag window",exact:true}).click();
      } catch (error) {
        const reading = await load(target);
        const message = await target.view.locator("#tactical-status").textContent();
        throw new Error(`Target Tag window unavailable. State ${reading.play?.state}, choices ${reading.choices.map(choice => choice.kind)}, status ${message}`, {cause:error});
      }
      const choose = actor.view.getByRole("button",{name:"Choose a question",exact:true});
      const answer = target.view.getByRole("button",{name:"Answer the question",exact:true});
      if (tacticalTier !== "low") {
        await actor.view.getByLabel("Ask the other player",{exact:true}).selectOption("name");
        if (tacticalTier === "high") {
          await actor.view.getByLabel("Choose how you go too far",{exact:true}).selectOption(flirtExtra);
          await actor.view.getByLabel("Describe how you go too far",{exact:true}).fill("I press for a callsign after a long silence.");
        }
        await choose.click();
      }
      await answer.waitFor();
      const pending = (await load(target)).choices.find(item => item.kind === "target_flirt");
      assert(!(await load(actor)).choices.some(choice => choice.id === pending.id));
      for (const role of ["pilot","opponent","handler"]) {
        assert.equal((await send(actor,"choice",{role,id:pending.id,revision:pending.revision,answer:{text:"Attempted proxy answer"}})).status,409);
      }
      await target.page.context().close();
      target = await openPilot(browser,server,"other");
      await showBattlefield(target);
      const reopened = (await load(target)).choices.find(item => item.kind === "target_flirt");
      assert.equal(reopened.id,pending.id);
      await target.view.getByLabel("Your answer",{exact:true}).fill("Call me Signal on this assignment.");
      await target.view.getByLabel("Optional return question",{exact:true}).selectOption("name");
      const response = target.page.waitForResponse(reply => reply.url().endsWith("/api/battlefield/choice"));
      await target.view.getByRole("button",{name:"Answer the question",exact:true}).click();
      const accepted = await response;
      assert.equal(accepted.status(),200);
      const repeated = await send(target,"choice",accepted.request().postDataJSON(),accepted.request().headers()["idempotency-key"]);
      assert.equal(repeated.status,200);
      assert.deepEqual(await repeated.json(),await accepted.json());
      await actor.view.getByLabel("Your answer to the return question",{exact:true}).fill("SYNTH is fine.");
      await actor.view.getByRole("button",{name:"Answer the return question",exact:true}).click();
      if (tacticalTier === "high" && flirtExtra === "owe") {
        await target.view.getByLabel("Give the actor a Tag",{exact:true}).fill("Persistent");
        await target.view.getByRole("button",{name:"Record a Tag",exact:true}).click();
      } else if (tacticalTier === "high" && flirtExtra === "handler") {
        if (handlerEffect !== "brief") {
          await actor.view.getByLabel("Handler Play",{exact:true}).selectOption(handlerEffect);
          await actor.view.getByLabel("Describe the threat or expectation",{exact:true}).fill(handlerEffect === "escalate" ? "The backup relay loses power." : "Wait for relief before clearing the console.");
          await actor.view.getByLabel("State the stakes or consequence",{exact:true}).fill("The relief pilot needs a complete handoff.");
        }
        await actor.view.getByLabel("Handler’s briefing",{exact:true}).fill("Both pilots have a clear exit to the observation deck.");
        await actor.view.getByRole("button",{name:"Save Handler Play",exact:true}).click();
      } else if (tacticalTier === "high" && flirtExtra === "escape") {
        await target.view.getByLabel("Choose your response",{exact:true}).selectOption("damage");
        const escape = (await load(target)).choices.find(item => item.kind === "flirt_escape");
        const asset = escape.schema.find(item => item.key === "denied").options[0];
        await target.view.getByLabel("Asset to damage (damage branch)",{exact:true}).selectOption(asset[0]);
        await target.view.getByRole("button",{name:"Choose a way out",exact:true}).click();
      }
      await actor.view.getByText("Call me Signal on this assignment.",{exact:true}).waitFor();
      await target.view.getByText("SYNTH is fine.",{exact:true}).waitFor();
      const saved = (await load(actor)).play;
      assert.equal(saved.result.tier,tacticalTier);
      if (tacticalTier === "high" && flirtExtra === "handler") assert.equal(saved.result.handler_play,handlerEffect);
      assert.deepEqual((await load(target)).play,saved);
      await Promise.all([actor.page.context().close(),target.page.context().close()]);
      await stopServer(server);
      server = await startServer();
      const reopenedTarget = await openPilot(browser,server,"other");
      await showBattlefield(reopenedTarget);
      assert.deepEqual((await load(reopenedTarget)).play,saved);
      if (followthroughCheck) {
        const active = await openPilot(browser,server,"invited");
        await showBattlefield(active);
        const obligation = (await load(active)).actions.find(action => action.label === "Flirt Follow-through");
        assert(obligation);
        assert.equal(obligation.range.label,"Call me Signal on this assignment.");
        assert.equal((await send(reopenedTarget,"fulfill",{id:obligation.obligation,account:"Not my obligation"})).status,409);
        const outcomeFor = async accepted => {
          await active.view.getByRole("button",{name:"Play",exact:true}).click();
          await selectPlayCategory(active.view.getByRole("dialog", {name:"Choose a Play"}), "Talk");
          await active.view.getByRole("button",{name:"Flirt Follow-through",exact:true}).click();
          await active.view.locator("#tactical-play-open").click();
          await active.view.getByLabel("Describe what your pilot does",{exact:true}).fill(accepted ? "I use Signal on the duty roster." : "I acknowledge the request.");
          await active.view.getByRole("button",{name:"Record follow-through",exact:true}).click();
          const decision = reopenedTarget.view.getByRole("button",{name:"Save follow-through decision",exact:true});
          await decision.waitFor();
          const pending = (await load(reopenedTarget)).choices.find(choice => choice.kind === "followthrough_confirm");
          assert(!(await load(active)).choices.some(choice => choice.id === pending.id));
          assert.equal((await send(active,"choice",{role:"pilot",id:pending.id,revision:pending.revision,answer:{flag:true,text:"Forged"}})).status,409);
          await reopenedTarget.view.getByLabel("Did this fulfill what you requested?",{exact:true}).selectOption(accepted ? "yes" : "no");
          await reopenedTarget.view.getByLabel("Confirm or explain your response",{exact:true}).fill(accepted ? "The duty roster uses the right callsign." : "The roster has not changed.");
          await decision.click();
          await active.view.getByText(accepted ? "Follow-through confirmed · Bond improved" : "Follow-through declined · Obligation still open",{exact:true}).waitFor();
        };
        await outcomeFor(false);
        await outcomeFor(true);
        const completed = (await load(active)).play;
        assert.equal(completed.result.confirmed,true);
        await Promise.all([active.page.context().close(),reopenedTarget.page.context().close()]);
        await stopServer(server);
        server = await startServer();
        const restored = await openPilot(browser,server,"other");
        await showBattlefield(restored);
        assert.deepEqual((await load(restored)).play,completed);
      }
    }
    if (orderCheck) {
      const saved = await verifyOrders(afterRestart, request, server.discord_activity_origin);
      await afterRestart.page.context().close();
      await stopServer(server);
      server = await startServer();
      const orderPilot = await openPilot(browser, server, "invited");
      await orderPilot.view.getByRole("button",{name:"Close inbox"}).click();
      await orderPilot.view.getByRole("button",{name:"Battlefield",exact:true}).click();
      await orderPilot.view.getByRole("heading",{name:"Disobey Orders receipt",exact:true}).waitFor();
      const persisted = await (await request(orderPilot,"/api/battlefield")).json();
      assert.deepEqual(persisted.play,saved.play);
      assert.deepEqual(persisted.refusal,saved.refusal);
      assert.deepEqual(persisted.history[0],saved.followed);
    }

    const audit = spawnSync(python, [...args, "--audit"], { cwd: app, encoding: "utf8", timeout: 15000 });
    assert.equal(audit.status, 0, audit.stderr);
    const snapshot = JSON.parse(audit.stdout);
    assert.deepEqual(snapshot.responses, { 2: "accept" });
    assert.deepEqual(snapshot.response_events, [{ actor: "2", key }]);
    assert.deepEqual({ ...snapshot.stored_receipts[key], response:"accept" }, receipt);
    assert.equal(snapshot.offers[0].revision, 2);
    console.log(JSON.stringify({
      campaign, discordOffline, dmOffline, revision: snapshot.offers[0].revision, responseEvents: snapshot.response_events.length,
      checks: [
        ...(dmOffline ? [
          "DM sign-in requires the allowlisted account and active test-guild membership",
          "receipt recovered from HarpyEngine after the gateway lost a successful response",
          "fresh DM sign-in and mission reads recover after transient gateway errors",
          "Keep Your Head roll, pilot choice, and Handler ruling survive reopening and restart",
          "the Activity recovers a started Play after a gateway error without starting it twice",
          "portrait-free folders, battlefield briefing, and saved Frame descriptions",
          "Operations Desk navigation, shared light/dark mode and Inbox fit desktop and narrow Activity widths",
          "inline Sheet Plays and scene Plays, transcript follow-to-bottom, and /play shortcuts",
          "profile Play picker opens the selected relay and Battlefield forms without rolling",
          ...(!sceneCheck && !orderCheck ? [
            "HarpyEngine validates the assault opening, reach, and targets before rolling",
            "HarpyEngine resolves All-Out Assault, Engage, and Check Sensors and saves each original roll",
          ] : []),
          ...(coreCase ? ["Go for the Core uses actual Core exposure, preserves the original roll, and resolves its " + coreCase + " outcome"] : []),
          ...(orderCheck ? ["Only the ordered pilot sees the applicable order Play, following uses no roll, and the refusal receipt survives restart"] : []),
          ...(offDutyReceipt ? ["Off-Duty picker keeps the original roll, scene, separate attendance confirmations, and once-only recovery after restart"] : []),
        ] : [
          "non-invitee cannot see or answer offer",
          "new player joins from the profile Play picker and scene membership survives restart",
          "room creation and binding-code membership persist after restart",
          "room dialogue is private to its members and survives restart",
          ...(communicationsCheck ? ["private character and Handler replies are owned, idempotent, and durable after restart"] : []),
          ...(relayPlaysCheck ? ["Check Sensors, Engage, Flirt and follow-through use native choices in the original relay scene"] : []),
          ...(roomPlaysCheck ? ["the profile picker explains unavailable Plays, issues scoped invites, and retains scene rolls and dialogue across restart"] : []),
          ...(flirtCheck ? ["Flirt uses two authenticated pilots, rejects proxy answers, and persists the original roll and responses"] : []),
          ...(beneathCheck ? ["Put Someone Beneath You assigns tier effects and private choices to the original owners and persists after restart"] : []),
          ...(defeatCase ? ["Last-Asset Defeat preserves its source, original roll and " + defeatCase + " outcome after restart, with owner checks and an idempotent roll"] : []),
          ...(followthroughCheck ? ["Flirt follow-through keeps declined obligations open, applies the Bond on confirmation, and survives restart"] : []),
        ]),
        "accepted through Activity UI",
        "exact retry returns original receipt",
        "changed and stale retries are rejected",
        "response survives fresh browser launch and server restart",
      ],
    }));
  } finally {
    await browser?.close();
    await stopServer(server);
  }
}

mainTest().catch(error => { console.error(error); process.exitCode = 1; });
