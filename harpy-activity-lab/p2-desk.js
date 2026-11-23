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

function textArea(panel, label, value, maxLength, required = true) {
  const row = element("label", label);
  const text = element("textarea");
  text.value = value ?? "";
  text.maxLength = maxLength;
  text.required = required;
  row.append(text);
  panel.append(row);
  return text;
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

export function openSheetPortrayal({activityFetch, scene, kind}) {
  const root = scene ? "/api/director/" + encodeURIComponent(scene) + "/" : "/api/campaign-opening/";
  const dialog = element("dialog");
  dialog.className = "activity-dialog terminal-dialog";
  const body = element("section");
  const status = element("p");
  status.setAttribute("role", "status");
  dialog.setAttribute("aria-label", "Character portrayal");
  const close = element("button", "Close");
  close.type = "button";
  close.addEventListener("click", () => dialog.close());
  dialog.append(element("h2", "Character portrayal"), close, status, body);
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  const active = new AbortController();
  dialog.addEventListener("close", () => active.abort());
  let token;
  const traits = [
    ["archetype", "Archetype", 60], ["vibe", "Vibe", 60], ["voice", "How they speak", 1000],
    ["approach", "What they do first", 1000], ["pressure", "Under pressure", 500],
    ["repair", "After a mistake", 400], ["value", "What they value", 500],
    ["fear", "What they fear", 500], ["contradiction", "Contradiction", 500],
    ["goal", "Personal goal", 400], ["initiative", "When they step in", 400],
  ];
  const handlerLabels = {
    voice:"Voice", priority:"What they protect first", intervention:"When they step in or wait",
    repair:"How they repair trust", concern:"Current concern", promise:"Current promise",
    obligation:"Obligation",
  };
  const memoryLabels = {
    experiences:"Experience", promises:"Promise", relationships:"View of someone",
    pressures:"Personal pressure", obligations:"Obligation", beliefs:"Belief", terms:"Relationship term",
  };
  const continuityLabels = {
    intention:"Intention", commitment:"Commitment", relationship:"View of someone",
  };
  const pressureLabels = {open:"Open", deferred:"Set aside", resolved:"Resolved", withdrawn:"Withdrawn"};

  async function request(route, data, key) {
    const response = await activityFetch(root + route, {
      signal: active.signal,
      ...(data ? {method:"POST", headers:{"Content-Type":"application/json", "Idempotency-Key":key},
        body:JSON.stringify(data)} : {}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The current portrayal is unavailable.");
    return result;
  }

  function action(parent, label, run, intent = () => "") {
    const button = element("button", label);
    button.type = "button";
    let key = crypto.randomUUID();
    let previous;
    button.addEventListener("click", async () => {
      const current = intent();
      if (current !== previous) key = crypto.randomUUID();
      previous = current;
      button.disabled = true;
      status.textContent = "";
      try {
        await run(key);
        key = crypto.randomUUID();
      } catch (error) {
        if (!active.signal.aborted) status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
    parent.append(button);
    return button;
  }

  function area(parent, name, value, maxLength) {
    const label = element("label", name);
    const input = element("textarea");
    input.rows = 2;
    input.maxLength = maxLength;
    input.value = value ?? "";
    label.append(input);
    parent.append(label);
    return input;
  }

  function details(parent, name) {
    const panel = element("details");
    panel.append(element("summary", name));
    parent.append(panel);
    return panel;
  }

  function writeConfirm(parent, sheet, id, label, openPreview = false) {
    return action(parent, label, async key => {
      await request("portrayal-confirm", {actor:sheet.actor, id}, key);
      await load(openPreview);
      status.textContent = "Approved and saved.";
    });
  }

  function editPortrayal(parent, sheet, catalogs) {
    const pending = sheet.pending?.kind === "portrayal" && !sheet.pending.stale
      ? sheet.pending : null;
    const values = pending?.portrayal ?? sheet.portrayal ?? {};
    const main = element("div");
    parent.append(main);
    const labels = {};
    if (sheet.actor.kind === "npc") {
      for (const [key, label, options] of [
        ["girl_playbook", "Girl playbook for portrayal", catalogs.girl_types],
        ["frame_playbook", "Frame for portrayal", catalogs.frame_types],
      ]) {
        const [field, select] = choiceField(label, Object.entries(options ?? {}), values[key]);
        labels[key] = select;
        main.append(field);
      }
    }
    const extra = details(parent, "Identity and motivations");
    const featured = new Set(["voice", "approach", "pressure", "repair"]);
    const inputs = traits.map(([key, label, limit]) => [
      key, area(featured.has(key) ? main : extra, label, values[key], limit),
    ]);
    const save = () => ({
      actor:sheet.actor, version:sheet.version,
      portrayal:Object.fromEntries(
        [...inputs, ...Object.entries(labels)].map(([key, input]) => [key, input.value.trim()])),
    });
    action(parent, "Save portrayal draft", async key => {
      await request("portrayal-draft", save(), key);
      await load();
      status.textContent = "Draft saved for your approval.";
    }, () => JSON.stringify(save()));
    if (pending) {
      const approve = writeConfirm(parent, sheet, pending.id, "Approve saved portrayal");
      for (const [, input] of inputs) input.addEventListener("input", () => { approve.disabled = true; });
      for (const select of Object.values(labels)) select.addEventListener("change", () => { approve.disabled = true; });
    }
  }

  const setupLabels = [
    ["drive", "What they want right now", 500],
    ["fear", "What they are afraid of losing", 500],
    ["contradiction", "Where their duty and instincts pull apart", 500],
    ["default_approach", "What they try first", 500],
    ["resources", "People, access or tools they can lean on (one per line)", 1600],
    ["limits", "What they will refuse or protect (one per line)", 1600],
    ["voice_at_ease", "Voice in routine conversation", 500],
    ["voice_under_pressure", "Voice when challenged", 500],
    ["voice_on_repair", "Voice when repairing trust", 500],
  ];

  function editCharacterSetup(parent, sheet) {
    const panel = details(parent, "Session Zero · Character direction");
    const pending = sheet.pending?.kind === "character_setup" && !sheet.pending.stale
      ? sheet.pending : null;
    const values = pending?.character_setup ?? sheet.character_setup ?? {};
    panel.open = !!pending || !sheet.character_setup;
    const inputs = setupLabels.map(([key, label, length]) => {
      const value = values[key];
      return [key, area(panel, label, Array.isArray(value) ? value.join("\n") : value, length)];
    });
    const save = () => ({
      actor: sheet.actor, version: sheet.version,
      character_setup: Object.fromEntries(inputs.map(([key, input]) => [
        key, ["resources", "limits"].includes(key)
          ? input.value.split("\n").map(line => line.trim()).filter(Boolean)
          : input.value.trim(),
      ])),
    });
    action(panel, "File direction for review", async key => {
      await request("portrayal-draft", save(), key);
      await load();
      status.textContent = "Awaiting controller approval.";
    }, () => JSON.stringify(save()));
    if (pending) {
      const approve = writeConfirm(panel, sheet, pending.id, "Approve character direction");
      for (const [, input] of inputs) input.addEventListener("input", () => { approve.disabled = true; });
    }
  }

  function approvedProfile(parent, preview) {
    const profile = preview.profile;
    if (profile?.pilot_portrayal) {
      for (const [key, label] of [["girl_playbook", "Girl playbook"], ["frame_playbook", "Frame"]]) {
        if (profile.pilot_portrayal[key]) parent.append(element("p", label + " · " + profile.pilot_portrayal[key]));
      }
      for (const [key, label] of traits) {
        if (profile.pilot_portrayal[key]) parent.append(element("p", label + " · " + profile.pilot_portrayal[key]));
      }
    } else if (profile) {
      for (const [key, label] of [["voice","Voice"], ["behavior","Behavior"], ["background","Background"]]) {
        if (profile[key]) parent.append(element("p", label + " · " + profile[key]));
      }
      for (const key of ["values", "fears", "contradictions", "reaction_tendencies", "limits"]) {
        for (const value of profile[key]) parent.append(element("p", value));
      }
    }
    if (preview.playbook_profile) parent.append(element("p", "Handler playbook · " + preview.playbook_profile.playbook));
    const relationship = preview.handler_identity?.starting_relationship;
    if (relationship) parent.append(element("p", "Approved starting relationship · " + relationship.shared_history));
    for (const [key, value] of Object.entries(preview.character_notes ?? {})) {
      parent.append(element("p", (handlerLabels[key] ?? key) + " · " + value));
    }
    if (profile?.character_setup) {
      for (const [key, label] of setupLabels) {
        const value = profile.character_setup[key];
        const summary = Array.isArray(value) ? value.join(" · ") : value;
        if (summary) parent.append(element("p", label.split(" (")[0] + " · " + summary));
      }
    }
  }

  function editMemory(parent, sheet, preview) {
    const form = details(parent, "Record a character memory");
    const [kindField, memoryKind] = choiceField("Type", Object.entries(memoryLabels), "experiences");
    const [subjectField, subject] = choiceField("About whom?", preview.memory_subjects.map(
      person => [JSON.stringify(person.actor), person.label]));
    const [sourceField, reference] = choiceField("Scene source", preview.context.references.map(
      item => [item.id, item.text]));
    const [termField, term] = choiceField("What happened?", [
      ["agreement", "Agreement"], ["refusal", "Refusal"], ["condition", "Condition offered"],
    ]);
    form.append(kindField, subjectField, termField, sourceField);
    const input = area(form, "What does this character remember or want?", "", 800);
    const pressures = new Map((preview.state?.pressures ?? [])
      .filter(entry => entry.pressure_id && ["open", "deferred"].includes(entry.pressure.status))
      .map(entry => [entry.pressure_id, entry]));
    const pressureFields = element("fieldset");
    pressureFields.append(element("legend", "Personal agenda"));
    const [existingField, existing] = choiceField("Existing pressure", [...pressures].map(
      ([id, entry]) => [id, entry.text]));
    existing.options[0].textContent = "Start a new pressure";
    const [statusField, pressureStatus] = choiceField("Status", Object.entries(pressureLabels), "open");
    pressureStatus.remove(0);
    pressureFields.append(existingField, statusField);
    const stake = area(pressureFields, "What do they want and why?", "", 500);
    const step = area(pressureFields, "Possible next step", "", 500);
    const blocker = area(pressureFields, "What stands in the way?", "", 500);
    const trigger = area(pressureFields, "What would make them act?", "", 500);
    const fallback = area(pressureFields, "What will they try if refused?", "", 500);
    const account = area(pressureFields, "What changed?", "", 800);
    const consequence = area(pressureFields, "What consequence did they witness?", "", 800);
    form.append(pressureFields);
    input.required = true;
    memoryKind.required = true;
    function sync() {
      term.required = memoryKind.value === "terms";
      termField.hidden = !term.required;
      subject.required = term.required || memoryKind.value === "relationships";
      subjectField.hidden = !subject.required;
      const editingPressure = memoryKind.value === "pressures";
      const prior = pressures.get(existing.value);
      const transition = editingPressure && prior && prior.pressure.status !== pressureStatus.value;
      pressureFields.hidden = !editingPressure;
      pressureStatus.disabled = !prior;
      stake.required = editingPressure;
      step.required = editingPressure && ["open", "deferred"].includes(pressureStatus.value);
      step.parentElement.hidden = !step.required;
      account.required = editingPressure && (transition || pressureStatus.value !== "open");
      reference.required = term.required || ["promises", "experiences"].includes(memoryKind.value)
        || Boolean(transition || (editingPressure && consequence.value.trim()));
    }
    memoryKind.addEventListener("change", sync);
    pressureStatus.addEventListener("change", sync);
    consequence.addEventListener("input", sync);
    existing.addEventListener("change", () => {
      const prior = pressures.get(existing.value);
      input.value = prior?.text ?? "";
      pressureStatus.value = prior?.pressure.status ?? "open";
      stake.value = prior?.pressure.stake ?? "";
      step.value = prior?.pressure.next_step ?? "";
      blocker.value = prior?.pressure.blocker ?? "";
      trigger.value = prior?.pressure.trigger ?? "";
      fallback.value = prior?.pressure.fallback ?? "";
      account.value = prior?.pressure.account ?? "";
      reference.value = "";
      sync();
    });
    sync();
    const save = () => ({actor:sheet.actor, version:sheet.version, memory:{
      kind:memoryKind.value, text:input.value.trim(),
      knowledge_refs:reference.value ? [reference.value] : [],
      ...(subject.required && subject.value ? {subject:JSON.parse(subject.value)} : {}),
      ...(term.required ? {term:term.value} : {}),
      ...(memoryKind.value === "pressures" ? {
        ...(existing.value ? {pressure_id:existing.value} : {}),
        pressure:{status:pressureStatus.value, stake:stake.value.trim(),
          ...(step.required ? {next_step:step.value.trim()} : {}),
          ...Object.fromEntries([["blocker", blocker], ["trigger", trigger], ["fallback", fallback],
            ["consequence", consequence]].filter(([, input]) => input.value.trim())
            .map(([key, input]) => [key, input.value.trim()])),
          ...(account.value.trim() ? {account:account.value.trim()} : {}),
        },
      } : {}),
    }});
    action(form, "Save memory draft", async key => {
      if (![memoryKind, subject, term, reference, input, stake, step, account].every(control => control.reportValidity())) return;
      await request("portrayal-memory", save(), key);
      await load(true);
    }, () => JSON.stringify(save()));
  }

  function showContinuity(parent, sheet, preview) {
    const entries = preview.state?.continuity ?? [];
    const pending = preview.pending_continuity;
    const sources = preview.continuity_sources ?? [];
    if (entries.length) {
      const saved = details(parent, "Saved character changes");
      saved.open = true;
      for (const entry of entries) {
        saved.append(element("p", continuityLabels[entry.kind] + " · " + entry.text));
      }
    }
    if (!pending && !sources.length) return;
    const panel = details(parent, "What changed this scene");
    panel.open = true;
    if (pending) {
      const review = details(panel, "Proposed changes");
      review.open = true;
      const evidence = new Map(sources.map(item => [item.id, item.text]));
      for (const entry of pending.entries) {
        review.append(element("p", continuityLabels[entry.kind] + " · " + entry.text));
        for (const ref of entry.knowledge_refs) {
          if (evidence.has(ref)) review.append(element("blockquote", evidence.get(ref)));
        }
      }
      writeConfirm(review, sheet, pending.id, "Approve character changes", true);
    }
    if (!sources.length || preview.pending_memory || preview.pending_experience) return;
    const subjects = preview.continuity_subjects ?? [];
    const form = details(panel, pending ? "Draft a replacement" : "Draft a character change");
    const kinds = Object.entries(continuityLabels).filter(([kind]) => kind !== "relationship" || subjects.length);
    const [kindLabel, kind] = choiceField("Type of change", kinds, "intention");
    kind.required = true;
    const [subjectLabel, subject] = choiceField("Relationship with",
      subjects.map(item => [JSON.stringify(item.actor), item.label]));
    const evidenceLabel = element("label", "Heard evidence (select up to three)");
    const evidence = element("select");
    evidence.multiple = true;
    evidence.required = true;
    evidence.size = Math.min(sources.length, 4);
    for (const source of sources) {
      const option = element("option", source.text);
      option.value = source.id;
      evidence.append(option);
    }
    evidenceLabel.append(evidence);
    form.append(kindLabel, subjectLabel, evidenceLabel);
    const input = area(form, "How has this character changed?", "", 320);
    input.required = true;
    function syncKind() {
      subject.required = kind.value === "relationship";
      subjectLabel.hidden = !subject.required;
    }
    kind.addEventListener("change", syncKind);
    syncKind();
    const selectedRefs = () => [...evidence.selectedOptions].map(option => option.value);
    evidence.addEventListener("change", () =>
      evidence.setCustomValidity(selectedRefs().length > 3 ? "Select at most three heard lines." : ""));
    const save = () => ({actor:sheet.actor, version:sheet.version, updates:[{
      kind:kind.value,
      text:input.value.trim(),
      knowledge_refs:selectedRefs(),
      ...(subject.required && subject.value ? {subject:JSON.parse(subject.value)} : {}),
    }]});
    action(form, "Save character change draft", async key => {
      if (![kind, subject, evidence, input].every(control => control.reportValidity())) return;
      await request("portrayal-continuity", save(), key);
      await load(true);
    }, () => JSON.stringify(save()));
  }

  async function showPreview(panel, changes, sheet) {
    panel.replaceChildren(element("summary", "What the AI can see"));
    changes.replaceChildren(element("summary", "What changed in play"));
    panel.open = true;
    let preview;
    try {
      preview = await request("portrayal-preview/" + encodeURIComponent(sheet.token));
    } catch (error) {
      panel.append(element("p", error.message));
      action(panel, "Refresh scene context", () => showPreview(panel, changes, sheet));
      return;
    }
    approvedProfile(panel, preview);
    action(panel, "Refresh scene context", () => showPreview(panel, changes, sheet));
    const refs = preview.context.references;
    const reports = preview.closed_scene_reports ?? [];
    panel.append(element("h3", "Known in this scene"));
    if (!refs.length) panel.append(element("p", "No shared references are available to this character."));
    for (const ref of refs) panel.append(element("p", ref.text));
    showContinuity(changes, sheet, preview);
    for (const [key, label] of Object.entries(memoryLabels)) {
      for (const entry of preview.state?.[key] ?? []) {
        changes.append(element("p", label + " · " + entry.text));
        if (entry.pressure) {
          const plan = entry.pressure;
          changes.append(element("p", [pressureLabels[plan.status], plan.stake,
            plan.next_step, plan.account].filter(Boolean).join(" · ")));
        }
      }
    }
    for (const experience of preview.handler_experiences ?? []) {
      changes.append(element("p", experience.reported_text));
    }
    if (reports.length) {
      const debrief = details(changes, "Approved debrief reports");
      for (const ref of reports) debrief.append(element("p", ref.text));
    }
    if (preview.pending_experience) {
      changes.open = true;
      changes.append(element("p", "Awaiting approval · " + preview.pending_experience.entry.text));
      writeConfirm(changes, sheet, preview.pending_experience.id, "Approve experience", true);
    }
    if (preview.pending_memory) {
      const entry = preview.pending_memory.entry;
      changes.append(element("p", ["Awaiting approval", entry.text, pressureLabels[entry.pressure?.status],
        entry.pressure?.account].filter(Boolean).join(" · ")));
      writeConfirm(changes, sheet, preview.pending_memory.id, "Approve memory", true);
    }
    if (preview.memory_subjects) {
      editMemory(changes, sheet, preview);
    } else if (refs.length) {
      const form = details(changes, "Record an experience");
      const [label, reference] = choiceField("What happened?",
        refs.map(ref => [ref.id, ref.text]));
      reference.setAttribute("aria-label", "Source for the experience");
      reference.required = true;
      form.append(label);
      const input = area(form, "How does this change what you do?", "", 800);
      input.required = true;
      const save = () => ({
        actor:sheet.actor, version:sheet.version, reference:reference.value, text:input.value.trim(),
      });
      action(form, "Save experience draft", async key => {
        if (!reference.reportValidity() || !input.reportValidity()) return;
        await request("portrayal-experience", save(), key);
        await load(true);
      }, () => JSON.stringify(save()));
    }
    changes.open = true;
  }

  async function load(openPreview = false) {
    const view = await request("portrayal-sheets");
    const kinds = kind === "pilot" ? ["pilot", "npc"]
      : kind === "alternate" ? ["npc", "gorgon", "external_pilot"] : [kind];
    const sheets = view.sheets.filter(sheet => kinds.includes(sheet.actor.kind));
    const sheet = sheets.find(sheet => sheet.token === token) ?? sheets.find(x => x.actor.kind === kind) ?? sheets[0];
    body.replaceChildren();
    if (!sheet) {
      body.append(element("p", "No active owned character sheet is available."));
      return;
    }
    token = sheet.token;
    if (sheets.length > 1) {
      const [label, select] = choiceField("Your character", sheets.map(x => [x.token, x.label]), token);
      select.remove(0);
      select.addEventListener("change", () => { token = select.value; load().catch(fail); });
      body.append(label);
    }
    body.append(
      element("h3", sheet.label),
      element("p", sheet.approved ? "Approved portrayal · Revision " + sheet.approved
        : sheet.actor.kind === "handler" ? "Handler portrayal comes from your private sheet notes."
        : "Portrayal awaits your approval."),
    );
    if (sheet.pending?.stale) body.append(element("p", "The saved draft is stale. Reopen the current sheet before editing."));
    else if (["experience", "memory", "continuity"].includes(sheet.pending?.kind)) body.append(element("p", "A character change awaits your approval in its source scene."));
    else if (sheet.pending) body.append(element("p", "A portrayal draft awaits your approval."));
    if (sheet.actor.kind !== "handler") editPortrayal(body, sheet, view);
    editCharacterSetup(body, sheet);
    const preview = details(body, "What the AI can see");
    const changes = details(body, "What changed in play");
    if (scene) {
      action(preview, "Load current scene context", () => showPreview(preview, changes, sheet));
      changes.append(element("p", "Load current scene context to review available experiences."));
      if (openPreview) await showPreview(preview, changes, sheet);
    } else {
      preview.append(element("p", "Scene context requires a current consented Director scene."));
      changes.append(element("p", "Open a consented scene to record an experience."));
    }
  }

  function fail(error) {
    if (!active.signal.aborted) status.textContent = error.message;
  }
  load().catch(fail);
}

export function mountDirectorDesk(parent, scene, activityFetch, activityShadow = false, liveTrial = false, reviewOnly = false, openNativePlay) {
  const details = element("details");
  details.append(element("summary", scene ? "Director work" : "Campaign setup"));
  const body = element("div");
  const status = element("p");
  status.setAttribute("role", "status");
  details.append(status, body);
  parent.prepend(details);
  const sceneHeader = element("section");
  sceneHeader.hidden = true;
  if (scene) details.before(sceneHeader);
  const root = scene ? "/api/director/" + encodeURIComponent(scene) + "/" : "/api/campaign-opening/";
  const routeId = id => encodeURIComponent(id).replaceAll("%3A", ":");
  let briefingExpanded = false;

  async function read(route, optional = false) {
    const response = await activityFetch(root + route);
    if (optional && [401, 403, 404, 409].includes(response.status)) return null;
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Unable to read scene work.");
    return result;
  }

  function renderShadow(policy, observation, review, signatures) {
    if (!observation) return;
    const row = card(body, liveTrial ? "Private AI review" : "Private shadow review");
    if (liveTrial) row.append(element("p", "Once every human participant consents, eligible in-character turns can be sent to the configured model for private review. Scene records are stored in this campaign."));
    row.append(element("p", "Scene observation · " + observation.phase.replaceAll("_", " ")));
    if (policy && !liveTrial) {
      row.append(button(policy.enabled ? "Disable campaign observation" : "Enable campaign observation", async key => {
        await write("activity-policy-save", {revision: policy.revision, enabled: !policy.enabled}, key);
        await refresh();
      }));
    }
    if (policy) {
      if (policy.enabled) row.append(button("Refresh scene consent notice", async key => {
        await write("configure", {revision: observation.policy_revision}, key);
        await refresh();
      }));
    }
    if (observation.policy_revision && !reviewOnly) {
      for (const [consent, label] of [[true, "Grant my observation consent"], [false, "Withdraw my observation consent"]]) {
        row.append(button(label, async key => {
          await write("consent", {policy_revision: observation.policy_revision, consent}, key);
          await refresh();
        }));
      }
    }
    if (!review) return;
    if (liveTrial && policy && !policy.enabled) {
      row.append(element("p", "AI assistance is off. Turn it on in Campaign Setup."));
    } else {
      row.append(button("Review eligible batch", async key => {
        const result = await write("activity-review-run", {}, key);
        await refresh();
        if (!result.batch) status.textContent = "No batch is ready.";
      }));
    }
    for (const batch of review.batches) {
      const group = element("details");
      const outcome = batch.model_outcome;
      group.append(element("summary", outcome?.status === "stale"
        ? `Stale batch through event ${batch.frontier}`
        : `Reviewed through event ${batch.frontier}`));
      if (outcome) {
        const label = {
          wait: outcome.pilot ? "AI Pilot stayed silent" : "Handler stayed silent",
          pilot_review: "AI Pilot proposal ready for controller review",
          draft: "Handler draft ready for review",
          world_review: "World proposal ready for review",
          native_signature: "Signature Play flagged for its original controller",
          escalated: "Facilitator review needed",
          rejected: "Model decision rejected",
          failed: "Model call failed",
          stale: "Context changed while reviewing",
        }[outcome.status];
        if (label) group.append(element("p", `${label} · ${outcome.reason.replaceAll("_", " ")}`));
        if (outcome.play) group.append(element("p", handlerPlayTitles[outcome.play] ?? outcome.play));
        if (outcome.status === "native_signature" && outcome.control && signatures?.handler) {
          const pending = outcome.destination === "signature_choice"
            ? signatures.choices.some(item => item.id === outcome.control)
            : outcome.destination === "conditioning_phrase"
            ? signatures.targets.some(item => item.id === outcome.control)
            : outcome.destination === "off_duty_signature" && openNativePlay;
          if (pending) group.append(button("Open assigned Signature Play", async () => {
            if (outcome.destination === "off_duty_signature") {
              await openNativePlay({id:outcome.play, destination:outcome.destination,
                control:outcome.control, target:outcome.target});
              return;
            }
            const row = [...body.querySelectorAll("[data-native-signature]")]
              .find(item => item.dataset.nativeSignature === (
                outcome.destination === "signature_choice" ? outcome.control : "conditioning_phrase"
              ));
            if (!row) throw new Error("Refresh the original Signature Play.");
            if (outcome.destination === "conditioning_phrase") {
              const target = row.querySelector("[data-signature-target]");
              target.value = outcome.control;
              target.dispatchEvent(new Event("change"));
            }
            row.focus();
          }));
        }
        if (outcome.status === "escalated" && outcome.source && !reviewOnly) {
          group.append(button("File facilitator review", async key => {
            const filed = await write("activity-review-refer", {run: batch.run}, key);
            status.textContent = filed.status === "configuration_required"
              ? "Review filed. Awaiting facilitator assignment."
              : "Review filed to the facilitator’s Inbox.";
          }));
        }
      }
      if (batch.initiative) {
        if (batch.initiative.prompt) {
          const heading = batch.initiative.prompt.replaceAll("_", " ");
          const origin = batch.initiative.inspired_by;
          group.append(element("h4", origin ? heading + " · inspired by " + origin : heading));
        }
        group.append(element("p", batch.initiative.opportunity));
        const play = batch.initiative.possible_play;
        if (play) group.append(element("p", `Check native Play · ${play.title}. ${play.trigger}`));
      }
      for (const item of batch.items) {
        const description = item.decision ? `${item.decision.action} · ${item.decision.reason.replaceAll("_", " ")}`
          : item.kind === "completed_play" ? "Completed Play · human GM review" : "Source changed. Review a current batch.";
        group.append(element("p", description));
        for (const fact of item.facts ?? []) group.append(element("p", fact.text));
      }
      row.append(group);
    }
  }

  function renderCanon(canon, booking) {
    const [window, own, knowledge, publication, queue, staffWindow, world, witnesses, briefings] = canon;
    if (booking?.joined && booking.status === "open") {
      const safety = card(body, "Scene safety");
      timeSave(safety, "Pause this scene", "scene-safety", () => ({pause: true}));
      if (booking.paused) timeSave(safety, "Clear my pause", "scene-safety", () => ({pause: false}));
    }
    if (!window && !own && !knowledge && !publication && !queue) return;
    const panel = timeForm(body, "Campaign canon");
    const statementForm = (label, route, sceneWindow) => {
      const labelNode = element("label", "Setting statement");
      const textarea = element("textarea");
      textarea.maxLength = 600;
      labelNode.append(textarea);
      panel.append(labelNode);
      timeSave(panel, label, route, () => ({window: sceneWindow, statement: textarea.value}));
    };
    if (window) statementForm("Submit for canon review", "canon-submit", window);
    for (const proposal of own?.proposals ?? []) {
      if (proposal.window.scene_id === scene)
        panel.append(element("p", `${proposal.status} · ${proposal.statement}`));
    }
    const known = knowledge?.facts ?? [];
    if (known.length) {
      const group = timeForm(panel, "My character’s known facts");
      for (const fact of known) group.append(element("p", `${fact.statement} · ${fact.status.replaceAll("_", " ")}`));
      const active = known.filter(fact => fact.status === "current");
      const reportable = active.filter(fact => fact.method === "witnessed");
      if (window && reportable.length) {
        const [label, fact] = choiceField("Witnessed fact", reportable.map(x => [x.fact_id, x.statement]), "");
        group.append(label);
        timeSave(group, "Report to the Handler", "canon-report", () => ({window, fact: fact.value}));
      }
      if (briefings && active.length) {
        const [label, facts] = choiceField("Briefing facts", active.map(x => [x.fact_id, x.statement]), "");
        facts.options[0].remove();
        facts.multiple = true;
        group.append(label);
        timeSave(group, "Save briefing draft", "canon-briefing", () => ({facts: [...facts.selectedOptions].map(x => x.value)}));
        for (const draft of briefings.drafts) {
          group.append(element("p", draft.needs_review ? `Needs review · ${draft.id}` : `Draft ID · ${draft.id}`));
        }
      }
    }
    if (publication?.facts.length) {
      const group = timeForm(panel, "Published reference");
      for (const fact of publication.facts) group.append(element("p", `${fact.statement} · ${fact.status.replaceAll("_", " ")}`));
    }
    if (queue) {
      const group = timeForm(panel, "Facilitator review");
      for (const proposal of queue.proposals.filter(x => x.status === "pending")) {
        group.append(element("p", proposal.statement));
        for (const [label, approve, published] of [
          ["Approve privately", true, false], ["Approve and publish", true, true], ["Decline", false, false],
        ]) {
          timeSave(group, label, "canon-review", () => ({id: proposal.id, approve, public: published}));
        }
      }
      if (staffWindow) statementForm("Establish private canon", "canon-establish", staffWindow);
      const current = world?.facts.filter(fact => fact.status !== "superseded") ?? [];
      if (current.length) {
        const [label, fact] = choiceField("Established fact", current.map(x => [x.fact_id, x.statement]), "");
        group.append(label);
        const [correction, text] = field("Corrected statement", "");
        text.maxLength = 600;
        group.append(correction);
        timeSave(group, "Save correction", "canon-correct", () => ({fact: fact.value, statement: text.value}));
        if (staffWindow && witnesses?.pilots.length) {
          const [pilotLabel, pilot] = choiceField("Witness", witnesses.pilots.map(x => [x.id, x.label]), "");
          group.append(pilotLabel);
          timeSave(group, "Record witness", "canon-witness", () => ({window: staffWindow, fact: fact.value, pilot: pilot.value}));
        }
      }
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

  function sessionZeroSave(panel, label, route, values) {
    panel.append(button(label, async key => {
      if (Array.from(panel.querySelectorAll("input, select, textarea"))
        .some(input => !input.reportValidity())) return;
      await write(route, values(), key);
      await refresh();
    }, () => JSON.stringify(values())));
  }

  function renderSessionZero(state) {
    const row = card(body, "Session Zero");
    if (state.owner_preview) {
      const plan = {approved:"Approved", pending:"Awaiting approval", not_filed:"Not filed"};
      row.append(
        element("p", "Campaign owner preview · Read only"),
        element("p", "Handler · HarpyEngine bot"),
        element("p", "Session Zero group · " + (state.group_configured ? "Filed" : "Not set")),
        element("p", "Campaign plan · " + plan[state.plan_status]),
        element("p", "Facilitator · " + (state.facilitator_appointed ? "Appointed" : "Unassigned")),
      );
      return;
    }
    const revision = state.revision;
    const member = id => state.viewer === id ? "You" : state.member_names?.[id] ?? "Discord member " + id;
    const isHandler = state.handler_ready === state.viewer;
    if (state.bot_managed) row.append(element("p", "Handler · HarpyEngine bot"));
    const profile = state.profile;
    const open = state.opening;
    const inIntro = open && state.opening_day < open.first_mission_day;
    const control = profile?.control ?? "player";
    function vote(panel, title, route, proposal, approved) {
      sessionZeroSave(panel, (approved ? "Withdraw approval of " : "Approve ") + title,
        route, () => ({proposal, approve: !approved}));
    }
    if (state.can_set_group) {
      const panel = timeForm(row, "Choose the Session Zero group");
      if (state.bot_managed) panel.open = !state.members.length;
      const required = state.bot_managed ? state.required_group_member : state.appointed;
      const choices = state.group_options.map(id => {
        const label = element("label");
        const input = element("input");
        input.type = "checkbox";
        input.checked = state.members.includes(id) || id === required;
        input.disabled = id === required;
        label.append(input, member(id));
        panel.append(label);
        return {id, input};
      });
      if (state.members.length) panel.append(element("p", "Changing the group starts a new approval round."));
      sessionZeroSave(panel, "Save group", "session-zero-group", () => ({
        revision, members: choices.filter(x => x.input.checked).map(x => x.id),
      }));
    }
    if (!state.in_group) return;
    if (profile && !state.bot_managed) {
      const handler = card(row, "Handler");
      handler.append(
        element("p", profile.name + " · " + profile.archetype),
        element("p", (control === "ai" ? "AI-assisted · Reviewed by " : "Played by ") +
          (profile.player_name || member(profile.member))),
        element("p", profile.appearance), element("p", profile.personality),
      );
      if (!open) {
        handler.append(element("p", state.approvals + "/" + state.members.length + " approvals"));
        vote(handler, "the Handler", "session-zero-handler-vote", state.proposal, state.own_approval);
        if (state.can_appoint) sessionZeroSave(handler, "Appoint approved Handler", "session-zero-appoint", () => ({
          setup_revision: state.setup_revision, proposal: state.proposal, nominee: state.nominee,
        }));
      }
    }
    if (!open && !state.bot_managed) {
      const panel = timeForm(row, profile ? "Edit Handler proposal" : "Propose the Handler");
      const options = state.appointed ? [state.appointed] : state.members;
      const [controllerLabel, controller] = choiceField("Handler player or AI reviewer",
        options.map(id => [id, member(id)]), profile?.member ?? state.appointed);
      const [modeLabel, mode] = choiceField("Who portrays the Handler?",
        [["player", "Player"], ["ai", "AI with human review"]], control);
      const [nameLabel, name] = field("Handler name", profile?.name);
      const [bookLabel, book] = choiceField("Handler playbook",
        state.playbooks.map(value => [value, value]), profile?.archetype);
      for (const input of [controller, mode, book]) input.required = true;
      name.maxLength = 100;
      panel.append(controllerLabel, modeLabel, nameLabel, bookLabel);
      const appearance = textArea(panel, "Appearance", profile?.appearance, 400);
      const personality = textArea(panel, "Personality", profile?.personality, 400);
      sessionZeroSave(panel, "Save Handler proposal", "session-zero-propose", () => ({
        revision, profile: {member: controller.value, control: mode.value, name: name.value.trim(),
          archetype: book.value, appearance: appearance.value.trim(), personality: personality.value.trim()},
      }));
    }
    if (state.handler_ready === null && !state.bot_managed) return;
    const sheets = Object.entries(state.sheets);
    if (!open) {
      const panel = card(row, "Pilot sheets");
      for (const [id, value] of sheets) panel.append(element("p", member(id) + " · " + value));
      if (state.is_pilot ?? !isHandler) {
        sessionZeroSave(panel, "Attach my current sheet", "session-zero-attach", () => ({revision}));
        if (state.sheets[state.viewer] === "attached") {
          const notes = timeForm(panel, "My character input");
          const inputs = Object.fromEntries([["goal", "Character goal"], ["hook", "Story hook"],
            ["spotlight", "Desired spotlight"]].map(([key, label]) =>
            [key, textArea(notes, label, state.own_notes[key], 400, false)]));
          sessionZeroSave(notes, "Save my input", "session-zero-notes", () => ({
            revision, notes: Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.value])),
          }));
        }
      }
    }
    const plan = card(row, "Campaign plan");
    const title = value => value[0].toUpperCase() + value.slice(1);
    const players = state.seats?.player_count ?? state.player_count;
    plan.append(
      element("p", title(state.difficulty) + " · " + players + (players === 1 ? " human player" : " human players")),
      element("p", state.difficulty_options[state.difficulty]),
    );
    if (state.goals) plan.append(element("p", state.goals));
    if (state.facilitator) plan.append(element("p", (state.bot_managed && !state.plan_approved ? "Proposed facilitator · " : "Facilitator · ") + member(state.facilitator) +
      (state.facilitator === state.handler_ready ? " · Also controls the Handler" :
        state.facilitator_only ? " · Facilitator only" : " · Also plays a Pilot")));
    for (const pilot of state.seats?.ai_pilots ?? []) {
      const details = timeForm(plan, "Planned AI Pilot · " + pilot.callsign);
      if (pilot.concept) details.append(element("p", pilot.concept));
      const labels = {girl_playbook: "Girl playbook", frame_playbook: "Frame",
        archetype: "Archetype", vibe: "Vibe", voice: "Voice", approach: "First move", initiative: "When they step in",
        pressure: "Under pressure", repair: "After a mistake", value: "Value", fear: "Fear",
        contradiction: "Contradiction", goal: "Personal goal"};
      for (const [key, label] of Object.entries(labels)) {
        if (pilot.portrayal?.[key]) details.append(element("p", label + " · " + pilot.portrayal[key]));
      }
    }
    if (state.plan_proposal && !open) {
      plan.append(element("p", state.plan_approvals + "/" + state.members.length + " plan approvals"));
      const voting = element("div");
      plan.append(voting);
      vote(voting, "the campaign plan", "session-zero-plan-vote", state.plan_proposal, state.own_plan_approval);
    }
    if ((isHandler || state.can_edit_plan) && !open) {
      const panel = timeForm(plan, "Draft campaign roles, difficulty, and goals");
      if (state.bot_managed) panel.open = !state.plan_proposal;
      const [facilitatorLabel, facilitator] = choiceField("Facilitator",
        state.members.map(id => [id, member(id) + (id === state.handler_ready ? " · Handler controller" : "")]),
        state.facilitator ?? state.handler_ready);
      facilitator.setAttribute("aria-label", "Facilitator");
      facilitator.required = true;
      const onlyLabel = element("label", "Facilitator only");
      const only = element("input");
      only.type = "checkbox";
      only.checked = state.facilitator_only === true;
      onlyLabel.prepend(only);
      const [difficultyLabel, select] = choiceField("Difficulty",
        Object.entries(state.difficulty_options).map(([key, note]) => [key, title(key) + " · " + note]),
        state.difficulty);
      select.required = true;
      const seatCount = () => state.members.length - Number(!state.bot_managed && control === "ai") - Number(only.checked);
      const seatNote = element("p");
      const updateSeats = () => {
        only.disabled = facilitator.value === state.handler_ready || state.members.length <= 2;
        if (only.disabled) only.checked = false;
        onlyLabel.hidden = only.disabled;
        const count = seatCount();
        seatNote.textContent = count + " human player " + (count === 1 ? "seat" : "seats") + ".";
      };
      facilitator.addEventListener("change", updateSeats);
      only.addEventListener("change", updateSeats);
      updateSeats();
      panel.append(facilitatorLabel, onlyLabel,
        element("p", "The facilitator reviews AI drafts and can also play a Pilot or control the Handler."),
        difficultyLabel, seatNote);
      const goals = textArea(panel, "Shared short-term goals", state.goals, 800);
      const pilots = [];
      const list = element("div");
      panel.append(list);
      const generator = state.pilot_generator ?? {portrayals: [], callsigns: []};
      let deck = [];
      const traits = {
        vibe: "Vibe",
        voice: "Voice",
        approach: "Typical first move",
        pressure: "Under pressure",
        repair: "After a mistake",
        value: "What they value",
        fear: "What they fear",
        contradiction: "Contradiction",
        goal: "Personal goal",
      };
      const pick = choices => choices[Math.floor(Math.random() * choices.length)];
      function nextArchetype(previous) {
        if (!deck.length) deck = [...generator.portrayals];
        const choices = deck.filter(item => item.archetype !== previous);
        const next = pick(choices.length ? choices : deck);
        deck.splice(deck.indexOf(next), 1);
        return next;
      }

      function unusedCallsign() {
        const used = new Set(pilots.map(pilot => pilot.callsign.value.trim().toLowerCase()));
        const names = generator.callsigns.filter(name => !used.has(name.toLowerCase()));
        if (names.length) return pick(names);
        let number = 1;
        while (used.has("pilot " + number)) number += 1;
        return "Pilot " + number;
      }

      function addPilot(saved) {
        const slot = element("fieldset");
        slot.append(element("legend", "AI Pilot"));
        const [label, callsign] = field("AI Pilot callsign", saved?.callsign);
        callsign.maxLength = 100;
        slot.append(label);
        const concept = textArea(slot, "AI Pilot background", saved?.concept, 400, false);
        const editor = timeForm(slot, "Edit AI Pilot personality");
        const archetypes = generator.portrayals.map(item => item.archetype);
        const savedArchetype = saved?.portrayal?.archetype;
        if (savedArchetype && !archetypes.includes(savedArchetype)) archetypes.push(savedArchetype);
        const [archetypeLabel, archetype] = choiceField("AI Pilot archetype",
          archetypes.map(name => [name, name]), savedArchetype);
        const [girlLabel, girl] = choiceField("Girl playbook for portrayal",
          Object.entries(generator.girl_types ?? {}), saved?.portrayal?.girl_playbook);
        const [frameLabel, frame] = choiceField("Frame for portrayal",
          Object.entries(generator.frame_types ?? {}), saved?.portrayal?.frame_playbook);
        archetype.setAttribute("aria-label", "AI Pilot archetype");
        editor.append(girlLabel, frameLabel, archetypeLabel);
        const initiative = textArea(editor, "When this Girl steps in", saved?.portrayal?.initiative, 400, false);
        const edits = Object.entries(traits).map(([key, label]) => {
          const input = textArea(editor, label, saved?.portrayal?.[key], key === "vibe" ? 60 : 400, false);
          const keepLabel = element("label", "Keep " + label.toLowerCase() + " on reroll");
          const lock = element("input");
          lock.type = "checkbox";
          keepLabel.prepend(lock);
          editor.append(keepLabel);
          return {key, input, lock};
        });
        editor.append(button("Use selected archetype", () => {
          const preset = generator.portrayals.find(item => item.archetype === archetype.value);
          if (!preset) throw new Error("Choose an AI Pilot archetype first.");
          for (const edit of edits) if (!edit.lock.checked) edit.input.value = preset[edit.key];
        }), button("Reroll unlocked traits", () => {
          const pool = generator.portrayals;
          for (const edit of edits) {
            if (edit.lock.checked) continue;
            const choices = pool.map(item => item[edit.key]).filter(value => value !== edit.input.value);
            if (choices.length) edit.input.value = pick(choices);
          }
        }));
        const entry = {
          callsign,
          save() {
            const portrayal = {
              archetype: archetype.value, girl_playbook: girl.value,
              frame_playbook: frame.value, initiative: initiative.value.trim(),
            };
            for (const {key, input} of edits) portrayal[key] = input.value.trim();
            return {
              callsign: callsign.value,
              concept: concept.value,
              ...(Object.values(portrayal).some(Boolean) ? {portrayal} : {}),
            };
          },
        };
        pilots.push(entry);
        slot.append(button("Remove AI Pilot", () => {
          pilots.splice(pilots.indexOf(entry), 1);
          slot.remove();
        }));
        list.append(slot);
        editor.open = Boolean(saved?.portrayal);
      }
      for (const pilot of state.seats?.ai_pilots ?? []) addPilot(pilot);
      panel.append(button("Add AI Pilot", () => {
        if (pilots.length >= state.limit) throw new Error("The AI Pilot list is full.");
        addPilot();
      }));
      if (generator.portrayals.length) panel.append(button("Generate AI Pilot", () => {
        if (pilots.length >= state.limit) throw new Error("The AI Pilot list is full.");
        const last = pilots.at(-1)?.save().portrayal?.archetype;
        addPilot({callsign: unusedCallsign(), portrayal: {
          ...nextArchetype(last),
          girl_playbook: pick(Object.keys(generator.girl_types ?? {})) ?? "",
          frame_playbook: pick(Object.keys(generator.frame_types ?? {})) ?? "",
        }});
      }));
      sessionZeroSave(panel, "Save campaign plan for approval", "session-zero-plan", () => ({
        revision, difficulty: select.value, goals: goals.value, facilitator: facilitator.value,
        facilitator_only: only.checked,
        seats: {player_count: seatCount(), ai_pilots: pilots.map(pilot => pilot.save())},
      }));
    }
    if (state.can_open_introduction) {
      const launch = timeForm(row, "Open the approved introduction");
      const introduction = textArea(launch, "Handler introduction", "", 1200);
      const [daysLabel, days] = field("Introductory days", "3");
      days.type = "number";
      days.min = "2";
      days.max = "7";
      launch.append(daysLabel);
      sessionZeroSave(launch, "Open introduction", "session-zero-open", () => ({
        revision, introduction: introduction.value, days: Number(days.value),
      }));
    }
    if (open) {
      const intro = card(row, "Cadre introduction");
      intro.append(element("p", open.introduction), element("p", inIntro
        ? "Roleplay only · Day " + state.opening_day + ". First mission opens on Day " + open.first_mission_day + "."
        : "The first mission can be offered in the Mission Desk."));
      for (const post of state.opening_posts) intro.append(element("p", post.author + " · " + post.text));
      if (inIntro && (isHandler || (state.is_pilot ?? true))) {
        const composer = element("div");
        intro.append(composer);
        const text = textArea(composer, "Introductory roleplay", "", 1200);
        sessionZeroSave(composer, "Post roleplay", "session-zero-post", () => ({
          anchor: state.opening_anchor, text: text.value,
        }));
      if (state.can_advance_introduction) intro.append(button("Advance one introductory day", async key => {
          await write("session-zero-advance", {anchor: state.opening_anchor}, key);
          await refresh();
        }));
      }
    }
    if (state.can_generate) row.append(button("View group worksheet", async () => {
      const result = await read("session-zero-worksheet");
      let worksheet = row.querySelector("pre");
      if (!worksheet) {
        worksheet = element("pre");
        row.append(worksheet);
      }
      worksheet.textContent = result.worksheet;
    }));
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
    session.append(element("summary", "Briefing guidance"));
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
      const line = [booking.chapter, booking.location, `${slotText(booking.start)} to ${slotText(booking.end)}`,
        booking.status, booking.dependency_pending ? "Waiting for required outcomes" : null].filter(Boolean).join(" · ");
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
      const [locationLabel, location] = field("Scene location", "");
      location.maxLength = 100;
      const dependencies = element("textarea");
      const dependencyLabel = element("label", "Required receipts, one per line as choice:id, work:id, play_receipt:id, or fact:id");
      dependencyLabel.append(dependencies);
      select.addEventListener("change", () => {
        const booking = scenes.find(item => item.id === select.value);
        location.value = booking?.location ?? "";
        dependencies.value = (booking?.requires ?? []).map(item => `${item.kind}:${item.id}`).join("\n");
      });
      form.append(selectLabel, pilotsLabel, locationLabel, dependencyLabel);
      const start = positionFields(form, "Scene starts", view.anchor.position);
      const end = positionFields(form, "Scene ends", view.anchor.position);
      form.append(lateLabel);
      timeSave(form, "Save scene booking", "time-schedule", () => {
        const booking = scenes.find(s => s.id === select.value);
        if (!booking) throw new Error("Choose a scene to schedule.");
        const requires = dependencies.value.split("\n").map(line => line.trim()).filter(Boolean).map(line => {
          const colon = line.indexOf(":");
          if (colon < 1 || colon === line.length - 1) throw new Error("Enter a receipt type and its ID.");
          return {kind: line.slice(0, colon), id: line.slice(colon + 1)};
        });
        return {scene: booking.id, channel: booking.channel, revision: booking.scene_revision ?? booking.revision,
          anchor: view.anchor_receipt, plan: {start: start(), end: end(),
            participants: [...pilots.selectedOptions].map(p => p.value), allow_late_narration: late.checked,
            location: location.value.trim() || null, requires}};
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

  const timingLabels = {
    unknown_duration: "Decide how long the option takes",
    unknown_consequence: "Define the missed-cutoff consequence",
    missed_cutoff: "Missed cutoff",
  };

  function renderTimingReviews(parent, items) {
    if (!items?.length) return;
    const group = card(parent, "Timing review");
    for (const item of items) {
      const work = element("section");
      work.append(element("h5", timingLabels[item.kind]),
        element("p", item.kind === "missed_cutoff"
          ? `${minuteText(item.from_minute)} to ${minuteText(item.minute)} · Cutoff ${minuteText(item.deadline)}`
          : `${minuteText(item.minute)} · Waiting for the Handler`));
      const proof = timeForm(work, "Source receipt");
      proof.append(element("code", item.source_receipt));
      if (item.kind === "missed_cutoff") {
        work.append(element("p", item.consequence));
        timeSave(work, "Acknowledge cutoff", "time-acknowledge", () => ({scene: item.scene_id, source_receipt: item.source_receipt}));
      } else {
        if (item.option_label) work.append(element("p", item.option_label));
        if (item.attempted_minute !== null) work.append(element("p", `Proposed arrival ${minuteText(item.attempted_minute)}`));
      }
      group.append(work);
    }
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
    const ruling = view.timing_ruling;
    if (ruling) {
      const link = element("a", timingLabels[ruling.kind]);
      link.href = "#" + ruling.next_action;
      link.addEventListener("click", () => document.getElementById(ruling.next_action)?.setAttribute("open", ""));
      row.append(link);
    }
    const revision = () => ({id: clock.id, revision: clock.revision});
    if (!clock.deadline.consequence) {
      const form = timeForm(row, "Define the missed-deadline consequence");
      form.id = "define_consequence";
      const [label, answer] = field("Fictional consequence", "");
      form.append(label);
      timeSave(form, "Save consequence", "time-consequence", () => ({...revision(), account: answer.value}));
    }
    if (!clock.selected.length && controls.clock_pilots.length) {
      const form = timeForm(row, "Publish Pilot options");
      form.id = "publish_options";
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
    notes.open = sheet.editable;
    notes.append(element("summary", "Private roleplay notes"));
    parent.append(notes);
    const current = sheet.draft.notes ?? {};
    const personalities = sheet.personalities ?? {};
    if (!sheet.editable && !sheet.notes_editable) {
      const personality = personalities[current.personality];
      if (personality) notes.append(element("p", personality.label + " · " + personality.prompt));
      for (const [key, label] of sheet.note_fields) {
        if (current[key]) notes.append(element("p", label + " · " + current[key]));
      }
      return () => null;
    }
    const options = Object.entries(personalities);
    const [personalityLabel, personality] = choiceField(
      "Personality", options.map(([key, value]) => [key, value.label]), current.personality);
    personality.options[0].textContent = "Use my roleplay notes";
    const prompt = element("p");
    function showPersonality() {
      prompt.textContent = personalities[personality.value]?.prompt ?? "";
      prompt.hidden = !personality.value;
    }
    personality.addEventListener("change", showPersonality);
    showPersonality();
    if (options.length) {
      notes.append(personalityLabel, prompt, button("Roll personality", () => {
        const eligible = options.filter(([key]) => key !== personality.value);
        const draw = crypto.getRandomValues(new Uint32Array(1))[0];
        personality.value = eligible[draw % eligible.length][0];
        showPersonality();
      }));
    }
    const fields = sheet.note_fields.map(([key, name]) => {
      const label = element("label", name);
      const input = element("textarea");
      input.value = current[key] ?? "";
      input.rows = 2;
      input.maxLength = key === "off_duty_cue" ? 80 : 400;
      label.append(input);
      notes.append(label);
      return [key, input];
    });
    function values() {
      const saved = Object.fromEntries(fields.map(([key, input]) => [key, input.value.trim()]).filter(([, value]) => value));
      if (personality.value) saved.personality = personality.value;
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

  function renderPersona(setup, approvedProfile) {
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
      row.append(element("p", [sheet.draft.name, sheet.playbook].filter(Boolean).join(" · ")));
      const notes = sheet.draft.notes ?? {};
      for (const key of ["voice", "priority", "intervention", "repair", "concern", "promise"]) {
        const field = sheet.note_fields.find(([name]) => name === key);
        if (notes[key] && field) row.append(element("p", field[1] + " · " + notes[key]));
      }
      renderHandlerNotes(row, sheet);
      if (sheet.activated) row.append(button("Open Handler portrayal", () =>
        openSheetPortrayal({activityFetch, scene, kind:"handler"})));
      row.append(guidance, rules);
      for (const value of [sheet.draft.appearance, sheet.draft.outfit, sheet.draft.background]) {
        if (value) row.append(element("p", value));
      }
      for (const gear of sheet.draft.gear) row.append(element("p", gear.description));
      return;
    }
    const draft = sheet.draft;
    const initialPlaybook = draft.playbook ?? approvedProfile?.archetype;
    const [playbookLabel, playbook] = choiceField(
      "Handler playbook", setup.playbooks.map(x => [x, x]), initialPlaybook);
    if (!draft.playbook && initialPlaybook) {
      renderHandlerProfile(guidance, setup.profiles[initialPlaybook]);
    }
    row.append(playbookLabel, guidance, rules);
    playbook.addEventListener("change", () => {
      renderHandlerProfile(guidance, setup.profiles[playbook.value]);
      rules.hidden = (playbook.value || null) !== sheet.playbook;
    });
    const details = Object.fromEntries([
      ["name", "Handler name"], ["appearance", "Handler appearance"],
      ["outfit", "Handler outfit"], ["background", "Handler background"],
    ].map(([key, label]) => {
      const [inputLabel, input] = field(label, draft[key] || approvedProfile?.[key]);
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

  function renderPilotDossiers(options, work) {
    const pending = work.dossiers.filter(item => item.generated_pilot);
    if (!pending.length && (!options.pilots.length || !options.actors.length)) return;
    const row = card(body, "AI Pilot dossiers");
    if (options.pilots.length && options.actors.length) {
      const form = timeForm(row, "Attach a planned Pilot");
      const [pilotLabel, pilot] = choiceField("Approved AI Pilot", []);
      const [actorLabel, actor] = choiceField("Your character in this scene",
        options.actors.map(item => [item.actor.entity, item.label]));
      pilot.required = actor.required = true;
      const selected = () => options.actors.find(item => item.actor.entity === actor.value);
      function filter() {
        const allowed = selected()?.eligible_pilots ?? [];
        pilot.replaceChildren(new Option("Choose…", ""),
          ...allowed.map(callsign => new Option(callsign, callsign)));
      }
      actor.addEventListener("change", filter);
      form.append(actorLabel, pilotLabel);
      sessionZeroSave(form, "Prepare dossier for review", "pilot-dossier-propose", () => ({
        actor: selected()?.actor,
        version: selected()?.version ?? 0,
        origin: {plan: options.plan, callsign: pilot.value},
      }));
    }
    for (const item of pending) {
      const panel = card(row, "Pilot dossier review");
      if (item.status !== "awaiting_controller_confirmation") {
        panel.append(element("p", "The actor or scene changed. Prepare a fresh dossier."));
        continue;
      }
      panel.append(button("Review Pilot dossier", async () => {
        const review = await read("dossier-review/" + routeId(item.id));
        const profile = review.profile;
        const fields = [["Background", profile.background], ["Voice", profile.voice],
          ["Behavior", profile.behavior], ["Under pressure", profile.reaction_tendencies.join(" · ")],
          ["Values", profile.values.join(" · ")], ["Fears", profile.fears.join(" · ")],
          ["Contradictions", profile.contradictions.join(" · ")]];
        panel.replaceChildren(element("h4", review.pilot_origin.callsign));
        for (const [label, value] of fields) if (value) panel.append(element("p", label + " · " + value));
        panel.append(button("Confirm Pilot dossier", async key => {
          await write("dossier-confirm", {id: item.id}, key);
          await refresh();
        }));
      }));
      if (state.first_briefing?.offered) {
        intro.append(element("p", "First mission offered."));
        if (state.first_briefing.ai_on && state.first_briefing.paired_ai_ready) {
          intro.append(element("p", "AI GM and Handler enabled. Scene consent and review still apply."));
        }
      }
      if (state.first_briefing?.ready) renderFirstMissionBriefing(intro, state);
    }
  }

  function renderFirstMissionBriefing(parent, state) {
    const view = state.first_briefing;
    const section = card(parent, "First mission briefing");
    if (view.review) {
      section.append(element("p", view.review.objective),
        element("p", view.pilots.filter(pilot => view.review.pilots.includes(pilot.id))
          .map(pilot => pilot.name).join(", ")));
      const enable = element("input");
      enable.type = "checkbox";
      if (view.paired_ai_ready && !view.ai_on) {
        enable.checked = true;
        const label = element("label", "Enable AI GM and Handler after the offer");
        label.prepend(enable);
        section.append(label, element("p", "Scene consent and review still apply."));
      } else if (!view.paired_ai_ready) {
        section.append(element("p", "Configure both models in AI setup to enable the AI GM and Handler."));
      }
      section.append(button("Offer approved briefing", async key => {
        await write("session-zero-briefing-offer", {review: view.review.id, enable_ai: enable.checked}, key);
        await refresh();
      }, () => String(enable.checked)));
    }
    const review = button(view.review ? "Revise briefing" : "Review first mission briefing", () => {
      const dialog = element("dialog");
      dialog.className = "activity-dialog terminal-dialog";
      dialog.setAttribute("aria-label", "Review first mission briefing");
      dialog.addEventListener("close", () => dialog.remove(), {once: true});
      const note = element("p");
      note.setAttribute("role", "status");
      const form = element("section");
      const objective = textArea(form, "First mission objective", view.review?.objective, 1200);
      const recipients = element("fieldset");
      recipients.append(element("legend", "Pilots receiving the offer"));
      const checks = view.pilots.map(pilot => {
        const label = element("label", pilot.name);
        const input = element("input");
        input.type = "checkbox";
        input.checked = view.review?.pilots.includes(pilot.id) ?? true;
        label.prepend(input);
        recipients.append(label);
        return {input, id: pilot.id};
      });
      const values = () => ({
        anchor: state.opening_anchor, objective: objective.value.trim(),
        pilots: checks.filter(pilot => pilot.input.checked).map(pilot => pilot.id),
      });
      const close = element("button", "Close");
      close.type = "button";
      close.addEventListener("click", () => dialog.close());
      const approve = button("Approve briefing", async key => {
        if (!objective.reportValidity()) return;
        if (!values().pilots.length) {
          note.textContent = "Select at least one Pilot.";
          return;
        }
        try {
          await write("session-zero-briefing-review", values(), key);
          dialog.close();
          await refresh();
        } catch (error) {
          note.textContent = error.message;
        }
      }, () => JSON.stringify(values()));
      form.append(recipients, approve, close, note);
      dialog.append(element("h2", "Review first mission briefing"), form);
      document.body.append(dialog);
      dialog.showModal();
    });
    review.disabled = !view.pilots.length;
    section.append(review);
  }

  function renderOwn(work) {
    const owned = card(body, "Your pending decisions");
    if (work.next_plan?.status === "ready") {
      const next = timeForm(owned, "Prepare a character's next move");
      next.append(element("p", work.next_plan.text), element("p", work.next_plan.why));
      for (const [decision, label] of [["prepare", "Prepare"], ["decline", "Decline"]]) {
        timeSave(next, label, "front-preparation", () => ({move: work.next_plan.id, decision}));
      }
    }
    if (work.gm_requests?.length) {
      const rules = timeForm(body, "Private GM requests");
      for (const request of work.gm_requests) {
        rules.append(element("p", request.text));
        if (request.reply) rules.append(element("p", request.reply));
        else timeSave(rules, "Get GM answer", "gm-answer", () => ({
          source: request.source, revision: request.revision,
        }));
      }
    }
    for (const item of work.declarations.filter(row => row.keep)) {
      const declaration = timeForm(owned, "Keep Your Head");
      declaration.append(element("p", item.keep.intent));
      const [label, heat] = field("Heat to spend", item.keep.available_heat >= 5 ? item.keep.available_heat : 0);
      heat.type = "number";
      heat.min = 0;
      heat.max = item.keep.available_heat;
      declaration.append(label);
      timeSave(declaration, "Open Keep Your Head", "open-declared-keep", () => ({
        review: item.id, sheet_revision: item.keep.sheet_revision, heat: Number(heat.value),
      }));
    }
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

  const handlerPlayTitles = {
    brief: "Brief Them on the Situation", support: "Introduce the Support",
    expectation: "Place an Expectation on Them", dress_them_down: "Dress Them Down",
    get_them_alone: "Get Them Alone", break_down: "Break Down",
    catch_more_flies_with_honey: "Catch More Flies With Honey",
    head_to_the_lab: "Head to the Lab", rebel_sympathizers: "Rebel Sympathizers",
    conditioning_phrases: "Conditioning Phrases",
  };

  function renderHandler(work) {
    for (const offer of work.handler_play_offers ?? []) {
      const title = handlerPlayTitles[offer.play];
      if (!title || offer.requires_native_grant) continue;
      const row = card(body, title);
      if (offer.native_text) row.append(element("p", offer.native_text));
      const payload = {draft: offer.id, game_revision: offer.game_revision, play: offer.play};
      let choice = null;
      if (offer.play === "get_them_alone") {
        const label = element("label", "Order offered by the Handler");
        choice = element("select");
        choice.required = true;
        for (const [value, text] of [["", "Choose an Order"], ["amuse", "Amuse"], ["silence", "Silence"]]) {
          const option = element("option", text);
          option.value = value;
          choice.append(option);
        }
        label.append(choice);
        row.append(label);
      } else if (offer.play === "break_down") {
        choice = textArea(row, "What happens when you break down?", "", 1200, true);
      }
      const request = () => ({...payload,
        ...(offer.play === "get_them_alone" ? {advocate_order: choice.value} : {}),
        ...(offer.play === "break_down" ? {breakdown_account: choice.value.trim()} : {}),
      });
      row.append(button("Start native Play", async key => {
        if (choice && !choice.reportValidity()) return;
        await write("handler-start-play", request(), key);
        await refresh();
      }, () => JSON.stringify(request())));
    }
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

  function renderNativeHandler(native) {
    if (!native) return;
    function confirm(row, label, action, item, payload, fields) {
      row.append(button(label, async key => {
        if (fields.some(field => !field.reportValidity())) return;
        await write("handler-native", {action, id: item.id, revision: item.revision, ...payload()}, key);
        await refresh();
      }, () => JSON.stringify(payload())));
    }
    for (const item of native.advocate) {
      const row = card(body, "Get Them Alone");
      row.append(element("p", item.question));
      if (!item.handler) {
        const answer = textArea(row, "Your answer", "", 1200);
        confirm(row, "Send private answer", "advocate-answer", item,
          () => ({text: answer.value}), [answer]);
      } else if (item.answer && !item.issued) {
        row.append(element("p", item.answer));
        const tag = textArea(row, "Private Tag", "", 120);
        const message = item.order === "amuse" ? textArea(row, "Amuse Order", "", 1200) : null;
        confirm(row, "Issue private Order", "advocate-issue", item,
          () => ({tag: tag.value, message: message?.value ?? ""}), message ? [tag, message] : [tag]);
      }
    }
    for (const item of native.orders) {
      const empathy = item.kind === "advocate_empathy";
      const row = card(body, empathy ? "Conditional Empathy" : "Private Order");
      row.append(element("p", item.order));
      const choices = empathy
        ? [["pass", "Pass"], ["apologize", "Apologize"], ["apologize_profusely", "Apologize profusely"],
          ["compliment_tag", "Compliment and tag"], ["raise_status", "Raise status"]]
        : [["obedient", "Obedient"], ["immediate", "Immediate"], ["hesitant", "Hesitant"],
          ["mouthing_off", "Mouthing off"], ["gritted_teeth", "Through gritted teeth"], ["disobey", "Disobey"]];
      const [label, choice] = choiceField("Your response", choices);
      choice.required = true;
      row.append(label);
      const text = empathy ? textArea(row, "What do you say?", "", 1200, false) : null;
      const tag = empathy ? textArea(row, "Tag", "", 120, false) : null;
      function sync() {
        if (!text || !tag) return;
        text.required = ["apologize", "apologize_profusely", "compliment_tag"].includes(choice.value);
        tag.required = choice.value === "compliment_tag";
        text.parentElement.hidden = !text.required;
        tag.parentElement.hidden = !tag.required;
      }
      choice.addEventListener("change", sync);
      sync();
      confirm(row, "Confirm response", "private-order", item, () => ({choice: choice.value,
        text: text?.required ? text.value : "", tag: tag?.required ? tag.value : "",
      }), empathy ? [choice, text, tag] : [choice]);
    }
    for (const item of native.dress) {
      const row = card(body, "Dress Them Down");
      const text = textArea(row, "Address the Girl’s competency", "", 1200);
      const tag = textArea(row, "Tag to record", "", 120);
      confirm(row, "Confirm competency step", "dress-submit", item,
        () => ({text: text.value, tag: tag.value, target: item.target}), [text, tag]);
    }
    for (const item of native.frantic) {
      const row = card(body, "Break Down");
      row.append(element("p", item.account), element("p", `Saved roll ${item.total}`));
      if (item.choose) {
        const options = element("select");
        options.multiple = options.required = true;
        for (const [value, label] of item.options) {
          const option = element("option", label);
          option.value = value;
          options.append(option);
        }
        const label = element("label", `Choose ${item.choose} effects`);
        label.append(options);
        const targets = item.targets.map(target => [JSON.stringify(target.ref), target.name]);
        const [officeLabel, office] = choiceField("Girl who may find the Handler", targets);
        const [moderateLabel, moderate] = choiceField("Girl for Moderate Punishment", targets);
        const selected = () => Array.from(options.selectedOptions, x => x.value);
        function sync() {
          office.required = selected().includes("office");
          moderate.required = selected().includes("moderate_one");
          officeLabel.hidden = !office.required;
          moderateLabel.hidden = !moderate.required;
          options.setCustomValidity(selected().length === item.choose ? "" : `Select ${item.choose} effects.`);
        }
        options.addEventListener("change", sync);
        sync();
        row.append(label, officeLabel, moderateLabel);
        confirm(row, "Confirm breakdown effects", "frantic-choose", item, () => ({options: selected(),
          office: office.required && office.value ? JSON.parse(office.value) : null,
          moderate: moderate.required && moderate.value ? JSON.parse(moderate.value) : null,
        }), [options, office, moderate]);
      }
      if (item.discover) {
        const text = textArea(row, "What did you find?", "", 1200);
        confirm(row, "Confirm office discovery", "frantic-discover", item, () => ({text: text.value}), [text]);
      }
    }
    renderAdditionalSignatures(native.signatures);
  }

  function menu(parent, label, choices) {
    const [caption, control] = choiceField(label, choices);
    parent.append(caption);
    return control;
  }

  function nativeChoiceForm(row, fields) {
    const controls = fields.map(spec => {
      const input = spec.options.length ? menu(row, spec.label, spec.options)
        : textArea(row, spec.label, "", 1200, spec.required);
      input.required = spec.required;
      if (spec.maximum > 1 && input.tagName === "SELECT") {
        input.multiple = true;
        input.options[0].remove();
        input.addEventListener("change", () => input.setCustomValidity(
          input.selectedOptions.length > spec.maximum || input.selectedOptions.length < spec.minimum
          ? "Choose the required number of entries." : ""
        ));
      }
      return [spec.key,input];
    });
    function answerFields() {
      const answer = {fields:{}};
      for (const [name, control] of controls) {
        const values = control.tagName === "SELECT" ? [...control.selectedOptions].map(x => x.value).filter(Boolean)
          : control.value ? [control.value] : [];
        if (!values.length) continue;
        if (name === "options" || name === "denied") answer[name] = values;
        else if (name === "flag") answer.flag = values[0] === "yes";
        else if (name === "number") answer.number = Number(values[0]);
        else if (name.startsWith("fields.")) answer.fields[name.slice(7)] = values[0];
        else answer[name] = values[0];
      }
      return answer;
    }
    return [answerFields, () => controls.every(([,control]) => control.reportValidity())];
  }

  function renderAdditionalSignatures(native) {
    if (!native || (!native.choices.length && !native.targets.length && !native.seated.length
      && !native.direct_targets.length && !native.hunts.length)) return;
    const section = card(body, "Signature Play decisions");
    for (const item of native.choices) {
      const kind = item.kind;
      if (kind === "trainer_hunt_play" && native.hunts.some(hunt => hunt.choice === item.id)) continue;
      const title = item.direct_order ? "Receive Orders"
        : item.fields ? kind.replaceAll("_", " ")
        : kind.startsWith("mistress_") ? handlerPlayTitles.catch_more_flies_with_honey
        : kind.startsWith("insurgent_") ? handlerPlayTitles.rebel_sympathizers
        : handlerPlayTitles.conditioning_phrases;
      const row = card(section, title);
      row.dataset.nativeSignature = item.id;
      row.tabIndex = -1;
      if (item.text) row.append(element("p", item.text));
      function confirm(label, answer, validate = () => true) {
        row.append(button(label, async key => {
          if (!validate()) return;
          await write("handler-native", {
            id:item.id, revision:item.revision, action:"signature-response", answer:answer(),
          }, key);
          await refresh();
        }, () => JSON.stringify(answer())));
      }
      if (item.fields?.length) {
        const [answerFields, validate] = nativeChoiceForm(row, item.fields);
        confirm("Confirm my choice", () => {
          const answer = answerFields();
          if (kind === "tag_window" && answer.options?.[0] === "tag" && item.tag_marker && !answer.fields.marker)
            answer.fields.marker = item.tag_marker;
          if (kind === "tag_window" && answer.options?.[0] === "gender_man" && answer.denied)
            answer.denied = answer.denied.map(x => x.replace(/^gender-partner:/, ""));
          if (kind === "battle_counter" && answer.options?.length === 1 && answer.options[0] === "pass")
            return {flag:false};
          return answer;
        }, validate);
      } else if (kind === "mistress_honey_offer") {
        const rewards = [["praise","Praise or sympathy"], ["pet_name","A pet name"], ["raise_status","Raise Status"]];
        const picks = rewards.map(([value,label]) => {
          const caption = element("label", label);
          const check = element("input");
          check.type = "checkbox";
          caption.prepend(check);
          row.append(caption);
          return [value,check];
        });
        const praise = textArea(row, "What do you say in praise or sympathy?", "", 1200, false);
        const name = textArea(row, "What pet name do you offer?", "", 1200, false);
        const tag = textArea(row, "Optional matching Tag", "", 120, false);
        const selected = () => picks.filter(([,control]) => control.checked).map(([value]) => value);
        const sync = () => {
          for (const [control, value] of [[praise,"praise"], [name,"pet_name"], [tag,"pet_name"]]) {
            control.parentElement.hidden = !selected().includes(value);
            control.required = control !== tag && !control.parentElement.hidden;
          }
        };
        for (const [,control] of picks) control.addEventListener("change", sync);
        sync();
        confirm("Offer selected rewards", () => ({options:selected(), fields:{
          ...(praise.required ? {praise:praise.value} : {}),
          ...(name.required ? {pet_name:name.value, tag:tag.value} : {}),
        }}), () => {
          if (selected().length < 1 || selected().length > 2) {
            status.textContent = "Choose one or two rewards.";
            return false;
          }
          return praise.reportValidity() && name.reportValidity();
        });
        confirm("Pass", () => ({options:["pass"]}));
      } else if (kind === "mistress_honey_reply") {
        const reward = item.reward;
        row.append(element("p", reward.label));
        if (reward.account) row.append(element("p", reward.account));
        if (reward.tag) row.append(element("p", "Matching Tag · " + reward.tag));
        confirm("Accept reward", () => ({flag:true}));
        confirm("Decline reward", () => ({flag:false}));
      } else if (kind === "mistress_honey_rejection") {
        confirm("Smile and let it go", () => ({options:["smile"]}));
        confirm("Choose Punishment", () => ({options:["punish"]}));
      } else if (kind.startsWith("insurgent_")) {
        const watch = kind === "insurgent_surveillance";
        const account = textArea(row, watch ? "What did you witness?" : "What sympathy do you disclose?", "", 1200);
        confirm(watch ? "Record witnessed lapse" : "Disclose my Girl’s sympathies",
          () => ({flag:true, text:account.value}), () => account.reportValidity());
        confirm("Pass", () => ({flag:false}));
      } else if (kind === "order_response") {
        const selected = menu(row, "Receive Orders", [
          ["obedient", "Obedient"], ["immediate", "Immediate"], ["hesitant", "Hesitant"],
          ["mouthing_off", "Mouthing off"], ["gritted_teeth", "Through gritted teeth"], ["disobey", "Disobey"],
        ]);
        selected.required = true;
        confirm("Confirm my response", () => ({options:[selected.value]}), () => selected.reportValidity());
      } else if (["trainer_speak_answer","trainer_sit","trainer_heel_response","trainer_protect_response"].includes(kind)) {
        const text = textArea(row, kind === "trainer_speak_answer" ? "Your actual answer" : "What does your Girl do?", "", 1200);
        confirm("Confirm my response", () => ({text:text.value}), () => text.reportValidity());
      } else if (["trainer_speak_heard","trainer_rough_heard"].includes(kind)) {
        confirm("Confirm I heard", () => ({flag:true}));
      } else if (kind === "trainer_rough_offer" || kind === "trainer_rough_reply") {
        confirm(kind === "trainer_rough_offer" ? "Extend invitation" : "Accept invitation", () => ({flag:true}));
        confirm("Decline", () => ({flag:false}));
      } else if (kind === "trainer_flirt_play" || kind === "order_disobey") {
        const child = kind === "trainer_flirt_play" ? "Flirt" : "Disobey Orders";
        const account = textArea(row, "What does your Girl do?", "", 1200);
        const [heatLabel, heat] = field("Heat to spend", "0");
        Object.assign(heat, {type:"number", min:"0", step:"1"});
        row.append(heatLabel);
        const witnessed = kind === "order_disobey" ? menu(row, "Was the refusal witnessed?", [
          ["yes","Yes"], ["no","No"],
        ]) : null;
        if (witnessed) witnessed.required = true;
        const request = () => ({action:"signature-child", id:item.id, revision:item.revision,
          sheet_revision:item.sheet_revision, text:account.value, heat:Number(heat.value),
          witnessed:witnessed?.value === "yes"});
        row.append(button("Start " + child, async key => {
          if ([account,heat,witnessed].some(x => x && !x.reportValidity())) return;
          await write("handler-native", request(), key);
          await refresh();
        }, () => JSON.stringify(request())));
      } else if (kind === "trainer_hunt_play") {
        row.append(button("Prepare the original Hunt", async () => {
          const preparation = await read("handler-hunt/" + routeId(item.id));
          const [actor,opponent] = preparation.actors;
          row.replaceChildren(element("h4", "Hunt · All Out Assault"));
          const attacking = menu(row, "Your attacking Asset", actor.assets.map(x => [x.id,x.name]));
          const target = menu(row, opponent.name + "’s Asset", opponent.assets.map(x => [x.id,x.name]));
          const text = textArea(row, "What is your opening?", "", 1200);
          attacking.required = target.required = true;
          const request = () => ({action:"hunt-declare", id:item.id, revision:preparation.revision,
            attacking_asset:attacking.value, target_asset:target.value, text:text.value});
          row.append(button("File Hunt declaration", async key => {
            if ([attacking,target,text].some(x => !x.reportValidity())) return;
            await write("handler-native", request(), key);
            await refresh();
          }, () => JSON.stringify(request())));
        }));
      }
    }
    for (const item of native.hunts) {
      const row = card(section, "Hunt · All Out Assault");
      row.append(element("p", item.text));
      function check(name) {
        const label = element("label", name);
        const input = element("input");
        input.type = "checkbox";
        label.prepend(input);
        row.append(label);
        return input;
      }
      if (item.can_confirm) {
        const opening = check("The opening is established");
        const reach = check("The target is in reach");
        const outside = check("Outside-Frame permission applies");
        const indirect = check("Use an indirect approach");
        const text = textArea(row, "Confirm the actual opening and reach", "", 1200);
        const request = () => ({action:"hunt-confirm", id:item.id, revision:native.game_revision,
          opening:opening.checked, reach:reach.checked, outside_permission:outside.checked,
          indirect:indirect.checked, text:text.value});
        row.append(button("Confirm Hunt facts", async key => {
          if (!text.reportValidity()) return;
          await write("handler-native", request(), key);
          await refresh();
        }, () => JSON.stringify(request())));
      } else if (item.can_roll) {
        const [label, heat] = field("Heat to spend", "0");
        Object.assign(heat,{type:"number",min:"0",step:"1"});
        row.append(label);
        const piloting = check("My Girl is piloting");
        const request = () => ({action:"hunt-roll", id:item.id, revision:native.game_revision,
          sheet_revision:item.sheet_revision, heat:Number(heat.value), piloting:piloting.checked});
        row.append(button("Start Hunt’s All Out Assault", async key => {
          if (!heat.reportValidity()) return;
          await write("handler-native", request(), key);
          await refresh();
        }, () => JSON.stringify(request())));
      } else row.append(element("p", "Waiting for the original adjudicator."));
    }
    for (const [target,name] of native.seated) {
      section.append(button("Grant " + name + " leave to stand", async key => {
        await write("handler-native", {action:"conditioning-leave", id:scene,
          revision:native.game_revision, target}, key);
        await refresh();
      }));
    }
    if (native.direct_targets.length) {
      const row = card(section, "Issue a direct Order");
      const target = menu(row, "Girl", native.direct_targets);
      const order = textArea(row, "What do you order?", "", 1200);
      target.required = true;
      const request = () => ({action:"signature-direct-order", id:scene,
        revision:native.game_revision, target:target.value, text:order.value});
      row.append(button("Issue Order", async key => {
        if (!target.reportValidity() || !order.reportValidity()) return;
        await write("handler-native", request(), key);
        await refresh();
      }, () => JSON.stringify(request())));
    }
    if (!native.targets.length) return;
    const row = card(section, "Issue a Conditioning Phrase");
    row.dataset.nativeSignature = "conditioning_phrase";
    row.tabIndex = -1;
    const target = menu(row, "Girl", native.targets.map(x => [x.id,x.name]));
    target.dataset.signatureTarget = "";
    const phrase = menu(row, "Phrase", []);
    const counterpart = menu(row, "Other Girl", []);
    const actor = menu(row, "Battlefield target", []);
    const text = textArea(row, "What do you say?", "", 1200);
    function options(control, values) {
      const previous = control.value;
      control.replaceChildren(new Option("Choose…",""), ...values.map(([id,name]) => new Option(name,id)));
      if (values.some(([id]) => id === previous)) control.value = previous;
    }
    function sync() {
      const selected = native.targets.find(x => x.id === target.value);
      options(phrase, selected?.phrases ?? []);
      counterpart.required = ["play_gentle","play_rough"].includes(phrase.value);
      actor.required = ["hunt","protect"].includes(phrase.value);
      options(counterpart,native.present.filter(([id]) => id !== target.value));
      options(actor,selected?.actors?.[phrase.value] ?? []);
      counterpart.parentElement.hidden = !counterpart.required;
      actor.parentElement.hidden = !actor.required;
    }
    target.required = phrase.required = true;
    sync();
    target.addEventListener("change",sync);
    phrase.addEventListener("change",sync);
    const order = () => ({action:"conditioning-order", id:scene, revision:native.game_revision,
      target:target.value, phrase:phrase.value, text:text.value,
      counterpart:counterpart.required ? counterpart.value : null, actor:actor.required ? actor.value : null});
    row.append(button("Issue owned phrase", async key => {
      if ([target,phrase,text,counterpart,actor].some(control => !control.reportValidity())) return;
      await write("handler-native", order(), key);
      await refresh();
    }, () => JSON.stringify(order())));
  }

  function renderAIPilotReview(work) {
    const items = (work.reactions ?? []).filter(item => item.ai_pilot || item.ai_alternate);
    if (!items.length) return;
    const list = card(body, "AI contributions");
    for (const item of items) {
      const action = item.ai_alternate ? "Alternate actor initiative"
        : item.kind === "DIALOGUE" ? "Pilot dialogue" : item.initiative ? "Pilot initiative" : "Pilot intent";
      const row = card(list, action);
      if (item.status === "stale_reopen_source") {
        row.append(element("p", "The scene changed. Review a fresh batch."));
        continue;
      }
      row.append(button("Preview " + action.toLowerCase(), async () => {
        const draft = await read("npc-owner-review/" + routeId(item.id));
        if (draft.receipt) {
          row.replaceChildren(element("p", "Native start saved. Any outstanding choices remain with their owners."));
          return;
        }
        if (!draft.proposal) {
          row.replaceChildren(element("p", "The scene changed. Review a fresh batch."));
          return;
        }
        row.replaceChildren(element("h4", action), element("p", draft.proposal.text));
        if (draft.native_play) row.append(element("p", "Native Play · " + draft.native_play.label));
        if (draft.native_play_approved) {
          if (draft.native_play.alternate) {
            const native = draft.native_play.alternate;
            if (native.reach === "requires_judge") row.append(element("p", "The original judge will review reach."));
            const fields = Object.entries(native.choices).map(([field, values]) => {
              const options = field === "heat" ? values.map(value => [String(value), String(value)]) : Object.entries(values);
              const labels = {heat:"Own Heat to spend", asset:"Own attacking Asset", item:"Your offered item"};
              const [label, select] = choiceField(labels[field], options);
              select.required = true;
              row.append(label);
              return [field, select];
            });
            row.append(button("Start approved Play", async key => {
              if (fields.some(([, select]) => !select.reportValidity())) return;
              const choices = Object.fromEntries(fields.map(([field, select]) =>
                [field, field === "heat" ? Number(select.value) : select.value]));
              await write("scene-alternate-start", {proposal:item.id, choices}, key);
              await refresh();
            }));
          } else if (openNativePlay) row.append(button("Open approved Play", () => openNativePlay(draft.native_play)));
          return;
        }
        if (draft.proposal.fiction?.own_action) {
          row.append(element("p", draft.proposal.fiction.own_action));
        }
        if (item.status === "awaiting_delivery") {
          timeSave(row, "Deliver approved dialogue", "npc-deliver", () => ({proposal: item.id}));
          return;
        }
        const reason = textArea(row, "Reason for review", "", 1200, true);
        const candidates = draft.delivery_candidates ?? [];
        const intended = draft.proposal.intended_recipients ?? [];
        const listeners = [];
        if (intended.length && candidates.length === intended.length) {
          row.append(element("p", "Intended listeners · " + candidates.map(item => item.label).join(", ")));
        } else if (!intended.length) {
          for (const listener of candidates) {
            const option = element("label");
            const check = element("input");
            check.type = "checkbox";
            option.append(check, document.createTextNode(listener.label));
            row.append(option);
            listeners.push([check, listener.actor]);
          }
        }
        const payload = decision => ({
          proposal: item.id, decision, reason: reason.value,
          recipients: decision === "approve"
            ? intended.length ? intended
              : listeners.filter(([check]) => check.checked).map(([, actor]) => actor)
            : [],
        });
        if (item.kind !== "DIALOGUE" || (candidates.length && candidates.length >= intended.length)) {
          if (draft.native_play && !draft.native_play.alternate && openNativePlay) {
            row.append(button("Approve intent and open Play", async key => {
              if (!reason.reportValidity()) return;
              await write("npc-review", payload("approve"), key);
              await openNativePlay(draft.native_play);
              await refresh();
            }, () => JSON.stringify(payload("approve"))));
          } else {
            timeSave(row, item.kind === "DIALOGUE" ? "Approve dialogue" : "Accept intent",
              "npc-review", () => payload("approve"));
          }
        }
        timeSave(row, "Decline contribution", "npc-review", () => payload("reject"));
      }));
    }
  }

  function renderAlternateControls(actors) {
    if (!actors?.length) return;
    const panel = card(body, "Alternate actor initiative");
    for (const actor of actors) {
      const row = card(panel, actor.label);
      if (actor.plays?.length) {
        const plays = element("ul");
        for (const play of actor.plays) {
          plays.append(element("li", play.label + (play.reach === "requires_judge" ? " · Reach review required" : "")));
        }
        row.append(plays);
      }
      row.append(button(actor.enabled ? "Return to manual control" : "Allow AI initiative in this scene", async key => {
        await write("scene-alternate-control", {actor:actor.actor, enabled:!actor.enabled,
          revision:actor.revision ?? null}, key);
        await refresh();
      }));
      if (actor.enabled) row.append(button("Refer " + actor.referral, async key => {
        await write("scene-alternate-refer", {actor:actor.actor}, key);
        status.textContent = "Filed for the assigned facilitator.";
      }));
    }
  }

  function renderNativeHandovers(handovers) {
    if (!handovers?.length) return;
    const panel = card(body, "Your handover decisions");
    for (const item of handovers) {
      const row = card(panel, "Handover");
      row.append(element("p", item.account));
      const prompt = item.job === "fan" ? "Item to hand over" : "Item to accept";
      const [label, select] = choiceField(prompt, Object.entries(item.items));
      if (Object.keys(item.items).length) {
        row.append(label);
        timeSave(row, "Accept handover", "scene-alternate-handover-answer", () => ({
          id:item.id, revision:item.revision, item:select.value,
        }));
      }
      timeSave(row, "Decline handover", "scene-alternate-handover-answer", () => ({
        id:item.id, revision:item.revision, item:null,
      }));
    }
  }

  function renderAlternateNativeChoices(choices) {
    if (!choices?.length) return;
    const panel = card(body, "Your alternate Play decisions");
    for (const item of choices) {
      const row = card(panel, item.kind.replaceAll("_", " "));
      const [answer, validate] = nativeChoiceForm(row, item.fields);
      row.append(button("Confirm my choice", async key => {
        if (!validate()) return;
        await write("scene-alternate-answer", {id:item.id, revision:item.revision, answer:answer()}, key);
        await refresh();
      }, () => JSON.stringify(answer())));
    }
  }

  function renderSceneInitiatives(gm, options) {
    const choices = options?.options ?? [];
    const pending = gm?.scene_initiatives ?? [];
    if (!gm || (!choices.length && !pending.length)) return;
    const panel = card(body, "Character initiatives");
    for (const item of choices) {
      const row = card(panel, item.label + " · " + item.subject);
      row.append(element("p", item.source.kind === "opening" ? "Approved opening"
        : item.source.kind === "native" ? "Eligible native Play" : "Witnessed outcome"));
      if (!item.model_configured) {
        row.append(element("p", "Model unassigned for this role."));
        continue;
      }
      row.append(button("Prepare initiative", async key => {
        const request = await write("scene-initiative-open", {option: item.id}, key + ".open");
        if (!request.proposal) await write("reaction-generate", {request: request.id}, key + ".generate");
        await refresh();
        status.textContent = "Filed for private review.";
      }));
    }
    for (const item of pending) {
      const row = card(panel, "Handler initiative");
      if (item.status === "stale_reopen_source") {
        row.append(element("p", "Source changed. Prepare a new initiative."));
        continue;
      }
      row.append(button("Review Handler initiative", async () => {
        const draft = await read("scene-initiative-review/" + routeId(item.id));
        if (!draft.proposal) {
          row.replaceChildren(element("p", "Source changed. Prepare a new initiative."));
          return;
        }
        row.replaceChildren(element("h4", "Handler initiative"), element("p", draft.proposal.text));
        if (draft.native_play) row.append(element("p", "Native Play · " + draft.native_play.label));
        if (draft.native_play_approved) {
          row.append(element("p", "Approved for the Handler’s native controls."));
          if (!reviewOnly && openNativePlay) row.append(button("Open Handler Plays", () => openNativePlay(draft.native_play)));
          return;
        }
        const reason = textArea(row, "Reason for review", "", 1200);
        for (const [decision, label] of [["approve", "Approve intent"], ["reject", "Decline intent"]]) {
          row.append(button(label, async key => {
            if (!reason.reportValidity()) return;
            await write("scene-initiative-review", {proposal:item.id, decision, reason:reason.value}, key);
            await refresh();
          }, () => reason.value));
        }
      }));
    }
  }

  function renderPlanning(queue, gm) {
    const planning = gm.planning;
    if (!planning || (!planning.enabled && !planning.items.length)) return;
    const panel = timeForm(queue, "Private ensemble planning");
    panel.open = planning.items.some(item => item.status === "pending");
    if (planning.enabled && planning.sources.length) {
      const [label, source] = choiceField("Planning source", planning.sources.map(
        (item, index) => [String(index), item.label],
      ));
      source.required = true;
      panel.append(label, button("Draft ensemble plan", async key => {
        if (!source.reportValidity()) return;
        const {kind, scene: source_scene, source: selected} = planning.sources[Number(source.value)];
        await write("plan-generate", {kind, source_scene, source: selected}, key);
        await refresh();
      }, () => source.value));
    } else if (!planning.items.length) {
      panel.append(element("p", "Ensemble planning needs a completed outcome or approved scene closeout."));
    }
    const statusLabels = {
      pending: "Awaiting review", approved: "Approved", rejected: "Declined", stale: "Source changed",
    };
    for (const item of planning.items) {
      const row = card(panel, item.label ?? "Ensemble plan");
      row.append(element("p", statusLabels[item.status] ?? item.status));
      if (item.status === "stale") continue;
      row.append(button("Open ensemble plan", async () => {
        const review = await read("plan-review/" + routeId(item.id));
        row.replaceChildren(element("h4", item.label ?? "Ensemble plan"),
          element("p", statusLabels[review.status] ?? review.status));
        const decision = review.decision;
        if (review.status === "stale" || !decision) return;
        if (decision.reasoning) row.append(element("p", decision.reasoning));
        if (!decision.moves.length) row.append(element("p", "No follow-up proposed."));
        for (const move of decision.moves) {
          const actor = gm.response_targets.find(target => target.actor.kind === move.actor.kind
            && target.actor.entity === move.actor.entity && target.actor.incarnation === move.actor.incarnation);
          const name = actor?.label ?? gm.npc_roster.find(npc => npc.id === move.actor.entity)?.name ?? move.actor.entity;
          const changed = card(row, name);
          changed.append(element("p", move.text), element("p", move.why));
          const handlerMove = review.handler_moves?.[move.front];
          if (handlerMove) {
            const listeners = handlerMove.eligible_listeners.map(listener => listener.label).join(", ");
            if (handlerMove.status === "delivered") {
              changed.append(element("p", "Delivered"));
            } else if (handlerMove.status === "waiting") {
              changed.append(element("p", listeners
                ? "Waiting for an eligible turn from " + listeners + "."
                : "Waiting for a Pilot who shares all cited evidence."));
            } else {
              changed.append(element("p", listeners
                ? "Eligible after approval · " + listeners
                : "No current Pilot shares all cited evidence."));
            }
          }
          const evidence = timeForm(changed, "Front and evidence");
          evidence.append(element("p", review.fronts?.[move.front] ?? move.front));
          for (const ref of move.evidence) evidence.append(element("p", review.evidence?.[ref] ?? ref));
        }
        if (review.status === "pending") {
          for (const [value, label] of [["approve", "Approve ensemble plan"], ["reject", "Decline ensemble plan"]]) {
            row.append(button(label, async key => {
              await write("plan-review", {proposal: item.id, decision: value}, key);
              await refresh();
            }));
          }
        }
      }));
    }
  }

  function renderFacilitator(gm) {
    const queue = card(body, "Facilitator review");
    renderTimingReviews(queue, gm.timing_reviews);
    renderPlanning(queue, gm);
    if (liveTrial && gm.can_generate_handler_need && !reviewOnly) {
      queue.append(button("Review a Handler cue", async () => {
        const timeline = await read("timeline");
        const sources = timeline.entries.filter(x => x.kind === "input" && x.actor.kind === "pilot"
          && ["scene", "comms"].includes(x.channel)).slice(-12).reverse();
        const cues = card(queue, "Choose heard dialogue");
        if (!sources.length) cues.append(element("p", "No eligible Pilot dialogue."));
        for (const entry of sources) {
          const row = card(cues, entry.speaker ?? "Pilot");
          row.append(element("p", entry.text), button("Draft response-need review", async key => {
            const request = await write("handler-need-open", {source_id: entry.id}, key + "-open");
            await write("handler-need-generate", {request: request.id}, key + "-draft");
            await refresh();
          }));
        }
      }));
    }
    for (const pending of gm.handler_needs ?? []) {
      const row = card(queue, "Handler response-need proposal");
      row.append(button("Open response-need proposal", async () => {
        const review = await read("handler-need/" + routeId(pending.id));
        row.replaceChildren(element("h4", "Handler response-need proposal"));
        if (review.status === "stale_reopen_source") {
          row.append(element("p", "This source changed. Reopen the current dialogue to review it."));
        } else {
          row.append(element("p", review.packet.request.question),
            element("p", [review.proposal.action, review.proposal.kind.replaceAll("_", " ")].join(" · ")));
          if (review.proposal.speech_quote) row.append(element("blockquote", review.proposal.speech_quote));
          for (const fact of review.packet.request.context.references) {
            if (review.proposal.source_refs.includes(fact.id)) row.append(element("p", fact.text));
          }
        }
        const reason = textArea(row, "Review note", "", 1200);
        for (const decision of ["approve", "reject"]) {
          if (decision === "approve" && review.status !== "awaiting_gm_review") continue;
          row.append(button(decision === "approve" ? "Approve cue" : "Reject cue", async key => {
            if (!reason.reportValidity()) return;
            await write("handler-need-review", {proposal: pending.id, decision, reason: reason.value}, key);
            await refresh();
          }, () => reason.value));
        }
      }));
    }
    const next = gm.next_plan;
    if (next?.status === "ready") {
      queue.append(element("p", next.text), element("p", next.why),
        element("p", "Awaiting the character’s controller."));
    } else if (next?.status === "waiting") {
      queue.append(element("p", "Waiting for the invited Pilot’s answer."));
    } else if (next?.status === "available") {
      queue.append(element("p", next.text), element("p", next.why));
    }
    if (scene) {
      const closeout = element("div");
      queue.append(closeout);
      closeout.append(button("Review scene closeout", async () => {
        const review = await read("closeout");
        const reports = review.reports.map(report => {
          const label = element("label");
          const checkbox = element("input");
          checkbox.type = "checkbox";
          label.append(checkbox, report.text);
          return {id: report.id, label, checkbox};
        });
        const [sourceLabel, source] = choiceField(
          "Carry one Pilot experience forward (optional)",
          review.reports.map(report => [report.id, report.text]),
        );
        const [kindLabel, kind] = choiceField("What did the Pilot report?", [
          ...(review.offers?.length ? [["accepted_help", "They accepted a Handler offer"]] : []),
          ["declined_help", "They declined help"],
          ["completed_handoff", "A handoff was completed"],
          ["kept_promise", "A promise was kept"],
        ]);
        const [offerLabel, offer] = choiceField("Which delivered offer?", [
          ["", "No linked offer"], ...(review.offers ?? []).map(item => [item.reference, item.text]),
        ]);
        kindLabel.hidden = true;
        const updateOffer = () => {
          offerLabel.hidden = !source.value || !review.offers?.length
            || !["accepted_help", "declined_help"].includes(kind.value);
          offer.required = !offerLabel.hidden && kind.value === "accepted_help";
        };
        source.addEventListener("change", () => {
          kindLabel.hidden = !source.value;
          kind.required = Boolean(source.value);
          updateOffer();
        });
        kind.addEventListener("change", updateOffer);
        updateOffer();
        const payload = () => ({
          revision: review.revision,
          reports: reports.filter(report => report.checkbox.checked || report.id === source.value)
            .map(report => report.id),
          ...(source.value ? {experience: {reference_id: source.value, kind: kind.value,
            ...(!offerLabel.hidden && offer.value ? {offer_reference: offer.value} : {})}} : {}),
        });
        const confirm = button("Close scene and file selected reports", async key => {
          if (!kind.reportValidity() || !offer.reportValidity()) return;
          await write("close", payload(), key);
          await refresh();
        }, () => JSON.stringify(payload()));
        closeout.replaceChildren(element("h4", "Approved Handler reports"));
        for (const report of reports) closeout.append(report.label);
        if (reports.length) closeout.append(sourceLabel, kindLabel, offerLabel);
        closeout.append(confirm);
      }));
      if (activityShadow) {
        const commitments = element("div");
        queue.append(commitments);
        commitments.append(button("Review Handler commitments", async () => {
          const response = await read("handler-commitments");
          commitments.replaceChildren(element("h4", "Handler commitments"));
          if (!response.items.length) commitments.append(element("p", "No pending commitments."));
          for (const item of response.items) {
            commitments.append(element("p", item.offer), element("p", item.choice));
            if (!item.results.length) {
              commitments.append(element("p", "Confirm and disclose a world result to the original participants first."));
              continue;
            }
            const [label, result] = choiceField("Reviewed world result",
              item.results.map(value => [value.id, value.text]));
            result.required = true;
            const payload = () => ({commitment: item.id, reference: result.value});
            commitments.append(label, button("Link result for Handler review", async key => {
              if (!result.reportValidity()) return;
              await write("handler-commitment-link", payload(), key);
              await refresh();
            }, () => JSON.stringify(payload())));
          }
        }));
      }
    }
    if (gm.fictional_time?.clock) {
      const clock = gm.fictional_time.clock;
      queue.append(element("p", `Saved scene clock · ${minuteText(clock.minute)} ${clock.boundary} ${minuteText(clock.deadline)} · ${clock.status.replaceAll("_", " ")}`));
    }
    if (!gm.handler_drafts.length && !gm.outcome_sources.length && !gm.timing_reviews?.length
      && !gm.planning?.items.some(item => item.status === "pending")) {
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
        const listeners = (draft.additional_listeners ?? []).map(listener => {
          const option = element("label");
          const input = element("input");
          input.type = "checkbox";
          input.checked = true;
          option.append(input, document.createTextNode("Also deliver to " + listener.label));
          return {option, input, actor: listener.actor};
        });
        const intended = draft.intended_listeners;
        const recipients = () => intended?.map(listener => listener.actor) ?? [
          draft.source_actor, ...listeners.filter(listener => listener.input.checked).map(x => x.actor),
        ];
        const approve = button("Approve Handler draft", async key => {
          if (!reason.reportValidity()) return;
          await write("handler-approve", {
            draft: item.id, reason: reason.value, recipients: recipients(),
          }, key);
          await refresh();
        }, () => JSON.stringify([reason.value, recipients()]));
        const reject = button("Reject Handler draft", async key => {
          if (!reason.reportValidity()) return;
          await write("handler-reject", {draft: item.id, reason: reason.value}, key);
          await refresh();
        }, () => reason.value);
        row.replaceChildren(element("h4", "Handler draft"), element("p", draft.reply.text));
        if (draft.reply.handler_action) row.append(element("p", draft.reply.handler_action));
        if (draft.reply.handler_play_offer) {
          const play = draft.reply.handler_play_offer;
          row.append(element("p", "Suggested Play · " + (handlerPlayTitles[play] ?? play.replaceAll("_", " "))));
        }
        if (intended) row.append(element("p", "Intended listeners · " + intended.map(x => x.label).join(", ")));
        if (draft.heard_reports?.length) {
          row.append(element("h5", "Heard reports"));
          for (const report of draft.heard_reports) {
            row.append(element("blockquote", `${report.speaker} · ${report.text}`));
          }
          row.append(element("p", "Check that the reply preserves what each speaker meant and what remains uncertain."));
        }
        if (draft.initiative) {
          if (!draft.heard_reports?.length) row.append(element("blockquote", draft.initiative.heard));
          const play = draft.initiative.possible_play;
          if (play) row.append(element("p", `Check native Play · ${play.title}. ${play.trigger}`));
        }
        row.append(...listeners.map(listener => listener.option), label, approve, reject);
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

  function renderMissionDrafts(view, known, pilots) {
    if (!view || (!view.enabled && !view.drafts.length)) return;
    const panel = timeForm(body, "Draft mission briefing");
    panel.open = briefingExpanded;
    panel.addEventListener("toggle", () => {
      if (panel.isConnected) briefingExpanded = panel.open;
    });
    if (view.enabled && view.can_request) {
      panel.append(element("p", "Generation sends the approved goals, difficulty, mission stage and selected facts to the configured provider. The draft stays with the Handler and facilitator until offered."));
      const facts = (known?.facts ?? []).filter(f => f.status === "current");
      const [label, select] = choiceField("Facts to include", facts.map(f => [f.fact_id, f.statement]), "");
      select.multiple = true;
      if (facts.length) panel.append(label);
      timeSave(panel, "Queue draft", "mission-briefing-queue", () => ({
        facts: [...select.selectedOptions].map(option => option.value).filter(Boolean),
      }));
    }
    for (const draft of view.drafts) {
      const heading = {
        queued: "Queued briefing", running: "Generating briefing", interrupted: "Generation interrupted",
        failed: "Generation failed", stale: "Campaign context changed", ready: "Ready for review",
        approved: "Approved briefing", declined: "Declined briefing",
      }[draft.status];
      const row = card(panel, heading ?? draft.status);
      if (view.enabled && draft.own_request && draft.status === "queued") {
        timeSave(row, "Generate briefing", "mission-briefing-run", () => ({id: draft.id}));
      }
      if (draft.status === "failed" && view.can_request) {
        row.append(element("p", "Check the provider settings, then queue a new draft."));
      }
      if (!draft.proposal) continue;
      row.append(element("p", draft.proposal.objective));
      if (draft.proposal.terms) {
        const terms = element("dl");
        terms.append(
          element("dt", "Boundary"), element("dd", draft.proposal.terms.scope),
          element("dt", "What to confirm"), element("dd", draft.proposal.terms.completion),
        );
        row.append(terms);
      }
      if (draft.proposal.hard_stake) row.append(element("p", draft.proposal.hard_stake));
      if (view.facilitator && draft.status === "ready") {
        timeSave(row, "Approve exact briefing", "mission-briefing-review", () => ({
          id: draft.id, result: draft.result_id, approve: true,
        }));
        timeSave(row, "Decline draft", "mission-briefing-review", () => ({
          id: draft.id, result: draft.result_id, approve: false,
        }));
      }
      if (view.can_request && draft.own_request && draft.status === "approved" && pilots?.length) {
        const [label, invitees] = choiceField("Invite Pilots", pilots.map(x => [x.id, x.label]), "");
        invitees.multiple = true;
        row.append(label);
        timeSave(row, "Send approved briefing", "mission-briefing-offer", () => ({
          briefing_draft: draft.briefing_draft,
          pilots: [...invitees.selectedOptions].map(option => option.value).filter(Boolean),
        }));
      }
    }
  }

  function showSceneOpening(opening) {
    sceneHeader.replaceChildren();
    sceneHeader.hidden = !opening;
    if (!opening) return;
    sceneHeader.append(element("h3", opening.position
      ? opening.location + " · " + slotText(opening.position) : opening.location));
    for (const detail of opening.details) sceneHeader.append(element("p", detail.text));
    if (opening.intro) sceneHeader.append(element("p", opening.intro));
  }

  function renderSceneOpening(view) {
    const {opening, draft} = view;
    showSceneOpening(opening);
    if (!draft) return;
    const row = card(body, "Scene opening");
    const form = timeForm(row, opening ? "Edit scene opening" : "Frame this scene");
    form.open = !opening;
    if (draft.position) form.append(element("p", slotText(draft.position)));
    const [locationLabel, location] = field("Location", draft.location);
    location.maxLength = 120;
    form.append(locationLabel);
    const intro = textArea(form, "Opening line", draft.intro, 600, false);
    const offDuty = element("input");
    offDuty.type = "checkbox";
    offDuty.checked = draft.off_duty === true;
    const offDutyLabel = element("label");
    offDutyLabel.append(offDuty, document.createTextNode("Off-Duty portrayal"));
    form.append(offDutyLabel);
    const choices = draft.suggestions.map(detail => {
      const input = element("input");
      input.type = "checkbox";
      input.checked = draft.selected.includes(detail.id);
      const label = element("label");
      label.append(input, document.createTextNode(detail.text));
      form.append(label);
      return {id: detail.id, input};
    });
    const intent = () => ({
      revision: draft.revision,
      draft: {
        location: location.value, intro: intro.value, off_duty: offDuty.checked,
        details: choices.filter(choice => choice.input.checked).map(choice => choice.id),
      },
    });
    form.append(button("Publish scene opening", async key => {
      if (!location.reportValidity()) return;
      const payload = intent();
      if (payload.draft.details.length > 2) throw new Error("Choose up to two scene details.");
      if (!payload.draft.details.length && !intro.value.trim()) {
        throw new Error("Enter a short opening line or choose a scene detail.");
      }
      await write("scene-opening-publish", payload, key);
      await refresh();
    }, () => JSON.stringify(intent())));
    if (!view.memory?.length) return;
    const memory = timeForm(row, "Private memory review");
    memory.open = !opening;
    const kinds = {promise: "Promise", pressure: "Pressure", corrected_report: "Corrected report", relationship_term: "Relationship term"};
    for (const suggestion of view.memory) {
      const item = timeForm(memory, [kinds[suggestion.kind], suggestion.character].filter(Boolean).join(" · "));
      if (suggestion.kind !== "corrected_report") item.append(element("p", suggestion.text));
      item.append(element("p", "Source scene · " + suggestion.source_label));
      for (const source of suggestion.sources) {
        item.append(element("p", source.text));
        item.append(element("p", "Known to " + source.audience.join(", ")));
      }
      item.append(button("Carry into this scene", async key => {
        try {
          await write("scene-memory-carry", {source_scene: suggestion.source_scene, review: suggestion.review}, key);
        } catch (error) {
          if (/^(STALE_SCENE_MEMORY|OBSERVATION_DISABLED):/.test(error.message)) await refresh();
          throw error;
        }
        await refresh();
        status.textContent = "Memory carried for the approved characters.";
      }));
    }
  }

  async function refresh() {
    if (reviewOnly) {
      const [gm, policy, observation, review, sceneOpening, initiatives] = await Promise.all([
        read("gm-work", true), read("activity-policy", true), read("status", true),
        read("activity-review", true), read("scene-opening", true), read("scene-initiative", true),
      ]);
      body.replaceChildren();
      renderSceneOpening(sceneOpening ?? {});
      renderShadow(policy, observation, review);
      renderSceneInitiatives(gm, initiatives);
      if (gm) renderFacilitator(gm);
      body.append(button("Refresh Director work", refresh));
      return;
    }
    const [work, gm, opening, brief, persona, policy, observation, review, time, timingReview, sessionZero, pilotDossiers, canon, missionDrafts, sceneOpening, nativeHandler, initiatives, alternate, handovers, alternateChoices] = await Promise.all([
      scene ? read("work", true) : null, scene ? read("gm-work", true) : null,
      read("opening", true), read("opening-brief", true), read("persona-setup", true),
      activityShadow ? read("activity-policy", true) : null,
      activityShadow ? read("status", true) : null,
      activityShadow ? read("activity-review", true) : null,
      read("fictional-time", true),
      scene ? read("timing-review", true) : null,
      !scene ? read("session-zero", true) : null,
      scene ? read("pilot-dossiers", true) : null,
      scene ? Promise.all([
        "canon-window", "canon-proposals", "canon-known", "canon-public", "canon-review",
        "canon-review-window", "canon-world", "canon-witnesses", "canon-briefing",
      ].map(route => read(route, true))) : null,
      scene ? read("mission-briefing", true) : null,
      scene ? read("scene-opening", true) : null,
      scene ? read("handler-native-work", true) : null,
      scene && liveTrial ? read("scene-initiative", true) : null,
      scene && liveTrial ? read("scene-alternate-actors", true) : null,
      scene && liveTrial ? read("scene-alternate-handovers", true) : null,
      scene && liveTrial ? read("scene-alternate-choices", true) : null,
    ]);
    body.replaceChildren();
    if (scene) renderSceneOpening(sceneOpening ?? {});
    if (activityShadow) renderShadow(policy, observation, review, nativeHandler?.signatures);
    renderSceneInitiatives(gm, initiatives);
    renderAlternateControls(alternate?.actors);
    renderNativeHandovers(handovers?.handovers);
    renderAlternateNativeChoices(alternateChoices?.choices);
    if (nativeHandler) renderNativeHandler(nativeHandler);
    if (canon) renderCanon(canon, time?.scenes?.find(booking => booking.id === scene));
    renderMissionDrafts(missionDrafts, canon?.[2], time?.handler_controls?.pilots);
    if (sessionZero && (sessionZero.owner_preview || sessionZero.can_set_group || sessionZero.in_group)) renderSessionZero(sessionZero);
    if (opening) renderOpening(opening);
    if (brief?.launched) renderBrief(brief);
    if (persona) renderPersona(persona, sessionZero?.handler_ready === sessionZero?.viewer
      ? sessionZero?.profile : null);
    const inIntro = sessionZero?.opening && sessionZero.opening_day < sessionZero.opening.first_mission_day;
    if (time && !inIntro && (time.mode === "asynchronous" || time.handler_controls)) {
      const row = card(body, "Fictional time");
      renderCalendar(row, time, time.handler_controls);
      if (time.mode === "asynchronous") renderMissionClock(row, time, time.handler_controls);
      renderTimingReviews(row, time.timing_reviews);
    }
    if (!work && scene) {
      body.append(element("p", "Scene work is unavailable. Check scene membership and consent."));
    } else if (work) {
      renderHandler(work);
      if (activityShadow) renderAIPilotReview(work);
      if (gm) renderFacilitator(gm);
      if (pilotDossiers) renderPilotDossiers(pilotDossiers, work);
      body.append(button("Open alternate actor portrayal", () =>
        openSheetPortrayal({activityFetch, scene, kind:"alternate"})));
      renderOwn(work);
    }
    if (!work || !gm) renderTimingReviews(body, timingReview?.items);
    body.append(button(scene ? "Refresh Director work" : "Refresh campaign setup", refresh));
  }

  const loadDesk = () => {
    refresh().catch(error => {
      body.replaceChildren();
      status.textContent = error.message;
    });
  };
  details.addEventListener("toggle", () => {
    if (details.open) loadDesk();
  });
  if (scene) read("scene-opening", true).then(view => showSceneOpening(view?.opening)).catch(error => {
    status.textContent = error.message;
  });
  return () => {
    if (details.open) loadDesk();
    else details.open = true;
  };
}

async function activityAIRequest(activityFetch, path, options) {
  const response = await activityFetch(path, options);
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || "AI setup or review is unavailable.");
    error.httpStatus = response.status;
    throw error;
  }
  return result;
}

export function mountActivityAISetup(parent, activityFetch, openReview) {
  const panel = element("details");
  panel.hidden = true;
  const setup = element("section");
  const providerBody = element("div");
  const providerStatus = element("p");
  providerStatus.setAttribute("role", "status");
  const refresh = element("button", "Refresh AI setup");
  refresh.type = "button";
  panel.append(element("summary", "Facilitator"), setup, providerStatus, providerBody, refresh);
  parent.prepend(panel);
  const probeKeys = new Map();
  let testing = false;
  let loading = false;
  const roleLabels = {handler:"Handler", pilot:"AI Pilots", director:"Director"};
  const providerLabels = {
    unchecked: "Connection unchecked",
    checking: "Checking connection",
    unused: "Awaiting first response",
    ok: "Response received",
    authentication: "The provider rejected the API key",
    model_access: "The project could not access this model",
    rate_limit: "The provider returned a rate or quota limit",
    timeout: "The provider timed out",
    incomplete: "The provider returned an incomplete response",
    invalid_response: "The response did not match the expected format",
    unavailable: "The provider request failed",
    attempt_limit: "The process has reached its attempt limit",
  };
  const providerUrl = "/api/activity/ai-provider";

  function renderModelSelection(selection) {
    const form = element("form");
    const inputs = new Map();
    for (const [role, labelText] of Object.entries(roleLabels)) {
      const [label, input] = field(labelText + " model ID", selection.models[role] ?? "");
      input.maxLength = 128;
      input.required = role === "handler";
      input.autocomplete = "off";
      form.append(label);
      inputs.set(role, input);
    }
    const save = element("button", "Save model selection");
    save.type = "submit";
    form.append(element("p", "Leave AI Pilots or Director blank to disable that role's model."), save);
    let previous;
    let key;
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (testing) return;
      const models = Object.fromEntries([...inputs].map(([role, input]) => [role, input.value.trim()]));
      const body = JSON.stringify({revision: selection.revision, models});
      if (body !== previous) {
        previous = body;
        key = crypto.randomUUID();
      }
      testing = save.disabled = true;
      try {
        const result = await activityAIRequest(activityFetch, "/api/activity/ai-models", {
          method: "POST",
          headers: {"Content-Type": "application/json", "Idempotency-Key": key},
          body,
        });
        renderSetup(result);
        providerStatus.textContent = "Model selection saved.";
      } catch (error) {
        providerStatus.textContent = error.message;
      } finally {
        testing = save.disabled = false;
      }
    });
    setup.append(form);
  }

  function renderProviders(view, enabled) {
    providerBody.replaceChildren();
    const entries = new Map();
    for (const [role, config] of Object.entries(view.roles)) {
      if (!config) continue;
      if (!entries.has(config.model)) entries.set(config.model, {role, config, labels: []});
      entries.get(config.model).labels.push(roleLabels[role]);
    }
    providerBody.append(element("p", "A connection check sends a synthetic request and uses API credits."));
    const modelVariables = {handler: "HANDLER", pilot: "PILOT", director: "DIRECTOR"};
    for (const [role, config] of Object.entries(view.roles)) {
      if (!config) providerBody.append(element("p", roleLabels[role] + " · No model configured on the host (" +
        "GIRLFRAME_ACTIVITY_" + modelVariables[role] + "_MODEL)"));
    }
    for (const {role, config, labels} of entries.values()) {
      const row = element("section");
      row.append(element("h3", labels.join(" · ")), element("p", config.model));
      const reachedLimit = config.attempts >= config.attempt_limit;
      row.append(element("p", config.attempts + " of " + config.attempt_limit + " attempts used this run"));
      if (config.reported_usage_calls) {
        row.append(element("p", "Reported tokens · " + config.input_tokens + " input · " + config.output_tokens + " output"));
      }
      const connection = providerLabels[config.connection];
      if (connection) row.append(element("p", connection));
      if (!["unused", config.connection].includes(config.last_status)) {
        row.append(element("p", "Latest API call · " + providerLabels[config.last_status]));
      }
      if (reachedLimit) row.append(element("p", providerLabels.attempt_limit));
      const test = element("button", "Check " + labels.join(" / ") + " connection");
      test.type = "button";
      test.disabled = !enabled || config.connection === "checking" || (reachedLimit && !probeKeys.has(role));
      test.addEventListener("click", async () => {
        if (testing) return;
        testing = true;
        test.disabled = true;
        providerStatus.textContent = providerLabels.checking;
        if (!probeKeys.has(role)) probeKeys.set(role, crypto.randomUUID());
        try {
          const result = await activityAIRequest(activityFetch, providerUrl, {method:"POST",
            headers:{"Content-Type":"application/json", "Idempotency-Key":probeKeys.get(role)},
            body:JSON.stringify({role}),
          });
          if (result.result !== "checking") probeKeys.delete(role);
          providerStatus.textContent = providerLabels[result.result];
          renderProviders(result, enabled);
        } catch (error) {
          if ([401, 403, 404].includes(error.httpStatus)) panel.hidden = true;
          else providerStatus.textContent = error.message;
          test.disabled = false;
        } finally {
          testing = false;
        }
      });
      row.append(test);
      providerBody.append(row);
    }
  }

  function renderSetup(view) {
    const [label, uuid] = field("Campaign UUID", view.campaign_id);
    uuid.required = false;
    uuid.readOnly = true;
    const copy = element("button", "Copy campaign UUID");
    copy.type = "button";
    const feedback = element("p");
    feedback.setAttribute("role", "status");
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(view.campaign_id);
        feedback.textContent = "Campaign UUID copied.";
      } catch {
        uuid.focus();
        uuid.select();
        feedback.textContent = "Campaign UUID selected. Use your copy shortcut.";
      }
    });
    setup.replaceChildren(element("h3", "AI setup"), label, copy, feedback);
    setup.append(element("p", "Set up AI Pilots under Session Zero → Campaign plan. The group approves their seats with the plan."));
    providerBody.replaceChildren();
    if (view.setup_preview) {
      setup.append(
        element("p", "Facilitator setup status · Read only"),
        element("p", "Handler · HarpyEngine bot"),
        element("p", "Model provider · " + (view.configured ? "Configured" : "Unconfigured")),
      );
      if (view.configured) setup.append(element("p", "Handler model · " + view.handler_model),
        element("p", view.ai_on ? "AI assistance · On" : "AI assistance · Off"));
    } else if (!view.configured) {
      setup.append(element("p", "Model connection needs server setup."),
        element("pre", [
          "GIRLFRAME_ACTIVITY_AI_CAMPAIGN=" + view.campaign_id,
          "GIRLFRAME_ACTIVITY_HANDLER_MODEL=<OpenAI model ID>",
        ].join("\n")),
        element("p", "Set these on the Activity host. Add OPENAI_API_KEY to the host’s secrets, then restart the test Activity."));
    } else if (!view.provider) {
      setup.append(element("p", "Server configured. The facilitator can manage AI after the group approves the Session Zero plan."));
    } else {
      const enabled = view.policy.enabled;
      setup.append(element("p", enabled ? "AI assistance · On" : "AI assistance · Off"),
        element("p", "Scene consent and facilitator review still apply when AI assistance is on."));
      const toggle = element("button", enabled ? "Turn AI assistance off" : "Turn AI assistance on");
      toggle.type = "button";
      toggle.addEventListener("click", async () => {
        if (testing) return;
        testing = toggle.disabled = true;
        try {
          renderSetup(await activityAIRequest(activityFetch, "/api/activity/ai-settings", {
            method: "POST",
            headers: {"Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID()},
            body: JSON.stringify({enabled: !enabled, revision: view.policy.revision}),
          }));
          providerStatus.textContent = enabled ? "AI assistance is off." : "AI assistance is on.";
        } catch (error) {
          providerStatus.textContent = error.message;
          toggle.disabled = false;
        } finally {
          testing = false;
        }
      });
      setup.append(toggle);
      renderModelSelection(view.model_selection);
      if (openReview) {
        const review = element("button", "Review Handler and Director Plays");
        review.type = "button";
        review.addEventListener("click", openReview);
        setup.append(review);
      }
      renderProviders(view.provider, enabled);
    }
    panel.hidden = false;
  }

  async function loadSetup() {
    if (testing || loading) return;
    loading = true;
    try {
      renderSetup(await activityAIRequest(activityFetch, "/api/activity/ai-setup"));
    } catch (error) {
      if ([401, 403, 404].includes(error.httpStatus)) panel.hidden = true;
      else providerStatus.textContent = error.message;
    } finally {
      loading = false;
    }
  }

  refresh.addEventListener("click", loadSetup);
  panel.addEventListener("toggle", () => { if (panel.open) loadSetup(); });
  return (show = false) => {
    if (show) panel.open = true;
    return loadSetup();
  };
}

export function mountStartFresh(parent, activityFetch, openCampaign) {
  const path = "/api/activity/start-fresh";
  const launch = element("button", "Start fresh");
  launch.type = "button";
  launch.hidden = true;
  launch.setAttribute("aria-haspopup", "dialog");
  parent.append(launch);
  const dialog = element("dialog");
  dialog.setAttribute("aria-labelledby", "start-fresh-title");
  const title = element("h2", "Start fresh");
  title.id = "start-fresh-title";
  const form = element("form");
  const [nameLabel, name] = field("New campaign name", "");
  name.maxLength = 80;
  const [confirmationLabel, confirmation] = field("Type the current campaign name", "");
  confirmation.maxLength = 80;
  const explanation = element("p");
  const feedback = element("p");
  feedback.setAttribute("role", "status");
  const cancel = element("button", "Cancel");
  cancel.type = "button";
  const confirm = element("button", "Archive and start fresh");
  confirm.type = "submit";
  form.append(explanation, nameLabel, confirmationLabel, confirm, cancel, feedback);
  dialog.append(title, form);
  document.body.append(dialog);
  let current;
  let filing = false;
  let intent;
  let key;
  launch.addEventListener("click", () => {
    if (!current || dialog.open) return;
    form.reset();
    intent = undefined;
    feedback.textContent = "";
    explanation.textContent = `Archive ${current} in a private backup and open a new campaign in this channel with empty scene, character, and Session Zero records.`;
    dialog.showModal();
    name.focus();
  });
  cancel.addEventListener("click", () => { if (!filing) dialog.close(); });
  dialog.addEventListener("cancel", event => { if (filing) event.preventDefault(); });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (filing) return;
    if (confirmation.value !== current || !name.value.trim()) {
      feedback.textContent = "Enter a new name and type the exact current campaign name.";
      return;
    }
    const body = JSON.stringify({name:name.value, confirmation:confirmation.value});
    if (body !== intent) {
      intent = body;
      key = crypto.randomUUID();
    }
    filing = confirm.disabled = cancel.disabled = true;
    feedback.textContent = "Verifying the backup and creating the new campaign…";
    try {
      const result = await activityAIRequest(activityFetch, path, {method:"POST",
        headers:{"Content-Type":"application/json","Idempotency-Key":key}, body});
      for (let remaining = 90; remaining > 0; remaining--) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const progress = await activityAIRequest(activityFetch, path + "/" + encodeURIComponent(result.job));
        if (progress.state === "failed") throw new Error(progress.error);
        if (progress.state === "complete") {
          dialog.close();
          openCampaign(progress.campaign_id);
          return;
        }
      }
      throw new Error("The reset is still running. Reopen the Activity from this channel to check its progress.");
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      filing = confirm.disabled = cancel.disabled = false;
    }
  });
  return async () => {
    launch.hidden = true;
    try {
      current = (await activityAIRequest(activityFetch, path)).current_name;
      launch.hidden = !current;
    } catch {
      current = undefined;
    }
  };
}

export function mountActivityAITrial(parent, activityFetch, openNativePlay) {
  const panel = element("details");
  const status = element("p");
  status.setAttribute("role", "status");
  const workspace = element("section");
  const [sceneLabel, scene] = choiceField("Scene", []);
  const refresh = element("button", "Refresh scenes");
  refresh.type = "button";
  panel.append(element("summary", "Reviewed AI scenes"), sceneLabel, refresh, status, workspace);
  parent.prepend(panel);
  let selectedScenes = [];
  let visit = 0;
  let discovery = 0;

  async function openScene() {
    const generation = ++visit;
    workspace.replaceChildren();
    const selection = selectedScenes.find(x => x.id === scene.value);
    if (!selection) return;
    const root = "/api/director/" + encodeURIComponent(selection.id) + "/";
    const reviewOnly = selection.speaker === null;
    mountDirectorDesk(workspace, selection.id, activityFetch, true, true, reviewOnly, openNativePlay);
    if (reviewOnly) return;
    const room = element("section");
    const transcript = element("ol");
    const form = element("form");
    const note = element("p");
    const reload = element("button", "Refresh scene dialogue");
    reload.type = "button";
    const text = textArea(form, "In-character dialogue", "", 1000);
    const [channelLabel, channel] = choiceField("Audience", [["comms", "Scene comms"], ["scene", "Scene"], ["private", "Private note"]], "comms");
    const send = element("button", "Send scene dialogue");
    const cancel = element("button", "Cancel correction");
    cancel.type = "button";
    cancel.hidden = true;
    note.setAttribute("role", "status");
    form.append(channelLabel, send, cancel);
    room.append(element("h3", selection.label), reload, note, transcript, form);
    workspace.append(room);
    let correction;
    let pending;

    function clear() {
      correction = undefined;
      pending = undefined;
      text.value = "";
      channel.value = "comms";
      channel.disabled = false;
      cancel.hidden = true;
      send.textContent = "Send scene dialogue";
    }

    async function load() {
      const state = await activityAIRequest(activityFetch, root + "status");
      if (generation !== visit) return;
      form.hidden = !(state.consented && state.mode === "shadow");
      transcript.replaceChildren();
      if (form.hidden) {
        note.textContent = "Scene dialogue opens when observation is enabled and every human participant consents.";
        return;
      }
      note.textContent = state.phase === "ready" ? "A batch is ready for private review." : "";
      const view = await activityAIRequest(activityFetch, root + "timeline");
      if (generation !== visit) return;
      for (const entry of view.entries) {
        const speaker = entry.speaker ?? ({gm:"GM", handler:"Handler", pilot:"Pilot", npc:"NPC"}[entry.actor.kind]);
        const item = element("li");
        item.append(element("strong", speaker), element("p", entry.text));
        if (entry.action) item.append(element("p", entry.action));
        if (entry.own_input) {
          const edit = element("button", "Correct my dialogue");
          edit.type = "button";
          edit.addEventListener("click", () => {
            correction = entry;
            pending = undefined;
            text.value = entry.text;
            channel.value = entry.channel;
            channel.disabled = true;
            cancel.hidden = false;
            send.textContent = "Save correction";
            text.focus();
          });
          item.append(edit);
        }
        transcript.append(item);
      }
    }

    cancel.addEventListener("click", clear);
    reload.addEventListener("click", () => load().catch(error => { note.textContent = error.message; }));
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (!text.value.trim()) return;
      send.disabled = true;
      try {
        const turn = {
          speaker: selection.speaker, text: text.value.trim(), fictional_channel: channel.value,
          ...(correction ? {source_id: correction.id, expected_source_revision: correction.revision} : {}),
        };
        const signature = JSON.stringify(turn);
        if (pending?.signature !== signature) {
          const state = await activityAIRequest(activityFetch, root + "status");
          pending = {signature, key: crypto.randomUUID(), body: {...turn, expected_scene_revision: state.scene_revision}};
        }
        if (generation !== visit) return;
        await activityAIRequest(activityFetch, root + "input", {method: "POST", headers: {"Content-Type": "application/json", "Idempotency-Key": pending.key},
          body: JSON.stringify(pending.body)});
        clear();
        await load();
      } catch (error) {
        if (error.httpStatus === 409) pending = undefined;
        note.textContent = error.message;
      } finally {
        send.disabled = false;
      }
    });
    await load();
  }

  async function discover() {
    const count = ++discovery;
    const previous = scene.value;
    const result = await activityAIRequest(activityFetch, "/api/activity/review-scenes");
    if (count !== discovery) return;
    selectedScenes = result.scenes;
    scene.replaceChildren(element("option", "Choose…"));
    scene.firstChild.value = "";
    for (const row of selectedScenes) {
      const option = element("option", row.label);
      option.value = row.id;
      scene.append(option);
    }
    status.textContent = selectedScenes.length ? "" : "No open reviewed scenes are available to you.";
    scene.value = selectedScenes.some(x => x.id === previous) ? previous : selectedScenes.length === 1 ? selectedScenes[0].id : "";
    await openScene();
  }

  const showError = error => { status.textContent = error.message; };
  scene.addEventListener("change", () => openScene().catch(showError));
  refresh.addEventListener("click", () => discover().catch(showError));
  panel.addEventListener("toggle", () => {
    if (panel.open) discover().catch(showError);
  });
  return () => {
    panel.open = true;
    panel.scrollIntoView({block: "nearest"});
  };
}
