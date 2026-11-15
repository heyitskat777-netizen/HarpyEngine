/** Portable file codec. Engine validation and live authority remain server-side. */
export const DRAFT_FORMAT = "harpyengine.character-draft";
export const SHEET_FORMAT = "harpyengine.character-sheet";
export const SCHEMA_VERSION = 1;
export const MAX_DOCUMENT_BYTES = 256 * 1024;

const profileKeys = new Set(["callsign", "girl_playbook", "frame_playbook", "notes"]);
const choiceKeys = new Set([
  "girl_assets", "frame_assets", "void_asset", "frame_name", "girl_appearance",
  "frame_appearance", "pair_asset_descriptions", "npc_bonds", "dna_basis", "fanbase", "girl_details",
]);
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
const invalid = () => { throw new Error("Invalid HarpyEngine creation document"); };
const finite = (value, seen = new WeakSet()) => {
  if (typeof value === "number" && !Number.isFinite(value)) invalid();
  if (value === null || typeof value !== "object") return;
  if (seen.has(value)) invalid();
  seen.add(value);
  for (const child of Object.values(value)) finite(child, seen);
  seen.delete(value);
};

export function assertDraftEnvelope(document) {
  if (!object(document) || document.format !== DRAFT_FORMAT || document.schema_version !== 1) invalid();
  if (Object.keys(document).some(key => !["format", "schema_version", "profile", "creation"].includes(key))) invalid();
  if (!object(document.profile) || Object.keys(document.profile).some(key => !profileKeys.has(key))) invalid();
  for (const key of ["callsign", "girl_playbook", "frame_playbook"]) {
    const value = document.profile[key];
    if (typeof value !== "string" || !value.trim() || /[\u0000-\u001f\u007f]/u.test(value)) invalid();
    if (Array.from(value).length > (key === "callsign" ? 32 : 60)) invalid();
  }
  const notes = document.profile.notes;
  if (notes != null && (typeof notes !== "string" || Array.from(notes).length > 1000)) invalid();
  if (document.creation !== undefined && (!object(document.creation) || Object.keys(document.creation).some(key => !choiceKeys.has(key)))) invalid();
  finite(document);
  return document;
}

export function createDraft(profile, creation = {}) {
  return assertDraftEnvelope({ format: DRAFT_FORMAT, schema_version: 1, profile: { ...profile }, creation: { ...creation } });
}

export function parseDraftJSON(text) {
  if (typeof text !== "string" || new TextEncoder().encode(text).length > MAX_DOCUMENT_BYTES) invalid();
  let document;
  try { document = JSON.parse(text); } catch { invalid(); }
  return assertDraftEnvelope(document);
}

export function serializeDraft(document) {
  assertDraftEnvelope(document);
  const text = JSON.stringify(document, null, 2) + "\n";
  if (new TextEncoder().encode(text).length > MAX_DOCUMENT_BYTES) invalid();
  return text;
}
