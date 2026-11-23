import catalog from "/character-sheets/creation-catalog-v1.json" with { type: "json" };
import {createDraft, serializeDraft} from "/character-sheets/harpyengine-sheets.mjs";
import {validateDraft} from "/character-sheets/validators.mjs";
import book from "/rulebook-text.json" with { type: "json" };
import {showSelectionText} from "/popup-ui.js";

/** @typedef {import('./character-sheets/harpyengine-sheets').CharacterDraftDocument} Draft */
/** @typedef {import('./character-sheets/harpyengine-sheets').PortableChoices} Choices */

export {catalog};
const npcRoleText = girl => book.npc_bonds[girl]?.text ?? catalog.npc_roles[girl] ?? [];
const standardText = [...book.choices.princess_standards.text, catalog.standards.at(-1)];
export const printedCreation = {
  standards:standardText, maxims:book.choices.oldgen_maxims.text,
  investor_desires:book.choices.investor_desires.text,
  npc_roles:Object.fromEntries(Object.entries(book.npc_bonds).map(([girl,entry]) => [girl,entry.text])),
};

const creationFields = ["girl_assets", "frame_assets", "void_asset", "frame_name", "girl_appearance",
  "frame_appearance", "pair_asset_descriptions", "npc_bonds", "dna_basis", "fanbase", "girl_details"];

export function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

export function action(label, activate) {
  const button = element("button", label);
  button.type = "button";
  button.addEventListener("click", activate);
  return button;
}

export function section(target, label) {
  const group = element("section");
  group.append(element("h3", label));
  target.append(group);
  return group;
}

export function list(target, items) {
  const ul = element("ul");
  for (const item of items) ul.append(element("li", item));
  target.append(ul);
}

export function schemaErrors(validate) {
  return (validate.errors ?? []).slice(0, 8).map(error => {
    const path = error.instancePath || "Document";
    if (error.keyword === "additionalProperties") return `${path}: unsupported field ${error.params.additionalProperty}.`;
    if (error.keyword === "required") return `${path}: missing ${error.params.missingProperty}.`;
    return `${path}: ${error.message}.`;
  });
}

let fieldSequence = 0;
function label(target, name, control) {
  const wrapper = element("div");
  wrapper.className = "field";
  control.id = `creation-file-field-${++fieldSequence}`;
  const caption = element("label", name);
  caption.htmlFor = control.id;
  wrapper.append(caption, control);
  target.append(wrapper);
  return control;
}

function text(target, name, value, write, multiline = false) {
  const control = label(target, name, element(multiline || /[\r\n]/.test(value ?? "") ? "textarea" : "input"));
  control.value = value ?? "";
  // Preserve imported strings in the model. Validation measures Unicode code points.
  control.addEventListener("input", () => write(control.value));
  return control;
}

const numbered = names => names.map((name, index) => [index, name]);
const named = names => names.map(name => [name, name]);

function picker(target, title, value, options, write, multiple = false) {
  const select = label(target, title, element("select"));
  select.multiple = multiple;
  let values = multiple ? value ?? [] : value == null ? [] : [value];
  const entries = new Map(options.map(([id, name]) => [String(id), {id, name}]));
  for (const id of values) {
    if (!entries.has(String(id))) entries.set(String(id), {id, name: `${id} (imported)`});
  }
  if (!multiple) select.append(element("option", "Select…"));
  if (!multiple) select.options[0].value = "";
  for (const [value, {name}] of entries) {
    const option = element("option", name);
    option.value = value;
    option.selected = values.some(id => String(id) === value);
    select.append(option);
  }
  if (multiple) select.size = Math.max(2, Math.min(5, entries.size));
  select.addEventListener("change", () => {
    if (!multiple) return write(entries.get(select.value)?.id ?? null);
    const selected = new Set(Array.from(select.selectedOptions, option => entries.get(option.value).id));
    values = [...values.filter(id => selected.has(id)), ...[...selected].filter(id => !values.includes(id))];
    write(values);
  });
  showSelectionText(select,select.parentElement);
  return select;
}

