import {DRAFT_FORMAT, MAX_DOCUMENT_BYTES, parseDraftJSON, SHEET_FORMAT} from "/character-sheets/harpyengine-sheets.mjs";
import {validateDraft, validateSheet} from "/character-sheets/validators.mjs";
import {action, catalog, printedCreation, element, list, renderDraft, schemaErrors, section, starterDraft} from "/character-draft-ui.js";

/** @typedef {import('./character-sheets/harpyengine-sheets').CharacterSheetDocument} Snapshot */

const array = value => Array.isArray(value) ? value : [];
const object = value => value && typeof value === "object" && !Array.isArray(value);
const string = value => typeof value === "string" ? value : "";
const discordId = value => typeof value === "string" && /^[1-9][0-9]{0,19}$/.test(value);

function readJSON(text) {
  let data;
  try { data = JSON.parse(text); }
  catch { throw new Error("This file is not valid JSON. Select the UTF-8 .json file exported by HarpyEngine."); }
  // JSON.parse accepts duplicate keys. Reject them before editing so a re-export
  // cannot silently turn an engine-rejected upload into a different document.
  const containers = [];
  for (const token of text.matchAll(/"(?:[^"\\]|\\.)*"|[{}\[\]]/gs)) {
    const value = token[0];
    if (value === "{") containers.push(new Set());
    else if (value === "[") containers.push(null);
    else if (value === "}" || value === "]") containers.pop();
    else if (containers.at(-1) && /^\s*:/.test(text.slice(token.index + value.length))) {
      const key = JSON.parse(value);
      if (containers.at(-1).has(key)) throw new Error("The file has a duplicate JSON field. Correct the original file before reopening it.");
      containers.at(-1).add(key);
    }
  }
  return data;
}

function decodeDocument(text) {
  const data = readJSON(text);
  if (!object(data) || ![DRAFT_FORMAT, SHEET_FORMAT].includes(data.format)) {
    throw new Error("Choose a HarpyEngine creation draft or character-sheet snapshot.");
  }
  if (data.schema_version !== 1) throw new Error("This Activity supports schema version 1 for HarpyEngine character files.");
  const validate = data.format === DRAFT_FORMAT ? validateDraft : validateSheet;
  if (!validate(data)) throw new Error(schemaErrors(validate).join("\n"));
  if (data.format === DRAFT_FORMAT) {
    try { return parseDraftJSON(text); }
    catch { throw new Error("The draft profile needs nonempty single-line labels. Check the callsign, playbooks, and file size."); }
  }
  if (Object.keys(data.members ?? {}).some(id => !discordId(id))) throw new Error("Personnel identifiers must remain text values in the exported record.");
  return data;
}

function rows(target, title, values) {
  const display = values.filter(value => value !== "");
  if (display.length) list(section(target, title), display);
}

function facts(source, fields) {
  return fields.flatMap(([key, title]) => {
    const value = source[key];
    if (typeof value === "boolean") return [`${title} · ${value ? "Yes" : "No"}`];
    if (Number.isFinite(value) || string(value)) return [`${title} · ${value}`];
    return [];
  });
}

function startingReferences(target, setup) {
  if (!object(setup)) return;
  const girl = string(setup.girl_playbook);
  const roles = printedCreation.npc_roles[girl] ?? [];
  const bondRows = array(setup.npc_bonds).filter(object).map(npc => {
    const role = Number.isInteger(npc.slot) ? roles[npc.slot] ?? "NPC" : "NPC";
    return [string(npc.name) || role, string(npc.name) ? role : "", string(npc.feelings)].filter(Boolean).join(" · ");
  });
  rows(target, "Starting NPC context · reference", bondRows);
  const choices = facts(setup, [["girl_playbook", "Starting Girl"], ["frame_playbook", "Starting Frame"], ["dna_basis", "DNA basis"]]);
  const details = setup.girl_details;
  if (object(details)) {
    const standard = details.own_standard;
    if (object(standard) && Number.isInteger(standard.slot) && catalog.standards[standard.slot]) {
      choices.push(`Own standard · ${standard.slot === 9 ? string(standard.custom) : printedCreation.standards[standard.slot]}`);
    }
    for (const slot of array(details.maxims)) if (Number.isInteger(slot) && catalog.maxims[slot]) choices.push(`Maxim · ${printedCreation.maxims[slot]}`);
    for (const investor of array(details.investors).filter(object)) {
      const desires = array(investor.desires?.slots).filter(Number.isInteger).map(slot => printedCreation.investor_desires[slot]).filter(Boolean);
      const role = Number.isInteger(investor.npc_slot) ? roles[investor.npc_slot] : undefined;
      if (desires.length) choices.push(`${role ?? "NPC investor"} · ${desires.join(", ")}`);
    }
  }
  if (object(setup.fanbase)) {
    for (const key of ["demographics", "demanded", "rejected"]) {
      const values = array(setup.fanbase[key]).filter(value => typeof value === "string").map(value => {
        if (!/^custom:[12]$/.test(value)) return value;
        return string(setup.fanbase[key === "demographics" ? "custom_demographic" : `custom_quality_${value.at(-1)}`]) || "Custom choice";
      });
      if (values.length) choices.push(`Fanbase ${key} · ${values.join(", ")}`);
    }
  }
  rows(target, "Starting playbook choices · reference", choices);
}

