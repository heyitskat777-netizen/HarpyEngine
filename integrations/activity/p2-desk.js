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

export function mountDirectorDesk(parent, scene, activityFetch) {
  const details = element("details");
  details.append(element("summary", "Director work"));
  const body = element("div");
  const status = element("p");
  status.setAttribute("role", "status");
  details.append(status, body);
  parent.prepend(details);
  const root = "/api/director/" + encodeURIComponent(scene) + "/";
  const routeId = id => encodeURIComponent(id).replaceAll("%3A", ":");

  async function read(route, optional = false) {
    const response = await activityFetch(root + route);
    if (optional && [401, 403, 409].includes(response.status)) return null;
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Unable to read scene work.");
    return result;
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
    if (!gm.handler_drafts.length && !gm.outcome_sources.length) {
      queue.append(element("p", "No pending reviews."));
    }
    for (const item of gm.handler_drafts) {
      const row = card(queue, "Handler draft");
      row.append(button("Review Handler draft", async () => {
        const draft = await read("handler-draft/" + routeId(item.id));
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
    const [work, gm] = await Promise.all([read("work", true), read("gm-work", true)]);
    body.replaceChildren();
    if (!work) {
      body.append(element("p", "Scene work is unavailable. Check scene membership and consent."));
      return;
    }
    renderHandler(work);
    if (gm) renderFacilitator(gm);
    renderOwn(work);
    body.append(button("Refresh Director work", refresh));
  }

  details.addEventListener("toggle", () => {
    if (details.open) refresh().catch(error => {
      body.replaceChildren();
      status.textContent = error.message;
    });
  });
}