const bookKey = value => value?.trim().toUpperCase().replace(/^AM \(ARTIFICIAL MIND\)$/, "AM") ?? "";

export function starterDraft(player) {
  /** @type {Draft} */
  const draft = {format:"harpyengine.character-draft", schema_version:1, profile:{
    callsign:player?.callsign ?? "",
    girl_playbook:player?.options?.girl ?? player?.cadre?.find(pilot => pilot.own)?.girl ?? "",
    frame_playbook:player?.options?.frame ?? player?.profile?.frame ?? "",
  }};
  if (player?.draft) {
    draft.creation = Object.fromEntries(creationFields.filter(key => Object.hasOwn(player.draft, key))
      .map(key => [key, structuredClone(player.draft[key])]));
  }
  return draft;
}

function draftIssues(draft) {
  if (!validateDraft(draft)) return schemaErrors(validateDraft);
  const {profile, creation = {}} = draft;
  const girl = bookKey(profile.girl_playbook), frame = bookKey(profile.frame_playbook);
  const issues = [];
  if (!profile.callsign.trim() || /[\u0000-\u001f\u007f]/u.test(profile.callsign)) issues.push("Callsign must be a nonempty single-line label.");
  if (!Object.hasOwn(catalog.girl_types, girl)) issues.push("Choose a Girl playbook from the catalog.");
  if (!Object.hasOwn(catalog.frame_types, bookKey(profile.frame_playbook))) issues.push("Choose a Frame playbook from the catalog.");
  for (const [key, source] of [["girl_assets", girl], ["frame_assets", frame], ["pair_asset_descriptions", "BONDED"]]) {
    const names = (creation[key] ?? []).map(asset => asset.name);
    if (new Set(names).size !== names.length || names.some(name => !catalog.playbooks[source]?.assets.includes(name))) {
      issues.push(`${key.replaceAll("_", " ")}: choose distinct Assets from the selected playbook.`);
    }
  }
  if (girl === "BONDED" && creation.girl_assets?.length) issues.push("Remove owner-selected Girl Assets for Bonded. The Pair must file its own selections.");
  if (girl !== "BONDED" && creation.pair_asset_descriptions?.length) issues.push("Pair Asset descriptions apply to Bonded.");
  if (creation.void_asset != null && (girl !== "MOCKINGBIRD" || !creation.girl_assets?.some(asset => asset.name === creation.void_asset))) {
    issues.push("The Void-altered Asset must be a selected Mockingbird Girl Asset.");
  }
  const roles = (creation.npc_bonds ?? []).map(npc => npc.slot);
  if (new Set(roles).size !== roles.length) issues.push("Choose distinct NPC Bond roles.");
  if (girl !== "VATGROWN" && creation.dna_basis) issues.push("DNA basis applies to Vatgrown.");
  const details = creation.girl_details;
  if (details?.own_standard && (girl !== "PRINCESS" || (details.own_standard.slot === 9) !== Boolean(details.own_standard.custom?.trim()))) {
    issues.push("Choose a Princess standard and supply text only for a custom standard.");
  }
  if (details?.maxims?.length && (girl !== "OLDGEN" || new Set(details.maxims).size !== details.maxims.length || details.maxims.some(n => !catalog.maxims[n]))) {
    issues.push("Choose distinct Oldgen maxims from the catalog.");
  }
  if (details?.investors?.length) {
    const investorRoles = details.investors.map(investor => investor.npc_slot);
    if (girl !== "VATGROWN" || new Set(investorRoles).size !== investorRoles.length || details.investors.some(investor =>
      !roles.includes(investor.npc_slot) || new Set(investor.desires.slots).size !== investor.desires.slots.length || investor.desires.slots.some(slot => !catalog.investor_desires[slot]))) {
      issues.push("Choose distinct Vatgrown NPC Bonds for investors and select their listed desires.");
    }
  }
  const fan = creation.fanbase;
  if (fan) {
    if (frame !== "THE PRINCE") issues.push("Fanbase choices apply to The Prince.");
    const qualities = [...catalog.fanbase.qualities, "custom:1", "custom:2"];
    for (const [key, allowed] of [["demographics", [...catalog.fanbase.demographics, "custom:1"]], ["demanded", qualities], ["rejected", qualities]]) {
      const choices = fan[key] ?? [];
      if (new Set(choices).size !== choices.length || choices.some(choice => !allowed.includes(choice))) issues.push(`Choose distinct catalog options for Fanbase ${key}.`);
    }
    if (fan.demanded?.some(value => fan.rejected?.includes(value))) issues.push("A Fanbase quality cannot be both demanded and rejected.");
    for (const [custom, printed] of [[[fan.custom_demographic], catalog.fanbase.demographics], [[fan.custom_quality_1, fan.custom_quality_2], catalog.fanbase.qualities]]) {
      const labels = custom.filter(value => value?.trim()).map(value => value.trim().toLowerCase());
      if (new Set(labels).size !== labels.length || labels.some(value => printed.some(name => name.toLowerCase() === value))) issues.push("Custom Fanbase labels must be distinct from printed labels and one another.");
    }
  }
  return issues;
}

