// Supervised timing review on a disposable Activity fixture. No Discord credentials.
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { randomUUID } = require("node:crypto");
const { once } = require("node:events");
const { createInterface } = require("node:readline");
const path = require("node:path");

const [labPath, pythonPath, chromePath, playwrightPath] = process.argv.slice(2);
const { chromium } = require(playwrightPath || "playwright");
const root = path.resolve(__dirname, "../..");
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) =>
  !/^(GIRLFRAME_|DISCORD_|DiscordBot$|OPENAI_API_KEY$)/.test(name)));
env.PYTHONPATH = ["src", "tests", "tests/rules"].map(dir => path.join(root, dir)).join(path.delimiter);
env.GIRLFRAME_RULES_REGISTRY = path.join(root, "rules/registry.json");

const seed = `
import json
import sys
import mission_lab
from girlframe.ai.observation import AppendSceneInput, ObservationPolicy
from girlframe.scenes.campaign_time import Anchor, Position, ScenePlan
from girlframe.scenes.mission_timing import Deadline, SequenceStart
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.mission_timing import MissionTimingService

service = mission_lab.open_campaign(sys.argv[1])
store, game = service.store, service.game
handler, pilot = mission_lab.HANDLER, mission_lab.OFFERED
timeline = CampaignTimeService(store)
with store.engine.connect() as c:
    mission = next(item for item in timeline._phase(c) if item['phase'] == 'offered')
mission = service.respond(pilot, 'accept', mission['id'], mission['revision'], 'accept')
mission = service.start(handler, 'start', mission['id'], mission['revision'])
game.bind_scene(handler, 'bind-parallel', 901)
game.join_scene(handler, 'join-parallel', 901)
position = Position(day=4, slot='afternoon')
anchor = timeline.initialize(handler, 'calendar', Anchor(chapter='Evacuation', position=position))['receipt']
observer = DirectorObservationService(store, synthetic=True)
for channel, title, cast in ((900, 'Relay', (handler, pilot)), (901, 'Operations', (handler,))):
    with store.engine.connect() as c:
        row = game.scene(c, channel, check_slot=False)
    scene = timeline.schedule(handler, f'book:{channel}', channel, row['id'], row['revision'], anchor,
        ScenePlan(chapter=title, start=position, end=position,
                  participants=tuple(viewer.user_id for viewer in cast)))['scene']
    observer.configure_scene(handler, f'notice:{channel}', scene, 0, ObservationPolicy(mode='shadow'))
    for viewer in cast:
        observer.set_consent(viewer, f'consent:{channel}:{viewer.user_id}', scene, 1, consent=True)
    if channel == 900:
        original = scene
    else:
        parallel = scene

clock = MissionTimingService(store).open(handler, 'clock', mission['id'], mission['revision'],
    900, original, anchor, SequenceStart(minute=1100,
        deadline=Deadline(minute=1120, boundary='before', label='Evacuation')))
known = DirectorContextService(observer)
with store.engine.connect() as c:
    _, _, actor = observer._authorize_input(c, pilot, original, 'pilot')
for index, (speech, channel) in enumerate((('The east panel is still loose.', 'comms'),
                                            ('UNREPORTED_TIMED_REHEARSAL', 'private'))):
    revision = observer.status(pilot, original).scene_revision
    source = observer.append_scene_input(pilot, original, AppendSceneInput(
        command_key=f'input:{index}', expected_scene_revision=revision,
        speaker='pilot', text=speech, fictional_channel=channel))
    reference = known.record(handler, f'known:{index}', original, source.source_id, index,
                             known_by=(actor,), topic='tactical')['id']
    if index == 0:
        report = reference
print(json.dumps({'parallel': parallel, 'report': report, 'clock': clock['id']}), flush=True)
mission_lab.serve(service, 0, True, None, p2_fixture=True)
`;

