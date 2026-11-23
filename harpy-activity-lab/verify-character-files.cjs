const assert = require("node:assert/strict");
const {spawnSync} = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {chromium} = require("../.sites-runtime/browser-acceptance/node_modules/playwright-core");

const engine = path.resolve(__dirname, "../.sites-runtime/harpyengine-mission-lab/HarpyEngine-playtest");
const python = path.join(engine, ".venv/Scripts/python.exe");
const origin = "https://character-files.test";
const offlineActivity = "https://character-activity.test";
const ownerId = "123456789012345678";
const otherId = "123456789012345679";
const packagePath = process.argv[2];
if (!packagePath) throw new Error("Pass the v0.1.4 package ZIP as the first argument.");
const privateOrigin = process.argv.slice(3).find(argument => argument.startsWith("--private-origin="))?.split("=")[1];
const chromePath = process.argv.slice(3).find(argument => !argument.startsWith("--"));

function runPython(script, args = [], input) {
  const result = spawnSync(python, ["-B", "-c", script, ...args], {
    input, encoding:"utf8", env:{...process.env, PYTHONIOENCODING:"utf-8"}, maxBuffer: 1024 * 1024 * 8, timeout:15000,
  });
  assert.equal(result.status,0,result.stderr || result.error?.message);
  return JSON.parse(result.stdout);
}

const assets = runPython(`
import base64, json, sys
sys.path.insert(0, sys.argv[1])
from mission_lab import activity_assets
version, files = activity_assets(None)
print(json.dumps([version, {name: base64.b64encode(data).decode() for name, data in files.items()}]))
`, [__dirname]);
const wheel = "girlframe_discord-0.1.4-py3-none-any.whl";