function missingChoices(draft) {
  const {profile, creation = {}} = draft;
  const girl = bookKey(profile.girl_playbook), frame = bookKey(profile.frame_playbook);
  const missing = [];
  if (!profile.callsign.trim()) missing.push("Callsign");
  if (!girl) missing.push("Girl playbook");
  if (!frame) missing.push("Frame playbook");
  if (girl === "BONDED") missing.push("Pair Asset selection and countersignature");
  else if (girl && creation.girl_assets?.length !== 2) missing.push("Two Girl Assets");
  if (frame && creation.frame_assets?.length !== 2) missing.push("Two Frame Assets");
  if ([...(creation.girl_assets ?? []), ...(creation.frame_assets ?? [])].some(item => !item.description?.trim())) missing.push("Descriptions for selected Assets");
  if (girl === "MOCKINGBIRD" && !creation.void_asset) missing.push("One Void-altered Girl Asset");
  for (const [key, title] of [["frame_name", "Frame name"], ["girl_appearance", "Girl appearance"], ["frame_appearance", "Frame appearance"]]) {
    if (!creation[key]?.trim()) missing.push(title);
  }
  if (girl && (creation.npc_bonds?.length ?? 0) < (girl === "OLDGEN" ? 2 : 1)) missing.push(girl === "OLDGEN" ? "Two NPC Bonds" : "An NPC Bond");
  if (girl === "VATGROWN" && !creation.dna_basis?.trim()) missing.push("DNA basis");
  if (frame === "THE PRINCE" && ["demographics", "demanded", "rejected"].some(key => creation.fanbase?.[key]?.length !== 2)) missing.push("The Prince’s Fanbase choices");
  return missing;
}

function collection(target, title, items, add, remove, render, redraw) {
    const group = section(target, title);
    items.forEach((item, index) => {
      const row = element("fieldset");
      row.append(element("legend", `${title} ${index + 1}`));
      render(row, item);
      row.append(action(`Remove ${title} ${index + 1}`, () => { remove(index); redraw(); }));
      group.append(row);
    });
    if (items.length < 2) group.append(action(`Add ${title}`, () => { add(); redraw(); }));
  }

