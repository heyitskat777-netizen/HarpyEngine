// Mount into the authenticated Activity scene. Sent and received text is plain text.
export function npcRpc(endpoint, headers = () => ({})) {
  const address = new URL(endpoint, document.baseURI);
  if (address.origin !== location.origin) {
    throw new Error("Use the Activity's authenticated, same-origin NPC endpoint.");
  }
  return async (sceneId, operation, payload = {}) => {
    const response = await fetch(address, {
      method: "POST",
      credentials: "same-origin",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ scene_id: sceneId, operation, payload }),
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(data.error || "The NPC controls are temporarily unavailable.");
    }
    return data;
  };
}

const statusText = {
  queued: "Queued",
  running: "Drafting",
  ready: "Ready for facilitator review",
  approved: "Approved",
  declined: "Declined",
  stale: "The scene changed. Request a new draft.",
  failed: "Drafting failed. Request a new draft or reply manually.",
  interrupted: "Drafting was interrupted. Request a new draft.",
  needs_ruling: "Awaiting a manual ruling",
};

export function mountNpcControls(root, { sceneId, call, openScene, sceneLabel, sourceTurn }) {
  const panel = document.createElement("section");
  panel.className = "harpy-npc-controls";
  panel.setAttribute("aria-label", "NPC scene controls");
  root.append(panel);

  let view;
  let alive = true;
  let busy = false;
  let notice = "";
  let error = "";
  let linkedTurn = sourceTurn;
  let statement = linkedTurn?.text ?? "";
  let npcId = "";
  const destinations = new Map();
  const pending = new Map();
  const speechEdits = new Map();

  function node(tag, value, parent) {
    const item = document.createElement(tag);
    if (value) item.textContent = value;
    parent.append(item);
    return item;
  }

  function button(label, parent, onClick) {
    const action = node("button", label, parent);
    action.type = "button";
    action.disabled = busy;
    action.addEventListener("click", onClick);
    return action;
  }

  function field(parent, labelText, tag) {
    const label = node("label", labelText, parent);
    const input = node(tag, "", label);
    input.disabled = busy;
    return input;
  }

  function option(select, value, label) {
    const entry = node("option", label, select);
    entry.value = value;
  }

  async function perform(label, action) {
    if (busy || !alive) return;
    busy = true;
    error = "";
    notice = label;
    render();
    try {
      await action();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The NPC controls are unavailable.";
      notice = "";
    } finally {
      busy = false;
      render();
    }
  }

  function refresh() {
    return perform("Refreshing…", async () => {
      view = await call(sceneId, "overview");
      notice = "";
    });
  }

  function mutate(label, operation, payload, success) {
    return perform(label, async () => {
      const identity = JSON.stringify({ operation, payload });
      if (operation !== "resume" && !pending.has(identity)) {
        pending.set(identity, crypto.randomUUID());
      }
      const data = operation === "resume"
        ? payload
        : { ...payload, submission_id: pending.get(identity) };
      const result = await call(sceneId, operation, data);
      view = await call(sceneId, "overview");
      pending.delete(identity);
      if (operation === "review") speechEdits.delete(payload.result_id);
      if (operation === "address") {
        statement = "";
        linkedTurn = undefined;
      }
      notice = typeof success === "function" ? success(result) : success;
    });
  }

  function addressForm() {
    const targets = view.targets;
    if (!targets || targets.npcs.length === 0) return;
    const form = node("form", "", panel);
    node("h3", "Address NPC", form);
    const select = field(form, "NPC", "select");
    for (const npc of targets.npcs) option(select, npc.id, npc.name);
    if (targets.npcs.some(npc => npc.id === npcId)) select.value = npcId;
    select.addEventListener("change", () => { npcId = select.value; });
    const input = field(form, "Your line", "textarea");
    input.value = statement;
    input.readOnly = Boolean(linkedTurn);
    input.maxLength = 600;
    input.required = true;
    input.rows = 3;
    input.addEventListener("input", () => { statement = input.value; });
    node("p", "The Handler may send your line and the NPC’s name to the configured AI.", form);
    const submit = node("button", "Address NPC", form);
    submit.type = "submit";
    submit.disabled = busy;
    form.addEventListener("submit", event => {
      event.preventDefault();
      if (!input.value.trim()) return;
      npcId = select.value;
      void mutate("Saving address…", "address", {
        npc_id: npcId, statement: input.value, window: targets.window,
        ...(linkedTurn ? {source_turn: {
          source_id: linkedTurn.source_id, revision: linkedTurn.revision,
        }} : {}),
      }, "Address saved.");
    });
  }

  function addressesSection() {
    if (view.addresses.length === 0) return;
    const section = node("section", "", panel);
    node("h3", view.role === "pilot" ? "Your addresses" : "NPC addresses", section);
    for (const address of view.addresses) {
      const card = node("article", "", section);
      node("strong", address.npc_name, card);
      node("p", address.statement, card);
      if (view.role !== "handler" || !view.enabled || view.unavailable) continue;
      const drafts = view.requests.filter(request => request.address_id === address.id);
      if (drafts.some(request => ["ready", "queued", "running", "approved"].includes(request.status))) {
        continue;
      }
      const actions = node("div", "", card);
      actions.className = "harpy-npc-actions";
      button("Draft NPC Reply", actions, () => void mutate(
        "Drafting NPC reply…", "draft", { address_id: address.id }, result => statusText[result.status],
      ));
      if (view.destinations?.length) {
        const select = field(actions, "Guide destination", "select");
        for (const place of view.destinations) option(select, place.id, place.name);
        if (view.destinations.some(place => place.id === destinations.get(address.id))) {
          select.value = destinations.get(address.id);
        }
        select.addEventListener("change", () => destinations.set(address.id, select.value));
        button("Draft Guide Offer", actions, () => void mutate(
          "Drafting guide offer…", "draft",
          { address_id: address.id, guide_destination_id: select.value },
          result => statusText[result.status],
        ));
      }
      const leads = view.leads?.[address.npc_id];
      if (leads?.length) {
        const select = field(actions, "Witnessed fact", "select");
        for (const lead of leads) option(select, lead.fact_id, lead.statement);
        button("Draft Private Lead", actions, () => void mutate(
          "Drafting private lead…", "draft",
          { address_id: address.id, lead_fact_id: select.value },
          result => statusText[result.status],
        ));
      }
    }
  }

  function witnessSection() {
    const witness = view.lead_witness;
    if (!witness?.npcs.length || !witness.facts.length) return;
    const form = node("form", "", panel);
    node("h3", "NPC witness", form);
    const npc = field(form, "Witnessing NPC", "select");
    for (const item of witness.npcs) option(npc, item.id, item.name);
    const fact = field(form, "Fact witnessed in this scene", "select");
    for (const item of witness.facts) option(fact, item.fact_id, item.statement);
    button("Record NPC Witness", form, () => void mutate(
      "Recording NPC witness…", "npc_witness",
      { npc_id: npc.value, fact_id: fact.value, window: witness.window },
      "NPC witness recorded.",
    ));
  }

  function reportSection() {
    const reports = view.lead_reports;
    if (!reports?.facts.length) return;
    const section = node("section", "", panel);
    node("h3", "Report a lead to the Handler", section);
    for (const lead of reports.facts) {
      const card = node("article", "", section);
      node("p", lead.statement, card);
      button("Report Lead", card, () => void mutate(
        "Reporting lead…", "report_lead", { fact_id: lead.fact_id, window: reports.window },
        "Lead reported to the Handler.",
      ));
    }
  }

  function guideBooking(request, card) {
    if (request.handoff) {
      const { position, followers } = request.handoff;
      node("p", `Booked for ${followers} · Day ${position.day} · ${position.slot}`, card);
      return;
    }
    const booking = view.guide_bookings;
    if (view.role !== "handler" || !booking || !request.guide_responses.follow) return;
    if (!booking.scenes.length) {
      node("p", "Bind an unused scene to book the continuation.", card);
      return;
    }
    const form = node("form", "", card);
    const scene = field(form, "Destination scene", "select");
    for (const target of booking.scenes) {
      option(scene, target.id, sceneLabel?.(target) || `Scene in ${target.channel}`);
    }
    const day = field(form, "Fictional day", "input");
    day.type = "number";
    day.min = String(booking.position.day);
    day.max = "999999";
    day.required = true;
    const slot = field(form, "Fictional slot", "select");
    for (const name of booking.slots) option(slot, name, name);
    const next = booking.slots.indexOf(booking.position.slot) + 1;
    day.value = String(booking.position.day + Number(next === booking.slots.length));
    slot.value = booking.slots[next % booking.slots.length];
    const submit = node("button", "Book Guide Continuation", form);
    submit.type = "submit";
    submit.disabled = busy;
    form.addEventListener("submit", event => {
      event.preventDefault();
      const target = booking.scenes.find(item => item.id === scene.value);
      void mutate("Booking guide continuation…", "guide_handoff", {
        reaction_id: request.reaction_id,
        destination_scene_id: target.id,
        destination_revision: target.revision,
        position: { day: day.valueAsNumber, slot: slot.value },
      }, "Guide continuation booked.");
    });
  }

  function requestsSection() {
    if (!view.requests?.length) return;
    const section = node("section", "", panel);
    node("h3", view.role === "facilitator" ? "Facilitator review" : "NPC drafts", section);
    for (const request of view.requests) {
      const card = node("article", "", section);
      const source = view.addresses.find(address => address.id === request.address_id);
      node("strong", source?.npc_name || "NPC draft", card);
      node("p", statusText[request.status] || request.status, card);
      if (request.guide) node("p", `Guide offer to ${request.guide.name}`, card);
      if (request.lead) node("p", `Private lead · ${request.lead.statement}`, card);
      if (request.proposal?.speech) node("blockquote", request.proposal.speech, card);
      if (request.guide_responses) {
        const { follow, decline } = request.guide_responses;
        node("p", `${follow} following · ${decline} declined`, card);
        guideBooking(request, card);
      }
      if (view.role === "handler" && request.status === "queued" && view.enabled) {
        button("Start Draft", card, () => void mutate(
          "Drafting…", "resume", { request_id: request.id }, result => statusText[result.status],
        ));
      }
      if (view.role === "facilitator" && request.status === "ready") {
        const actions = node("div", "", card);
        actions.className = "harpy-npc-actions";
        const review = { request_id: request.id, result_id: request.result_id };
        const audience = request.review_audience;
        if (audience) {
          node("p", (audience.kind === "private_lead" ? "Private for " : "Heard by ")
            + audience.listeners.join(", "), card);
          const edit = field(card, "Review or edit the spoken line", "textarea");
          edit.value = speechEdits.get(request.result_id) ?? request.proposal.speech;
          edit.addEventListener("input", () => speechEdits.set(request.result_id, edit.value));
          edit.rows = 2;
          edit.maxLength = 600;
          edit.required = true;
          button("Approve", actions, () => {
            if (!edit.value.trim() || !edit.reportValidity()) return;
            void mutate("Saving review…", "review", {
              ...review, approve: true, expected_audience: audience.receipt,
              ...(edit.value === request.proposal.speech ? {} : {edited_speech: edit.value}),
            }, "Reaction published.");
          });
        } else {
          node("p", "Refresh the audience before approving this draft.", card);
        }
        button("Decline", actions, () => void mutate("Saving review…", "review", {
          ...review, approve: false,
        }, "Draft declined."));
      }
    }
  }

  function sceneFeed() {
    const section = node("section", "", panel);
    node("h3", "Scene replies", section);
    if (!view.feed.length) node("p", "No NPC replies yet.", section);
    for (const line of view.feed) {
      const card = node("article", "", section);
      node("strong", line.npc_name, card);
      node("p", `Day ${line.position.day} · ${line.position.slot}`, card);
      node("blockquote", line.speech, card);
      if (line.lead) node("p", `Private lead · ${line.lead.statement}`, card);
      if (!line.guide) continue;
      node("p", `Guide offer to ${line.guide.name}`, card);
      if (line.guide.response) {
        node("p", line.guide.response === "follow" ? "You chose to follow." : "You declined.", card);
        if (line.guide.booking) {
          const { scene, position } = line.guide.booking;
          node("p", `Continuation · Day ${position.day} · ${position.slot}`, card);
          if (openScene) button("Open Scheduled Scene", card, () => openScene(scene));
        }
      } else if (line.guide.open) {
        const actions = node("div", "", card);
        actions.className = "harpy-npc-actions";
        for (const [choice, label] of [["follow", "Follow"], ["decline", "Decline"]]) {
          button(label, actions, () => void mutate(
            "Saving your choice…", "guide_response", { reaction_id: line.id, choice },
            "Your choice was saved.",
          ));
        }
      }
    }
  }

  function render() {
    if (!alive) return;
    panel.replaceChildren();
    panel.setAttribute("aria-busy", String(busy));
    const header = node("header", "", panel);
    node("h2", "NPC dialogue", header);
    button("Refresh", header, () => void refresh());
    if (notice) node("p", notice, panel).setAttribute("role", "status");
    if (error) node("p", error, panel).setAttribute("role", "alert");
    if (!view) return;
    if (!view.enabled) node("p", "NPC drafting is disabled for this campaign.", panel);
    if (view.unavailable) node("p", view.unavailable, panel);
    if (view.targets?.npcs.length === 0) node("p", "There is no eligible NPC cast in this scene.", panel);
    if (view.role === "pilot") addressForm();
    witnessSection();
    reportSection();
    addressesSection();
    requestsSection();
    sceneFeed();
  }

  void refresh();
  return {
    refresh,
    destroy() {
      alive = false;
      panel.remove();
    },
  };
}
