export interface AssetChoice { name: string; description?: string }
export interface NpcBond { slot: number; name?: string; feelings?: string }
export interface Fanbase {
  demographics?: string[]; demanded?: string[]; rejected?: string[];
  custom_demographic?: string; custom_quality_1?: string; custom_quality_2?: string;
}
export interface GirlDetails {
  own_standard?: { slot: number; custom?: string } | null;
  maxims?: number[];
  investors?: { npc_slot: number; desires: { slots: number[] } }[];
}
export interface PortableProfile {
  callsign: string; girl_playbook: string; frame_playbook: string;
  /** Omit/null to preserve existing private notes; empty string explicitly clears. */
  notes?: string | null;
}
export interface PortableChoices {
  girl_assets?: AssetChoice[]; frame_assets?: AssetChoice[];
  void_asset?: string | null; frame_name?: string;
  girl_appearance?: string; frame_appearance?: string;
  pair_asset_descriptions?: AssetChoice[]; npc_bonds?: NpcBond[];
  dna_basis?: string; fanbase?: Fanbase | null; girl_details?: GirlDetails | null;
}
export interface CharacterDraftDocument {
  format: "harpyengine.character-draft"; schema_version: 1;
  profile: PortableProfile; creation?: PortableChoices;
}
export interface CharacterSheetDocument {
  format: "harpyengine.character-sheet"; schema_version: 1;
  engine_version: string; audience: "owner" | "public";
  owner_id: string; character_id?: string | null; revision: number;
  display_name?: string; members?: Record<string, string>;
  sheet: Record<string, unknown>; rules_status: "RULES_SUBSET";
}
export const DRAFT_FORMAT: "harpyengine.character-draft";
export const SHEET_FORMAT: "harpyengine.character-sheet";
export const SCHEMA_VERSION: 1;
export const MAX_DOCUMENT_BYTES: number;
/** Structural browser checks only; use schema and engine for semantic validation. */
export function assertDraftEnvelope(document: unknown): CharacterDraftDocument;
export function createDraft(profile: PortableProfile, creation?: PortableChoices): CharacterDraftDocument;
export function parseDraftJSON(text: string): CharacterDraftDocument;
export function serializeDraft(document: CharacterDraftDocument): string;