/** @param {Snapshot} snapshot */
function renderProjection(snapshot, includeNotes) {
  const projection = snapshot.sheet;
  const owner = snapshot.audience === "owner";
  const active = projection.state === "active_m2_subset" || projection.status === "active_m2_subset";
  const draft = projection.state === "draft_rules_unverified";
  const memberName = id => discordId(id) && Object.hasOwn(snapshot.members ?? {}, id) ? snapshot.members[id] : "Unavailable member";
  const sheet = element("article");
  sheet.className = "portable-sheet";
  const header = element("header");
  header.append(element("h3", string(projection.callsign) || "Unnamed character"),
    element("p", draft ? "Draft · Not activated" : active ? "Active character" : "Activation state not supplied"),
    element("p", `${owner ? "Owner" : "Public"} projection · Read-only snapshot`),
    element("p", `Personnel nickname · ${snapshot.display_name || memberName(snapshot.owner_id)}`));
  sheet.append(header);
  rows(sheet, "Personnel record", facts(projection, [["girl_playbook", "Girl"], ["frame_playbook", "Frame"], ["frame_name", "Frame name"], ["appearance", "Girl appearance"], ["girl_appearance", "Girl appearance"], ["frame_appearance", "Frame appearance"]]));
  if (active && !draft) {
    const attributes = [["rank", "Status"]];
    if (owner) attributes.push(["heat", "Heat"], ["permissions", "Permissions"], ["medical_state", "Medical state"], ["frame_scrapped", "Frame scrapped"], ["status_marked", "Status marked"], ["obsolescence_marked", "Obsolescence marked"]);
    rows(sheet, "Current resources", facts(projection, attributes));
  }
  rows(sheet, draft ? "Planned Identities" : "Identities", array(projection.identities).map(item => {
    if (!object(item)) return string(item);
    const name = string(item.name);
    return name && owner && active && !draft && item.marked === true ? `${name} · Marked` : name;
  }));
  rows(sheet, draft ? "Planned Assets" : "Assets", array(projection.assets).map(asset => {
    if (!object(asset)) return string(asset);
    if (!owner && asset.concealed) return "";
    return [string(asset.name), string(asset.family), !draft && asset.damaged === true ? "Damaged" : "",
      owner && asset.void === true ? "Void-altered" : "", owner && asset.concealed === true ? "Concealed" : "", string(asset.description)].filter(Boolean).join(" · ");
  }));
  if (owner) {
    if (active && !draft) {
      rows(sheet, "Current Bonds", array(projection.bonds).filter(object).map(bond => [
        memberName(bond.counterpart_id ?? bond.counterpart), ["pilot","handler"].includes(bond.role) ? bond.role : "",
        string(bond.depth), string(bond.context),
      ].filter(Boolean).join(" · ")));
      rows(sheet, "Current Tags", array(projection.tags).map(tag => object(tag) ? [string(tag.label), tag.marked === true ? "Marked" : ""].filter(Boolean).join(" · ") : string(tag)));
    }
    startingReferences(sheet, projection.starting_setup);
    rows(sheet, "Still needed before activation", array(projection.creation_requirements).map(string));
    if (includeNotes) rows(sheet, "Private notes", [string(projection.private_notes)]);
  }
  sheet.append(element("footer", `HarpyEngine ${snapshot.engine_version} · Revision ${snapshot.revision} · ${snapshot.rules_status ?? "RULES_SUBSET"}`));
  return sheet;
}

