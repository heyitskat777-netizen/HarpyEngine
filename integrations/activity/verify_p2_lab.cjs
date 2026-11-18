const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { randomUUID } = require("node:crypto");
const { createInterface } = require("node:readline");
const path = require("node:path");

const [labPath, pythonPath, chromePath, playwrightPath, mode] = process.argv.slice(2);
const shadow = mode === "--shadow-readiness";
const { chromium } = require(playwrightPath || "playwright");
const env = Object.fromEntries(
  Object.entries(process.env).filter(([name]) => !/^(GIRLFRAME_|DISCORD_|DiscordBot$|OPENAI_API_KEY$)/.test(name))
);

async function verify() {
  const lab = path.resolve(labPath);
  const python = path.resolve(pythonPath);
  const child = spawn(python, [
    "mission_lab.py", "--p2-fixture", "--campaign", "p2-browser-" + randomUUID().slice(0, 8),
    "--port", "0", "--stop-on-input-close", ...(shadow ? ["--p2-shadow-readiness"] : []),
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
    await get(pilot, "opening", 403);
    await handler.getByText("Director work", {exact:true}).click();
    await handler.getByLabel("Opening location").fill("Relay service hall");
    await handler.getByLabel("Opening situation").fill("The technicians need a maintenance window.");
    await handler.getByLabel("First player decision").fill("Wait for maintenance or reroute the check-in?");
    await handler.getByRole("button", {name:"Add starting fact"}).click();
    await handler.getByLabel("Fact to share").fill("Technicians filed a delay notice.");
    await handler.getByLabel("How it was learned (GM notes)").fill("The Handler read the notice.");
    await handler.getByLabel("Who knows this? Leave empty for GM only.").selectOption({label:"Handler"});
    await handler.getByRole("button", {name:"Save opening draft"}).click();
    await handler.getByRole("heading", {name:"Who knows what"}).waitFor();
    const opening = (await get(handler, "opening")).previews;
    assert.deepEqual(opening.find(role => role.label === "Handler").facts, ["Technicians filed a delay notice."]);
    assert.equal(opening.filter(role => role.facts.length).length, 1);
    const init = await get(handler, "status");
    if (shadow) {
      assert.equal((await get(handler, "activity-policy")).enabled, false);
      await handler.getByRole("button", {name:"Enable campaign observation"}).click();
      await handler.getByRole("button", {name:"Disable campaign observation"}).waitFor();
    }
    await post(handler, "configure", {revision:init.policy_revision,
      ...(shadow ? {policy:{mode:"shadow", quiet_seconds:1, min_interval_seconds:1}} : {})});
    const policy = (await get(handler, "status")).policy_revision;
    await post(handler, "consent", {policy_revision:policy, consent:true});
    await post(pilot, "consent", {policy_revision:policy, consent:true});
    await handler.getByRole("button", {name:"Refresh Director work"}).click();
    await handler.getByText("Review & launch", {exact:true}).click();
    await handler.getByRole("button", {name:"Launch reviewed opening"}).click();
    await handler.getByText("The campaign opening has been launched.", {exact:true}).waitFor();
    const scoped = await get(pilot, "opening-brief");
    assert.equal(scoped.location, "Relay service hall");
    assert.ok(scoped.roles.every(role => role.facts.length === 0));

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
    if (shadow) {
      await get(pilot, "activity-review", 403);
      await handler.getByRole("button", {name:"Refresh Director work"}).click();
      await handler.getByRole("button", {name:"Review eligible batch"}).waitFor();
      await handler.waitForTimeout(1100);
      await handler.getByRole("button", {name:"Review eligible batch"}).click();
      await handler.getByText("Reviewed through event 1", {exact:true}).click();
      await handler.getByText(/^RESPOND/).waitFor();
      const reviewed = await get(handler, "activity-review");
      assert.equal(reviewed.batches.length, 1);
      assert.ok(reviewed.batches[0].items[0].facts.some(f => f.text.includes("Technicians filed a delay notice")));
      assert.equal((await get(handler, "gm-work")).handler_drafts.length, 0);
      assert.deepEqual((await post(handler, "activity-review-run", {})), {batch:null});
      await post(pilot, "consent", {policy_revision:policy, consent:false});
      await get(handler, "activity-review", 403);
      process.stdout.write(JSON.stringify({campaign_opt_in:true, quiet_batch:true, handler_readiness:true,
        approved_opening_facts:true, review_denied_to_pilot:true, no_automatic_reply:true, withdrawal:true}) + "\n");
      return;
    }
    const draft = (await get(handler, "gm-work")).handler_drafts[0].id;
    await handler.getByRole("button", {name:"Refresh Director work"}).click();
    await handler.getByRole("button", {name:"Review Handler draft"}).click();
    await handler.getByLabel("Review reason").fill("Review the reply and the original listener.");
    await handler.getByRole("button", {name:"Approve Handler draft"}).click();
    await handler.getByRole("button", {name:"Preview Handler reply"}).click();
    await handler.getByText("I set my own report pad on the table.", {exact:true}).waitFor();
    await post(pilot, "handler-deliver", {draft}, randomUUID(), 409);
    await handler.getByRole("button", {name:"Deliver Handler reply"}).click();
    await handler.getByRole("heading", {name:"Handler delivery"}).waitFor({state:"hidden"});
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
    assert.equal(receipt.handler_report_count, 5);
    assert.equal((await get(reopened, "timeline")).open, false);
    await post(pilot, "consent", {policy_revision:policy, consent:false});
    await get(reopened, "timeline", 403);
    process.stdout.write(JSON.stringify({
      activity_login:true, opening_preview:true, opening_launch:true, private_brief:true,
      wrong_owner_denied:true, facilitator_review_ui:true, handler_delivery_ui:true,
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