async function verify() {
  const child = spawn(path.resolve(pythonPath), ["-c", seed, "timed-review-" + randomUUID()], {
    cwd: path.resolve(labPath), env, stdio: ["pipe", "pipe", "inherit"],
  });
  const exited = once(child, "exit");
  let browser;
  try {
    const fixture = await new Promise((resolve, reject) => {
      const metadata = {};
      child.once("exit", code => reject(Error(`Fixture exited with code ${code}`)));
      child.once("error", reject);
      createInterface({ input: child.stdout }).on("line", line => {
        try { Object.assign(metadata, JSON.parse(line)); } catch { return; }
        if (metadata.director_scene && metadata.parallel) resolve(metadata);
      });
    });
    browser = await chromium.launch({
      executablePath: chromePath || undefined, headless: true, args: ["--no-sandbox"],
    });
    async function signIn(role) {
      const context = await browser.newContext();
      const page = await context.newPage();
      await page.goto(fixture.pilots[role]);
      await page.waitForURL("**/activity");
      await page.getByText("Director work", { exact: true }).click();
      await page.getByRole("button", { name: "Refresh Director work" }).waitFor();
      return page;
    }
    const endpoint = (route, scene) => `${fixture.origin}/api/director/${scene}/${route}`;
    async function get(page, route, scene = fixture.director_scene, status = 200) {
      const response = await page.request.get(endpoint(route, scene));
      const body = await response.json();
      assert.equal(response.status(), status, JSON.stringify(body));
      return body;
    }
    async function post(page, route, data, {scene = fixture.director_scene, key = randomUUID(), status = 200} = {}) {
      const response = await page.request.post(endpoint(route, scene), {
        data, headers: {Origin: fixture.origin, "Idempotency-Key": key},
      });
      const body = await response.json();
      assert.equal(response.status(), status, JSON.stringify(body));
      return body;
    }

    let handler = await signIn("Facilitator / Handler");
    const pilot = await signIn("Invited pilot");
    const other = await signIn("Other pilot");
    const before = await get(handler, "fictional-time");
    assert.equal(before.scenes.filter(scene => scene.status === "open").length, 2);
    assert.deepEqual((await get(handler, "reports", fixture.parallel)).reports, []);
    assert.deepEqual((await get(handler, "timing-review", fixture.parallel)).items, []);
    assert.equal((await get(other, "fictional-time")).mission_timing, undefined);
    await get(pilot, "timing-review", fixture.director_scene, 403);
    const clock = before.mission_timing;
    const option = randomUUID();
    const menu = await post(handler, "time-publish", {
      id: fixture.clock, revision: clock.revision, options: {available: [
        {id: option, pilot: before.handler_controls.clock_pilots[0], label: "Escort the technician", minutes: 25},
      ]},
    });
    const request = {id: fixture.clock, menu: menu.receipt, option};
    const ruling = await post(pilot, "time-choose", request);
    assert.equal(ruling.reason, "unknown_consequence");
    await handler.getByRole("button", { name: "Refresh Director work" }).click();
    await handler.getByRole("link", { name: "Define the missed-cutoff consequence" }).click();
    await handler.getByLabel("Fictional consequence").fill("The evacuation shuttle has left.");
    const save = handler.waitForResponse(r => r.url().endsWith("/time-consequence"));
    await handler.getByRole("button", { name: "Save consequence", exact: true }).click();
    const resolved = await (await save).json();
    assert.equal(resolved.status, "consequence_declared");
    await handler.getByRole("link", { name: "Define the missed-cutoff consequence" }).waitFor({state: "hidden"});
    assert.deepEqual((await get(handler, "timing-review")).items, []);
    await post(pilot, "time-choose", request, {status: 409});
    const choice = {...request, menu: resolved.receipt};
    const key = randomUUID();
    const cutoff = await post(pilot, "time-choose", choice, {key});
    assert.equal(cutoff.minute, 1125);
    assert.deepEqual(await post(pilot, "time-choose", choice, {key}), cutoff);
    await handler.context().close();
    handler = await signIn("Facilitator / Handler");
    const pending = (await get(handler, "gm-work")).timing_reviews;
    assert.equal(pending.length, 1);
    assert.equal(pending[0].source_receipt, cutoff.receipt);
    await handler.getByRole("heading", { name: "Missed cutoff", exact: true }).waitFor();
    assert.deepEqual((await get(handler, "timing-review", fixture.parallel)).items, []);
    assert.deepEqual((await get(handler, "reports", fixture.parallel)).reports, []);
    await post(handler, "time-close", {id: fixture.clock, revision: cutoff.receipt});
    const status = await get(handler, "status");
    const closure = await post(handler, "close", {revision: status.scene_revision, reports: [fixture.report]});
    assert.equal(closure.handler_report_count, 1);
    const reports = (await get(handler, "reports", fixture.parallel)).reports;
    assert.deepEqual(reports.map(r => r.text), ["Reported claim: The east panel is still loose."]);
    await handler.getByRole("button", { name: "Refresh Director work" }).click();
    await handler.getByRole("button", { name: "Acknowledge cutoff", exact: true }).click();
    await handler.getByRole("heading", { name: "Missed cutoff", exact: true }).waitFor({state: "hidden"});
    assert.deepEqual((await get(handler, "timing-review")).items, []);
    console.log("Timing review passed with parallel scenes, reconnect, one cutoff, and consent-scoped closeout.");
  } finally {
    if (browser) await browser.close();
    child.stdin.end();
    await exited;
  }
}

verify().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
