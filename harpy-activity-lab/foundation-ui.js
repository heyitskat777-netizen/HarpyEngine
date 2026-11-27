import {closePopup, popupAction} from "/popup-ui.js";
import {createShiftHandover} from "/shift-handover.js";

function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function button(label, action, className) {
  const item = element("button", label, className);
  item.type = "button";
  item.addEventListener("click", action);
  return item;
}

export function renderRecordMetadata(target, {location, state, owner, room = false}) {
  const values = [
    ["Location",location,room && "room-location"],
    ["Record state",state,room && "room-access"],
    ["Action owner",owner],
  ];
  const visible = values.filter(([,value]) => value);
  target.hidden = !visible.length;
  const signature = JSON.stringify(visible);
  if (target.dataset.record === signature) return;
  target.dataset.record = signature;
  target.replaceChildren(...visible.map(([label,value,id]) => {
    const row = element("div");
    const detail = element("dd", value, label === "Record state" ? "record-state" : undefined);
    if (id) detail.id = id;
    row.append(element("dt", label), detail);
    return row;
  }));
}

function sceneEndTime(archivedAt) {
  const date = new Date(archivedAt * 1000);
  const time = element("time", "Ended " + date.toLocaleString(undefined, {
    year:"numeric", month:"short", day:"numeric", hour:"numeric", minute:"2-digit", timeZoneName:"short",
  }), "scene-end-time");
  time.dateTime = date.toISOString();
  return time;
}

function locationName(directory, room) {
  return room.location_name ?? directory.locations.find(place => place.id === room.location)?.name ?? "Unassigned";
}

function sceneLocationGroups(directory, rooms) {
  const groups = new Map();
  for (const room of rooms) {
    const id = room.location ?? null;
    if (!groups.has(id)) groups.set(id, {id, name:locationName(directory, room), rooms:[]});
    groups.get(id).rooms.push(room);
  }
  return [...groups.values()].sort((left, right) => {
    if (left.id === null) return 1;
    if (right.id === null) return -1;
    return left.name.localeCompare(right.name);
  });
}

export function playName(id) {
  return {check_sensors:"Check Sensors", keep_your_head:"Keep Your Head",
    flirt_followthrough:"Flirt Follow-through", go_off_duty:"Go Off-Duty", void_observation:"Void Observation",
    put_someone_beneath_you:"Put Someone Beneath You", dive_deep:"Dive Deep", all_out_assault:"All-Out Assault",
    go_for_the_core:"Go for the Core", living_battery:"Living Battery",
    receive_orders:"Receive Orders", disobey_orders:"Disobey Orders",
    mockingbird_person:"Bad at Being a Person", reject_tag:"Reject Tag",
    changeling_blank_slate:"Blank Slate", changeling_body_of_clay:"Body of Clay", red_queen_memory:"Memory Extraction"}[id]
    ?? id.replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
}

export function decisionName(kind) {
  return {tag_window:"Tag window", actor_keep:"Pilot response", handler_keep:"Handler ruling",
    actor_sensors:"Sensor questions", handler_sensors:"Sensor answers", actor_engage:"Engage maneuvers",
    target_flirt:"Pilot response", followthrough_confirm:"Follow-through response",
    order_response:"Answer the order", order_disobey:"Roll Disobey Orders",
    actor_disobey:"Refusal outcome", handler_disobey:"Handler refusal ruling"}[kind]
    ?? kind.replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
}

export function focusDecision(root, id) {
  if (!id) return false;
  const link = root.querySelector(`[data-play-decisions~="${CSS.escape(id)}"]`);
  if (link) link.click();
  const container = link ? document.getElementById("scene-action-fields") : root;
  const record = container?.querySelector(`[data-scene-choice="${CSS.escape(id)}"]`);
  if (!record) return false;
  const details = record.closest("details[data-play]");
  if (details) revealPlay(details);
  const control = record.querySelector(":is(input,select,textarea,button):not(:disabled)");
  control?.focus();
  return Boolean(control);
}

function readFile(panel, rows) {
  const list = element("dl", undefined, "data-list");
  for (const [label, value] of rows) {
    const detail = element("dd");
    detail.append(value ?? "Unassigned");
    list.append(element("dt", label), detail);
  }
  panel.append(list);
}

const playSymbols = {
  engage:"⚔", all_out_assault:"✦", go_for_the_core:"⊙", check_sensors:"⌁",
  keep_your_head:"◉", flirt:"♡", receive_orders:"⌃", disobey_orders:"↶", dive_deep:"⋈",
};

export function playCard(play, caption, activate) {
  const card = activate ? button("", activate, "play-card") : element("span", undefined, "play-card");
  card.dataset.group = play.group ?? (["engage", "all_out_assault", "go_for_the_core"].includes(play.id) ? "combat" : "basic");
  if (activate) card.setAttribute("aria-label", play.label);
  const icon = element("span", playSymbols[play.id] ?? (play.group === "frame" ? "▣" : "◇"), "play-icon");
  icon.setAttribute("aria-hidden", "true");
  const copy = element("span");
  copy.append(element("strong", play.label));
  if (caption) copy.append(element("small", caption));
  card.append(icon, copy);
  return card;
}

const playCategories = [["talk", "Talk", "◫"], ["scan", "Scan", "⌁"],
  ["fight", "Fight", "⚔"], ["recover", "Recover", "◉"]];
export function playRail(entries, preferred) {
  const rail = element("div", undefined, "play-rail");
  const register = element("div", undefined, "play-rail-register");
  const groups = new Map(playCategories.map(([id]) => [id, []]));
  for (const {play, row} of entries) {
    const id = groups.has(play.category) ? play.category : "other";
    if (!groups.has(id)) groups.set(id, []);
    groups.get(id).push(row);
  }
  const categories = groups.has("other") ? [...playCategories, ["other", "Other", "◇"]] : playCategories;
  for (const [category, title, symbol] of categories) {
    const rows = groups.get(category);
    if (!rows.length) continue;
    const heading = element("h4", undefined, "play-category-heading");
    const icon = element("span", symbol, "play-category-icon");
    icon.setAttribute("aria-hidden", "true");
    heading.append(icon, document.createTextNode(title));
    const panel = element("div", undefined, "play-rail-list");
    panel.dataset.playPanel = category;
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", title + " Plays");
    panel.append(heading,...rows);
    register.append(panel);
  }
  rail.append(register);
  return rail;
}

export function sheetPlayCaption(play, caption) {
  const source = {girl:"Girl playbook", frame:"Frame playbook"}[play.group];
  return [source, caption].filter(Boolean).join(" · ");
}

function revealPlay(details) {
  const panel = details.closest("[data-play-panel]");
  if (panel?.hidden) {
    panel.closest(".play-rail").querySelector(`[data-play-category="${panel.dataset.playPanel}"]`)?.click();
  }
  if (details.matches("details")) details.open = true;
}

function textField(label, maxLength, value = "") {
  const wrapper = element("label", label, "field");
  const input = element("input");
  input.required = true;
  input.maxLength = maxLength;
  input.value = value;
  wrapper.append(input);
  return {wrapper, input};
}

const facilities = await fetch("/facility-plans.json").then(response => {
  if (!response.ok) throw new Error("Could not load the facility plans.");
  return response.json();
});

export const terrainNames = {w:"Wall", d:"Doorway", c:"Cover", ".":"Open floor"};

export function markTerrain(tile, row, x) {
  const type = row[x];
  tile.classList.add("terrain");
  tile.dataset.tile = type;
  if (type === "w" && row[x + 1] === "w") tile.classList.add("wall-join-next");
  if (type === "w" && row[x - 1] === "w") tile.classList.add("wall-join-previous");
  if (type === "d" && (row[x - 1] === "w" || row[x + 1] === "w")) tile.dataset.threshold = "horizontal";
}

export function facilityLabels(rooms) {
  return rooms.map(([name, area]) => {
    const marker = element("span", name, "map-room-label");
    marker.style.gridArea = area;
    return marker;
  });
}
const signs = [
  "Record all deviations before shift handover.",
  "Pilot classification determines reporting obligations.",
  "Equipment discrepancies require a signed exception.",
  "Unlogged overtime remains chargeable to the cadre.",
  "Use its issued callsign in every pilot record.",
  "An unresolved discrepancy rolls forward to the next shift.",
  "A verbal exception must be entered in the ledger.",
  "Authorization expires at the end of the assigned watch.",
  "One incident per report. Attach further incidents separately.",
  "Pilot classification confers no civilian personnel benefits.",
  "Training hours remain chargeable to the cadre budget.",
  "Personnel movements require an entry in the duty register.",
  "A delayed acknowledgement does not extend a deadline.",
];

const folderNotices = {
  profile:"Use its issued callsign in every pilot record.",
  scenes:"Record all deviations before shift handover.",
  battlefield:"Report equipment damage before leaving the field.",
  missions:"File mission receipts before requesting reassignment.",
  cadre:"Pilot classification determines reporting obligations.",
  frame:"Log equipment variances before handover.",
};

