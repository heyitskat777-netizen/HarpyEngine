/** Private work for the current authenticated Activity scene. */
function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function field(label, value) {
  const row = element("label", label);
  const input = element("input");
  input.required = true;
  input.value = value ?? "";
  row.append(input);
  return [row, input];
}

function choiceField(label, choices, value) {
  const row = element("label", label);
  const control = element("select");
  for (const [id, name] of [["", "Choose…"], ...choices]) {
    const option = element("option", name);
    option.value = id;
    control.append(option);
  }
  control.value = value ?? "";
  row.append(control);
  return [row, control];
}

export function mountDirectorDesk(parent, scene, activityFetch, activityShadow = false) {
  const details = element("details");
  details.append(element("summary", scene ? "Director work" : "Campaign setup"));
  const body = element("div");
  const status = element("p");
  status.setAttribute("role", "status");
  details.append(status, body);
  parent.prepend(details);
  const root = scene ? "/api/director/" + encodeURIComponent(scene) + "/" : "/api/campaign-opening/";
  const routeId = id => encodeURIComponent(id).replaceAll("%3A", ":");

  async function read(route, optional = false) {
    const response = await activityFetch(root + route);
    if (optional && [401, 403, 404, 409].includes(response.status)) return null;
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Unable to read scene work.");
    return result;
  }

  function renderShadow(policy, observation, review) {
    if (!observation) return;
    const row = card(body, "Private shadow review");
    row.append(element("p", "Scene observation · " + observation.phase.replaceAll("_", " ")));
    if (policy) {
      row.append(button(policy.enabled ? "Disable campaign observation" : "Enable campaign observation", async key => {
        await write("activity-policy-save", {revision: policy.revision, enabled: !policy.enabled}, key);
        await refresh();
      }));
      if (policy.enabled) row.append(button("Refresh scene consent notice", async key => {
        await write("configure", {revision: observation.policy_revision}, key);
        await refresh();
      }));
    }
    if (observation.policy_revision) {
      for (const [consent, label] of [[true, "Grant my observation consent"], [false, "Withdraw my observation consent"]]) {
        row.append(button(label, async key => {
          await write("consent", {policy_revision: observation.policy_revision, consent}, key);
          await refresh();
        }));
      }
    }
    if (!review) return;
    row.append(button("Review eligible batch", async key => {
      const result = await write("activity-review-run", {}, key);
      await refresh();
      if (!result.batch) status.textContent = "No batch is ready.";
    }));
    for (const batch of review.batches) {
      const group = element("details");
      group.append(element("summary", `Reviewed through event ${batch.frontier}`));
      for (const item of batch.items) {
        const description = item.decision ? `${item.decision.action} · ${item.decision.reason.replaceAll("_", " ")}`
          : item.kind === "completed_play" ? "Completed Play · human GM review" : "Source changed. Review a current batch.";
        group.append(element("p", description));
        for (const fact of item.facts ?? []) group.append(element("p", fact.text));
      }
      row.append(group);
    }
  }

  async function write(route, data, key) {
    const response = await activityFetch(root + route, {
      method: "POST",
      headers: {"Content-Type": "application/json", "Idempotency-Key": key},
      body: JSON.stringify(data),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Scene work could not be saved.");
    return result;
  }

  function button(label, operation, currentIntent = () => "") {
    const node = element("button", label);
    node.type = "button";
    let key = crypto.randomUUID();
    let intent;
    node.addEventListener("click", async () => {
      const next = currentIntent();
      if (intent !== next) key = crypto.randomUUID();
      intent = next;
      node.disabled = true;
      status.textContent = "";
      try {
        await operation(key);
        key = crypto.randomUUID();
      } catch (error) {
        status.textContent = error.message;
      } finally {
        node.disabled = false;
      }
    });
    return node;
  }

  function card(container, title) {
    const row = element("section");
    row.append(element("h4", title));
    container.append(row);
    return row;
  }

  function renderOpening(opening) {
    const row = card(body, "Campaign opening");
    if (opening.launched) {
      row.append(element("p", "The campaign opening has been launched."));
      const notes = element("details");
      notes.append(element("summary", "Facilitator opening notes"));
      if (opening.draft.gm_pressure) notes.append(element("p", opening.draft.gm_pressure));
      for (const fact of opening.draft.facts) {
        const names = opening.roles.filter(x => fact.known_by.includes(x.id)).map(x => x.label);
        notes.append(element("p", fact.text + " · " + fact.learned_from + " · " + (names.join(", ") || "GM only")));
      }
      row.append(notes);
      return;
    }
    const draft = opening.draft ?? {};
    const [locationLabel, location] = field("Opening location", draft.location);
    const [situationLabel, situation] = field("Opening situation", draft.situation);
    const [choiceLabel, choice] = field("First player decision", draft.first_choice);
    const [pressureLabel, pressure] = field("GM-only pressure", draft.gm_pressure);
    pressure.required = false;
    row.append(locationLabel, situationLabel, choiceLabel, pressureLabel);
    const session = element("details");
    session.append(element("summary", "Session Zero"));
    const [toneLabel, tone] = field("Campaign tone", draft.session_zero?.tone);
    const [offscreenLabel, offscreen] = field("What stays offscreen?", draft.session_zero?.offscreen);
    const [fallbackLabel, fallback] = field("Human fallback", draft.session_zero?.human_fallback);
    for (const input of [tone, offscreen, fallback]) input.required = false;
    const initiativeLabel = element("label", "Handler initiative");
    const initiative = element("select");
    for (const value of ["respond when called", "also offer help when needed"]) {
      const opt = element("option", value);
      opt.value = value;
      opt.selected = value === draft.session_zero?.handler_initiative;
      initiative.append(opt);
    }
    initiativeLabel.append(initiative);
    session.append(toneLabel, offscreenLabel, initiativeLabel, fallbackLabel);
    row.append(session);
    const npcLabel = element("label", "NPC pilots played by their verified controllers");
    const npcPilots = element("select");
    npcPilots.multiple = true;
    for (const role of opening.roles.filter(x => x.kind === "pilot")) {
      const option = element("option", role.label);
      option.value = role.id;
      option.selected = draft.npc_pilots?.includes(role.id) ?? false;
      npcPilots.append(option);
    }
    npcLabel.append(npcPilots);
    row.append(npcLabel, element("p", "Add a Pilot through character setup and join them to the opening scene to assign this role."));
    const facts = element("div");
    const editors = [];
    let changed = () => {};
    row.append(facts);

    function addFact(fact = {}) {
      const editor = element("fieldset");
      editor.append(element("legend", "Starting fact"));
      const [textLabel, factText] = field("Fact to share", fact.text);
      const [sourceLabel, source] = field("How it was learned (GM notes)", fact.learned_from);
      editor.append(textLabel, sourceLabel);
      const recipients = element("select");
      recipients.multiple = true;
      const audience = element("label", "Who knows this? Leave empty for GM only.");
      for (const role of opening.roles) {
        const option = element("option", role.label);
        option.value = role.id;
        option.selected = fact.known_by?.includes(role.id) ?? false;
        recipients.append(option);
      }
      audience.append(recipients);
      const entry = {factText, source, recipients};
      editors.push(entry);
      editor.append(audience, button("Remove fact", () => {
        editors.splice(editors.indexOf(entry), 1);
        editor.remove();
        changed();
      }));
      facts.append(editor);
    }

    for (const fact of draft.facts ?? []) addFact(fact);
    if (opening.stale_audience) {
      row.append(element("p", "The cast has changed. Review each audience before saving again."));
    }
    const fields = () => ({
      location: location.value, situation: situation.value, first_choice: choice.value,
      gm_pressure: pressure.value,
      npc_pilots: Array.from(npcPilots.selectedOptions, option => option.value),
      session_zero: {
        tone: tone.value, offscreen: offscreen.value, handler_initiative: initiative.value,
        human_fallback: fallback.value,
      },
      facts: editors.map(({factText, source, recipients}) => ({
        text: factText.value, learned_from: source.value,
        known_by: Array.from(recipients.selectedOptions, option => option.value),
      })),
    });
    row.append(button("Add starting fact", () => {
      if (editors.length >= 16) throw new Error("An opening can include up to 16 facts.");
      addFact();
      changed();
    }), button("Save opening draft", async key => {
      if (Array.from(row.querySelectorAll("input")).some(input => !input.reportValidity())) return;
      await write("opening-save", {revision: opening.revision, draft: fields()}, key);
      await refresh();
    }, () => JSON.stringify(fields())));

    if (opening.draft) {
      const preview = card(row, "Who knows what");
      preview.append(element("p", "The opening location, situation and first decision are planned for the full cast."));
      for (const role of opening.previews) {
        const list = element("ul");
        for (const fact of role.facts) list.append(element("li", fact));
        preview.append(element("h5", role.label), role.facts.length ? list : element("p", "No assigned facts."));
      }
      for (const blocker of opening.blockers) preview.append(element("p", blocker));
      if (!opening.blockers.length) {
        const launch = button("Launch reviewed opening", async key => {
          await write("opening-launch", {review: opening.review}, key);
          await refresh();
        });
        const confirm = element("details");
        confirm.append(element("summary", "Review & launch"),
          element("p", "Launch publishes the saved draft to the approved cast."), launch);
        // Compare the live fields with the reviewed values in their form order.
        const reviewedFields = JSON.stringify(fields());
        changed = () => { launch.disabled = JSON.stringify(fields()) !== reviewedFields; };
        row.addEventListener("input", changed);
        preview.append(confirm);
      }
    }
  }

  function renderBrief(brief) {
    const row = card(body, "Your opening brief");
    row.append(element("p", brief.location), element("p", brief.situation), element("p", brief.first_choice));
    for (const role of brief.roles) {
      if (!role.facts.length) continue;
      const list = element("ul");
      for (const fact of role.facts) list.append(element("li", fact));
      row.append(element("h5", role.label), list);
    }
    const settings = brief.session_zero;
    const agreement = card(row, "Session Zero notes");
    if (settings.tone) agreement.append(element("p", "Tone · " + settings.tone));
    if (settings.offscreen) agreement.append(element("p", "Offscreen · " + settings.offscreen));
    agreement.append(element("p", "Handler · " + settings.handler_initiative));
    if (settings.human_fallback) agreement.append(element("p", "Human fallback · " + settings.human_fallback));
  }

  const timeSlots = [["morning", "Morning"], ["afternoon", "Afternoon"], ["night", "Night"]];
  const slotText = position => `Day ${position.day} · ${position.slot}`;
  const minuteText = minute => `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;

  function timeField(parent, label) {
    const [row, input] = field(label, "");
    input.type = "time";
    parent.append(row);
    return () => {
      if (!/^\d\d:\d\d$/.test(input.value)) throw new Error("Enter a fictional time.");
      const [hour, minute] = input.value.split(":").map(Number);
      return hour * 60 + minute;
    };
  }

  function positionFields(parent, label, at) {
    const [dayLabel, day] = field(`${label} day`, at?.day);
    day.type = "number";
    day.min = "1";
    const [slotLabel, slot] = choiceField(`${label} slot`, timeSlots, at?.slot);
    parent.append(dayLabel, slotLabel);
    return () => ({day: Number(day.value), slot: slot.value});
  }

  function timeForm(parent, label) {
    const panel = element("details");
    panel.append(element("summary", label));
    parent.append(panel);
    return panel;
  }

  function timeSave(parent, label, route, values) {
    parent.append(button(label, async key => {
      const result = await write(route, values(), key);
      await refresh();
      if (result.reason) status.textContent = "Waiting for the Handler to review the timing.";
      if (result.action_id) status.textContent = "Timed Play opened. Continue with the scene’s Play controls.";
    }, () => {
      try { return JSON.stringify(values()); } catch { return ""; }
    }));
  }

  function renderCalendar(row, view, controls) {
    if (view.mode === "legacy") {
      if (!controls) return;
      const form = timeForm(row, "Set the fictional calendar");
      const [title, chapter] = field("Opening chapter", "");
      const position = positionFields(form, "Opening", {day: 1, slot: "morning"});
      form.append(title);
      timeSave(form, "Initialize calendar", "time-initialize", () => ({anchor: {chapter: chapter.value, position: position()}}));
      return;
    }
    row.append(element("p", `${view.anchor.chapter} · ${slotText(view.anchor.position)}`));
    for (const booking of view.scenes) {
      const line = `${booking.chapter} · ${slotText(booking.start)} to ${slotText(booking.end)} · ${booking.status}`;
      row.append(element("p", line));
      for (const entry of booking.entries) row.append(element("p", entry.account));
      if (booking.status === "late" && (booking.joined || controls)) {
        const form = timeForm(row, "Late debrief");
        const [entryLabel, entry] = field("Debrief account", "");
        form.append(entryLabel);
        const submission = kind => ({scene: booking.id, cut: booking.late_cut, entry: {kind, account: entry.value}});
        timeSave(form, "Request review", "time-late", () => submission("uncertain"));
        if (controls) {
          timeSave(form, "Record narration", "time-late", () => submission("narration"));
          timeSave(form, "Close late debrief", "time-late-close", () => ({scene: booking.id, cut: booking.late_cut}));
        }
      }
    }
    if (!controls) return;
    const scenes = [...view.unscheduled_scenes, ...view.scenes.filter(s => ["open", "scheduled"].includes(s.status))];
    if (scenes.length && controls.pilots.length) {
      const form = timeForm(row, "Schedule a scene");
      const [selectLabel, select] = choiceField("Scene to schedule", scenes.map(s => [s.id, s.chapter ?? `Channel ${s.channel}`]), "");
      const [pilotsLabel, pilots] = choiceField("Scheduled Pilots", controls.pilots.map(p => [p.id, p.label]), "");
      pilots.options[0].remove();
      pilots.multiple = true;
      const [lateLabel, late] = field("Allow a late debrief", "");
      late.type = "checkbox";
      form.append(selectLabel, pilotsLabel);
      const start = positionFields(form, "Scene starts", view.anchor.position);
      const end = positionFields(form, "Scene ends", view.anchor.position);
      form.append(lateLabel);
      timeSave(form, "Save scene booking", "time-schedule", () => {
        const booking = scenes.find(s => s.id === select.value);
        if (!booking) throw new Error("Choose a scene to schedule.");
        return {scene: booking.id, channel: booking.channel, revision: booking.scene_revision ?? booking.revision,
          anchor: view.anchor_receipt, plan: {start: start(), end: end(),
            participants: [...pilots.selectedOptions].map(p => p.value), allow_late_narration: late.checked}};
      });
    }
    const form = timeForm(row, "Review a chapter cut");
    const position = positionFields(form, "Cut to", view.anchor.position);
    const [title, chapter] = field("Next chapter", view.anchor.chapter);
    const review = element("div");
    form.append(title, button("Preview chapter cut", async key => {
      const cut = {target: {chapter: chapter.value, position: position()}};
      const preview = await write("time-preview", {cut}, key);
      review.replaceChildren();
      for (const blocker of preview.blockers) {
        review.append(element("p", blocker.kind.replaceAll("_", " ") + (blocker.id ? ` · ${blocker.id}` : "")));
      }
      if (!preview.blockers.length) timeSave(review, "Confirm chapter cut", "time-cut", () => ({cut, token: preview.token}));
    }), review);
    form.addEventListener("input", () => review.replaceChildren());
  }

  function renderMissionClock(row, view, controls) {
    const clock = view.mission_timing;
    if (!clock) {
      const mission = controls?.active_mission;
      const rooms = view.scenes.filter(s => s.status === "open");
      if (!mission || !rooms.length) return;
      const form = timeForm(row, "Open a timed mission scene");
      const [roomLabel, room] = choiceField("Timed scene", rooms.map(s => [s.id, `${s.chapter} · ${slotText(s.start)}`]), "");
      form.append(roomLabel);
      const minute = timeField(form, "Clock starts");
      const deadline = timeField(form, "Deadline time");
      const [boundaryLabel, boundary] = choiceField("Cutoff", [["before", "Before this time"], ["by", "By this time"]], "before");
      const [labelRow, label] = field("Deadline label", "");
      form.append(boundaryLabel, labelRow);
      timeSave(form, "Open mission clock", "time-open", () => {
        const selected = rooms.find(s => s.id === room.value);
        if (!selected) throw new Error("Choose an open scheduled scene.");
        return {mission: mission.id, revision: mission.revision, channel: selected.channel, scene: selected.id,
          anchor: view.anchor_receipt, start: {minute: minute(), deadline: {minute: deadline(), boundary: boundary.value, label: label.value}}};
      });
      return;
    }
    const head = `${minuteText(clock.minute)} · ${clock.deadline.label} ${clock.deadline.boundary} ${minuteText(clock.deadline.minute)}`;
    row.append(element("h5", "Mission clock"), element("p", `${head} · ${clock.deadline_status.replaceAll("_", " ")}`));
    if (clock.consequence_receipt) row.append(element("p", clock.deadline.consequence));
    if (clock.ruling) row.append(element("p", clock.ruling.reason.replaceAll("_", " ")));
    const own = clock.options.filter(option => option.pilot === view.viewer);
    const chosen = own.some(option => clock.selected.some(choice => choice.option === option.id));
    for (const option of own) {
      const picked = clock.selected.find(choice => choice.option === option.id);
      const quote = option.arrival_minute === null ? "Duration needs review" : `${option.estimated ? "Estimated arrival" : "Arrival"} ${minuteText(option.arrival_minute)}`;
      row.append(element("p", `${option.label} · ${quote}${picked ? " · Selected" : ""}`));
      if (!clock.ruling && !chosen) {
        timeSave(row, `Choose ${option.label}`, "time-choose", () => ({id: clock.id, menu: clock.menu_receipt, option: option.id}));
      }
      if (picked && option.play) {
        const play = timeForm(row, "Begin timed Keep Your Head");
        const [contextLabel, context] = field("Describe what you do", "");
        const [heatLabel, heat] = field("Heat to spend", 0);
        heat.type = "number";
        play.append(contextLabel, heatLabel);
        timeSave(play, "Confirm and open native Play", "time-begin-play", () => ({channel: clock.channel,
          sheet_revision: view.sheet_revision, selection: picked.receipt, context: context.value, heat: Number(heat.value)}));
        timeSave(play, "Withdraw timed choice", "time-withdraw", () => ({id: clock.id, selection: picked.receipt}));
      }
    }
    if (!controls) return;
    const revision = () => ({id: clock.id, revision: clock.revision});
    if (!clock.deadline.consequence) {
      const form = timeForm(row, "Define the missed-deadline consequence");
      const [label, answer] = field("Fictional consequence", "");
      form.append(label);
      timeSave(form, "Save consequence", "time-consequence", () => ({...revision(), account: answer.value}));
    }
    if (!clock.selected.length && controls.clock_pilots.length) {
      const form = timeForm(row, "Publish Pilot options");
      const [modeLabel, mode] = choiceField("Exchange", [["single", "One Pilot"], ["parallel", "Parallel Pilots"]], "single");
      const list = element("div");
      const choices = controls.pilots.filter(p => controls.clock_pilots.includes(p.id)).map(p => [p.id, p.label]);
      const options = [];
      const add = () => {
        const id = crypto.randomUUID();
        const group = element("fieldset");
        const [pilotLabel, pilot] = choiceField("Option Pilot", choices, "");
        const [labelRow, label] = field("Option", "");
        const [minutesLabel, minutes] = field("Option minutes", "");
        minutes.type = "number";
        const [estimateLabel, estimate] = field("Estimated duration", "");
        estimate.type = "checkbox";
        const [playLabel, play] = field("Use Keep Your Head", "");
        play.type = "checkbox";
        group.append(pilotLabel, labelRow, minutesLabel, estimateLabel, playLabel);
        list.append(group);
        options.push(() => ({id, pilot: pilot.value, label: label.value, minutes: minutes.value === "" ? null : Number(minutes.value),
          estimated: estimate.checked, play: play.checked ? "keep_your_head" : null}));
      };
      add();
      form.append(modeLabel, list, button("Add option", async () => { if (options.length < 25) add(); }));
      timeSave(form, "Publish options", "time-publish", () => ({...revision(), options: {mode: mode.value, available: options.map(read => read())}}));
    }
    if (clock.mode === "parallel" && clock.selected.length) {
      const form = timeForm(row, "Resolve the parallel exchange");
      const minute = timeField(form, "Common ending time");
      const [label, account] = field("What brought the Pilots back together", "");
      form.append(label);
      timeSave(form, "Confirm parallel ending", "time-rejoin", () => ({...revision(), rejoin: {minute: minute(), account: account.value}}));
    }
    timeSave(row, "Close mission clock", "time-close", revision);
  }

  function renderHandlerProfile(parent, profile) {
    parent.replaceChildren();
    parent.hidden = !profile;
    if (!profile) return;
    const guidance = [["Routine voice", profile.voice], ["When to step in", profile.initiative],
      ["When to hold back", profile.behavior.wait], ["Under pressure", profile.behavior.under_pressure],
      ["After a mistake", profile.behavior.recovery], ["Strength", profile.behavior.strength],
      ["Blind spot", profile.behavior.blind_spot]];
    parent.append(element("summary", "Playbook guidance"));
    for (const [label, detail] of guidance) parent.append(element("p", label + " · " + detail));
  }

  function renderHandlerRules(parent, rules) {
    parent.append(element("summary", "Plays and advancement"), element("h5", "Shared Plays"));
    for (const rule of rules.shared) parent.append(element("p", rule.title + " · " + rule.trigger));
    const access = {draft: "On creation", owned: "Check the native trigger", gated: "Release or ownership required"};
    for (const rule of rules.playbook) {
      parent.append(element("h5", `${rule.title} · ${rule.book}`),
        element("p", `${rule.kind} · ${access[rule.access]}`), element("p", rule.trigger));
    }
    for (const [label, triggers] of [["Shared advancement triggers", rules.shared_advancement_triggers],
      ["Playbook advancement triggers", rules.advancement_triggers]]) {
      if (!triggers.length) continue;
      const list = element("ul");
      for (const trigger of triggers) list.append(element("li", trigger));
      parent.append(element("h5", label), list);
    }
  }

  function renderHandlerNotes(parent, sheet) {
    const notes = element("details");
    notes.append(element("summary", "Private roleplay notes"));
    parent.append(notes);
    const current = sheet.draft.notes ?? {};
    if (!sheet.editable && !sheet.notes_editable) {
      for (const [key, label] of sheet.note_fields) {
        if (current[key]) notes.append(element("p", label + " · " + current[key]));
      }
      return () => null;
    }
    const fields = sheet.note_fields.map(([key, name]) => {
      const label = element("label", name);
      const input = element("textarea");
      input.value = current[key] ?? "";
      input.rows = 2;
      input.maxLength = 400;
      label.append(input);
      notes.append(label);
      return [key, input];
    });
    function values() {
      const saved = Object.fromEntries(fields.map(([key, input]) => [key, input.value.trim()]).filter(([, value]) => value));
      return Object.keys(saved).length ? saved : null;
    }
    if (sheet.notes_editable) {
      notes.append(button("Save roleplay notes", async key => {
        await write("persona-notes", {revision: sheet.revision, persona_id: sheet.persona_id, notes: values()}, key);
        await refresh();
      }, () => JSON.stringify(values())));
    }
    return values;
  }

  function renderPersona(setup) {
    for (const request of setup.requests.filter(x => x.kind !== "handler_creation" && !x.stale)) {
      const row = card(body, request.label);
      if (!request.actionable) {
        row.append(element("p", "Waiting for " + request.assignee + " to answer."));
        continue;
      }
      row.append(button("Review starting relationship", async () => {
        const review = await read("persona-agreement/" + routeId(request.id));
        const choice = review.proposal.bond ?? review.proposal.relationship;
        const response = element("div");
        response.append(element("p", choice.history));
        if (choice.rank) response.append(element("p", `Starting rank · ${choice.rank}. Bond depth · ${choice.depth}`));
        if (review.proposal.phrases?.length) response.append(element("p", review.proposal.phrases.join(", ")));
        for (const [accept, label] of [[true, "Accept relationship"], [false, "Decline relationship"]]) {
          const action = button(label, async key => {
            await write("persona-answer", {id: request.id, revision: review.revision, accept}, key);
            await refresh();
          });
          action.disabled = !review.can_answer;
          response.append(action);
        }
        row.replaceChildren(response);
      }));
    }
    const sheet = setup.sheet;
    if (!sheet) return;
    const row = card(body, "Handler character sheet");
    const guidance = element("details");
    const rules = element("details");
    renderHandlerProfile(guidance, sheet.playbook_profile);
    renderHandlerRules(rules, sheet.rules);
    if (sheet.activated || !sheet.editable) {
      row.append(element("p", [sheet.draft.name, sheet.playbook].filter(Boolean).join(" · ")), guidance, rules);
      renderHandlerNotes(row, sheet);
      for (const value of [sheet.draft.appearance, sheet.draft.outfit, sheet.draft.background]) {
        if (value) row.append(element("p", value));
      }
      for (const gear of sheet.draft.gear) row.append(element("p", gear.description));
      return;
    }
    const draft = sheet.draft;
    const [playbookLabel, playbook] = choiceField("Handler playbook", setup.playbooks.map(x => [x, x]), draft.playbook);
    row.append(playbookLabel, guidance, rules);
    playbook.addEventListener("change", () => {
      renderHandlerProfile(guidance, setup.profiles[playbook.value]);
      rules.hidden = (playbook.value || null) !== sheet.playbook;
    });
    const details = Object.fromEntries([
      ["name", "Handler name"], ["appearance", "Handler appearance"],
      ["outfit", "Handler outfit"], ["background", "Handler background"],
    ].map(([key, label]) => {
      const [inputLabel, input] = field(label, draft[key]);
      row.append(inputLabel);
      return [key, input];
    }));
    const gearInputs = [0, 1].map(i => {
      const item = draft.gear[i];
      const [pick, kind] = choiceField(`Gear ${i+1}`, setup.gear, item?.kind);
      const [descriptionLabel, description] = field(`Gear ${i+1} description`, item?.description);
      row.append(pick, descriptionLabel);
      return {kind, description};
    });
    const readNotes = renderHandlerNotes(row, sheet);
    const relationships = element("details");
    relationships.append(element("summary", "Starting relationships"));
    row.append(relationships);
    if (!sheet.pilots.length) relationships.append(element("p", "Pilots can be selected after they activate their sheets."));
    const bondInputs = [0, 1].map(i => {
      const rank = i === 0 ? "ace" : "dog";
      const item = draft.starting.find(x => x.rank === rank);
      const role = sheet.pilots.find(x => JSON.stringify(x.ref) === JSON.stringify(item?.pilot));
      const [pilotLabel, pilot] = choiceField(`Starting ${rank}`, sheet.pilots.map(x => [x.token, x.label]), role?.token);
      const [depthLabel, depth] = choiceField(`Starting ${rank} Bond`, [["1", "Personal"], ["2", "Intense"]], String(item?.depth ?? 1));
      const [historyLabel, history] = field(`Starting ${rank} history`, item?.history);
      const promptRow = element("div");
      let prompt;
      function refreshPrompts(selected) {
        const result = choiceField(`Starting ${rank} prompt`, (setup.histories[playbook.value] ?? []).map((x, j) => [String(j), x]), selected);
        prompt = result[1];
        promptRow.replaceChildren(result[0]);
      }
      refreshPrompts(item?.prompt == null ? "" : String(item.prompt));
      playbook.addEventListener("change", () => refreshPrompts(""));
      relationships.append(pilotLabel, depthLabel, historyLabel, promptRow);
      return () => pilot.value ? {
        pilot: sheet.pilots.find(x => x.token === pilot.value).ref,
        rank, depth: Number(depth.value || 1), history: history.value,
        prompt: prompt.value === "" ? null : Number(prompt.value),
      } : null;
    });
    const npcFields = element("section");
    const npcChoices = sheet.npcs.map(x => [x.id, x.name]);
    const npcInputs = ["Surveilled NPC 1", "Surveilled NPC 2", "Sympathizer"].map((label, i) => {
      const id = i === 2 ? draft.sympathizer : draft.surveilled[i];
      const saved = draft.npc_starting.find(x => x.npc.entity === id);
      const [npcLabel, npc] = choiceField(label, npcChoices, id);
      const [historyLabel, history] = field(label + " history", saved?.history);
      npcFields.append(npcLabel, historyLabel);
      return {npc, history};
    });
    npcFields.hidden = playbook.value !== "Insurgent";
    playbook.addEventListener("change", () => { npcFields.hidden = playbook.value !== "Insurgent"; });
    relationships.append(npcFields);
    function values() {
      const selected = playbook.value === "Insurgent" ? npcInputs.map(x => x.npc.value) : [];
      const npcStarting = new Map();
      for (const {npc, history} of npcInputs) {
        if (!selected.includes(npc.value) || !npc.value || !history.value.trim()) continue;
        const actual = sheet.npcs.find(x => x.id === npc.value);
        npcStarting.set(actual.id, {npc: {kind: "npc", entity: actual.id}, controller: actual.controller, history: history.value});
      }
      return {
        playbook: playbook.value || null,
        ...Object.fromEntries(Object.entries(details).map(([key, input]) => [key, input.value])),
        gear: gearInputs.filter(x => x.kind.value).map(x => ({kind: x.kind.value, description: x.description.value})),
        starting: bondInputs.map(readBond => readBond()).filter(Boolean),
        surveilled: selected.slice(0, 2).filter(Boolean), sympathizer: selected[2] || null,
        npc_starting: [...npcStarting.values()],
        notes: readNotes(),
      };
    }
    row.append(button("Save Handler draft", async key => {
      await write("persona-save", {
        revision: sheet.revision, generation: sheet.generation, appointment: sheet.appointment, draft: values(),
      }, key);
      await refresh();
    }, () => JSON.stringify(values())));
    if (sheet.missing.length) {
      row.append(element("p", "Still needed · " + sheet.missing.join(", ")));
    } else {
      const reviewed = JSON.stringify(values());
      const propose = button("Send starting relationship requests", async key => {
        await write("persona-propose", {revision: sheet.revision, generation: sheet.generation}, key);
        await refresh();
      });
      const confirmation = element("details");
      confirmation.append(element("summary", "Review Handler activation"),
        element("p", "Activation applies the approved starting choices to the campaign."));
      const activate = button("Activate approved Handler", async key => {
        await write("persona-activate", {revision: sheet.revision, game_revision: sheet.game_revision, confirmed: true}, key);
        await refresh();
      });
      confirmation.append(activate);
      row.addEventListener("input", () => { propose.disabled = activate.disabled = JSON.stringify(values()) !== reviewed; });
      row.append(propose, confirmation);
    }
  }

  function renderOwn(work) {
    const owned = card(body, "Your pending decisions");
    if (work.native.choices.length) {
      owned.append(element("p", "Open Scene Plays or the Inbox for your native choices."));
    }
    for (const item of work.proposals.filter(x => x.status === "awaiting_confirmation")) {
      const row = card(owned, "Review " + item.operation.replaceAll("_", " "));
      row.append(button("Preview ruling", async () => {
        const review = await read("owner-review/" + routeId(item.id));
        const decision = review.decision;
        const summary = decision.narration ?? Object.values(decision.answers ?? {}).join("\n");
        if (summary) row.append(element("p", summary));
        const structured = element("pre", JSON.stringify(decision, null, 2));
        const fields = element("details");
        fields.append(element("summary", "Ruling details"), structured);
        row.append(fields, button("Confirm ruling", async key => {
          await write("ruling-confirm", {proposal: item.id}, key);
          await refresh();
        }));
      }));
    }
    if (!work.native.choices.length && !owned.querySelector("button")) {
      owned.append(element("p", "No pending decisions."));
    }
  }

  function renderHandler(work) {
    if (!work.handler_deliveries.length) return;
    const queue = card(body, "Handler delivery");
    for (const item of work.handler_deliveries) {
      const row = card(queue, "Approved scene reply");
      row.append(button("Preview Handler reply", async () => {
        const preview = await read("handler-preview/" + routeId(item.id));
        const content = element("div");
        content.append(element("p", preview.text));
        if (preview.action) content.append(element("p", preview.action));
        content.append(button("Deliver Handler reply", async key => {
          await write("handler-deliver", {draft: item.id}, key);
          await refresh();
        }));
        row.replaceChildren(element("h4", "Approved scene reply"), content);
      }));
    }
  }

  function renderFacilitator(gm) {
    const queue = card(body, "Facilitator review");
    if (gm.fictional_time?.clock) {
      const clock = gm.fictional_time.clock;
      queue.append(element("p", `Saved scene clock · ${minuteText(clock.minute)} ${clock.boundary} ${minuteText(clock.deadline)} · ${clock.status.replaceAll("_", " ")}`));
    }
    if (!gm.handler_drafts.length && !gm.outcome_sources.length) {
      queue.append(element("p", "No pending reviews."));
    }
    for (const item of gm.handler_drafts) {
      const row = card(queue, "Handler draft");
      if (item.status === "stale_reopen_source") {
        row.append(element("p", "Source changed. Review the current message."));
        continue;
      }
      row.append(button("Review Handler draft", async () => {
        const draft = await read("handler-draft/" + routeId(item.id));
        if (draft.status === "stale_reopen_source") {
          await refresh();
          status.textContent = "Source changed. Review the current message.";
          return;
        }
        const [label, reason] = field("Review reason");
        const approve = button("Approve Handler draft", async key => {
          if (!reason.reportValidity()) return;
          await write("handler-approve", {
            draft: item.id, reason: reason.value, recipients: [draft.source_actor],
          }, key);
          await refresh();
        }, () => reason.value);
        const reject = button("Reject Handler draft", async key => {
          if (!reason.reportValidity()) return;
          await write("handler-reject", {draft: item.id, reason: reason.value}, key);
          await refresh();
        }, () => reason.value);
        row.replaceChildren(element("h4", "Handler draft"), element("p", draft.reply.text));
        if (draft.reply.handler_action) row.append(element("p", draft.reply.handler_action));
        row.append(label, approve, reject);
      }));
    }
    for (const item of gm.outcome_sources) {
      const row = card(queue, item.operation.replaceAll("_", " "));
      if (item.operation === "table") {
        row.append(element("p", "Use the native GM choice to select the table outcome."));
        continue;
      }
      row.append(element("p", item.action_id ? "Pending on the native Play." : "Pending native work."));
      if (!gm.model_rulings) continue;
      const [stakesLabel, stakes] = field("What is at stake?");
      const [demandLabel, demand] = field("What must the attempt accomplish?");
      const scopeLabel = element("label", "Whose response determines the goal?");
      const scope = element("select");
      for (const [value, label] of [["unresolved", "Unclear"], ["self", "Acting Pilot"]]) {
        const option = element("option", label);
        option.value = value;
        scope.append(option);
      }
      for (const target of gm.response_targets) {
        const option = element("option", target.label + " (other actor)");
        option.value = JSON.stringify(target.actor);
        scope.append(option);
      }
      scopeLabel.append(scope);
      if (item.frame_required) row.append(stakesLabel, demandLabel, scopeLabel);
      row.append(button("Generate ruling for review", async key => {
        let frame = null;
        if (item.frame_required) {
          if (!stakes.reportValidity() || !demand.reportValidity()) return;
          frame = {
            stakes: stakes.value,
            demands: [{id: "goal", question: demand.value}],
            response_scope: scope.value.startsWith("{") ? "other" : scope.value,
          };
          if (frame.response_scope === "other") frame.response_target = JSON.parse(scope.value);
        }
        const opened = await write("ruling-open", {
          source_kind: item.source_kind, source_id: item.source_id, frame,
        }, key + ".open");
        await write("ruling-generate", {request: opened.id}, key + ".generate");
        await refresh();
      }, () => JSON.stringify([stakes.value, demand.value, scope.value])));
    }
    if (gm.npc_roster.length) {
      const roster = card(queue, "Campaign NPCs");
      const list = element("ul");
      for (const npc of gm.npc_roster) {
        list.append(element("li", npc.name + (npc.support_play ? " · Handler support" : "") +
          (npc.present ? " · In this scene" : "")));
      }
      roster.append(list);
    }
  }

  async function refresh() {
    const [work, gm, opening, brief, persona, policy, observation, review, time] = await Promise.all([
      scene ? read("work", true) : null, scene ? read("gm-work", true) : null,
      read("opening", true), read("opening-brief", true), read("persona-setup", true),
      activityShadow ? read("activity-policy", true) : null,
      activityShadow ? read("status", true) : null,
      activityShadow ? read("activity-review", true) : null,
      read("fictional-time", true),
    ]);
    body.replaceChildren();
    if (activityShadow) renderShadow(policy, observation, review);
    if (opening) renderOpening(opening);
    if (brief?.launched) renderBrief(brief);
    if (persona) renderPersona(persona);
    if (time && (time.mode === "asynchronous" || time.handler_controls)) {
      const row = card(body, "Fictional time");
      renderCalendar(row, time, time.handler_controls);
      if (time.mode === "asynchronous") renderMissionClock(row, time, time.handler_controls);
    }
    if (!work && scene) {
      body.append(element("p", "Scene work is unavailable. Check scene membership and consent."));
    } else if (work) {
      renderHandler(work);
      if (gm) renderFacilitator(gm);
      renderOwn(work);
    }
    body.append(button(scene ? "Refresh Director work" : "Refresh campaign setup", refresh));
  }

  details.addEventListener("toggle", () => {
    if (details.open) refresh().catch(error => {
      body.replaceChildren();
      status.textContent = error.message;
    });
  });
}
