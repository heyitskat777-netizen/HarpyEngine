import {closePopup, popupAction} from "/popup-ui.js";

const PHASES = {
  offered: "Offer filed",
  active: "Dispatched",
  ending: "Post-mission review",
  awaiting_consequences: "Debrief and consequences",
  complete: "Debrief filed",
  cancelled: "Cancelled",
};
const WAITING = {
  viewer: "Your response required",
  invitees: "Awaiting invited pilots",
  dispatch: "Awaiting Handler dispatch",
  handler_review: "Awaiting Handler review",
};
export const missionStatus = mission => WAITING[mission.waiting_on] ?? PHASES[mission.phase] ?? mission.phase;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function field(form, label, input) {
  const wrapper = element("label", label, "field");
  input.setAttribute("aria-label",label);
  wrapper.append(input);
  form.append(wrapper);
}

function button(label, run, primary = false) {
  const result = element("button", label, primary ? "primary" : "");
  result.type = "button";
  result.addEventListener("click", () => run(result));
  return result;
}

function submit(form, label, send, payload) {
  const control = element("button", label, "primary");
  control.type = "submit";
  form.append(control);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const key = form.dataset.popupKey;
    if (await send(payload(new FormData(form)), control)) closePopup(key);
  });
}

function offerForm(desk, send) {
  const captureTargets = desk.capture_targets;
  const form = element("form");
  const objective = element("textarea");
  objective.name = "objective";
  objective.required = true;
  objective.maxLength = 1200;
  const label = desk.introductory ? "One clear introductory objective"
    : captureTargets ? "Mission plan" : "Mission objective";
  field(form, label, objective);
  if (desk.requires_hard_stake) {
    const extra = element("textarea");
    extra.name = "hard_stake";
    extra.required = true;
    extra.maxLength = 300;
    field(form, "Extra Hard-mode obstacle", extra);
  }
  if (captureTargets) {
    const target = element("select");
    target.name = "capture_target";
    target.required = true;
    const prompt = element("option", "Select a Harpy");
    prompt.value = "";
    target.append(prompt);
    for (const [id, name] of captureTargets) {
      const option = element("option", name);
      option.value = id;
      target.append(option);
    }
    field(form, "Harpy to capture and convert", target);
  }
  const choices = element("fieldset");
  choices.append(element("legend", "Assigned pilot roster"));
  for (const [id, callsign] of desk.pilots) {
    const input = element("input");
    input.type = "checkbox";
    input.name = "pilots";
    input.value = id;
    const label = element("label");
    label.append(input, document.createTextNode(" " + callsign));
    const line = element("div");
    line.append(label);
    choices.append(line);
  }
  form.append(choices);
  const validate = () => {
    const first = choices.querySelector("input");
    first?.setCustomValidity(choices.querySelector("input:checked") ? "" : "Assign at least one pilot.");
  };
  choices.addEventListener("change",validate);
  validate();
  submit(form, "File mission offer", send, values => ({
    action: "offer", objective: values.get("objective"), pilots: values.getAll("pilots"),
    ...(captureTargets ? {capture_target: values.get("capture_target")} : {}),
    ...(desk.requires_hard_stake ? {hard_stake: values.get("hard_stake")} : {}),
  }));
  return form;
}

function debriefForm(ref, send) {
  const form = element("form");
  const outcome = element("select");
  outcome.name = "outcome";
  outcome.required = true;
  for (const [value, label] of [["", "Select outcome"], ["success", "Objective achieved"], ["failure", "Objective failed"]]) {
    const option = element("option", label);
    option.value = value;
    outcome.append(option);
  }
  field(form, "Mission outcome", outcome);
  const report = element("textarea");
  report.name = "debrief";
  report.maxLength = 1200;
  field(form, "Debrief · assigned pilots may read", report);
  submit(form, "File outcome", send, values => ({
    ...ref, action: "debrief", success: values.get("outcome") === "success", debrief: values.get("debrief"),
  }));
  return popupAction("File debrief",form,"debrief:" + ref.id);
}

