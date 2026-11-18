const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { randomUUID } = require("node:crypto");
const { createInterface } = require("node:readline");
const path = require("node:path");

const [labPath, pythonPath, chromePath, playwrightPath] = process.argv.slice(2);
const { chromium } = require(playwrightPath || "playwright");
const env = Object.fromEntries(
  Object.entries(process.env).filter(([name]) => !/^(GIRLFRAME_|DISCORD_)/.test(name))
);

async function verify() {
  const lab = path.resolve(labPath);
  const python = path.resolve(pythonPath);
  const child = spawn(python, [
    "mission_lab.py", "--p2-fixture", "--campaign", "p2-browser-" + randomUUID().slice(0, 8),
    "--port", "0", "--stop-on-input-close",
  ], {cwd:lab, env, stdio:["pipe","pipe","inherit"]});
  let browser;
  try {
    const server = await new Promise((resolve, reject) => {
      child.once("exit", status => reject(new Error("Activity startup exited with " + status)));
      child.once("error", reject);
      createInterface({input:child.stdout}).on("line", line => {
        try {
          const value = JSON.parse(line);
          if (value.director_scene) resolve(value);
        } catch (_) {}
      });
    });
    browser = await chromium.launch({
      executablePath:chromePath || undefined, headless:true, args:["--no-sandbox"],
    });
    const signIn = async role => {
      const context = await browser.newContext();
      const page = await context.newPage();
      await page.goto(server.pilots[role]);
      await page.waitForURL("**/activity");
      return page;
    };
    const pilot = await signIn("Invited pilot");
    const handler = await signIn("Facilitator / Handler");
    const outsider = await signIn("Other pilot");
    const endpoint = server.origin + "/api/director/" + server.director_scene + "/";
    async function get(page, route, expected = 200) {
      const response = await page.request.get(endpoint + route);
      const value = await response.json();
      assert.equal(response.status(), expected, JSON.stringify(value));
      return value;
    }
    async function post(page, route, data, key = randomUUID(), expected = 200) {
      const response = await page.request.post(endpoint + route, {
        headers:{Origin:server.origin, "Idempotency-Key":key}, data,
      });
      const value = await response.json();
      assert.equal(response.status(), expected, JSON.stringify(value));
      return value;
    }
    await get(outsider, "status", 403);
    const init = await get(handler, "status");
    await post(handler, "configure", {revision:init.policy_revision});
    const policy = (await get(handler, "status")).policy_revision;
    await post(handler, "consent", {policy_revision:policy, consent:true});
    await post(pilot, "consent", {policy_revision:policy, consent:true});

    await pilot.getByRole("button", {name:"Scenes", exact:true}).click();
    await pilot.getByRole("button", {name:"Open Relay operations", exact:true}).click();
    const modes = pilot.getByLabel("What can the Handler hear?");
    await modes.selectOption("comms");
    const request = "Handler, can you repeat the scope?";
    await pilot.getByRole("textbox", {name:"Dialogue or narration"}).fill(request);
    await pilot.getByRole("button", {name:"Add to scene", exact:true}).click();
    await pilot.getByText(request, {exact:true}).waitFor();
    const timeline = await get(pilot, "timeline");
    assert.equal(timeline.entries.length, 1);
    assert.equal(timeline.entries[0].channel, "comms");
    await get(pilot, "gm-work", 403);
    const draft = (await get(handler, "gm-work")).handler_drafts[0].id;
    await post(handler, "handler-approve", {
      draft, reason:"Review the reply and the original listener.", recipients:[timeline.entries[0].actor],
    });
    await post(pilot, "handler-deliver", {draft}, randomUUID(), 409);
    const deliveryKey = randomUUID();
    const delivery = await post(handler, "handler-deliver", {draft}, deliveryKey);
    assert.deepEqual(await post(handler, "handler-deliver", {draft}, deliveryKey), delivery);
    const reopened = await signIn("Invited pilot");
    await reopened.getByRole("button", {name:"Scenes", exact:true}).click();
    await reopened.getByRole("button", {name:"Open Relay operations", exact:true}).click();
    await reopened.getByText("I set my own report pad on the table.", {exact:true}).waitFor();
    assert.equal((await get(reopened, "timeline")).entries.length, 2);

    const final = await get(handler, "status");
    const receipt = await post(handler, "close", {revision:final.scene_revision,reports:[]});
    assert.equal(receipt.handler_report_count, 1);
    assert.equal((await get(reopened, "timeline")).open, false);
    await post(pilot, "consent", {policy_revision:policy, consent:false});
    await get(reopened, "timeline", 403);
    process.stdout.write(JSON.stringify({
      activity_login:true, wrong_owner_denied:true,
      engine_composer:true, rendered_scoped_delivery:true, reconnect_entries:2,
      closed_scene_report_count:receipt.handler_report_count, withdrawal_blocked:true,
    }) + "\n");
  } finally {
    if (browser) await browser.close();
    child.stdin.end();
  }
}
verify().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