async function verify() {
  const work = fs.mkdtempSync(path.join(os.tmpdir(),"harpy-character-files-"));
  const wheelPath = path.join(work,wheel);
  let browser;
  try {
    const {draft:example, sheet:sample} = runPython(`
import json, sys
from pathlib import Path
from zipfile import ZipFile
with ZipFile(sys.argv[1]) as package:
    Path(sys.argv[2]).write_bytes(package.read("engine/" + sys.argv[3]))
    (draft_path,) = [
        name for name in package.namelist()
        if name.startswith("campaign-ui/example-mockingbird-") and name.endswith(".json")
    ]
    draft = json.loads(package.read(draft_path))
    draft["profile"]["frame_playbook"] = "JANUS"
    print(json.dumps({"draft": draft, "sheet": json.loads(package.read("campaign-ui/example-read-only-sheet.json"))}))
`, [packagePath,wheelPath,wheel]);
    function engineParse(text, notes) {
      const parsed = runPython(`
import json, sys
sys.path.insert(0, sys.argv[1])
from girlframe import __file__ as source
from girlframe.engine.character_documents import parse_draft
document = parse_draft(sys.stdin.buffer.read())
print(json.dumps({"source": source, "profile": document.profile.as_profile("Existing notes").model_dump(), "creation": document.to_creation().model_dump(mode="json")}))
`, [wheelPath], text);
      assert(parsed.source.includes(wheel));
      assert.equal(parsed.profile.notes,notes);
      return parsed;
    }
    browser = await chromium.launch({executablePath:chromePath ?? "C:/Program Files/Google/Chrome/Application/chrome.exe"});
    const page = await browser.newPage();
    page.setDefaultTimeout(5000);
    const errors = [], writes = [];
    const frameOrigin = privateOrigin ? new URL(privateOrigin).origin : offlineActivity;
    page.on("pageerror",error => errors.push(error.message));
    await page.route(origin + "/",route => route.fulfill({contentType:"text/html",body:"<style>body{margin:0}iframe{width:100vw;height:100vh;border:0}</style>" +
      `<iframe title="Activity" sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" src="${frameOrigin}/?frame_id=files-test&amp;instance_id=files-test&amp;platform=desktop"></iframe>`}));
    await page.route(offlineActivity + "/**",route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.pathname === "/api/discord/challenge") {
        assert.equal(request.method(),"POST");
        return route.fulfill({json:{nonce:"synthetic-nonce"}});
      }
      if (url.pathname === "/api/discord/session") {
        assert.equal(request.method(),"POST");
        assert.deepEqual(request.postDataJSON(),{code:"synthetic-code",nonce:"synthetic-nonce",guild_id:null});
        return route.fulfill({json:{session:"synthetic-session",access_token:"synthetic-token",discord_user_id:ownerId}});
      }
      if (request.method() !== "GET") writes.push(request.url());
      if (url.pathname === "/api/activity/config") return route.fulfill({json:{client_id:"111111111111111111",allow_dm:true,battlefield:false}});
      if (url.pathname === "/discord-sdk.js") {
        return route.fulfill({contentType:"text/javascript",body:`export class DiscordSDK {
          ready = async () => {};
          commands = {
            authorize: async () => ({code:"synthetic-code"}),
            authenticate: async () => ({user:{id:${JSON.stringify(ownerId)}}}),
          };
        }`});
      }
      const name = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
      if (!assets[1][name]) return route.fulfill({status:401,json:{error:"Test uses local files only."}});
      if (name !== "index.html") assert.equal(url.searchParams.get("v"),assets[0],name);
      const media = {".html":"text/html",".css":"text/css",".json":"application/json"}[path.extname(name)] ?? "text/javascript";
      return route.fulfill({contentType:media + "; charset=utf-8",body:Buffer.from(assets[1][name],"base64"),
        headers:{"Content-Security-Policy":"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"}});
    });
    if (privateOrigin) {
      await page.route(new URL(privateOrigin).origin + "/**", route => {
        if (route.request().method() === "GET") return route.continue();
        writes.push(route.request().url());
        return route.abort();
      });
    }
    await page.goto(origin + "/");
    const activity = page.frameLocator("iframe");
    const auth = activity.getByRole("dialog",{name:"Discord authentication"});
    await auth.waitFor();
    await auth.getByRole("button",{name:/Close/}).click();
    await activity.getByRole("button",{name:"Character Sheets",exact:true}).click();
    const dialog = activity.getByRole("dialog",{name:"Character Sheets"});
    const file = dialog.getByLabel("Open a HarpyEngine JSON file");
    const exported = () => save("Export creation JSON","harpyengine-character-draft.json");
    async function save(label, filename) {
      const [download] = await Promise.all([page.waitForEvent("download"),dialog.getByRole("button",{name:label,exact:true}).click()]);
      assert.equal(download.suggestedFilename(),filename);
      return fs.readFileSync(await download.path(),"utf8");
    }
    async function load(value, expected) {
      const bytes = Buffer.isBuffer(value) ? value : Buffer.from(typeof value === "string" ? value : JSON.stringify(value),"utf8");
      await file.setInputFiles({name:"character.json",mimeType:"application/json",buffer:bytes});
      const status = dialog.locator("#character-files-status");
      await status.waitFor();
      if (await status.getByRole("button",{name:"Replace editor draft"}).isVisible()) {
        await status.getByRole("button",{name:"Replace editor draft"}).click();
      }
      await status.getByText(expected).waitFor();
    }

    await dialog.getByLabel("Callsign",{exact:true}).fill("VÉGA");
    await dialog.getByLabel("Girl playbook",{exact:true}).selectOption("MOCKINGBIRD");
    const framePicker = dialog.getByLabel("Frame playbook",{exact:true});
    await framePicker.selectOption("JANUS");
    assert.deepEqual(await framePicker.locator("option").evaluateAll(options =>
      options.filter(option => option.textContent.toUpperCase().startsWith("JANUS")).map(option => option.value)
    ), ["JANUS"]);
    await dialog.getByText("Incomplete draft",{exact:true}).waitFor();
    const incomplete = await exported();
    assert(!Object.hasOwn(JSON.parse(incomplete).profile,"notes"));
    assert.equal(engineParse(incomplete,"Existing notes").profile.callsign,"VÉGA");
    await dialog.getByRole("button",{name:"Add Girl Asset",exact:true}).click();
    await dialog.getByLabel("Girl Asset description").fill("Line 1.\nLine 2 · café");
    await dialog.getByRole("button",{name:"Add Frame Asset",exact:true}).click();
    await dialog.getByLabel("Frame Asset name").selectOption("Enhanced Nerve Processors");
    await dialog.getByLabel("Frame Asset description").fill("Synthetic Frame Asset.");
    const output = engineParse(await exported(),"Existing notes");
    assert.equal(output.profile.frame_playbook,"JANUS");
    assert.equal(output.creation.frame_assets[0].name,"Enhanced Nerve Processors");
    assert.equal(output.creation.girl_assets[0].description,"Line 1.\nLine 2 · café");
    await dialog.getByRole("button",{name:"Add Girl Asset",exact:true}).click();
    await dialog.getByLabel("Girl Asset description").last().fill("Second Girl Asset.");
    await dialog.getByRole("button",{name:"Add Frame Asset",exact:true}).click();
    await dialog.getByLabel("Frame Asset description").last().fill("Second Frame Asset.");
    await dialog.getByLabel("Void-altered Girl Asset").selectOption("Adaptive Restraints");
    await dialog.getByLabel("Frame name",{exact:true}).fill("SILVER ECHO");
    await dialog.getByLabel("Girl appearance",{exact:true}).fill("A charcoal pilot uniform.");
    await dialog.getByLabel("Frame appearance",{exact:true}).fill("A slate-blue Frame.");
    await dialog.getByRole("button",{name:"Add NPC Bond",exact:true}).click();
    await dialog.getByLabel("NPC name",{exact:true}).fill("Custodian");
    await dialog.getByLabel("Feelings about the NPC").fill("An old acquaintance.");
    await dialog.getByText("Creation fields filled",{exact:true}).waitFor();
    const created = engineParse(await exported(),"Existing notes").creation;
    assert.equal(created.girl_assets.length,2);
    assert.equal(created.frame_assets.length,2);
    assert.equal(created.void_asset,"Adaptive Restraints");
    assert.equal(created.npc_bonds[0].name,"Custodian");

    const profile = (girl, frame, extra) => ({callsign:"ROUNDTRIP", girl_playbook:girl, frame_playbook:frame, ...extra});
    const cases = [
      [{...example,profile:{...example.profile,notes:null}},"Existing notes"],
      [{...example,profile:profile("BONDED","JANUS",{notes:""}),creation:{pair_asset_descriptions:[{name:"Magnetic Bands",description:"Pair description\nretained"}]}},""],
      [{...example,profile:profile("OLDGEN","JANUS",{notes:"Private draft notes"}),creation:{girl_details:{maxims:[5,0]}}},"Private draft notes"],
      [{...example,profile:profile("PRINCESS","JANUS"),creation:{girl_details:{own_standard:{slot:9,custom:"A custom standard"}},fanbase:null}},"Existing notes"],
      [{...example,profile:profile("VATGROWN","THE PRINCE"),creation:{dna_basis:"Synthetic\norigin",npc_bonds:[{slot:1,name:"Researcher",feelings:"A memory"}],girl_details:{investors:[{npc_slot:1,desires:{slots:[10,0]}}]},fanbase:{demographics:["custom:1","Young boys"],custom_demographic:"Technicians",demanded:["Kind","custom:1"],rejected:["Masculine","custom:2"],custom_quality_1:"Steady",custom_quality_2:"Impatient"}}},"Existing notes"],
    ];
    for (const [draft,notes] of cases) {
      await load(draft,/Creation draft loaded/);
      const text = await exported();
      assert.deepEqual(JSON.parse(text),draft);
      engineParse(text,notes);
    }
    await dialog.getByLabel("DNA basis",{exact:true}).fill("Revised DNA narrative\nwithout truncation");
    const edited = JSON.parse(await exported());
    assert.deepEqual(edited.creation,{...cases.at(-1)[0].creation,dna_basis:"Revised DNA narrative\nwithout truncation"});
    engineParse(JSON.stringify(edited),"Existing notes");
    await load({...example,creation:{...example.creation,heat:5}},/unsupported field heat/);
    await load(JSON.stringify(example).replace('"profile":','"profile":{},"profile":'),/duplicate JSON field/);
    await load({...example,schema_version:2},/supports schema version 1/);
    await load(Buffer.from([0xff,0xfe]),/not valid UTF-8/);
    await load(Buffer.alloc(256*1024+1),/256 KiB/);
    assert.deepEqual(JSON.parse(await exported()),edited);

    const hostile = '<img src=x onerror="window.sheetInjected=true">';
    const snapshot = {...sample,owner_id:ownerId,display_name:"Current Discord nickname",sheet:{...sample.sheet,state:"active_m2_subset",callsign:hostile,private_notes:"PRIVATE NOTES SENTINEL",starting_setup:{girl_playbook:"MOCKINGBIRD",npc_bonds:[{slot:0,name:"Starting contact",feelings:"Reference only"}]}}};
    const printable = dialog.getByRole("button",{name:"Download printable sheet",exact:true});
    await load(snapshot,/Sign in with Discord to open your owner snapshot/);
    assert.equal(await printable.count(),0);
    await load({...snapshot,audience:"public"},/Read-only snapshot loaded/);
    await dialog.getByText("Current Discord nickname",{exact:false}).waitFor();
    assert.equal(await dialog.getByRole("heading",{name:"Current Bonds"}).count(),0);
    assert.equal(await dialog.getByLabel(/Include private notes/).count(),0);
    assert.equal(await dialog.getByRole("button",{name:"Export creation JSON"}).count(),0);
    assert.equal(await dialog.locator(".portable-sheet img").count(),0);
    const printed = () => save("Download printable sheet","harpyengine-character-sheet.html");
    const print = await printed();
    assert(print.includes("&lt;img"));
    assert(!print.includes("<img") && !print.includes("<script") && !print.includes("PRIVATE NOTES SENTINEL") &&
      !print.includes("Starting contact") && !print.includes("Heat"));
    const paper = await browser.newPage();
    await paper.setContent(print);
    await paper.getByText("Active character",{exact:true}).waitFor();
    assert.equal(await paper.locator("img,script").count(),0);
    const pdf = await paper.pdf({format:"A4"});
    assert.equal(pdf.subarray(0,5).toString(),"%PDF-");
    assert(pdf.length > 1000);
    await paper.close();
    if (!privateOrigin) {
      await dialog.getByRole("button",{name:"Close Character Sheets"}).click();
      await activity.getByRole("button",{name:"Open sign-in",exact:true}).click();
      await auth.getByRole("button",{name:"Sign in with Discord",exact:true}).click();
      await auth.waitFor({state:"hidden"});
      await activity.getByRole("button",{name:"Character Sheets",exact:true}).click();
      await dialog.getByRole("button",{name:"Return to creation draft"}).click();
      await load({...snapshot,owner_id:Number(ownerId)},/owner_id.*string/);
      await load({...snapshot,owner_id:otherId},/belongs to a different Discord account/);
      assert.equal(await printable.count(),0);
      await load(snapshot,/Read-only snapshot loaded/);
      await dialog.getByText("Synthetic partner",{exact:false}).waitFor();
      await dialog.getByRole("heading",{name:"Current Bonds"}).waitFor();
      await dialog.getByRole("heading",{name:"Starting NPC context · reference"}).waitFor();
      assert(!(await printed()).includes("PRIVATE NOTES SENTINEL"));
      await dialog.getByLabel(/Include private notes/).check();
      assert((await printed()).includes("PRIVATE NOTES SENTINEL"));
      await load({...snapshot,sheet:{...snapshot.sheet,state:"draft_rules_unverified",creation_requirements:["Review the starting Bond."]}},/Read-only snapshot loaded/);
      await dialog.getByText("Draft · Not activated",{exact:true}).waitFor();
      await dialog.getByText("Review the starting Bond.",{exact:true}).waitFor();
      assert.equal(await dialog.getByRole("heading",{name:"Current resources"}).count(),0);
    }
    await dialog.getByRole("button",{name:"Return to creation draft"}).click();
    assert.deepEqual(JSON.parse(await exported()),edited);
    assert.deepEqual(errors,[]);
    assert.deepEqual(writes,[]);
    console.log(`${privateOrigin ? "Private Activity origin in an embedded browser" : "Offline Activity UI"}: generator, 5 exact draft round trips, packaged v0.1.4 parser, snapshot privacy, and PDF printing passed.`);
  } finally {
    if (browser) await browser.close();
    if (fs.existsSync(wheelPath)) fs.unlinkSync(wheelPath);
    fs.rmdirSync(work);
  }
}

verify().catch(error => { console.error(error); process.exitCode = 1; });