export function foundationUI(send, readTranscript, showBattlefield, battlefield, renderRoomPlays, refreshPlayer, artwork, renderPilotBonds, resumeEnrollment, openSheetReset, requestCancellation) {
  let openPortrayal;
  let openCampaignSetup;
  let setDossierVisible;
  let dossierVisible = false;
  const folderBar = document.querySelector(".folders");
  const folders = [...folderBar.querySelectorAll("[data-folder]")];
  function revealActiveFolder() {
    const active = folderBar.querySelector('[aria-current="page"]:not([hidden])');
    if (!active) return;
    const tab = active.getBoundingClientRect();
    const bar = folderBar.getBoundingClientRect();
    const delta = tab.left < bar.left ? tab.left - bar.left : Math.max(0, tab.right - bar.right);
    if (delta) folderBar.scrollLeft += delta;
  }
  new ResizeObserver(revealActiveFolder).observe(folderBar);
  const panes = [...document.querySelectorAll("[data-pane]")];
  const back = document.getElementById("back");
  const directory = document.getElementById("directory");
  const directoryHeader = element("div");
  const directoryRooms = element("div");
  const archivePanel = element("div");
  archivePanel.hidden = true;
  const locationDecks = new Map();
  const recordArtworks = new Map();
  const archiveLabel = element("label", "Search archive", "field archive-search");
  const archiveSearch = element("input");
  archiveSearch.type = "search";
  archiveSearch.placeholder = "Scene name, location, or pilot";
  const archiveResults = element("div");
  archiveLabel.append(archiveSearch);
  archivePanel.append(archiveLabel, archiveResults);
  directory.append(directoryHeader, directoryRooms, archivePanel);
  const deskContext = document.getElementById("desk-context");
  const roomPane = document.getElementById("room-pane");
  const roomArtwork = document.getElementById("room-artwork");
  let sceneArtwork;
  const setup = document.getElementById("setup");
  const offDutyDialog = document.getElementById("off-duty-panel");
  const punishmentDialog = document.getElementById("punishment-work");
  document.getElementById("open-off-duty").addEventListener("click",() => offDutyDialog.showModal());
  document.getElementById("open-punishment-work").addEventListener("click",() => punishmentDialog.showModal());
  const invite = document.getElementById("invite-dialog");
  const startScene = document.getElementById("start-scene-dialog");
  const sceneAccess = document.getElementById("scene-access-dialog");
  const endScene = document.getElementById("end-scene-dialog");
  const shareIntel = document.getElementById("share-intel-dialog");
  const intelStatus = document.getElementById("scene-intel-status");
  const playDialog = document.getElementById("profile-play-dialog");
  const playDialogTitle = document.getElementById("profile-play-title");
  const playDialogContent = document.getElementById("profile-play-context");
  const playDialogState = document.getElementById("profile-play-state");
  const scenePlayPanel = document.getElementById("scene-play-panel");
  const scenePlayTitle = document.getElementById("scene-play-title");
  const scenePlayOptions = document.getElementById("scene-play-options");
  const scenePlayFeedback = document.getElementById("scene-play-feedback");
  const enterScene = document.getElementById("enter-scene-controls");
  const sceneCommands = document.getElementById("scene-command-rail");
  const emptyCategory = element("p", "No Plays are available in this category.", "terminal-feedback");
  scenePlayOptions.after(emptyCategory);
  emptyCategory.hidden = true;
  let selectedCategory;
  for (const [id, label, symbol] of playCategories) {
    const command = dialogButton(label, () => openRoomPlays(view.room, "", false, null, id));
    const icon = element("span", symbol, "play-category-icon");
    icon.setAttribute("aria-hidden", "true");
    command.prepend(icon);
    command.dataset.playCategory = id;
    sceneCommands.append(command);
  }
  const otherPlays = dialogButton("Other", () => openRoomPlays(view.room, "", false, null, "other"));
  otherPlays.hidden = true;
  sceneCommands.append(otherPlays);
  const locationsToggle = document.getElementById("locations-toggle");
  const communicationsToggle = document.getElementById("communications-toggle");
  const communicationsDesk = document.getElementById("communications-desk");
  for (const [trigger,content,id] of [
    [locationsToggle,document.getElementById("location-list"),"mobile-locations"],
    [communicationsToggle,document.getElementById("communications-scene-list"),"communications-desk"],
  ]) {
    const dialog = document.getElementById(id);
    trigger.addEventListener("click",() => dialog.showModal());
    dialog.addEventListener("close",() => {
      if (!document.querySelector("dialog[open]")) trigger.focus();
    });
    content.addEventListener("click",event => {
      if (event.target.closest("button") && dialog.open) dialog.close();
    });
  }
  communicationsToggle.addEventListener("click", () => refreshPlayer().catch(() => {}));
  const trail = [];
  const initialView = {folder:"scenes", location:"hangar", mode:"locations", room:null, pilot:null, tacticalPilot:null};
  let view = {...initialView};
  let lastRoom;
  let player;
  let tacticalRoster;
  let notice = 0;
  let noticeFolder;
  let transcriptRoom;
  let transcriptArchived = false;
  let transcriptFetch = 0;
  let transcriptSnapshot;
  let sceneCast = [];
  let transcriptTarget;
  let pickerRevision = 0;
  let playSelection = {room:null};
  let playProjection;
  const sceneDrafts = new Map();
  let draftIdentity;
  const handover = createShiftHandover(document.querySelector('[data-pane="handover"]'), {
    openScene:openHandoverScene, artwork,
  });

  function sceneDraft(id) {
    if (!sceneDrafts.has(id)) sceneDrafts.set(id,{text:"",intent:null,pending:false});
    return sceneDrafts.get(id);
  }

  function navigate(change) {
    trail.push(view);
    view = {...view, ...change};
    render();
  }

  back.addEventListener("click", () => {
    if (trail.length) view = trail.pop();
    render();
  });

  for (const folder of folders) folder.addEventListener("click", () => {
    const name = folder.dataset.folder;
    if (name === "scenes") {
      const resume = player?.directory?.rooms.find(room => room.id === lastRoom && room.joined && room.archived_at == null);
      navigate({folder:name, mode:"locations", room:resume?.id ?? null, tacticalPilot:null});
    }
    else if (name === "profile") navigate({folder:name, pilot:null, tacticalPilot:null});
    else if (name === "frame") navigate({folder:name, pilot:null, tacticalPilot:null});
    else navigate({folder:name, tacticalPilot:null});
    if (name === "campaign-setup") openCampaignSetup?.();
  });

  function nextNotice() {
    notice = (notice + 1) % signs.length;
    showNotice(signs[notice]);
  }

  function showNotice(text) {
    document.getElementById("notice").textContent = text;
  }

  document.getElementById("next-notice").addEventListener("click", nextNotice);

  function selectedRoom() {
    return player?.directory?.rooms.find(room => room.id === view.room);
  }

  function syncPlaySelection(room = null) {
    if (room === playSelection.room) return;
    const selection = {room};
    playSelection = selection;
    playProjection = room ? refreshPlayer().catch(error => {
      if (selection !== playSelection) return;
      scenePlayFeedback.textContent = error.message;
      scenePlayFeedback.hidden = false;
    }) : undefined;
  }

  function viewingScene(room) {
    return view.folder === "scenes" && view.room === room;
  }

  function dialogButton(label, action, className) {
    const control = button(label, action, className);
    control.setAttribute("aria-haspopup", "dialog");
    return control;
  }

  function cancellationControl(source, room, caption = "Cancel pending Play") {
    if (!source.can_cancel) {
      return source.can_request ? dialogButton("Request cancellation",() => requestCancellation(source,room)) : null;
    }
    const key = "cancel-play:" + source.id;
    const form = element("form");
    form.append(element("p",playName(source.play) + " · " + room.name),
      element("p","The original roll stays on file. HarpyEngine will withdraw the pending choices and release this Play."));
    const label = element("label");
    const confirmed = element("input");
    confirmed.type = "checkbox";
    confirmed.required = true;
    label.append(confirmed,document.createTextNode(" I confirm cancellation of this pending Play."));
    const submit = element("button","Confirm cancellation","primary");
    const result = element("p");
    result.setAttribute("role","status");
    form.append(label,submit,result);
    const requestKey = crypto.randomUUID();
    form.addEventListener("submit",async event => {
      event.preventDefault();
      submit.disabled = true;
      try {
        await send("scene-cancel",{room:room.id,id:source.id,confirmed:confirmed.checked},requestKey);
        closePopup(key);
      } catch (error) {
        result.textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
    return popupAction(caption,form,key);
  }

  function openSceneAccess() {
    const room = selectedRoom();
    if (!room) return;
    const panel = document.getElementById("scene-access-record");
    panel.replaceChildren(element("h3", room.name));
    readFile(panel, [
      ["Membership", room.joined ? "Participant" : "Not joined"],
      ["Transcript", room.archived_at != null ? "Archived · Read-only" : room.joined ? "Participant transcript" : "Join for participant access"],
      ["Room invitation", room.can_invite ? "Available" : "Unavailable"],
    ]);
    sceneAccess.showModal();
  }

  function openSceneInvitation(record) {
    document.getElementById("invite-title").textContent = "Scene invitation";
    const content = document.getElementById("invite-content");
    const result = element("p");
    result.setAttribute("role","status");
    const controls = ["accept","decline"].map(decision => button(
      decision === "accept" ? "Accept invitation" : "Decline invitation",
      async () => {
        for (const control of controls) control.disabled = true;
        try {
          const saved = await send("scene-invite-decision", {id:record.id,decision});
          invite.close();
          if (saved.decision === "accept") {
            const room = player?.directory?.rooms.find(item => item.id === saved.room);
            if (room) openDirectoryRoom(room);
          }
        } catch (error) {
          result.textContent = error.message;
          for (const control of controls) control.disabled = false;
        }
      },
      decision === "accept" ? "primary" : undefined,
    ));
    const actions = element("div", undefined, "actions");
    actions.append(...controls);
    content.replaceChildren(element("p", record.name),actions,result);
    if (!invite.open) invite.showModal();
  }

  function openDirectoryRoom(room) {
    navigate({
      folder:"scenes", mode:room.archived_at != null ? "archive" : "locations",
      location:room.location ?? null, room:room.id, tacticalPilot:null,
    });
  }

  function sceneInvitation(room) {
    return player?.scene_invites?.find(record => record.room === room.id);
  }

  function sceneDirectoryState(room, invitation) {
    if (room.archived_at != null) return "Archived";
    if (room.joined) return room.play_active ? "Channel active" : "Joined";
    if (invitation) return "Invited";
    return room.kind === "lobby" ? "Invitation required" : "Admission open";
  }

  function openRelayPlays(name = "", focusForm = false) {
    openRoomPlays("relay", name, focusForm);
  }

  function filterScenePlays() {
    let matching = false;
    const categories = scenePlayOptions.querySelectorAll("[data-play-panel]");
    for (const group of categories) {
      group.hidden = Boolean(selectedCategory && group.dataset.playPanel !== selectedCategory);
      matching ||= !group.hidden;
    }
    emptyCategory.hidden = scenePlayOptions.hidden || !selectedCategory || matching;
    otherPlays.hidden = !scenePlayOptions.querySelector('[data-play-panel="other"]');
  }

  function showScenePlayPicker(room, category) {
    selectedCategory = category;
    const label = playCategories.find(([id]) => id === category)?.[1];
    scenePlayTitle.textContent = label ? label + " Plays" : "Scene Plays";
    document.getElementById("scene-play-location").textContent = room.name;
    filterScenePlays();
    if (!scenePlayPanel.open) scenePlayPanel.showModal();
    scenePlayTitle.focus({preventScroll:true});
  }

  async function openRoomPlays(roomId, name = "", focusForm = false, source = null, category) {
    const room = player?.directory?.rooms.find(item => item.id === roomId);
    if (!room || room.archived_at != null) return;
    if (!viewingScene(roomId)) {
      navigate({folder:"scenes", room:roomId});
    }
    const selection = playSelection;
    if (player.active_scene?.id !== roomId) await playProjection;
    if (!viewingScene(roomId) || selection !== playSelection) return;
    if (player.active_scene?.id !== roomId) {
      if (room.joined) showScenePlayPicker(room, category);
      else setup.querySelector("button")?.focus();
      return;
    }
    const requestedPlay = name.toLowerCase().replace(/[ _-]+/g, "_");
    const id = requestedPlay === "flirt_followthrough" ? "flirt" : requestedPlay;
    const choice = [...scenePlayOptions.querySelectorAll("[data-play]")]
      .find(row => row.dataset.play === id);
    scenePlayFeedback.textContent = id && !choice ? "That Play is unavailable in this scene." : "";
    scenePlayFeedback.hidden = !scenePlayFeedback.textContent;
    if (choice?.matches("button")) {
      choice.click();
      const fields = document.getElementById("scene-action-fields");
      const target = fields.querySelector("select[name=target]");
      if (source && target && [...target.options].some(option => option.value === source)) {
        target.value = source;
        fields.querySelector("textarea, input[name=context]")?.focus();
      } else if (focusForm) {
        fields.querySelector("form :is(select, input, textarea, button)")?.focus();
      }
      return;
    }
    showScenePlayPicker(room, category);
  }

  function openHandoverScene(room, target = {}) {
    const scene = player?.directory?.rooms.find(item => item.id === room && item.joined && item.archived_at == null);
    if (!scene) return;
    transcriptTarget = target.entry != null || target.receipt
      ? {room, entry:target.entry, receipt:target.receipt}
      : undefined;
    navigate({folder:"scenes", mode:"locations", room, location:scene.location, tacticalPilot:null});
  }

  async function reviewSceneChoice(room, choice) {
    if (!choice || player?.stage !== "active" || !viewingScene(room)) return;
    const selection = playSelection;
    if (player.active_scene?.id !== room) await playProjection;
    if (!viewingScene(room) || selection !== playSelection) return;
    if (player.active_scene?.id === room && focusDecision(scenePlayOptions, choice)) return;
    if (!scenePlayFeedback.hidden) return;
    scenePlayFeedback.textContent = player.active_scene?.id === room
      ? "This response is no longer available."
      : "Enter this scene or synchronize the terminal to retrieve its Plays.";
    scenePlayFeedback.hidden = false;
    const scene = selectedRoom();
    if (scene) showScenePlayPicker(scene);
  }

  function openSceneReceipt(room, receipt, choice) {
    if (player?.stage === "handler" && choice) {
      if (view.folder !== "scenes") navigate({folder:"scenes", tacticalPilot:null});
      focusDecision(document.getElementById("handler-choices"), choice);
      return;
    }
    const scene = player?.directory?.rooms.find(item => item.id === room && item.joined);
    if (!scene) return;
    const archived = scene.archived_at != null;
    const mode = archived ? "archive" : view.mode;
    transcriptTarget = {room, receipt};
    if (view.folder !== "scenes" || view.room !== room || view.mode !== mode) navigate({folder:"scenes", mode, room});
    else render();
    if (!archived && choice) reviewSceneChoice(room, choice);
  }

  function playLocation(label, details, radio) {
    const row = element("li", undefined, "record-row");
    const copy = element("div");
    const name = radio ? element("label", undefined, "play-destination-choice") : element("strong");
    if (radio) name.append(radio);
    name.append(label);
    copy.append(name, ...details.map(detail => element("p", detail)));
    row.append(copy);
    return row;
  }

  async function pickPlayScene(pilot, play, remembered, source = null) {
    const revision = ++pickerRevision;
    playDialogTitle.textContent = play.label;
    playDialogState.textContent = "CHECKING AVAILABILITY";
    playDialogContent.replaceChildren();
    if (play.trigger) playDialogContent.append(element("p", play.trigger));
    if (!playDialog.open) playDialog.showModal();
    if (!pilot.own) {
      playDialogState.textContent = "OWNER REQUIRED";
      playDialogContent.append(element("p", "Only this pilot’s player can start its Plays."));
      return;
    }

    playDialogContent.append(element("h3", "Which scene is this Play for?"));
    const locations = element("ul", undefined, "records");
    const feedback = element("p", undefined, "terminal-feedback");
    feedback.setAttribute("role", "status");
    const actions = element("div", undefined, "actions terminal-actions");
    const destinations = new Map();
    let selected;
    const confirm = button("Open Play", async () => {
      if (!selected) return;
      await selected.open();
    }, "primary");
    confirm.disabled = true;
    function choose(key) {
      selected = destinations.get(key);
      if (!selected) return;
      selected.radio.checked = true;
      confirm.disabled = false;
      confirm.textContent = selected.actionLabel;
      playDialogState.textContent = "DESTINATION SELECTED";
    }
    function addDestination(key, label, details, actionLabel, open) {
      let radio;
      if (actionLabel) {
        radio = element("input");
        radio.type = "radio";
        radio.name = "play-destination";
        radio.addEventListener("change", () => choose(key));
        destinations.set(key, {key, radio, actionLabel, open});
      }
      const row = playLocation(label, details, radio);
      locations.append(row);
      return row;
    }
    const refresh = button("Refresh scene availability", async () => {
      refresh.disabled = true;
      playDialogState.textContent = "CHECKING AVAILABILITY";
      try {
        await refreshPlayer();
        if (!playDialog.open || revision !== pickerRevision) return;
        const latestPilot = player.cadre?.find(item => item.id === pilot.id);
        const latestPlay = source && latestPilot ? play : latestPilot?.plays?.find(item => item.id === play.id);
        if (latestPlay) pickPlayScene(latestPilot, latestPlay, selected?.key, source);
        else {
          confirm.disabled = true;
          playDialogState.textContent = "PLAY UNAVAILABLE";
          feedback.textContent = "This Play is no longer on your sheet.";
        }
      } catch (error) {
        feedback.textContent = error.message;
        playDialogState.textContent = "REFRESH FAILED";
      } finally {
        refresh.disabled = false;
      }
    });
    actions.append(refresh, confirm);
    playDialogContent.append(locations, feedback, actions);
    for (const room of player?.directory?.rooms ?? []) {
      if (!room.play_availability) continue;
      const option = room.play_availability[play.id];
      if (source && !option?.sources?.includes(source)) continue;
      const issues = option?.reasons.map(reason => reason.message)
        ?? [play.blocked ? "This Play is blocked on your sheet." : "The Activity does not have controls to run this Play in a scene yet."];
      const detail = room.play_active ? "Active scene" : "Enter this scene to continue";
      const label = !option || option.state === "unavailable" ? null : option.state === "resume"
        ? "Open pending Play" : room.play_active ? "Continue in " + room.name
        : "Enter scene and open Play";
      const needsPilot = option?.reasons.some(reason => reason.code === "needs_pilot");
      if (needsPilot && !room.can_invite) issues.push("The scene host can send an invitation.");
      const row = addDestination(room.id, room.name, issues.length ? issues : [detail], label, async () => {
          if (!room.play_active) {
            const controls = [...playDialog.querySelectorAll(":is(button,input):not(:disabled)")];
            const hold = closeEvent => closeEvent.preventDefault();
            playDialog.addEventListener("cancel", hold);
            playDialogState.textContent = "OPENING SCENE";
            for (const control of controls) control.disabled = true;
            try {
              await send("enter-scene", {room:room.id,play:play.id});
            } catch (error) {
              if (!playDialog.open || revision !== pickerRevision) return;
              playDialogState.textContent = "COULD NOT OPEN SCENE";
              feedback.textContent = error.message;
              return;
            } finally {
              for (const control of controls) control.disabled = false;
              playDialog.removeEventListener("cancel", hold);
            }
          }
          if (!playDialog.open || revision !== pickerRevision) return;
          playDialog.close();
          await openRoomPlays(room.id, play.id, true, source);
      });
      if (needsPilot && room.can_invite) row.append(button("Invite another pilot", () => showInvite(room.id, room.name, true)));
    }
    playDialogState.textContent = destinations.size ? "SELECT DESTINATION" : "CHECKING AVAILABILITY";
    const preferred = [remembered, lastRoom, player.active_scene?.id].find(room => destinations.has(room));
    if (destinations.has(preferred)) choose(preferred);
    if (source) {
      if (!selected && destinations.size === 1) choose(destinations.keys().next().value);
      if (!selected) playDialogState.textContent = destinations.size ? "SELECT DESTINATION" : "NO ELIGIBLE DESTINATION";
      if (!locations.children.length) feedback.textContent = "HarpyEngine found no scene for this assignment. Refresh to check its current state.";
      return;
    }
    try {
      const drill = await battlefield.view();
      if (!playDialog.open || revision !== pickerRevision) return;
      if (drill) {
        const ready = drill.actions.some(item => item.id === play.id);
        const detail = ready ? (drill.encounter ? "Current Battlefield encounter" : "Separate Battlefield test encounter")
          : play.blocked ? "This Play is blocked on your sheet."
          : drill.busy ? "Resolve the pending Battlefield Play first."
          : play.id === "go_for_the_core" && drill.core_exposure_targets?.length ? "The Core must be exposed."
          : "This Play is unavailable in the current Battlefield encounter.";
        addDestination("battlefield", drill.title, [detail],
          ready ? "Continue in Battlefield" : null, () => {
            playDialog.close();
            navigate({folder:"battlefield"});
            battlefield.open(play.id);
          });
      }
      if (!selected && destinations.has(remembered)) choose(remembered);
      else if (!selected && destinations.size === 1) choose(destinations.keys().next().value);
      if (!selected) playDialogState.textContent = destinations.size ? "SELECT DESTINATION" : "NO ELIGIBLE DESTINATION";
      feedback.textContent = locations.children.length ? "" : "Join a scene to see its Play availability.";
    } catch (error) {
      if (playDialog.open && revision === pickerRevision) {
        if (!selected) playDialogState.textContent = destinations.size ? "SELECT DESTINATION" : "CHECK FAILED";
        feedback.textContent = "Battlefield availability could not be checked. Reopen this picker to try again.";
      }
    }
  }

  function pilotRecordButton(pilot, compact) {
    const title = pilot.callsign + " | " + (pilot.status || "Unassigned");
    const card = button(title, () => navigate({folder:"profile", pilot:pilot.id, tacticalPilot:null}), "presence-file");
    card.dataset.pilot = pilot.id;
    card.setAttribute("aria-label", title);
    const initials = Array.from(pilot.callsign).slice(0, 2).join("");
    const portrait = element("span", initials, "dialogue-portrait presence-portrait");
    portrait.setAttribute("aria-hidden", "true");
    if (pilot.artwork) artwork.picture(portrait, pilot.artwork, {decorative:true, fallback:initials});
    const details = element("span");
    details.append(element("strong", compact ? pilot.callsign : title));
    if (!compact) details.append(element("small", pilot.frame_name || pilot.frame));
    card.replaceChildren(portrait, details);
    return card;
  }

  function renderPilotList(list, pilots, compact = false) {
    const current = new Map([...list.querySelectorAll("button[data-pilot]")].map(card => [card.dataset.pilot, card]));
    const focused = list.contains(document.activeElement) ? document.activeElement.dataset.pilot : null;
    list.replaceChildren(...pilots.map(pilot => {
      const signature = JSON.stringify([pilot.callsign, pilot.status, pilot.frame_name, pilot.frame, pilot.artwork]);
      const previous = current.get(pilot.id);
      if (previous?.dataset.record === signature) return previous.parentElement;
      const row = element("li");
      const card = pilotRecordButton(pilot, compact);
      card.dataset.record = signature;
      row.append(card);
      return row;
    }));
    if (focused) list.querySelector(`[data-pilot="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
  }

  function openTacticalPilot(id) {
    if (tacticalRoster?.some(pilot => pilot.id === id)) navigate({folder:"profile", tacticalPilot:id});
  }

  function renderScenePersonnel(room) {
    const panel = document.getElementById("present-pilots");
    const castPanel = document.getElementById("scene-cast");
    const current = player.stage === "active" && view.folder === "scenes" && room?.joined && room.archived_at == null;
    const active = current && player.active_scene?.id === room.id ? player.active_scene : null;
    const ids = current ? active?.pilot_ids ?? (room.id === "relay" ? player.scene?.pilot_ids : room.pilot_ids) ?? [] : [];
    const pilots = (player.cadre ?? []).filter(pilot => ids.includes(pilot.id));
    panel.hidden = !pilots.length;
    renderPilotList(document.getElementById("present-pilot-list"), pilots, true);
    const cast = current && room.id === transcriptRoom ? sceneCast : [];
    castPanel.hidden = !cast.length;
    document.getElementById("scene-cast-list").replaceChildren(...cast.map(actor => {
      const row = element("li",undefined,"presence-file");
      row.append(element("strong",actor.name),element("small",actor.kind === "npc" ? "NPC" : actor.kind === "gorgon" ? "Gorgon" : "External pilot"));
      return row;
    }));
  }

  function renderCommunicationsScenes(record) {
    const list = document.getElementById("communications-scene-list");
    const rooms = new Map(record.directory?.rooms.map(room => [room.id, room]) ?? []);
    const scenes = record.scene_activity ?? [];
    list.replaceChildren(...scenes.map(scene => {
      const row = element("li", undefined, "communications-scene");
      const room = rooms.get(scene.id);
      row.append(room
        ? button(scene.name, () => openDirectoryRoom(room), "link-button")
        : element("strong", scene.name));
      row.append(element("span", scene.location_name || "Location unassigned", "eyebrow"));
      row.append(element("p", "Present pilots · " + scene.pilots.join(", ")));
      return row;
    }));
    if (!scenes.length) list.append(element("li", "No active scenes."));
  }

  function showInvite(target, label, forPlay = false) {
    document.getElementById("invite-title").textContent = "Invite · " + label;
    const content = document.getElementById("invite-content");
    content.replaceChildren();
    const feedback = element("p");
    feedback.setAttribute("role", "status");
    const candidates = (player.scene_invite_targets ?? []).filter(row => !forPlay || row.pilot);
    const form = element("form");
    const field = element("label", "Recipient", "field");
    const pilot = element("select");
    pilot.required = true;
    pilot.append(new Option("Select pilot", ""), ...candidates.map(row => new Option(row.name,row.id)));
    field.append(pilot);
    const submit = element("button", "File scene invitation", "primary");
    submit.disabled = candidates.length === 0;
    form.append(field, submit);
    let intent;
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (submit.disabled || !pilot.value) return;
      if (intent?.recipient !== pilot.value) intent = {recipient:pilot.value, key:crypto.randomUUID()};
      submit.disabled = pilot.disabled = true;
      try {
        await send("scene-invite", {room:target,recipient:intent.recipient}, intent.key);
        feedback.textContent = "Invitation filed in the recipient’s Inbox.";
      } catch (error) {
        feedback.textContent = error.message;
      } finally {
        submit.disabled = pilot.disabled = false;
      }
    });
    if (!candidates.length) feedback.textContent = "No eligible recipients are available.";
    content.append(form);
    content.append(feedback);
    if (!invite.open) invite.showModal();
  }

  function sceneForm(dialog, fields, label, action) {
    const form = element("form");
    form.className = "terminal-form";
    const feedback = element("p", "", "terminal-feedback");
    feedback.setAttribute("role", "status");
    const submit = element("button", label, "primary");
    const actions = element("div", undefined, "actions terminal-actions");
    actions.append(submit);
    const close = dialog.querySelector("header button");
    form.append(...fields, feedback, actions);
    const hold = event => { if (submit.disabled) event.preventDefault(); };
    dialog.addEventListener("cancel", hold);
    dialog.addEventListener("close", () => dialog.removeEventListener("cancel", hold), {once:true});
    form.addEventListener("submit", async event => {
      event.preventDefault();
      submit.disabled = close.disabled = true;
      feedback.textContent = "";
      try {
        const destination = await action();
        dialog.close();
        if (destination) navigate(destination);
      } catch (error) {
        feedback.textContent = error.message;
      } finally {
        submit.disabled = close.disabled = false;
      }
    });
    return form;
  }

  function openStartScene() {
    if (startScene.open) return;
    const name = textField("Scene name", 80);
    const location = textField("Location (optional)", 80);
    location.input.required = false;
    location.input.placeholder = "Choose or enter a location";
    location.input.setAttribute("list", "active-scene-location-names");
    const suggestions = element("datalist");
    suggestions.id = "active-scene-location-names";
    for (const place of player.directory.locations) {
      const option = element("option");
      option.value = place.name;
      suggestions.append(option);
    }
    const fields = [name.wrapper, location.wrapper, suggestions];
    const invitees = (player?.scene_invite_targets ?? []).map(pilot => {
      const label = element("label");
      const box = element("input");
      box.type = "checkbox";
      box.value = pilot.id;
      label.append(box, " " + pilot.name);
      return {label, box};
    });
    if (invitees.length) {
      const roster = element("fieldset", undefined, "intel-recipients");
      roster.append(element("legend", "Invite pilots (optional)"), ...invitees.map(row => row.label));
      fields.push(roster);
    }
    let intent;
    const form = sceneForm(startScene, fields, "Create room", async () => {
      const recipients = invitees.filter(row => row.box.checked).map(row => row.box.value);
      const payload = {name:name.input.value.trim(), location:location.input.value.trim(), recipients};
      const signature = JSON.stringify(payload);
      if (signature !== intent?.signature) intent = {signature,key:crypto.randomUUID()};
      name.input.readOnly = location.input.readOnly = true;
      for (const {box} of invitees) box.disabled = true;
      try {
        const result = await send("room-create", payload, intent.key);
        const room = player?.directory?.rooms.find(item => item.id === result.room);
        return {folder:"scenes",mode:"locations",location:room?.location ?? null,room:result.room,tacticalPilot:null};
      } finally {
        name.input.readOnly = location.input.readOnly = false;
        for (const {box} of invitees) box.disabled = false;
      }
    });
    document.getElementById("start-scene-fields").replaceChildren(form);
    startScene.showModal();
    name.input.focus();
  }

  function openEndScene(room) {
    if (endScene.open) return;
    const key = crypto.randomUUID();
    const form = sceneForm(endScene, [
      element("p", room.name),
      element("p", "Ending this scene saves its transcript and Play receipts in the read-only Archive."),
    ], "End and archive scene", async () => {
      const result = await send("room-end", {room:room.id}, key);
      return {mode:"archive",room:result.room};
    });
    document.getElementById("end-scene-fields").replaceChildren(form);
    endScene.showModal();
  }

  function openShareIntel(room) {
    if (shareIntel.open) return;
    intelStatus.textContent = "";
    const targets = element("fieldset", undefined, "intel-recipients");
    targets.append(element("legend", "Pilot recipients"));
    for (const pilot of player.intel_targets) {
      const label = element("label");
      const check = element("input");
      check.type = "checkbox";
      check.value = pilot.id;
      label.append(check, pilot.callsign);
      targets.append(label);
    }
    const field = element("label", "Discovery", "field");
    const text = element("textarea");
    text.required = true;
    text.maxLength = 1200;
    text.rows = 4;
    field.append(text);
    const instructions = element("p", "Selected pilots receive your report in their Inbox. The scene transcript stays private.");
    let intent;
    const line = element("div", undefined, "terminal-line");
    line.append(element("span", "Foundation / Communications"), element("span", room.name, "terminal-state"));
    const form = sceneForm(shareIntel, [line, field, targets, instructions], "Send Intel", async () => {
      const recipients = [...targets.querySelectorAll("input:checked")].map(option => option.value);
      if (!recipients.length) throw new Error("Choose at least one recipient.");
      const payload = {room:room.id, recipients, text:text.value.trim()};
      const signature = JSON.stringify(payload);
      if (signature !== intent?.signature) intent = {signature,key:crypto.randomUUID()};
      targets.disabled = text.readOnly = true;
      try {
        await send("share-intel", payload, intent.key, false);
        intelStatus.textContent = "Intel sent.";
      } finally {
        targets.disabled = text.readOnly = false;
      }
    });
    document.getElementById("share-intel-fields").replaceChildren(form);
    shareIntel.showModal();
    text.focus();
  }

  function renderLocationRail(data) {
    const target = document.getElementById("location-list");
    const rooms = data.rooms.filter(room => room.archived_at == null);
    const count = element("p", rooms.length + (rooms.length === 1 ? " active scene" : " active scenes"), "eyebrow location-count");
    const groups = sceneLocationGroups(data, rooms).map(group => {
      const section = element("section", undefined, "scene-location-group");
      section.setAttribute("aria-label", group.name);
      const heading = element("h3", group.name, "scene-location-heading");
      const list = element("div", undefined, "location-scenes");
      for (const room of group.rooms) {
        const invitation = sceneInvitation(room);
        const choice = button("", () => invitation ? openSceneInvitation(invitation) : openDirectoryRoom(room), "location location-scene");
        choice.append(element("strong", room.name), element("span", sceneDirectoryState(room, invitation), "eyebrow"));
        if (invitation) {
          choice.setAttribute("aria-haspopup", "dialog");
          choice.setAttribute("aria-label", "Review invitation for " + room.name);
        }
        if (view.folder === "scenes" && view.room === room.id) choice.setAttribute("aria-current", "location");
        list.append(choice);
      }
      section.append(heading, list);
      return section;
    });
    target.replaceChildren(count, ...groups);
    if (data.can_create) {
      const start = button("Start Scene", openStartScene, "location-start");
      start.setAttribute("aria-haspopup", "dialog");
      target.append(start);
    }
    target.append(button("Scene Archive", () => navigate({
      folder:"scenes", mode:"archive", room:null, tacticalPilot:null,
    }), "location-archive"));
  }

  function locationDeck(data, group) {
    const id = facilities[group.id]?.artwork;
    if (!id) return element("h3", group.name, "scene-location-heading");
    let deck = locationDecks.get(group.id);
    if (!deck) {
      deck = element("div", undefined, "deck location-deck");
      const photo = element("div", undefined, "deck-artwork");
      const caption = element("div", undefined, "deck-caption");
      const area = data.locations.find(place => place.id === group.id)?.area;
      if (area) caption.append(element("span", area, "eyebrow"));
      caption.append(element("h3", group.name));
      deck.append(photo, caption);
      artwork.picture(photo, id, {decorative:true, fallback:""});
      locationDecks.set(group.id, deck);
    }
    return deck;
  }

  function renderDirectory(data) {
    const archived = view.mode === "archive";
    const tabs = element("div", undefined, "subtabs");
    for (const [id, label] of [["locations", "Locations"], ["mine", "My scene files"], ["archive", "Archive"]]) {
      const tab = button(label, () => navigate({mode:id, room:null}));
      tab.setAttribute("aria-pressed", String(view.mode === id));
      tabs.append(tab);
    }
    directoryHeader.replaceChildren(tabs);
    const heading = element("div", undefined, "record-heading");
    heading.append(element("h2", view.mode === "archive" ? "Closed scene files" : view.mode === "mine" ? "Assigned scene files" : "Open scene files"));
    if (!archived && data.can_create) heading.append(dialogButton("Start Scene", openStartScene, "primary"));
    directoryHeader.append(heading);
    archivePanel.hidden = !archived;
    directoryRooms.hidden = archived;

    const rooms = data.rooms.filter(room => archived ? room.joined && room.archived_at != null
      : room.archived_at == null && (view.mode !== "mine" || room.joined));
    const placeName = room => locationName(data, room);
    const rowFor = room => {
      const row = element("article", undefined, "record-row scene-directory-entry");
      const details = element("div");
      details.append(element("strong", room.name));
      if (view.mode !== "locations") details.append(element("p", placeName(room)));
      if (archived) {
        if (room.archived_pilots?.length) {
          details.append(element("p", "Pilots · " + room.archived_pilots.join(", ")));
        }
        details.append(sceneEndTime(room.archived_at));
      }
      const actions = element("div", undefined, "scene-row-actions");
      const invitation = sceneInvitation(room);
      const action = invitation
        ? dialogButton("Review invitation", () => openSceneInvitation(invitation))
        : button("Open " + room.name, () => openDirectoryRoom(room), room.joined ? "primary" : undefined);
      actions.append(element("span", sceneDirectoryState(room, invitation), "scene-state"), action);
      row.append(details, actions);
      return row;
    };
    if (!archived) {
      const rows = view.mode === "locations" ? sceneLocationGroups(data, rooms).map(group => {
        const section = element("section", undefined, "scene-location-group");
        section.append(locationDeck(data, group), ...group.rooms.map(rowFor));
        return section;
      }) : rooms.map(rowFor);
      directoryRooms.replaceChildren(...(rows.length ? rows : [element("p", "No open scene files.")]));
      return;
    }
    rooms.sort((left, right) => right.archived_at - left.archived_at);
    archiveSearch.oninput = () => {
      const query = archiveSearch.value.trim().toLocaleLowerCase();
      const tokens = query ? query.split(/\s+/) : [];
      const matches = rooms.filter(room => {
        const searchable = [room.name, placeName(room), ...(room.archived_pilots ?? [])].join(" ").toLocaleLowerCase();
        return tokens.every(token => searchable.includes(token));
      });
      archiveResults.replaceChildren(...(matches.length ? matches.map(rowFor)
        : [element("p", query ? "No archived scene files match this search." : "No closed scene files on record.")]));
    };
    archiveSearch.oninput();
  }

  function renderTranscript(room) {
    const panel = document.getElementById("room-dialogue");
    const composer = document.getElementById("scene-composer-host");
    const visible = (room?.joined || room?.id === "relay") && player.stage === "active" && view.folder === "scenes";
    panel.hidden = !visible;
    if (!visible || transcriptTarget?.room !== room?.id) transcriptTarget = undefined;
    if (!visible) {
      transcriptRoom = undefined;
      sceneCast = [];
      composer.replaceChildren();
      return;
    }
    const roomId = room.id;
    const archived = room.archived_at != null;
    const isNew = transcriptRoom !== roomId || archived !== transcriptArchived;
    transcriptRoom = roomId;
    transcriptArchived = archived;
    if (isNew) {
      transcriptSnapshot = undefined;
      sceneCast = [];
      scenePlayFeedback.hidden = true;
      const history = element("ol", undefined, "records");
      history.id = "dialogue-entries";
      const form = element("form", undefined, "scene-composer");
      const label = element("label", "Dialogue or narration", "field");
      const input = element("textarea");
      input.maxLength = 1200;
      input.required = true;
      input.rows = 2;
      input.placeholder = "Record the pilot’s words or actions…";
      const draft = sceneDraft(roomId);
      input.value = draft.text;
      input.addEventListener("input",() => { draft.text = input.value; });
      const mode = element("select");
      mode.id = "director-fictional-channel";
      mode.hidden = true;
      mode.setAttribute("aria-label", "What can the Handler hear?");
      for (const [value, text] of [["scene", "Narration for review"], ["comms", "Public scene speech"]]) {
        const option = element("option", text);
        option.value = value;
        mode.append(option);
      }
      label.append(input);
      const submit = element("button", room.joined ? "File transmission" : "Join and transmit", "primary");
      submit.type = "submit";
      const status = element("p", undefined, "scene-composer-status");
      status.setAttribute("role", "status");
      const actions = element("div", undefined, "scene-compose-actions");
      const share = dialogButton("Share Intel", () => openShareIntel(selectedRoom()));
      share.id = "compose-share-intel";
      share.hidden = true;
      actions.append(status, share, submit);
      form.append(label, mode, actions);
      submit.disabled = draft.pending;
      form.addEventListener("submit", async event => {
        event.preventDefault();
        if (draft.pending) return;
        const command = /^\/play(?:[ \t]+([^\r\n]+))?$/i.exec(input.value.trim());
        if (command) {
          input.value = "";
          draft.text = "";
          status.textContent = "";
          openRoomPlays(roomId, command[1]);
          return;
        }
        const directorRevision = mode.dataset.revision;
        const payload = {target:roomId,text:input.value};
        if (directorRevision) {
          payload.fictional_channel = mode.value;
          payload.scene_revision = Number(directorRevision);
        }
        const text = payload.text;
        const intent = JSON.stringify(payload);
        if (draft.intent?.payload !== intent) draft.intent = {payload:intent,key:crypto.randomUUID()};
        draft.pending = true;
        submit.disabled = true;
        try {
          await send("room-post", payload, draft.intent.key);
          if (draft.text === text) draft.text = "";
          if (input.value === text) input.value = "";
          draft.intent = null;
          status.textContent = "Transmission filed.";
          submit.textContent = "File transmission";
          await refreshPlayer();
          if (transcriptRoom === roomId) await refreshTranscript(roomId, true);
        } catch (error) {
          status.textContent = error.message;
        } finally {
          draft.pending = false;
          const current = composer.querySelector(".scene-composer button[type=submit]");
          if (transcriptRoom === roomId && current) current.disabled = false;
          submit.disabled = false;
        }
      });
      composer.replaceChildren(...(archived ? [] : [form]));
      panel.replaceChildren(element("h3", "Scene transcript"), history);
    }
    refreshTranscript(roomId, isNew).catch(() => {
      if (transcriptRoom !== roomId) return;
      transcriptSnapshot = undefined;
      document.getElementById("dialogue-entries").replaceChildren(
        element("li", room.joined ? "Refresh records to retrieve the transmission log." : "Transmit to register participation and retrieve this log.")
      );
    });
  }

  function focusTranscriptReceipt(room, history) {
    if (transcriptTarget?.room !== room) return;
    const {entry, receipt} = transcriptTarget;
    const target = history.querySelector(entry != null
      ? `[data-dialogue-entry="${CSS.escape(String(entry))}"]`
      : `[data-scene-receipt="${CSS.escape(receipt)}"]`);
    transcriptTarget = undefined;
    if (target) {
      history.querySelector(".transcript-target")?.classList.remove("transcript-target");
      target.classList.add("transcript-target");
      if (!document.querySelector("dialog[open]")) target.focus({preventScroll:true});
      target.scrollIntoView({block:"nearest"});
    }
  }

  async function refreshTranscript(roomId, followLatest = false) {
    const request = ++transcriptFetch;
    const {entries, receipts = [], cast = [], director} = await readTranscript(roomId);
    if (request !== transcriptFetch || transcriptRoom !== roomId || view.folder !== "scenes") return;
    if (!transcriptArchived && selectedRoom()?.joined) handover.markRead(roomId, entries, receipts);
    const history = document.getElementById("dialogue-entries");
    const mode = document.getElementById("director-fictional-channel");
    if (mode) {
      mode.hidden = !director;
      mode.dataset.revision = director?.revision ?? "";
      const composer = mode.closest("form");
      composer.querySelector("textarea").maxLength = director ? 1000 : 1200;
      composer.hidden = director?.open === false;
    }
    const snapshot = JSON.stringify([entries, receipts, cast, director]);
    if (snapshot === transcriptSnapshot) {
      focusTranscriptReceipt(roomId, history);
      return;
    }
    transcriptSnapshot = snapshot;
    sceneCast = cast;
    renderScenePersonnel(selectedRoom());
    const scrollTop = history.scrollTop;
    const rows = entries.map(entry => {
      const row = element("li", undefined, "dialogue-entry");
      row.dataset.dialogueEntry = entry.id;
      row.tabIndex = -1;
      const content = element("p", entry.body);
      if (!transcriptArchived && entry.body.trim().toLowerCase() === "/play") {
        const link = button("/play", () => openRoomPlays(roomId), "link-button");
        link.setAttribute("aria-label", "Open Scene Plays from transcript");
        content.replaceChildren(link);
      }
      const author = element("div", undefined, "dialogue-author");
      const initials = Array.from(entry.callsign.trim()).slice(0, 2).join("");
      const avatar = element("span", initials, "dialogue-portrait");
      avatar.setAttribute("aria-hidden", "true");
      if (entry.portrait) artwork.picture(avatar, entry.portrait, {decorative:true, fallback:initials});
      author.append(avatar, transcriptHeading(entry.callsign, entry.created * 1000));
      row.append(author, content);
      if (entry.action) row.append(element("p", entry.action));
      return {date:entry.created * 1000, id:entry.id, row};
    });
    for (const receipt of receipts) {
      const date = Date.parse(receipt.created);
      rows.push({date:Number.isFinite(date) ? date : 0, id:0, row:receiptRow(receipt, date)});
    }
    rows.sort((first, second) => second.date - first.date || second.id - first.id);
    if (!rows.length) rows.push({row:element("li","Awaiting first transmission.")});
    history.replaceChildren(...rows.map(item => item.row));
    history.scrollTop = followLatest ? 0 : scrollTop;
    focusTranscriptReceipt(roomId, history);
  }

  function transcriptHeading(label, date) {
    const header = element("header", undefined, "transcript-heading");
    header.append(element("strong", label));
    if (Number.isFinite(date)) {
      const time = element("time", new Date(date).toLocaleString(undefined, {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"}));
      time.dateTime = new Date(date).toISOString();
      header.append(time);
    }
    return header;
  }

  function receiptRow(receipt, date) {
    const row = element("li", undefined, "scene-receipt");
    row.dataset.sceneReceipt = receipt.id;
    row.tabIndex = -1;
    const author = element("div", undefined, "dialogue-author");
    const mark = element("i", undefined, "insignia notice-insignia");
    mark.setAttribute("aria-hidden", "true");
    author.append(mark, transcriptHeading("HARPYENGINE · BOT", date));
    row.append(author, element("h4", playName(receipt.play)));
    if (receipt.pilot && receipt.pilot !== "Scene operations") {
      row.append(element("p", receipt.pilot, "receipt-pilot"));
    }
    if (receipt.roll) row.append(element("p", `Original roll · ${receipt.roll.faces.join(" + ")} · Total ${receipt.roll.pre_total}`, "receipt-roll"));
    if (receipt.result) {
      const result = receipt.result;
      if (result.total !== undefined && result.total !== receipt.roll?.pre_total)
        row.append(element("p", "Final total · " + result.total));
      if (typeof result.enough === "boolean")
        row.append(element("p", result.enough ? "Ruling · Yes" : "Ruling · No"));
      if (typeof result.ruling === "string" && result.ruling)
        row.append(element("p", result.ruling));
      if (typeof result.response === "string" && result.response)
        row.append(element("p", result.response));
      for (const answer of Object.values(result.answers ?? {})) {
        if (typeof answer === "string") row.append(element("p", answer));
      }
    }
    if (!transcriptArchived && receipt.pending.length) {
      const decisions = element("div", undefined, "actions");
      for (const choice of receipt.pending) decisions.append(button(decisionName(choice.kind), () => {
        reviewSceneChoice(transcriptRoom, choice.id);
      }, "link-button"));
      row.append(element("p", receipt.waiting_on?.length
        ? "Waiting on " + receipt.waiting_on.join(", ") : "Your response required", "eyebrow"), decisions);
    } else {
      const status = {complete:"Filed", aborted:"Voided", awaiting_choices:"Awaiting response",
        awaiting_response:"Awaiting response", tag_window:"Awaiting response"}[receipt.state] ?? "Processing";
      row.append(element("p", !transcriptArchived && receipt.waiting_on?.length
        ? "Waiting on " + receipt.waiting_on.join(", ") : status, "eyebrow"));
    }
    return row;
  }

  function artworkButton(kind, target, id, label) {
    const action = button((id ? "Change " : "Select ") + kind + " artwork", () => artwork.open(kind, target, id, label), "link-button");
    action.setAttribute("aria-haspopup", "dialog");
    return action;
  }

  function recordArtwork(container, kind, target, id, canEdit, label, fallback = "") {
    if (!id && !canEdit && !fallback) return;
    const key = JSON.stringify([kind,target]);
    let record = recordArtworks.get(key);
    if (!record) {
      const panel = element("div",undefined,"record-artwork record-artwork--" + kind);
      const figure = element("figure",fallback);
      panel.append(figure);
      record = {panel,figure};
      recordArtworks.set(key,record);
    }
    if (record.id !== id || record.fallback !== fallback) {
      record.id = id;
      record.fallback = fallback;
      if (id) artwork.picture(record.figure,id,{fallback:fallback || "Artwork unavailable."});
      else {
        artwork.picture(record.figure,null);
        record.figure.textContent = fallback;
      }
    }
    const signature = JSON.stringify([id,canEdit,label]);
    if (record.signature !== signature) {
      record.control?.remove();
      record.control = canEdit ? artworkButton(kind,target,id,label) : null;
      if (record.control) record.panel.append(record.control);
      record.signature = signature;
    }
    container.append(record.panel);
  }

  function renderSceneArtwork(room) {
    if (view.folder !== "scenes" || !room?.joined || (!room.artwork && !room.can_invite)) {
      if (sceneArtwork) roomArtwork.replaceChildren();
      sceneArtwork = undefined;
      return;
    }
    if (sceneArtwork?.room !== room.id) {
      const panel = element("div", undefined, "record-artwork record-artwork--scene");
      const figure = element("figure", undefined, "scene-artwork-frame");
      panel.append(figure);
      roomArtwork.replaceChildren(panel);
      sceneArtwork = {room:room.id, panel, figure};
    }
    const record = sceneArtwork;
    const id = room.artwork ?? null;
    if (id !== record.id || room.can_invite !== record.canEdit || room.name !== record.name) {
      record.control?.remove();
      record.control = room.can_invite ? artworkButton("scene", room.id, id, room.name) : null;
      if (record.control) record.panel.append(record.control);
      record.canEdit = room.can_invite;
      record.name = room.name;
    }
    if (id === record.id) return;
    record.id = id;
    record.figure.hidden = !id;
    record.pending = null;
    if (!id) {
      record.figure.replaceChildren();
      return;
    }
    // Decode off-screen and swap only the latest selection for the current room.
    if (!record.figure.querySelector("img")) record.figure.textContent = "Loading scene artwork…";
    const pending = element("figure");
    record.pending = pending;
    artwork.picture(pending, id).then(() => {
      if (sceneArtwork === record && record.pending === pending) {
        record.figure.replaceChildren(...pending.childNodes);
      }
    });
  }

  function renderRoom(room) {
    roomPane.hidden = !room;
    setup.hidden = player?.stage === "active" && (room?.id !== "relay" || room.joined);
    const roomActions = document.getElementById("room-actions");
    roomActions.replaceChildren();
    if (intelStatus.dataset.room !== room?.id) {
      document.getElementById("scene-direct-feedback").hidden = true;
      intelStatus.dataset.room = room?.id ?? "";
      intelStatus.textContent = "";
    }
    renderSceneArtwork(room);
    document.getElementById("room-name").textContent = room?.name ?? "";
    renderTranscript(room);
    renderScenePersonnel(room);
    const hasComposer = room?.joined && room.archived_at == null && player.stage === "active" && view.folder === "scenes";
    const activeScene = hasComposer && player.active_scene?.id === room.id ? player.active_scene : null;
    sceneCommands.hidden = !hasComposer;
    if (!hasComposer && scenePlayPanel.open) scenePlayPanel.close();
    scenePlayOptions.hidden = !activeScene;
    renderRoomPlays(activeScene, roomActions);
    filterScenePlays();
    enterScene.replaceChildren();
    if (hasComposer && !activeScene && room.play_active) {
      if (scenePlayFeedback.hidden) enterScene.append(element("p", "Retrieving this scene’s Plays."));
    } else if (hasComposer && !activeScene) {
      const status = element("p");
      status.setAttribute("role", "status");
      const open = button("Enter scene for Plays", async () => {
        const selection = playSelection;
        open.disabled = true;
        try {
          await send("enter-scene", {room:room.id});
          if (selection === playSelection && viewingScene(room.id)) {
            await openRoomPlays(room.id, "", false, null, selectedCategory);
          }
        } catch (error) {
          if (selection === playSelection) status.textContent = error.message;
        } finally {
          open.disabled = false;
        }
      }, "primary");
      enterScene.append(open, status);
    }
    if (!room) {
      renderRecordMetadata(document.getElementById("room-record"), {});
      document.getElementById("scene-assigned-controls").replaceChildren();
      return;
    }
    roomActions.append(dialogButton("Scene access", openSceneAccess));
    if (room.can_invite) roomActions.append(button("Invite to room", () => showInvite(room.id, room.name)));
    const share = document.getElementById("compose-share-intel");
    if (share) share.hidden = !hasComposer || !player.intel_targets?.length;
    if (room.can_end) {
      const end = button("End Scene", () => openEndScene(room), "warning-outline");
      end.setAttribute("aria-haspopup", "dialog");
      roomActions.append(end);
    }
    if (room.archived_at != null) roomActions.append(sceneEndTime(room.archived_at));
    const choices = [
      ["keep_your_head", activeScene?.keep], ...Object.entries(activeScene?.options ?? {}),
    ].flatMap(([play,record]) => (record?.choices ?? []).map(choice => ({...choice,play})));
    const hasWork = player.scene_beneath_work?.some(card => card.room === room.id && card.action)
      || activeScene?.specialist_work?.some(card => card.action && !card.waiting);
    const assigned = room.archived_at == null && room.joined && (choices.length || hasWork);
    const waiting = !assigned && room.joined && room.archived_at == null
      ? player.scene_mail?.find(receipt => receipt.room === room.id && receipt.waiting_on?.length)
      : undefined;
    const assignedControls = document.getElementById("scene-assigned-controls");
    assignedControls.replaceChildren();
    if (choices.length || waiting) {
      const summary = element("div", undefined, "scene-assignment-copy");
      const owner = waiting?.waiting_on.join(", ") ?? (choices[0].role === "handler" ? "Handler" : player.callsign || "You");
      summary.append(element("span", "HARPYENGINE · " + (waiting ? "Waiting on " + owner : "Your response required"), "eyebrow"),
        element("strong", playName(waiting?.play ?? choices[0].play)));
      assignedControls.append(summary);
      for (const [index,choice] of choices.entries()) {
        const control = dialogButton("Review " + (index === 0 ? playName(choice.play) : decisionName(choice.kind)),
          () => reviewSceneChoice(room.id, choice.id));
        if (index === 0) control.classList.add("primary");
        assignedControls.append(control);
      }
    }
    if (activeScene?.cancellation) {
      const cancel = cancellationControl(activeScene.cancellation,room);
      if (cancel) assignedControls.append(cancel);
    }
    const owners = new Set(choices.map(choice => choice.role === "handler" ? "Handler" : player.callsign));
    if (hasWork) owners.add(player.callsign);
    renderRecordMetadata(document.getElementById("room-record"), {
      room:true,
      location:locationName(player.directory, room),
      state:room.archived_at != null ? "Archived · Read-only" : activeScene?.safety?.paused ? "Safety pause"
        : assigned ? "Action required" : activeScene?.locked ? "Play in progress" : activeScene ? "Scene active"
        : room.joined ? "Joined" : room.kind === "lobby" ? "Invitation required" : "Join required",
      owner:assigned ? [...owners].filter(Boolean).join(" · ") : undefined,
    });
  }

  function pilotFile(pilots) {
    if (view.tacticalPilot) {
      const pilot = tacticalRoster?.find(item => item.id === view.tacticalPilot);
      return {pilot:pilot && {...pilot, callsign:pilot.label}, profile:pilot?.profile, tactical:true};
    }
    const pilot = pilots.find(item => item.id === view.pilot) ?? pilots.find(item => item.own);
    return {pilot, profile:pilot?.own ? player.profile : null, tactical:false};
  }

  function renderDossier(panel, kind, name, status, pilot, tactical, facts) {
    const dossier = element("div", undefined, "dossier-grid");
    const header = element("header", undefined, "dossier-header dossier-header--" + kind);
    header.append(element("h3", name));
    if (!tactical) {
      const image = kind === "pilot" ? pilot.artwork : pilot.frame_artwork;
      const fallback = kind === "pilot" ? Array.from(name).slice(0, 2).join("") : "▣";
      recordArtwork(header, kind, pilot.id, image, pilot.own, name, fallback);
    }
    dossier.append(header);
    readFile(dossier, [["Status", element("span", status, "file-stamp")], ...facts]);
    panel.append(dossier);
  }

  function assetStamps(asset) {
    const group = element("span", undefined, "file-stamps");
    const condition = element("span", asset.damaged ? "Damaged" : "Operational", "file-stamp");
    if (asset.damaged) condition.dataset.condition = "damaged";
    group.append(condition);
    if (asset.void) {
      const exposure = element("span", "Void-touched", "file-stamp");
      exposure.dataset.condition = "void";
      group.append(exposure);
    }
    return group;
  }

  function renderPeople(pilots) {
    const {pilot:selected, profile, tactical} = pilotFile(pilots);
    const file = document.getElementById("profile-data");
    const previousRail = file.querySelector(".play-rail");
    file.replaceChildren();
    if (selected) {
      const frameName = profile?.frame_name || selected.frame_name || selected.frame;
      const records = [["Frame", frameName ? button(frameName, () => navigate({folder:"frame"}), "link-button") : "Unassigned"],
        ["Girl", selected.girl ?? "Unassigned"]];
      if (profile) {
        records.push(["Heat", String(profile.heat)], ["Tags", profile.tags.join(", ") || "None"]);
        if (profile.identities?.length) {
          records.push(["Identities", profile.identities.map(item => item.name + (item.marked ? " (marked)" : "")).join(", ")]);
        }
      }
      if (view.folder === "profile") {
        renderDossier(file, "pilot", selected.callsign, "PILOT | " + (selected.status || "Unassigned"),
          selected, tactical, records);
      } else {
        readFile(file, records);
      }
      if (profile) renderAssetRecords(file, "Girl", profile.girl_assets ?? [], selected.own && !tactical);
      if (selected.own && !tactical) {
        const actions = element("div", undefined, "profile-actions");
        actions.setAttribute("role", "group");
        actions.setAttribute("aria-label", "Pilot file actions");
        if (openPortrayal) {
          const portrayal = button("Open portrayal", openPortrayal);
          portrayal.setAttribute("aria-haspopup", "dialog");
          actions.append(portrayal);
        }
        renderPilotBonds(actions, player);
        if (player.sheet_reset) {
          const restart = button("Restart character", () => openSheetReset(player.sheet_reset), "warning-outline");
          restart.setAttribute("aria-haspopup","dialog");
          actions.append(restart);
        }
        if (actions.childElementCount) file.append(actions);
      }
      const specialistPlays = selected.plays?.filter(play => play.group === "girl" || play.group === "frame") ?? [];
      if (specialistPlays.length) {
        const entries = specialistPlays.map(play => {
          const activate = tactical ? selected.controlled ? () => {
            navigate({folder:"battlefield"});
            battlefield.open(play.id);
          } : undefined : () => pickPlayScene(selected, play);
          const row = playCard(play, sheetPlayCaption(play,
            play.blocked ? "Blocked on this sheet" : play.trigger), activate);
          if (activate && !tactical) row.setAttribute("aria-haspopup", "dialog");
          return {play, row};
        });
        const rail = playRail(entries, previousRail?.dataset.playPilot === selected.id
          ? previousRail.dataset.selectedPlayCategory : undefined);
        rail.dataset.playPilot = selected.id;
        const sheet = element("section");
        sheet.append(element("h3", "Girl and Frame Plays"), rail);
        file.append(sheet);
      }
    } else if (player.enrollment && !tactical) {
      if (player.callsign) file.append(element("h3", player.callsign));
      file.append(element("p", "Enrollment pending", "eyebrow"),
        button("Resume enrollment", resumeEnrollment, "primary"));
    } else {
      file.append(element("p", "Complete character setup to open this file."));
    }
    const cadre = document.getElementById("cadre-data");
    renderPilotList(cadre, pilots);
    if (!pilots.length) cadre.append(element("li", "No active pilots."));
  }

  function renderFrame(pilots) {
    const {pilot, profile, tactical} = pilotFile(pilots);
    const panel = document.getElementById("frame-data");
    panel.replaceChildren();
    if (!pilot) {
      panel.append(element("p", "No Frame assigned."));
      return;
    }
    const name = profile?.frame_name || pilot.frame_name || profile?.frame || pilot.frame;
    const facts = [["Pilot", pilot.callsign], ["Frame playbook", profile?.frame ?? pilot.frame]];
    if (pilot.frame_class) {
      const frameClass = pilot.frame_class === "legion" ? "LEGION"
        : pilot.frame_class[0].toUpperCase() + pilot.frame_class.slice(1);
      facts.push(["Frame class", frameClass]);
    }
    if (view.folder === "frame") renderDossier(panel, "frame", name, "Assigned", pilot, tactical, facts);
    else readFile(panel, facts);
    if (!profile) return;
    renderAssetRecords(panel, "Frame", profile.assets, pilot.own && !tactical);
    panel.append(element("h3", "Upgrades"));
    for (const upgrade of profile.upgrades ?? []) {
      const content = element("p", upgrade.description || "No description recorded.");
      const trigger = popupAction(upgrade.name, content, "frame-upgrade:" + upgrade.id, {compact:true});
      trigger.classList.add("link-button");
      panel.append(trigger);
    }
    if (!profile.upgrades?.length) panel.append(element("p", "None recorded."));
    if (pilot.own && !tactical && view.folder === "frame" && player.frame_purchase) {
      renderFramePurchases(panel, player.frame_purchase);
    }
  }

  function renderAssetRecords(panel, family, assets, editable) {
    panel.append(element("h3", family + " assets"));
    if (!assets.length) {
      panel.append(element("p", "No " + family + " assets listed."));
      return;
    }
    const records = element("ul", undefined, "records asset-records");
    for (const asset of assets) {
      const row = element("li", undefined, "record-row asset-record");
      const key = family.toLowerCase() + "-asset:" + asset.id;
      row.append(assetPopup(asset, key, editable), assetStamps(asset));
      records.append(row);
    }
    panel.append(records);
  }

  function assetPopup(asset, key, editable) {
    const content = element("div");
    readFile(content, [["Condition", assetStamps(asset)]]);
    if (editable) {
      const form = element("form");
      const label = element("label", "Description", "field");
      const description = element("textarea");
      description.maxLength = 700;
      description.rows = 3;
      description.value = asset.description;
      label.append(description);
      const status = element("p", "", "terminal-feedback");
      status.setAttribute("role", "status");
      const submit = element("button", "Save description", "primary");
      form.append(label, submit, status);
      form.addEventListener("submit", async event => {
        event.preventDefault();
        if (submit.disabled) return;
        submit.disabled = true;
        try {
          await send("asset-description", {asset:asset.id, description:description.value, revision:asset.description_revision});
          closePopup(key);
        } catch (error) {
          status.textContent = error.message;
          submit.disabled = false;
        }
      });
      content.append(form);
    } else {
      content.append(element("p", asset.description || "No description recorded."));
    }
    const trigger = popupAction(asset.name, content, key, {compact:true});
    trigger.classList.add("link-button");
    return trigger;
  }

  function renderFramePurchases(panel, purchase) {
    const details = element("div");
    panel.append(popupAction("Requisition a Frame Asset",details,"frame-purchase:" + purchase.actor));
    if (purchase.reason) {
      details.append(element("p", purchase.reason));
      return;
    }
    const price = purchase.asset_installment_price;
    details.append(element("p", `Cost ${price} Permission · Available ${purchase.permissions}`));
    const cap = purchase.asset_count === purchase.frame_capacity;
    const unavailable = purchase.permissions < price ? "Insufficient Permissions."
      : purchase.asset_count > purchase.frame_capacity || cap && !purchase.replacement_options.length
        ? "HarpyEngine found no legal replacement slot." : null;
    if (unavailable) details.append(element("p", unavailable));
    else {
      const form = element("form");
      const values = {};
      const field = (key, caption, input) => {
        const wrapper = element("label", caption, "field");
        wrapper.append(input);
        form.append(wrapper);
        values[key] = input;
        return input;
      };
      const source = field("source", "Asset source", element("select"));
      source.add(new Option("Custom Asset", ""));
      for (const asset of purchase.catalog) source.add(new Option(asset.frame + " · " + asset.name, asset.key));
      const name = field("name", "Custom Asset name", element("input"));
      name.maxLength = 80;
      name.required = true;
      source.addEventListener("change", () => {
        name.disabled = Boolean(source.value);
        name.required = !name.disabled;
        name.parentElement.hidden = name.disabled;
      });
      const description = field("description", "Description", element("textarea"));
      description.required = true;
      description.maxLength = 700;
      const account = field("account", "Describe the installation", element("textarea"));
      account.required = true;
      account.maxLength = 1200;
      if (cap) {
        const replace = field("replace", "Replace an Asset", element("select"));
        replace.add(new Option("Choose an Asset", ""));
        for (const [id, label] of purchase.replacement_options) replace.add(new Option(label, id));
        replace.required = true;
      }
      const confirmation = field("confirm", "I approve spending " + price + " Permission", element("input"));
      confirmation.type = "checkbox";
      confirmation.required = true;
      const submit = element("button", "Install Frame Asset", "primary");
      const status = element("p");
      status.setAttribute("role", "status");
      form.append(submit, status);
      let requestKey;
      form.addEventListener("input", () => { requestKey = undefined; });
      form.addEventListener("submit", async event => {
        event.preventDefault();
        requestKey ||= crypto.randomUUID();
        const printed = purchase.catalog.find(asset => asset.key === source.value);
        const choice = {
          ...(printed ? {from_frame:printed.frame,index:printed.index} : {name:name.value}),
          description:description.value, account:account.value, trigger_confirmed:confirmation.checked,
          ...(cap ? {replace:values.replace.value} : {}),
        };
        submit.disabled = true;
        try {
          await send("frame-purchase", {actor:purchase.actor,expected:purchase.source_sha256,choice}, requestKey);
          closePopup("frame-purchase:" + purchase.actor);
        } catch (error) {
          status.textContent = error.message;
        } finally {
          submit.disabled = false;
        }
      });
      details.append(form);
    }
    if (purchase.receipts.length) {
      details.append(element("h3", "Filed installations"));
      const receipts = element("ul");
      for (const receipt of purchase.receipts) receipts.append(element("li", receipt.name));
      details.append(receipts);
    }
    renderFrameAcquisition(panel, purchase.abilities, purchase.permissions);
  }

  function renderFrameAcquisition(panel, offer, permissions) {
    if (!offer.rules.length && !offer.enforcer_rules.length) return;
    const details = element("div");
    const title = offer.kind === "ability_unlock" ? "Ability Unlock" : "Frame Grafting";
    details.append(element("p", `Cost ${offer.price} Permissions · Available ${permissions}`));
    panel.append(popupAction(title,details,"frame-acquire:" + offer.actor + ":" + offer.kind));
    if (offer.enforcer_rules.length) {
      const held = element("ul");
      for (const rule of offer.enforcer_rules) {
        held.append(element("li", rule.label + (rule.active ? " · Active" : " · Inactive")));
      }
      details.append(held);
    }
    if (!offer.rules.length || permissions < offer.price) {
      details.append(element("p", offer.rules.length ? "Insufficient Permissions." : "No additional reviewed abilities are available."));
      return;
    }
    const form = element("form");
    const rule = element("select");
    rule.add(new Option("Choose an ability", ""));
    rule.required = true;
    for (const entry of offer.rules) rule.add(new Option(entry.label, entry.id));
    const selection = element("label", "Ability", "field");
    selection.append(rule);
    const account = textField("Describe the acquisition", 1200);
    const approval = element("label", "I approve spending " + offer.price + " Permissions", "field");
    const confirmed = element("input");
    confirmed.type = "checkbox";
    confirmed.required = true;
    approval.append(confirmed);
    const submit = element("button", "File acquisition", "primary");
    const status = element("p");
    status.setAttribute("role", "status");
    form.append(selection, account.wrapper, approval, submit, status);
    details.append(form);
    let requestKey;
    form.addEventListener("input", () => { requestKey = undefined; });
    form.addEventListener("submit", async event => {
      event.preventDefault();
      requestKey ||= crypto.randomUUID();
      submit.disabled = true;
      try {
        await send("frame-acquire-rule", {
          actor:offer.actor, expected:offer.source_sha256, kind:offer.kind,
          rule:rule.value, account:account.input.value, confirmed:confirmed.checked,
        }, requestKey);
        closePopup("frame-acquire:" + offer.actor + ":" + offer.kind);
      } catch (error) {
        status.textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
  }

  function renderBattlefield() {
    const board = document.getElementById("battlefield-map");
    const location = player.directory?.locations.find(place => place.id === view.location);
    const facility = facilities[location?.id];
    if (!facility || board.dataset.location === location.id) return;
    board.dataset.location = location.id;
    document.getElementById("briefing-site").textContent = location.name + " · Facility plan";
    board.setAttribute("aria-label", `Top-down ${location.name} plan. ${facility.rooms.map(([name]) => name).join(", ")}. Walls, doorways and cover are marked.`);
    board.replaceChildren();
    board.style.setProperty("--columns", facility.floor[0].length);
    for (const [y, row] of facility.floor.entries()) {
      for (const [x, tile] of [...row].entries()) {
        const cell = element("span");
        markTerrain(cell, row, x);
        cell.title = terrainNames[tile];
        cell.style.gridArea = `${y + 1} / ${x + 1}`;
        board.append(cell);
      }
    }
    board.append(...facilityLabels(facility.rooms));
  }

  function render() {
    const handler = player?.stage === "handler";
    if (handler && scenePlayPanel.open) scenePlayPanel.close();
    const canHandover = handler || player?.stage === "active";
    const canCampaignSetup = Boolean(player && openCampaignSetup);
    const canReviewDossiers = Boolean(player?.can_review_dossiers && setDossierVisible);
    const handlerFolders = ["handover", "scenes", "missions", ...(battlefield.enabled() ? ["battlefield"] : []),
      ...(canCampaignSetup ? ["campaign-setup"] : []), ...(canReviewDossiers ? ["dossiers"] : [])];
    if (handler && !handlerFolders.includes(view.folder)) {
      view = {...view, folder:"scenes", tacticalPilot:null};
    }
    if (view.folder === "dossiers" && !canReviewDossiers) view = {...view, folder:"scenes"};
    const root = document.documentElement;
    const folderChanged = root.dataset.activityFolder !== view.folder;
    root.dataset.activityFolder = view.folder;
    const showDossiers = view.folder === "dossiers";
    if (showDossiers !== dossierVisible) {
      dossierVisible = showDossiers;
      setDossierVisible?.(showDossiers);
    }
    for (const folder of folders) {
      const name = folder.dataset.folder;
      folder.hidden = name === "handover" ? !canHandover
        : name === "campaign-setup" ? !canCampaignSetup
        : name === "dossiers" ? !canReviewDossiers : handler && !handlerFolders.includes(name);
      if (name === "scenes") folder.textContent = handler ? "Handler desk" : "Scenes";
      if (name === view.folder) folder.setAttribute("aria-current", "page");
      else folder.removeAttribute("aria-current");
    }
    if (folderChanged) revealActiveFolder();
    if (folderChanged && view.folder === "campaign-setup") window.scrollTo(0, 0);
    back.hidden = !trail.length;
    locationsToggle.hidden = !player?.directory || view.folder === "scenes" && !handler;
    communicationsToggle.hidden = !player || (player.stage !== "active" && player.stage !== "handler");
    handover.setVisible(canHandover && view.folder === "handover");
    const handlerDesk = document.getElementById("handler-desk");
    handlerDesk.hidden = !handler || view.folder !== "scenes";
    if (noticeFolder !== view.folder) {
      noticeFolder = view.folder;
      showNotice(folderNotices[view.folder] ?? signs[0]);
    }
    document.getElementById("open-off-duty").hidden = !player?.off_duty || view.folder !== "scenes";
    document.getElementById("open-punishment-work").hidden = !player?.handler_punishments?.length || view.folder !== "scenes";
    if (punishmentDialog.open && !player?.handler_punishments?.length) punishmentDialog.close();
    if (handler) {
      syncPlaySelection();
      const onBattlefield = view.folder === "battlefield" && battlefield.enabled();
      deskContext.textContent = onBattlefield ? "Handler · Battlefield" : "Handler desk";
      deskContext.hidden = false;
      const onMissions = view.folder === "missions";
      if (onMissions) deskContext.textContent = "Handler · Dispatch desk";
      if (view.folder === "campaign-setup") deskContext.textContent = "Handler · Campaign Setup";
      if (showDossiers) deskContext.textContent = "Campaign Dossiers";
      for (const item of panes) item.hidden = !(item.dataset.pane === view.folder && view.folder !== "scenes");
      showBattlefield(onBattlefield);
      return;
    }
    for (const item of panes) item.hidden = item.dataset.pane !== view.folder;
    showBattlefield(view.folder === "battlefield");
    if (!player) return;
    const data = player.directory ?? {locations:[], rooms:[]};
    const pilots = player.cadre ?? [];
    const location = data.locations.find(item => item.id === view.location);
    renderLocationRail(data);
    const room = selectedRoom();
    syncPlaySelection(view.folder === "scenes" && player.stage === "active" && room?.joined && room.archived_at == null ? room.id : null);
    if (view.folder === "scenes" && room?.joined && room.archived_at == null) lastRoom = room.id;
    const folderLabel = folders.find(folder => folder.dataset.folder === view.folder)?.textContent.trim();
    const sectionLabel = view.folder === "scenes" ? (room?.name ?? (view.mode === "archive" ? "Archive" : view.mode === "mine" ? "My scenes" : location?.name)) : null;
    deskContext.textContent = [folderLabel, sectionLabel].filter(Boolean).join(" / ");
    deskContext.hidden = false;
    directory.hidden = Boolean(room);
    if (!room) renderDirectory(data);
    renderRoom(room);
    renderPeople(pilots);
    renderFrame(pilots);
    renderBattlefield();
  }

  return {
    updateHandoverAssignments:handover.updateAssignments,
    setPortrayal(open) { openPortrayal = open; if (player) render(); },
    setCampaignSetup(open) { openCampaignSetup = open; if (player) render(); },
    setDossierReview(setVisible) { setDossierVisible = setVisible; if (player) render(); },
    playSelection() { return playSelection; },
    renderCancellations(target,records) {
      target.replaceChildren(...records.filter(source => source.can_cancel).map(source =>
        cancellationControl(source,{id:source.room,name:source.room_name},
          "Cancel " + playName(source.play) + " · " + source.room_name)));
    },
    update(record) {
      const admitted = record.stage === "active" || record.stage === "handler";
      const sameMode = player && (player.stage === "handler") === (record.stage === "handler");
      if (!sameMode || draftIdentity !== record.mailbox || (admitted && player?.stage !== record.stage)) {
        trail.length = 0;
        lastRoom = undefined;
        transcriptTarget = undefined;
        view = {...initialView, folder:admitted ? "handover" : "scenes"};
      }
      if (draftIdentity !== record.mailbox) {
        sceneDrafts.clear();
        recordArtworks.clear();
        locationDecks.clear();
        draftIdentity = record.mailbox;
      }
      player = record;
      handover.update(record);
      renderCommunicationsScenes(record);
      render();
    },
    updateTacticalRoster(roster) { tacticalRoster = roster; },
    openTacticalPilot,
    openSceneInvitation,
    openOffDuty() {
      if (view.folder !== "scenes") navigate({folder:"scenes"});
      if (!offDutyDialog.open) offDutyDialog.showModal();
      document.getElementById("off-duty-title").focus();
    },
    openMissionWork() {
      if (view.folder !== "scenes") navigate({folder:"scenes"});
      if (!punishmentDialog.open) punishmentDialog.showModal();
      document.querySelector("[data-punishment-case]")?.focus();
    },
    openMissionRecord(id, work) {
      if (view.folder !== "missions") navigate({folder:"missions"});
      const record = document.getElementById("mission-desk")
        .querySelector(`[data-mission-id="${CSS.escape(id)}"]`);
      record?.scrollIntoView({block:"nearest"});
      record?.focus();
      if (work) record?.querySelector(`[data-mission-work="${CSS.escape(work)}"]`)?.click();
    },
    openAssignedDefeat(source) {
      const owner = player?.cadre?.find(pilot => pilot.own);
      if (owner) return pickPlayScene(owner, {id:"defeat",label:"Defeat"}, undefined, source);
    },
    openPunishmentCase(id) {
      if (view.folder !== "scenes") navigate({folder:"scenes"});
      if (!punishmentDialog.open) punishmentDialog.showModal();
      const record = [...punishmentDialog.querySelectorAll("[data-punishment-case]")]
        .find(item => item.dataset.punishmentCase === id);
      record?.scrollIntoView({block:"nearest"});
      record?.focus();
    },
    openBattlefieldPlay(id) {
      navigate({folder:"battlefield"});
      return battlefield.open(id);
    },
    openBattlefieldFramePlay(id) {
      navigate({folder:"battlefield"});
      return battlefield.openFrame(id);
    },
    openRelayPlays,
    openRoomPlays,
    openSceneReceipt,
  };
}
