function node(tag, text) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  return result;
}

export function mountDirectorTrial(request) {
  const launch = node("button", "Training terminal");
  launch.type = "button";
  launch.setAttribute("aria-haspopup", "dialog");
  const campaignMenu = document.querySelector(".campaign-menu");
  campaignMenu.querySelector(".campaign-actions").append(launch);
  const dialog = node("dialog");
  dialog.id = "director-trial-dialog";
  dialog.className = "terminal-dialog activity-dialog";
  const title = node("h2", "Training terminal");
  title.id = "director-trial-title";
  dialog.setAttribute("aria-labelledby", title.id);
  const notice = node("p", "FOUNDATION TRAINING · Use fictional transmissions in this rehearsal. Each participant must authorize access before transmissions can be filed.");
  notice.className = "terminal-caption";
  const status = node("p");
  status.className = "terminal-feedback";
  status.setAttribute("role", "status");
  const controls = node("div");
  controls.className = "actions";
  const body = node("section");
  const result = node("section");
  const stage = node("div");
  stage.className = "terminal-line";
  const stageLabel = node("span", "Foundation / Training record");
  const phase = node("span");
  phase.className = "terminal-state";
  stage.append(stageLabel, phase);
  const header = node("header");
  header.className = "record-heading";
  header.append(title);
  const panel = node("div");
  panel.className = "terminal-panel";
  panel.append(stage, notice, controls, status, body, result);
  dialog.append(header, panel);
  document.body.append(dialog);
  let epoch = 0;
  let busy = false;
  let retry;
  let data;
  let privateRequest;
  let screen = "main";
  let timer;
  let reading = false;
  let dialogueDraft = "";
  let lastSnapshot;

  function schedule() {
    clearTimeout(timer);
    if (dialog.open && data?.training_available !== false) timer = setTimeout(poll, 1500);
  }

  async function poll() {
    if (!dialog.open) return;
    if (busy || reading || document.visibilityState === "hidden") return schedule();
    reading = true;
    const current = epoch;
    try {
      const next = await request();
      if (current !== epoch || !dialog.open || busy) return;
      const snapshot = JSON.stringify(next);
      data = next;
      if (snapshot !== lastSnapshot) {
        lastSnapshot = snapshot;
        if (screen === "main" || !data.work) {
          screen = "main";
          result.replaceChildren();
          privateRequest = undefined;
          render();
        }
      }
    } catch (error) {
      if (current === epoch && dialog.open) status.textContent = "Record refresh interrupted. " + error.message;
    } finally {
      reading = false;
      schedule();
    }
  }

  function button(parent, label, run) {
    const control = node("button", label);
    control.type = "button";
    control.addEventListener("click", () => act(run));
    parent.append(control);
  }

  async function act(run) {
    if (busy) return;
    busy = true;
    const current = epoch;
    status.textContent = "";
    try {
      const apply = await run();
      if (epoch === current && dialog.open) apply?.();
    } catch (error) {
      if (epoch === current && dialog.open) status.textContent = error.message;
    } finally {
      busy = false;
      schedule();
    }
  }

  async function send(operation, fields = {}) {
    const command = {operation, ...fields};
    const payload = JSON.stringify(command);
    if (retry?.payload !== payload) retry = {payload, key:crypto.randomUUID()};
    const answer = await request(command, retry.key);
    retry = undefined;
    return answer;
  }

  function textInput(parent, caption, max) {
    const label = node("label", caption);
    label.className = "field";
    const input = node("textarea");
    input.maxLength = max;
    label.append(input);
    parent.append(label);
    return input;
  }

  function show(label, value, parent = result) {
    parent.append(node("h3", label), node("pre", JSON.stringify(value, null, 2)));
  }

  async function load() {
    const next = await request();
    return () => {
      data = next;
      lastSnapshot = JSON.stringify(next);
      screen = "main";
      result.replaceChildren();
      privateRequest = undefined;
      render();
    };
  }

  function render() {
    const {status: state, work, contributions, speaker, facilitator, own_consent, own_pause, safety_revision} = data;
    const previousInput = body.querySelector("textarea[data-training-composer]");
    const editing = previousInput === document.activeElement;
    const selection = editing ? [previousInput.selectionStart, previousInput.selectionEnd] : null;
    body.replaceChildren();
    if (data.training_available === false) {
      phase.textContent = "NOT COMMISSIONED";
      body.append(node("p", data.availability_message));
      button(body, "Return to Operations desk", async () => () => dialog.close());
      return;
    }
    phase.textContent = state.phase.replaceAll("_", " ").toUpperCase();
    if (state.phase === "awaiting_consent") {
      body.append(node("p", own_consent
        ? "Your authorization is recorded. The rehearsal is waiting for the remaining participants."
        : "Authorize your participation to join this rehearsal."));
      const roster = node("ul");
      roster.setAttribute("aria-label", "Training authorizations");
      for (const participant of data.participants ?? []) {
        roster.append(node("li", participant.label + (participant.own ? " · You" : "") + " · "
          + (!participant.active ? "Membership review required"
            : participant.consented ? "Authorization recorded" : "Countersignature required")));
      }
      body.append(roster);
    } else if (state.phase === "off") {
      body.append(node("p", facilitator
        ? "The rehearsal channel is disabled. Enable it to request participant authorizations."
        : "The Handler must enable the rehearsal channel."));
    } else if (state.phase === "paused") {
      body.append(node("p", own_pause
        ? "Your safety pause is active."
        : "A participant has paused the rehearsal."));
    } else {
      body.append(node("p", "Channel ready. File a transmission or review assigned work."));
    }
    button(body, own_pause ? "Lift my safety pause" : "Safety pause", async () => {
      await send("safety", {revision:safety_revision,pause:!own_pause});
      return load();
    });
    if (facilitator) button(body, state.mode === "off" ? "Enable rehearsal channel" : "Disable rehearsal channel", async () => {
      await send("configure", {revision:state.policy_revision, mode:state.mode === "off" ? "shadow" : "off"});
      return load();
    });
    if (state.mode === "shadow") button(body, own_consent ? "Withdraw my consent" : "I consent to use invented dialogue in this trial", async () => {
      await send("consent", {revision:state.policy_revision, consent:!own_consent});
      return load();
    });
    if (!work) return;
    const input = textInput(body, speaker === "handler" ? "Handler transmission" : "Pilot transmission", 1000);
    input.dataset.trainingComposer = "";
    input.value = dialogueDraft;
    input.addEventListener("input", () => { dialogueDraft = input.value; });
    if (editing) {
      input.focus({preventScroll:true});
      input.setSelectionRange(...selection);
    }
    button(body, "File transmission", async () => {
      const text = input.value;
      const sent = await send("submit", {revision:state.scene_revision,text,classification:"ic"});
      if (dialogueDraft === text) dialogueDraft = "";
      const refresh = await load();
      return () => {
        refresh();
        status.textContent = "Transmission filed.";
        for (const reply of sent.replies) result.append(node("h3", reply.role), node("p", reply.reply));
      };
    });
    for (const declaration of work.declarations) {
      body.append(node("p", "Play request · " + declaration.status.replaceAll("_", " ")));
    }
    if (work.native.choices.length || work.native.required_work.length || work.native.handler_grants.length) {
      body.append(node("h3", "Assigned HarpyEngine work"));
      for (const item of [...work.native.choices, ...work.native.required_work]) {
        body.append(node("p", item.kind.replaceAll("_", " ")));
      }
      for (const item of work.native.handler_grants) {
        body.append(node("p", (item.selected ?? "Handler Play").replaceAll("_", " ")));
      }
      button(body, "Return to Activity controls", async () => () => dialog.close());
    }
    for (const proposal of work.proposals) {
      body.append(node("p", proposal.operation + " · " + proposal.status.replaceAll("_", " ")));
      if (proposal.status === "awaiting_confirmation") button(body, "Review my assigned proposal", async () => {
        const own = await send("review", {proposal:proposal.id});
        return () => {
          screen = "owner-review";
          body.replaceChildren();
          result.replaceChildren();
          backToRecord();
          show("Owner review", own);
          button(result, "Confirm these effects", async () => {
            await send("confirm", {proposal:proposal.id,approved:true});
            return load();
          });
        };
      });
    }
    for (const contribution of contributions) {
      const record = node("article");
      record.className = "record-card";
      record.append(node("h3", "Approved GM readback"), node("p", contribution.text));
      const receipt = contribution.native?.receipt;
      if (receipt?.faces) record.append(node("p", "Original roll · " + receipt.faces.join(" + ")));
      body.append(record);
    }
    if (facilitator) button(body, "Open private GM desk", async () => {
      const gm = await send("gm-work");
      return () => gmDesk(gm);
    });
    if (facilitator) button(body, "Review retained references", async () => {
      const memory = await send("memory");
      return () => memoryDesk(memory);
    });
  }

  function memoryDesk(memory) {
    screen = "memory";
    body.replaceChildren();
    result.replaceChildren();
    backToRecord();
    const source = textInput(result, "Original source ID", 128);
    const topic = node("select");
    const topicField = node("label", "Topic");
    topicField.append(topic);
    result.append(topicField);
    for (const value of ["general", "objective", "scope", "status"]) topic.add(new Option(value, value));
    const roles = [["invited","First pilot"],["other","Second pilot"],["handler","Handler"]].map(([id, label]) => {
      const field = node("label", label);
      const check = node("input");
      check.type = "checkbox";
      field.append(check);
      result.append(field);
      return [id, check];
    });
    button(result, "Retain for selected roles", async () => {
      await send("remember", {source:source.value,order:memory.next_order,
        roles:roles.filter(([,check]) => check.checked).map(([id]) => id),topic:topic.value});
      const refreshed = await send("memory");
      return () => memoryDesk(refreshed);
    });
    const selected = new Map();
    for (const reference of memory.references) {
      const field = node("label", reference.topic + " · " + reference.text);
      field.className = "field";
      const check = node("input");
      check.type = "checkbox";
      field.append(check);
      result.append(field);
      selected.set(reference.id, check);
    }
    if (!selected.size) return;
    const reason = textInput(result, "Reason for retiring references", 1200);
    button(result, "Retire selected references from prompts", async () => {
      await send("archive", {revision:memory.revision,
        references:[...selected].filter(([,check]) => check.checked).map(([id]) => id),reason:reason.value});
      const refreshed = await send("memory");
      return () => memoryDesk(refreshed);
    });
  }

  function gmDesk(gm) {
    screen = "gm";
    body.replaceChildren();
    result.replaceChildren();
    backToRecord();
    result.append(node("h3", "Private GM review"));
    if (gm.declarations.length) show("Play requests", gm.declarations);
    const review = textInput(result, "Declaration ID", 128);
    const action = textInput(result, "Original native action ID", 128);
    button(result, "Bind exact native action", async () => {
      await send("bind", {review:review.value,action:action.value});
      const latest = await send("gm-work");
      return () => gmDesk(latest);
    });
    const frame = textInput(result, "Task frame JSON (required for Keep Your Head)", 10000);
    for (const source of gm.outcome_sources) button(result, "Open " + source.operation + " proposal", async () => {
      const response = await send("open", {
        kind:source.source_kind, source:source.source_id,
        frame:source.frame_required ? JSON.parse(frame.value) : null,
      });
      return () => {
        screen = "proposal";
        body.replaceChildren();
        privateRequest = response.request;
        result.replaceChildren();
        backToRecord();
        show("Private source packet", response.packet);
        const proposal = textInput(result, "Typed proposal JSON", 24000);
        button(result, "File for original owner review", async () => {
          await send("propose", {request:privateRequest,proposal:JSON.parse(proposal.value)});
          return load();
        });
      };
    });
  }

  function backToRecord() {
    button(body, "Back to training record", async () => () => {
      screen = "main";
      result.replaceChildren();
      privateRequest = undefined;
      render();
    });
  }

  button(controls, "Refresh training record", async () => {
    const next = await request();
    return () => {
      data = next;
      lastSnapshot = JSON.stringify(next);
      if (screen === "main" || !next.work) {
        screen = "main";
        result.replaceChildren();
        privateRequest = undefined;
        render();
      }
      status.textContent = "Training record current.";
    };
  });
  button(controls, "Close training terminal", async () => () => dialog.close());
  dialog.addEventListener("close", () => {
    epoch++;
    clearTimeout(timer);
    data = privateRequest = undefined;
    retry = undefined;
    body.replaceChildren();
    result.replaceChildren();
    status.textContent = "";
    screen = "main";
    lastSnapshot = undefined;
    launch.focus();
  });
  launch.addEventListener("click", () => {
    status.textContent = "Opening training record…";
    dialog.showModal();
    act(load);
  });
}