function reactionForm(reaction, send) {
  const form = element("form");
  const payload = {
    action: "reaction", id: reaction.id, revision: reaction.revision,
    game_revision: reaction.game_revision,
  };
  if (reaction.kind === "doctor_obsolescence") {
    form.append(element("p", reaction.callsign + " · Planned Obsolescence " + reaction.obsolescence_marked + "/8"));
    submit(form, "File Obsolescence mark", send, () => ({...payload, answer: {confirm: true}}));
  } else {
    form.append(element("h3", reaction.callsign + " · Standards review"));
    for (const standard of reaction.standards) form.append(element("p", standard.label));
    const finding = element("select");
    finding.name = "finding";
    for (const [value, label] of [["no", "Standards were not upheld"], ["yes", "Standards upheld"]]) {
      const option = element("option", label);
      option.value = value;
      option.disabled = value === "yes" && !reaction.ruling_ready;
      finding.append(option);
    }
    const rationale = element("textarea");
    rationale.name = "rationale";
    rationale.required = true;
    rationale.maxLength = 1200;
    field(form, "Finding", finding);
    field(form, "Factual review", rationale);
    submit(form, "File Standards review", send, values => ({
      ...payload, answer: {upheld: values.get("finding") === "yes", rationale: values.get("rationale")},
    }));
  }
  return form;
}

export function renderMissions(target, data, {send, respond, responding, openOffDuty, openWork}) {
  target.replaceChildren();
  if (data.desk) {
    if (data.desk.off_duty) {
      target.append(button("Open current Off-Duty", openOffDuty, true));
    } else {
      if (data.desk.can_begin_off_duty) {
        target.append(button("Prepare Off-Duty", control => send({action: "off_duty"}, control), true));
      }
      if (data.desk.can_offer ?? data.desk.pilots.length > 0) {
        target.append(popupAction("New mission offer",offerForm(data.desk,send),"mission-offer"));
      } else if (data.desk.offer_blocker) {
        target.append(element("p", data.desk.offer_blocker));
      }
    }
  }
  if (!data.offers.length) target.append(element("p", "No missions are filed for your account."));
  for (const mission of data.offers) {
    const card = element("article");
    card.dataset.missionId = mission.id;
    card.tabIndex = -1;
    const ref = {id: mission.id, revision: mission.revision};
    card.append(element("p", missionStatus(mission), "eyebrow"),
      element("h3", mission.objective));
    if (mission.introductory) card.append(element("p", "Introductory mission"));
    if (mission.hard_stake) card.append(element("p", mission.hard_stake));
    if (mission.response) {
      card.append(element("p", mission.response === "accept" ? "RESPONSE FILED · Accepted" : "RESPONSE FILED · Declined"));
    }
    if (mission.success !== null) {
      card.append(element("p", mission.success ? "Objective achieved" : "Objective failed"));
    }
    if (mission.debrief) card.append(element("p", mission.debrief));
    if (mission.pending_count) {
      card.append(element("p", "ASSIGNMENTS OUTSTANDING · " + mission.pending_count));
      for (const followup of mission.followups ?? []) {
        card.append(button(followup.label, () => openWork(followup)));
      }
      if (data.desk) card.append(button("Open assigned work", () => openWork()));
    }
    const actions = element("div", undefined, "actions");
    if (mission.needs_response) {
      for (const choice of ["accept", "decline"]) {
        const control = button(choice === "accept" ? "Accept mission" : "Decline mission",
          () => respond(mission, choice), choice === "accept");
        control.dataset.missionResponse = mission.id;
        control.disabled = responding(mission.id);
        actions.append(control);
      }
    }
    if (mission.actions) {
      card.append(element("p", `${mission.answered}/${mission.offered} responses · ${mission.accepted} accepted`));
      for (const action of mission.actions) {
        if (action === "debrief") {
          card.append(debriefForm(ref, send));
        } else {
          const label = action === "dispatch" ? "Dispatch accepted pilots"
            : action === "cancel" ? "Cancel offer"
            : mission.phase === "ending" ? "Commit mission rewards" : "Close debrief";
          actions.append(button(label, control => send({...ref, action}, control), action !== "cancel"));
        }
      }
      for (const reaction of mission.reactions) {
        const open = popupAction("Review " + reaction.callsign,reactionForm(reaction,send),"mission-reaction:" + reaction.id);
        open.dataset.missionWork = reaction.id;
        card.append(open);
      }
    }
    card.append(actions);
    target.append(card);
  }
}