function download(content, filename, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = element("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function printDocument(sheet) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HarpyEngine character sheet</title><style>
  body{font:16px/1.5 system-ui,sans-serif;max-width:56rem;margin:2rem auto;padding:0 1rem;color:#182930;background:#fff}
  header,section{border-bottom:1px solid #aebcbe;margin-bottom:1rem;padding-bottom:.5rem}h3{margin:.25rem 0}p,li{white-space:pre-wrap;overflow-wrap:anywhere}footer{font-size:.9rem}
  @media print{body{margin:0;padding:0}header,h3{break-after:avoid}li{break-inside:avoid}}
  </style></head><body>${sheet.outerHTML}</body></html>`;
}

export function characterFiles(dialog) {
  const target = dialog.querySelector("#character-files-content");
  const status = dialog.querySelector("#character-files-status");
  const tools = element("div");
  tools.className = "character-file-tools";
  const label = element("label", "Open a HarpyEngine JSON file");
  label.className = "field";
  const file = element("input");
  file.type = "file";
  file.accept = ".json,application/json";
  label.append(file);
  const body = element("div");
  const newDraft = action("Start a new draft", () => {
    replaceDraft(starterDraft(player), "New creation draft ready.");
  });
  const returnDraft = action("Return to creation draft", () => { mode = "draft"; showStatus(""); show(); });
  tools.append(label, newDraft, returnDraft);
  target.append(tools, body);
  let player, draft, baseline, snapshot, discordUserId, mode = "draft";
  let selection = 0;

  function showStatus(message) {
    status.textContent = message;
    status.hidden = !message;
  }

  function replaceDraft(next, message) {
    const replace = () => {
      draft = next;
      baseline = JSON.stringify(draft);
      mode = "draft";
      showStatus(message);
      show();
    };
    if (draft && JSON.stringify(draft) !== baseline) {
      showStatus("The current draft has local edits. Export a copy first if you want to keep them.");
      const choices = element("div");
      choices.className = "actions";
      choices.append(action("Replace editor draft", replace), action("Keep current draft", () => showStatus("")));
      status.append(choices);
    } else replace();
  }

  function show() {
    returnDraft.hidden = mode === "draft" || !draft;
    if (mode === "draft") {
      renderDraft(body, draft, download);
      return;
    }
    body.replaceChildren();
    const preview = element("div");
    const button = action("Download printable sheet", () => download(printDocument(preview.firstElementChild), "harpyengine-character-sheet.html", "text/html;charset=utf-8"));
    body.append(button, element("p", "Open the downloaded HTML in your browser to print or save it as PDF."));
    if (snapshot.audience === "owner" && string(snapshot.sheet.private_notes)) {
      const notes = element("label", " Include private notes in this view and print file");
      const toggle = element("input");
      toggle.type = "checkbox";
      notes.prepend(toggle);
      body.append(notes);
      toggle.addEventListener("change", () => preview.replaceChildren(renderProjection(snapshot, toggle.checked)));
    }
    preview.append(renderProjection(snapshot, false));
    body.append(preview);
  }

  file.addEventListener("change", async () => {
    const chosen = file.files?.[0];
    file.value = "";
    if (!chosen) return;
    showStatus("");
    const pending = ++selection;
    try {
      if (chosen.size > MAX_DOCUMENT_BYTES) throw new Error("Character files must be 256 KiB or smaller.");
      const bytes = await chosen.arrayBuffer();
      if (pending !== selection) return;
      let content;
      try { content = new TextDecoder("utf-8", {fatal:true, ignoreBOM:true}).decode(bytes); }
      catch { throw new Error("This character file is not valid UTF-8."); }
      const document = decodeDocument(content);
      if (document.format === DRAFT_FORMAT) {
        replaceDraft(document, "Creation draft loaded. Changes stay in this editor until you export.");
        return;
      }
      if (document.audience === "owner") {
        if (!discordUserId) {
          throw new Error("Present credentials to open your private personnel record. Public records are available without clearance.");
        }
        if (document.owner_id !== discordUserId) {
          throw new Error("This private record belongs to another principal. Request a public export from its owner.");
        }
      }
      snapshot = document;
      mode = "sheet";
      showStatus("Read-only snapshot loaded from this file.");
      show();
    } catch (error) {
      if (pending === selection) showStatus(error.message);
    }
  });

  return {
    open(currentPlayer, verifiedDiscordId) {
      player = currentPlayer;
      if (discordUserId !== verifiedDiscordId) {
        ++selection;
        discordUserId = verifiedDiscordId;
        if (snapshot?.audience === "owner" && snapshot.owner_id !== discordUserId) {
          snapshot = undefined;
          mode = "draft";
        }
      }
      if (!draft) {
        draft = starterDraft(player);
        baseline = JSON.stringify(draft);
      }
      showStatus("");
      show();
      if (!dialog.open) dialog.showModal();
    },
  };
}