export function renderPlaybookFields(target, form, girl, frame, creation, updateCreation, changes, redraw) {
  const npcRoles = npcRoleText(girl);
  if (girl === "VATGROWN" || creation.dna_basis) text(form, "DNA basis", creation.dna_basis, value => updateCreation("dna_basis", value), true);
  const details = creation.girl_details ?? {};
  const updateDetails = (key, value) => { details[key] = value; updateCreation("girl_details", details); };
  if (girl === "PRINCESS" || details.own_standard) {
    const group = section(target, "Princess standard");
    picker(group, "Own standard", details.own_standard?.slot, numbered(standardText), slot => {
      updateDetails("own_standard", slot == null ? null : {...details.own_standard, slot});
      redraw();
    });
    if (details.own_standard?.slot === 9 || details.own_standard?.custom) text(group, "Custom standard", details.own_standard.custom, value => {
      details.own_standard.custom = value;
      changes();
    }, true);
  }
  if (girl === "OLDGEN" || details.maxims?.length) picker(form, "Oldgen maxims", details.maxims, numbered(book.choices.oldgen_maxims.text), value => updateDetails("maxims", value), true);
  if (girl === "VATGROWN" || details.investors?.length) {
    const investors = details.investors ?? [];
    const slots = (creation.npc_bonds ?? []).map(npc => [npc.slot, npc.name || npcRoles[npc.slot] || `Role ${npc.slot}`]);
    collection(target, "NPC investor", investors, () => {
      const next = slots.find(([slot]) => !investors.some(item => item.npc_slot === slot));
      updateDetails("investors", [...investors, {npc_slot:next?.[0] ?? 0, desires:{slots:[]}}]);
    }, index => updateDetails("investors", investors.filter((_, i) => i !== index)), (row, investor) => {
      picker(row, "Investor NPC Bond", investor.npc_slot, slots, value => { investor.npc_slot = value; changes(); });
      picker(row, "Investor desires", investor.desires.slots, numbered(book.choices.investor_desires.text), value => { investor.desires.slots = value; changes(); }, true);
    }, redraw);
  }
  if (frame === "THE PRINCE" || creation.fanbase) {
    const group = section(target, "The Prince’s Fanbase");
    if (creation.fanbase) group.append(action("Remove Fanbase choices", () => { updateCreation("fanbase", null); redraw(); }));
    const fanbase = creation.fanbase ?? {};
    const update = (key, value) => { fanbase[key] = value; updateCreation("fanbase", fanbase); };
    const demographics = [...named(catalog.fanbase.demographics), ["custom:1", "Custom demographic"]];
    const qualities = [...named(catalog.fanbase.qualities), ["custom:1", "Custom quality 1"], ["custom:2", "Custom quality 2"]];
    picker(group, "Fan demographics", fanbase.demographics, demographics, value => update("demographics", value), true);
    picker(group, "Demanded qualities", fanbase.demanded, qualities, value => update("demanded", value), true);
    picker(group, "Rejected qualities", fanbase.rejected, qualities, value => update("rejected", value), true);
    for (const [key, title] of [["custom_demographic", "Custom demographic"], ["custom_quality_1", "Custom quality 1"], ["custom_quality_2", "Custom quality 2"]]) {
      text(group, title, fanbase[key], value => update(key, value));
    }
  }
}

export function renderDraft(target, draft, download) {
  target.replaceChildren();
  const changes = () => {
    const issues = draftIssues(draft);
    const missing = missingChoices(draft);
    status.replaceChildren(element("strong", missing.length || issues.length ? "Incomplete draft" : "Creation fields filled"));
    if (missing.length) list(status, missing);
    validation.replaceChildren();
    if (issues.length) list(validation, issues);
    exportButton.disabled = Boolean(issues.length);
  };
  const redraw = () => renderDraft(target, draft, download);
  const profile = draft.profile;
  const girl = bookKey(profile.girl_playbook), frame = bookKey(profile.frame_playbook);
  /** @type {Choices} */
  const creation = draft.creation ?? {};
  const updateCreation = (key, value) => {
    draft.creation = creation;
    creation[key] = value;
    changes();
  };
  const form = section(target, "Creation draft");
  form.append(element("p", "Export this personnel draft for private intake preview, confirmation, and review."));
  text(form, "Callsign", profile.callsign, value => { profile.callsign = value; changes(); });
  picker(form, "Girl playbook", girl, Object.entries(catalog.girl_types), value => { profile.girl_playbook = value ?? ""; redraw(); });
  picker(form, "Frame playbook", frame, Object.entries(catalog.frame_types), value => { profile.frame_playbook = value ?? ""; redraw(); });
  if (catalog.playbooks[girl]?.identities.length) {
    form.append(element("p", `Starting Identity references · ${catalog.playbooks[girl].identities.join(", ")}`));
  }
  const appearance = section(target, "Appearance");
  for (const [key, title] of [["frame_name", "Frame name"], ["girl_appearance", "Girl appearance"], ["frame_appearance", "Frame appearance"]]) {
    text(appearance, title, creation[key], value => updateCreation(key, value), key !== "frame_name");
  }
  function assetFields(key, title, names) {
    const items = creation[key] ?? [];
    collection(target, title, items, () => {
      const name = names.find(name => !items.some(item => item.name === name));
      updateCreation(key, [...items, {name:name ?? ""}]);
    }, index => updateCreation(key, items.filter((_, i) => i !== index)), (row, item) => {
      picker(row, title + " name", item.name, named(names), value => { item.name = value ?? ""; redraw(); });
      text(row, title + " description", item.description, value => { item.description = value; changes(); }, true);
    }, redraw);
  }
  if (girl && (girl !== "BONDED" || creation.girl_assets?.length)) assetFields("girl_assets", "Girl Asset", catalog.playbooks[girl]?.assets ?? []);
  if (frame) assetFields("frame_assets", "Frame Asset", catalog.playbooks[frame]?.assets ?? []);
  if (girl === "BONDED" || creation.pair_asset_descriptions?.length) assetFields("pair_asset_descriptions", "Pair Asset description", catalog.playbooks.BONDED.assets);
  if (girl === "MOCKINGBIRD" || creation.void_asset != null) {
    picker(appearance, "Void-altered Girl Asset", creation.void_asset, named((creation.girl_assets ?? []).map(asset => asset.name)), value => updateCreation("void_asset", value));
  }
  const npcRoles = npcRoleText(girl);
  if (girl) {
    const npcs = creation.npc_bonds ?? [];
    collection(target, "NPC Bond", npcs, () => {
      const slot = npcRoles.findIndex((_, slot) => !npcs.some(npc => npc.slot === slot));
      updateCreation("npc_bonds", [...npcs, {slot:Math.max(0, slot)}]);
    }, index => updateCreation("npc_bonds", npcs.filter((_, i) => i !== index)), (row, npc) => {
      picker(row, "NPC Bond role", npc.slot, numbered(npcRoles), value => { npc.slot = value; redraw(); });
      text(row, "NPC name", npc.name, value => { npc.name = value; changes(); });
      text(row, "Feelings about the NPC", npc.feelings, value => { npc.feelings = value; changes(); }, true);
    }, redraw);
  }
  renderPlaybookFields(target, form, girl, frame, creation, updateCreation, changes, redraw);
  const notes = section(target, "Personal notes");
  const noteMode = typeof profile.notes === "string" ? "replace" : "preserve";
  picker(notes, "Notes on engine import", noteMode, [["preserve", "Preserve existing engine notes"], ["replace", "Replace or clear engine notes"]], mode => {
    if (mode === "preserve") delete profile.notes;
    else if (mode === "replace" && typeof profile.notes !== "string") profile.notes = "";
    redraw();
  }).options[0].disabled = true;
  if (noteMode === "replace") {
    text(notes, "Personal notes to include", profile.notes, value => { profile.notes = value; changes(); }, true);
    notes.append(element("p", "An empty field explicitly clears existing engine notes. This text is included in the download."));
  }
  const feedback = section(target, "Draft status");
  const validation = element("div");
  validation.setAttribute("role", "status");
  const exportButton = action("Export creation JSON", () => {
    try {
      const output = createDraft(profile, creation);
      if (!Object.hasOwn(draft, "creation")) delete output.creation;
      download(serializeDraft(output), "harpyengine-character-draft.json", "application/json;charset=utf-8");
    } catch (error) {
      validation.replaceChildren(element("p", error.message + ". Check the profile fields and file size."));
    }
  });
  // Keep the status heading separate from the dynamic list and validation region.
  const status = element("div");
  feedback.append(status, validation, exportButton);
  changes();
}
