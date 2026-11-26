import {decisionName, playCard, playName, playRail, renderRecordMetadata} from "/foundation-ui.js";
import {catalog, renderPlaybookFields} from "/character-draft-ui.js";
import {popupAction, renderDraftDialog, showSelectionText} from "/popup-ui.js";

let fieldSequence = 0;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function action(label, callback) {
  const button = element("button", label);
  button.type = "button";
  button.addEventListener("click", () => callback());
  return button;
}

function actionStages(target, operations, preferred = "") {
  if (!operations.length) return;
  const stage = element("section", undefined, "assigned-action-stage");
  const choices = element("div", undefined, "actions");
  const panels = new Map();
  let initial;
  for (const operation of operations) {
    const open = action(operation.label, () => {
      let panel = panels.get(operation);
      if (!panel) {
        panel = element("div");
        panel.append(action("Back to assigned actions", () => {
          stage.replaceChildren(choices);
          open.focus();
        }), element("h4", operation.label));
        operation.render(panel);
        panels.set(operation,panel);
      }
      stage.replaceChildren(panel);
      panel.querySelector("input,select,textarea,button[type=submit]")?.focus();
    });
    choices.append(open);
    if (operation.id === preferred) initial = open;
  }
  stage.append(choices);
  target.append(stage);
  initial?.click();
}

function form(target, label, save) {
  const node = element("form");
  const submit = element("button", label);
  submit.type = "submit";
  node.addEventListener("submit", event => {
    event.preventDefault();
    save(new FormData(node));
  });
  node.append(submit);
  target.append(node);
  return node;
}

function field(form, name, label, value = "", options) {
  const container = element("div");
  container.className = "field";
  const caption = element("label", label);
  const input = element(options ? "select" : "input");
  input.name = name;
  input.id = "setup-" + (++fieldSequence);
  caption.htmlFor = input.id;
  if (options) {
    for (const [key, text] of options) {
      const option = element("option", text);
      option.value = key;
      input.append(option);
    }
  }
  input.value = value;
  container.append(caption, input);
  if (options) showSelectionText(input,container,name === "prompt");
  form.insertBefore(container, form.lastElementChild);
  return input;
}

function input(form, name, label, value, maxLength, required = true) {
  const control = field(form, name, label, value);
  control.required = required;
  control.maxLength = maxLength;
  return control;
}

function picks(form, prefix, label, options, selected) {
  for (const index of [0, 1]) {
    const name = prefix + index;
    const choice = field(form, name, label + " asset " + (index + 1), selected[index]?.name ?? "", [
      ["", "Choose an asset"], ...options.map(value => [value, value]),
    ]);
    choice.required = true;
    const description = input(form, name + "-description", label + " asset " + (index + 1) + " description",
      selected[index]?.description ?? "", 700);
    const updateDescription = () => { description.disabled = !choice.value; };
    choice.addEventListener("change", updateDescription);
    updateDescription();
  }
}

function assets(values, prefix) {
  return [0, 1].flatMap(index => {
    const name = values.get(prefix + index);
    return name ? [{name, description: values.get(prefix + index + "-description") ?? ""}] : [];
  });
}

function rollLabel(play) {
  return `Roll ${play.receipt.faces.join(" + ")} · Total ${play.result?.total ?? play.receipt.pre_total}`;
}

function appendKeepResult(target, play) {
  if (play.result) {
    const receipt = element("section");
    receipt.dataset.keepReceipt = play.id;
    receipt.append(element("h3", "Keep Your Head resolved"));
    receipt.append(element("p", play.result.enough ? "The pilot held." : "It was not enough."));
    receipt.append(element("p", play.result.ruling));
    receipt.append(element("p", "Positive traits · " + play.result.positive.join(", ")));
    receipt.append(element("p", "Negative traits · " + play.result.negative.join(", ")));
    target.append(receipt);
  }
}

const sceneLessonLabels = {
  learned_keep_rider: "Apply an eligible learned ability",
  learned_call: "Apply Call of the Void",
  learned_show_dog: "Apply Show Dog",
  learned_psyche: "Apply Disposable Psyche",
};

function sceneLessonFields(formNode, state) {
  const controls = [];
  for (const [key, options] of Object.entries(state.lessons ?? {})) {
    if (key in sceneLessonLabels) controls.push(offDutySelect(formNode, key, sceneLessonLabels[key], options));
  }
  if (!controls.length && !state.native_psyche) return;
  const psyche = controls.find(control => control.name === "learned_psyche");
  const marks = state.lesson_marks ?? [];
  const identity = marks.length ? offDutySelect(formNode, "identity", "Identity to mark and remove",
    marks.map(mark => [mark.id, mark.name])) : null;
  const gain = identity && offDutySelect(formNode, "gain", "Heat from marking", []);
  const disposal = identity && offDutySelect(formNode, "disposable_heat", "Extra Heat from removal", []);
  const existingHeat = formNode.querySelector('[name="heat"]');
  const heat = existingHeat || (state.lesson_heat?.length
    ? offDutySelect(formNode, "heat", "Heat to spend", []) : null);
  function replaceAmounts(control, amounts) {
    const previous = control.value;
    const values = amounts.map(String);
    control.replaceChildren(...values.map(value => new Option(value, value)));
    if (values.includes(previous)) control.value = previous;
  }
  const sync = () => {
    const marking = identity && (state.native_psyche || psyche?.value);
    const mark = marking && marks.find(row => row.id === identity.value);
    if (identity) {
      toggleField(identity, Boolean(marking));
      identity.required = Boolean(psyche?.value) && state.lesson_disposal_required;
      toggleField(gain, Boolean(mark));
      toggleField(disposal, Boolean(mark));
      if (mark) {
        replaceAmounts(gain, Object.keys(mark.amounts));
        replaceAmounts(disposal, Object.keys(mark.amounts[gain.value]));
      }
    }
    if (heat) {
      toggleField(heat, Boolean(existingHeat || mark) || controls.some(control => control.value));
      replaceAmounts(heat, mark ? mark.amounts[gain.value][disposal.value] : state.lesson_heat);
    }
  };
  for (const control of [...controls, identity, gain, disposal].filter(Boolean)) {
    control.addEventListener("change", sync);
  }
  sync();
}

function selectedSceneLessons(values) {
  const selected = Object.fromEntries(Object.keys(sceneLessonLabels)
    .filter(name => values.get(name)).map(name => [name, values.get(name)]));
  if (values.get("identity")) {
    selected.identity = values.get("identity");
    selected.gain = Number(values.get("gain"));
    selected.disposable_heat = Number(values.get("disposable_heat"));
  }
  return selected;
}

export function renderTagDecision(target, choice, submit, role) {
  const isWindow = choice.kind === "tag_window";
  if (isWindow) target.append(action(role + " · Pass Tag window", () => submit({options:["pass"]})));
  const fields = choice.schema ?? [];
  if (!fields.length) return;
  if (choice.prompt) target.append(element("p", choice.prompt));
  const entry = form(target, isWindow ? "File Tag proposal" : "File Tag decision", values => {
    const answer = {};
    for (const spec of fields) {
      const selected = values.getAll(spec.key).map(value => value.trim()).filter(Boolean);
      if (!selected.length) continue;
      if (spec.key.startsWith("fields.")) (answer.fields ??= {})[spec.key.slice(7)] = selected[0];
      else if (spec.key === "number") answer.number = Number(selected[0]);
      else if (spec.key === "member") answer.member = selected[0];
      else if (spec.key === "flag") answer.flag = selected[0] === "yes";
      else answer[spec.key] = spec.paragraph ? selected[0] : selected;
    }
    submit(answer);
  });
  const controls = new Map();
  const hasStatus = fields.some(spec => spec.key === "fields.status");
  for (const spec of fields) {
    if (isWindow && spec.key === "options") {
      const options = spec.options.filter(([value]) => value !== "pass" || hasStatus)
        .map(([value, label]) => [value, value === "pass" ? "Apply Status modifier only" : label]);
      controls.set(spec.key, offDutySelect(entry, spec.key, spec.label, options, {required:true}));
    } else if (spec.options?.length) {
      controls.set(spec.key, offDutySelect(entry, spec.key, spec.label, spec.options,
        {required:spec.required, multiple:spec.multiple}));
    } else if (spec.paragraph) {
      input(entry, spec.key, spec.label, "", 1200, spec.required);
      controls.set(spec.key, entry.elements.namedItem(spec.key));
    }
  }
  if (!isWindow) return;
  const intent = controls.get("options");
  const marker = controls.get("fields.marker");
  const sync = () => {
    const ordinary = intent.value === "tag";
    const partner = intent.value === "gender_man";
    const statusOnly = intent.value === "pass";
    for (const name of ["denied","number","text","fields.as_actor","fields.marker","fields.status"]) {
      const control = controls.get(name);
      if (!control) continue;
      const visible = ordinary || (partner && name === "denied") || (statusOnly && name === "fields.status");
      control.disabled = control.parentElement.hidden = !visible;
      control.required = visible && (statusOnly || ["denied","number","text"].includes(name));
    }
    if (ordinary && marker?.options.length === 2) marker.value = marker.options[1].value;
  };
  intent.addEventListener("change", sync);
  sync();
}

export function renderRiskChoice(target, choice, submit) {
  target.append(element("h4", "Risk Factor"), element("p", choice.prompt));
  renderVoidOperations(target, choice.risk_operations, ({operation, values}) => {
    if (operation === "mockingbird_risk") {
      submit({});
      return;
    }
    const {total, account, ...fields} = values;
    if (operation === "risk_grow_asset") fields.sup_replace ??= "";
    submit({number:Number(total), text:account, fields});
  });
}

function renderKeep(details, state, send) {
  const { current, choices, character_revision, history = [] } = state;
  const handlerLabel = "Handler";
  details.open = Boolean(current);
  if (state.can_start) {
    const start = form(details, "Roll Keep Your Head", values => send("keep-start", {
      context: values.get("context"), confirmed: true, character_revision,
      ...(values.has("heat") ? {heat:Number(values.get("heat"))} : {}),
      ...selectedSceneLessons(values),
    }));
    input(start, "context", "What are you trying to endure?", "", 1200);
    sceneLessonFields(start, state);
  }
  if (current?.receipt) {
    const roll = element("output", rollLabel(current));
    roll.setAttribute("aria-label", "Keep Your Head roll");
    details.append(roll);
    appendKeepResult(details, current);
  }
  if (history.length) {
    const previous = element("section");
    previous.setAttribute("aria-label", "Past Keep Your Head results");
    previous.append(element("h3", "Past Keep Your Head results"));
    for (const play of history) {
      const entry = element("details");
      entry.append(element("summary", rollLabel(play)));
      appendKeepResult(entry, play);
      previous.append(entry);
    }
    details.append(previous);
  }
  for (const choice of choices) {
    const record = element("div", undefined, "scene-choice-record");
    record.dataset.sceneChoice = choice.id;
    details.append(record);
    const submit = answer => send("keep-choice", {
      id: choice.id, revision: choice.revision, role: choice.role, answer,
    });
    const label = choice.role === "handler" ? handlerLabel : "Pilot";
    if (choice.schema) {
      renderTagDecision(record, choice, submit, label);
      continue;
    }
    if (choice.risk_operations) {
      renderRiskChoice(record, choice, submit);
      continue;
    }
    record.append(element("h3", label + (choice.role === "handler" ? " ruling" : " choice")));
    const decision = form(record, choice.role === "handler" ? "Record Handler ruling" : "Record pilot choice", values => {
      const answer = {};
      for (const spec of choice.fields) {
        const selected = values.getAll(spec.key).filter(Boolean);
        if (spec.key === "flag") answer.flag = selected[0] === "yes";
        else if (spec.key === "text") answer.text = selected[0] ?? "";
        else if (selected.length) answer[spec.key] = selected;
        if (spec.options.length && (selected.length < spec.minimum || selected.length > spec.maximum)) {
          decision.querySelector(`[name="${spec.key}"]`).reportValidity();
          if (selected.length < spec.minimum) return;
        }
      }
      submit(answer);
    });
    for (const spec of choice.fields) {
      if (!spec.options.length) {
        input(decision, spec.key, spec.label, "", 1200, spec.required);
        continue;
      }
      const options = spec.maximum > 1 ? spec.options : [["", "Select"], ...spec.options];
      const fieldControl = field(decision, spec.key, spec.label, "", options);
      fieldControl.required = spec.required;
      if (spec.maximum > 1) {
        fieldControl.multiple = true;
        fieldControl.size = spec.options.length;
        fieldControl.addEventListener("change", () => {
          const count = fieldControl.selectedOptions.length;
          fieldControl.setCustomValidity(count < spec.minimum || count > spec.maximum
            ? `Select ${spec.minimum} to ${spec.maximum} options.` : "");
        });
      }
    }
  }
  if (state.waiting && !current?.result) {
    const waiting = element("p", "AWAITING RULING");
    waiting.dataset.playWaiting = "";
    details.append(waiting);
  }
}

const choiceLabels = {
  oldgen_listen:"File your response to the advice", oldgen_low_maxim:"File your maxim", oldgen_write_maxim:"File your maxim",
  dive_select:"Choose Dive effect", dive_effect:"File Dive effect",
  dive_table_answer:"File your answer", dive_table_agreement:"File your decision",
  mockingbird_person_capabilities:"File conversation capabilities",
  mockingbird_person_tag:"Propose a Tag", mockingbird_person_agreement:"Answer Tag proposal",
  mockingbird_person_commit:"Commit agreed Tag",
  beneath_select:"File confrontation effects", beneath_details:"File private choice", beneath_pin_response:"File pin response",
  defeat_select:"File Defeat consequences", defeat_tag_gift:"File Tag decision",
  defeat_alternative:"Send Handler offer", defeat_accept_alternative:"File your response to the offer",
  actor_sensors:"Send sensor questions", handler_sensors:"Record sensor answers",
  actor_engage:"Resolve Engage", actor_flirt:"Ask the other pilot", target_flirt:"Answer the other pilot",
  actor_flirt_answer:"Answer the return question", flirt_escape:"Record your way out",
  flirt_owe_tag:"Give a Tag", handler_brief:"Record the Handler brief",
  actor_keep:"Record pilot choice", handler_keep:"Record Handler ruling",
  followthrough_confirm:"Record follow-through response",
  order_response:"Answer the original order", actor_disobey:"File the refusal outcome",
  handler_disobey:"Record the Handler’s refusal ruling",
};

function appendSceneResult(target, label, play) {
  if (play.receipt) target.append(element("p", rollLabel(play)));
  const result = play.result;
  if (play.state !== "complete" || !result) return;
  target.append(element("h4", label + " resolved"));
  for (const answer of Object.values(result.answers ?? {})) target.append(element("p", answer));
  if (result.maneuvers) target.append(element("p", "Maneuvers · " + Object.keys(result.maneuvers).map(id => id.replaceAll("_", " ")).join(", ")));
  if (result.consequence?.length) target.append(element("p", "Consequence · " + result.consequence.map(id => id.replaceAll("_", " ")).join(", ")));
  if (result.damaged?.length) target.append(element("p", "Asset damage recorded."));
  for (const text of [result.target_answer, result.actor_answer, result.ruling, result.response]) {
    if (typeof text === "string" && text) target.append(element("p", text));
  }
}

function renderSceneAction(details, play, label, state, send) {
  const {current, child, choices, waiting, can_start, character_revision, targets, history, period} = state;
  const handlerLabel = "Handler";
  if (choices.length || waiting) details.open = true;
  if (can_start) {
    const proposing = Boolean(state.counterparts);
    const startLabel = proposing ? "Record conversation trigger"
      : play.id === "flirt_followthrough" ? "Start follow-through"
      : play.id === "reject_tag" ? "Record Tag rejection" : "Roll " + label;
    const start = form(details, startLabel, values => {
      const target = proposing ? values.getAll("target") : values.get("target");
      send("scene-start", {
        play:play.id, context:state.sources?.find(item => item.id === target)?.label ?? values.get("context"),
        confirmed:true, character_revision, target,
        ...(values.has("heat") ? {heat:Number(values.get("heat"))} : {}),
        ...(period ? {period} : {}),
        ...selectedSceneLessons(values),
      });
    });
    if (state.counterparts) offDutySelect(start, "target", "Conversation counterparts",
      state.counterparts.map(item => [item.id,item.label]),{required:true,multiple:true});
    if (state.sources) offDutySelect(start, "target", "Saved conversation trigger",
      state.sources.map(item => [item.id,item.label]),{required:true});
    if (targets.length) {
      const targetLabel = {defeat:"Assigned Defeat", reject_tag:"Assigned Tag", snoop:"Property owner"}[play.id] ?? "Pilot";
      field(start, "target", targetLabel, "",
        [["", "Choose an option"], ...targets.map(item => [item.id, item.label])]).required = true;
    }
    if (state.heat_options) offDutySelect(start,"heat","Heat to spend",state.heat_options.map(value => [value,String(value)]),{required:true});
    if (!state.sources) input(start, "context", play.trigger || "Describe the actual trigger", "", 1200);
    sceneLessonFields(start, state);
  } else if (state.reason) {
    details.append(element("p", state.reason));
  }
  for (const choice of choices) {
    const record = element("div", undefined, "scene-choice-record");
    record.dataset.sceneChoice = choice.id;
    details.append(record);
    const sendChoice = answer => send("scene-choice", {id:choice.id, revision:choice.revision, role:choice.role, answer});
    const role = choice.role === "handler" ? handlerLabel : "Pilot";
    if (choice.schema) {
      renderTagDecision(record, choice, sendChoice, role);
      continue;
    }
    if (choice.risk_operations) {
      renderRiskChoice(record, choice, sendChoice);
      continue;
    }
    if (choice.kind === "order_disobey") {
      record.append(element("h4", "Required Disobey Orders"));
      if (choice.prompt) record.append(element("p", choice.prompt));
      const response = form(record, "Roll Disobey Orders", values => sendChoice({
        context:values.get("context"), character_revision:choice.character_revision,
        heat:Number(values.get("heat")), witnessed:values.get("witnessed") === "yes",
      }));
      input(response, "context", "Describe how you refuse the original order", "", 1200);
      offDutySelect(response, "heat", "Heat to spend", choice.heat_options.map(value => [value,String(value)]), {required:true});
      offDutySelect(response, "witnessed", "Was the refusal witnessed?", [["no","No"],["yes","Yes"]], {required:true});
      continue;
    }
    if (["escape_play","beneath_response_play","beneath_defeat"].includes(choice.kind)) {
      const defeat = choice.kind === "beneath_defeat";
      if (defeat) record.append(element("h4","Required Defeat"));
      const response = form(record, defeat ? "Roll Defeat" : "Roll Keep Your Head", values => sendChoice({
        context:values.get("context"), character_revision:choice.character_revision ?? character_revision,
      }));
      input(response, "context", defeat ? "Describe the actual Defeat" : "Describe how you keep your head", "", 1200);
      continue;
    }
    const decisionLabel = choiceLabels[choice.kind] ?? decisionName(choice.kind);
    record.append(element("h4", role + " · " + decisionLabel));
    if (choice.prompt) record.append(element("p", choice.prompt));
    if (choice.unavailable) {
      record.append(element("p", choice.unavailable));
      continue;
    }
    if (choice.fixed_answer) {
      record.append(action(decisionLabel, () => sendChoice(choice.fixed_answer)));
      continue;
    }
    if (choice.offer) {
      const offer = choice.offer;
      for (const text of [offer.account, "Permissions removed · " + offer.permissions,
        offer.assets.length ? "Assets removed · " + offer.assets.join(", ") : null,
        offer.identities.length ? "Identities removed · " + offer.identities.join(", ") : null,
        offer.tag ? "Inflicted Tag · " + offer.tag : null,
        typeof offer.outside_frame === "boolean" ? "Girl Asset loss · " + (offer.outside_frame ? "Outside a Frame" : "Inside a Frame") : null,
        offer.foe ? "Helpless before · " + offer.foe : null]) {
        if (text) record.append(element("p",text));
      }
    }
    const decision = form(record, decisionLabel, values => {
      const answer = {};
      for (const spec of choice.fields) {
        const selected = values.getAll(spec.key).map(value => value.trim()).filter(Boolean);
        if (!selected.length) continue;
        if (spec.key.startsWith("fields.")) (answer.fields ??= {})[spec.key.slice(7)] =
          choice.kind === "defeat_alternative" && ["fields.assets","fields.identities"].includes(spec.key)
            ? selected.join(",") : selected[0];
        else if (spec.key === "beneath_extra") (answer.options ??= []).push(...selected);
        else if (spec.key === "flag") answer.flag = selected[0] === "yes";
        else if (spec.key === "number") answer.number = Number(selected[0]);
        else if (spec.key === "member") answer.member = selected[0];
        else if (spec.paragraph) answer[spec.key] = selected[0];
        else answer[spec.key] = selected;
      }
      sendChoice(answer);
    });
    const controls = new Map();
    for (const spec of choice.fields) {
      if (!spec.options.length) {
        input(decision, spec.key, spec.label, "", 1200, spec.required && spec.paragraph);
        continue;
      }
      const options = spec.maximum > 1 ? spec.options : [["", "Select"], ...spec.options];
      const control = field(decision, spec.key, spec.label, "", options);
      controls.set(spec.key, control);
      control.required = spec.required;
      if (spec.maximum > 1) {
        control.multiple = true;
        control.size = Math.min(6, spec.options.length);
        const checkCount = () => {
          const count = control.selectedOptions.length;
          control.setCustomValidity(count < spec.minimum || count > spec.maximum
            ? `Select ${spec.minimum} to ${spec.maximum} options.` : "");
        };
        control.addEventListener("change", checkCount);
        checkCount();
      }
    }
    if (choice.kind === "actor_engage" || choice.kind === "flirt_escape") {
      const selection = controls.get("options");
      const sync = () => {
        const selected = new Set([...selection.selectedOptions].map(item => item.value));
        for (const [key, control] of controls) {
          if (choice.kind === "actor_engage" && key.startsWith("fields.")) {
            control.disabled = !selected.has(key.slice(7));
          } else if (choice.kind === "flirt_escape" && key === "denied") {
            control.disabled = !selected.has("damage");
          } else continue;
          control.required = !control.disabled;
          control.parentElement.hidden = control.disabled;
        }
      };
      selection.addEventListener("change", sync);
      sync();
    }
  }
  if (waiting) details.append(element("p", "AWAITING ASSIGNED RESPONSE"));
  if (current) appendSceneResult(details, label, current);
  for (const nested of state.children ?? (child ? [child] : [])) {
    appendSceneResult(details, playName(nested.play), nested);
  }
  if (history.length) {
    const results = element("details");
    results.append(element("summary", "Past " + label + " results"));
    for (const previous of history) appendSceneResult(results, label, previous);
    details.append(results);
  }
}

export function renderScenePlays(target, scene, send, openBattlefieldPlay) {
  const actionDialog = document.getElementById("scene-action-dialog");
  const actionFields = document.getElementById("scene-action-fields");
  if (!scene && actionDialog?.open && actionDialog.dataset.role === "pilot") actionDialog.close();
  const previousRail = target.querySelector(".play-rail");
  const sameScene = previousRail && previousRail.dataset.playScene === scene?.id;
  if (actionDialog.open && actionDialog.dataset.role === "pilot" && actionDialog.dataset.room !== scene?.id) actionDialog.close();
  target.replaceChildren();
  if (!scene?.joined) return;
  if (scene.safety) {
    const {paused, own, revision} = scene.safety;
    const safety = element("div");
    safety.className = "scene-safety actions";
    if (paused) safety.append(element("span", "Play is paused."));
    safety.append(action(own ? "Clear my safety pause" : "Safety pause", () => send("scene-safety", {pause:!own, revision})));
    target.append(safety);
  }
  if (scene.locked) target.append(element("p", "A Play is in progress."));
  if (!scene.plays.length) target.append(element("p", "There are no Plays available in this scene."));
  const follow = scene.options?.flirt_followthrough;
  const followPlay = {id:"flirt_followthrough",trigger:"Describe how you followed through on the other pilot’s answer."};
  const entries = scene.plays.filter(play => play.id !== followPlay.id).map(play => {
    const label = play.label ?? playName(play.id);
    const keep = play.id === "keep_your_head" ? scene.keep : null;
    const state = keep ?? scene.options?.[play.id];
    const related = play.id === "flirt" && (follow?.targets.length || follow?.current) ? follow : null;
    const fill = () => renderDraftDialog(actionDialog,
      JSON.stringify(["scene-play",scene.id,play.id,state?.current?.id,
        [...(state?.choices ?? []), ...(related?.choices ?? [])].map(choice => [choice.id,choice.revision])]), () => {
      actionDialog.dataset.root = state?.current?.id ?? "";
      document.getElementById("scene-action-title").textContent = label;
      const assigned = [...(state?.choices ?? []), ...(related?.choices ?? [])];
      renderRecordMetadata(document.getElementById("scene-action-record"), {
        location:scene.name,
        state:assigned.length ? "Action required" : state?.current?.state === "complete" ? "Filed"
          : state?.current?.state === "aborted" ? "Voided" : state?.waiting ? "Awaiting response" : "Play instructions",
        owner:assigned.length ? [...new Set(assigned.map(choice => choice.role === "handler" ? "Handler" : "You"))].join(" · ") : undefined,
      });
      actionFields.replaceChildren();
      if (keep) renderKeep(actionFields, keep, send);
      else if (state) renderSceneAction(actionFields, play, label, state, send);
      else if (play.destination === "battlefield" && openBattlefieldPlay) {
        actionFields.append(element("p", "Tactical control verifies the active turn, authorized targets, and reach."));
        actionFields.append(action("Open on Battlefield", () => {
          actionDialog.close();
          openBattlefieldPlay(play.id);
        }));
      } else {
        actionFields.append(element("p", play.reference_reason ?? "This Play’s workflow is unavailable in the Activity."));
      }
      if (related) {
        const followUp = element("section");
        followUp.append(element("h3", "Flirt follow-through"));
        renderSceneAction(followUp, followPlay, "Flirt follow-through", related, send);
        actionFields.append(followUp);
      }
      if (state?.resume_source) {
        actionFields.append(action("Continue in " + playName(state.resume_source), () => {
          target.querySelector(`button[data-play="${CSS.escape(state.resume_source)}"]`)?.click();
        }));
      }
      actionDialog.dispatchEvent(new Event("beneath-source"));
    });
    const row = playCard({...play,label},play.trigger,() => {
      actionDialog.dataset.role = "pilot";
      actionDialog.dataset.play = play.id;
      actionDialog.dataset.room = scene.id;
      document.getElementById("scene-action-feedback").hidden = true;
      fill();
      if (!actionDialog.open) actionDialog.showModal();
    });
    row.dataset.play = play.id;
    row.dataset.playDecisions = [...(state?.choices ?? []), ...(related?.choices ?? [])]
      .map(choice => choice.id).join(" ");
    row.setAttribute("aria-haspopup","dialog");
    if (actionDialog.open && actionDialog.dataset.role === "pilot" && actionDialog.dataset.play === play.id) fill();
    return {play,row};
  });
  if (entries.length) {
    const rail = playRail(entries, sameScene ? previousRail.dataset.selectedPlayCategory : "recover");
    rail.dataset.playScene = scene.id;
    target.append(rail);
  }
}

export function renderHandlerPlaybook(target, book, send) {
  target.hidden = !book;
  target.replaceChildren();
  if (!book) return;
  const reference = element("section", undefined, "record-card");
  reference.append(element("h3", "Handler rulebook"));
  const index = element("ul", undefined, "records");
  for (const play of book.plays) {
    const line = element("li");
    const status = play.playable ? "Effect form available" : "Reference only in the Activity";
    line.append(element("strong", play.label), element("p", play.page ? status + " · Rulebook p. " + play.page : status));
    index.append(line);
  }
  reference.append(index);
  target.append(reference);
  if (book.successor) renderSuccessor(target, book.successor, book.targets, send);
  if (book.off_duty_phase) {
    target.append(element("p", "Off-Duty period · " + book.off_duty_phase.replaceAll("_", " ")));
  } else if (book.targets.length) {
    target.append(action("Prepare Off-Duty", () => send("handler-play-prepare-off-duty", {revision:book.revision})));
  }
  if (book.warp_zones.length) {
    const warp = form(target, "Start zone warp", values => send("handler-play-warp", {revision:book.revision, zone:values.get("zone")}));
    field(warp, "zone", "Owned quarantined zone", "", [["", "Choose a zone"], ...book.warp_zones.map(zone => [zone.id,zone.label])]).required = true;
  }
  if (book.targets.length) {
    const request = form(target, "Start Handler Play", values => {
      const targets = values.getAll("target").map(key => book.targets[Number(key)].ref);
      const {suggestedPlay, suggestedRoom} = target.closest("dialog")?.dataset ?? {};
      const scope = suggestedPlay && suggestedRoom
        ? {room:suggestedRoom, play:suggestedPlay} : {};
      if (targets.length) send("handler-play-start", {revision:book.revision, targets, ...scope});
    });
    request.dataset.handlerStart = "";
    const pilots = element("fieldset");
    pilots.append(element("legend", "Affected pilots"));
    book.targets.forEach((pilot, position) => {
      const label = element("label");
      const check = element("input");
      check.type = "checkbox";
      check.name = "target";
      check.value = position;
      label.append(check, document.createTextNode(pilot.label));
      pilots.append(label);
    });
    const submit = request.lastElementChild;
    submit.disabled = true;
    pilots.addEventListener("change", () => { submit.disabled = !pilots.querySelector(":checked"); });
    request.insertBefore(pilots, submit);
  } else {
    target.append(element("p", "An enrolled pilot is required to start a Handler Play."));
  }
  for (const task of book.tasks) {
    const entry = element("article", undefined, "record-card");
    entry.dataset.handlerTask = task.id;
    entry.append(element("h3", task.targets.map(target => target.label).join(", ") || "Saved Handler Play"));
    if (task.observed_moment) entry.append(element("p", task.observed_moment));
    target.append(entry);
    if (task.stale) {
      entry.append(element("p", task.stale));
    } else if (task.state !== "pending") {
      entry.append(element("p", "Waiting for its assigned follow-up."));
    } else if (task.plays.length) {
      const payload = {id:task.id, revision:task.revision};
      const effect = form(entry, "File effect", values => {
        const fields = {};
        for (const key of additional.keys()) {
          if (values.has(key)) fields[key] = key === "status" ? Number(values.get(key))
            : key === "dress_steps" ? values.getAll(key) : values.get(key);
        }
        send("handler-play-submit", {
          ...payload, play:values.get("play"), account:values.get("account"),
          detail:values.get("detail") ?? "", stakes:values.get("stakes") ?? "", fields,
        });
      });
      const move = field(effect, "play", "Handler Play", "", [
        ["", "Choose a Play"], ...task.plays.filter(play => !play.reason).map(play => [play.id, play.label]),
      ]);
      move.required = true;
      for (const play of task.plays.filter(play => play.reason)) {
        entry.append(element("p", play.label + " · " + play.reason));
      }
      input(effect, "account", "Information or consequence to communicate", "", 1200);
      const detail = input(effect, "detail", "What changes?", "", 1200, false);
      const stakes = input(effect, "stakes", "What is at stake?", "", 1200, false);
      const select = (name, label, options) => field(effect, name, label, "", [["", "Choose"], ...options]);
      const target = select("target", "Affected original", task.targets.map(item => [item.token, item.label]));
      const kind = select("kind", "Change", [["status","Change Status"], ["tag","Give a Tag"], ["damage","Damage an Asset"]]);
      const asset = select("asset", "Undamaged Asset", []);
      const description = input(effect, "description", "Employee description", "", 1200, false);
      const dressSteps = field(effect, "dress_steps", "Printed steps", "", book.dress_steps ?? []);
      dressSteps.multiple = true;
      dressSteps.size = 5;
      const additional = new Map([
        ["target", target],
        ["executor", select("executor", "Original executor", task.executors)],
        ["name", input(effect, "name", "Employee name", "", 120, false)],
        ["department", select("department", "Department", book.support_jobs)],
        ["location", select("location", "Campaign location", task.locations)],
        ["description", description],
        ["cell", input(effect, "cell", "Zone coordinates (x, y)", "", 40, false)],
        ["feature", input(effect, "feature", "Warped feature name", "", 100, false)],
        ["kind", kind],
        ["status", select("status", "Status change", [["1","Raise one position"], ["-1","Lower one position"]])],
        ["tag", input(effect, "tag", "New Tag", "", 120, false)],
        ["asset", asset],
        ["dress_steps", dressSteps],
        ["dress_contact", select("dress_contact", "Physical action", book.dress_contacts ?? [])],
        ["dress_delegate", select("dress_delegate", "Other original participant", task.executors)],
        ["dress_dismissal", input(effect, "dress_dismissal", "Final dismissal", "", 1200, false)],
      ]);
      const update = () => {
        const needed = move.value === "escalate" || move.value === "expectation";
        const dress = move.value === "dress_them_down";
        const steps = [...dressSteps.selectedOptions].map(item => item.value);
        const order = steps.some(step => step === "demeaning" || step === "dismissal");
        for (const [control, visible] of [[detail, needed || dress && order], [stakes, needed]]) {
          control.parentElement.hidden = !visible;
          control.disabled = !visible;
          control.required = visible;
        }
        detail.labels[0].textContent = dress ? "Original Order" : "What changes?";
        dressSteps.setCustomValidity(dress && steps.length > 3 ? "Choose up to three steps." : "");
        const visible = {
          punish:["target", "executor"],
          support:["name", "department", "location", "description"],
          tracker_intercept:["target"], tracker_voyeur:["target"],
          contaminant_warp:["cell", "feature", "description"],
          mess:["kind", "target", kind.value === "damage" ? "asset" : kind.value],
          dress_them_down:[
            "target", "dress_steps", "tag",
            ...(steps.includes("physical") ? ["dress_contact"] : []),
            ...(steps.includes("delegate") ? ["dress_delegate"] : []),
            ...(steps.includes("demeaning") && steps.includes("dismissal") ? ["dress_dismissal"] : []),
          ],
        }[move.value] ?? [];
        description.labels[0].textContent = move.value === "contaminant_warp" ? "Warped feature description" : "Employee description";
        for (const [name, control] of additional) {
          control.disabled = !visible.includes(name);
          control.required = !control.disabled && !(dress && name === "tag");
          control.parentElement.hidden = control.disabled;
        }
        const selected = task.targets.find(item => item.token === target.value);
        const previous = asset.value;
        asset.replaceChildren(new Option("Choose", ""), ...(selected?.assets ?? []).map(item => new Option(item.name, item.id)));
        asset.value = [...asset.options].some(item => item.value === previous) ? previous : "";
      };
      for (const control of [move, target, kind, dressSteps]) control.addEventListener("change", update);
      update();
      if (task.ordinary) entry.append(action("Withdraw untouched Play", () => send("handler-play-withdraw", payload)));
    } else {
      entry.append(element("p", "This source-owned Play has no effect form in the Activity."));
    }
  }
}

function renderSuccessor(target, work, pilots, send) {
  const card = element("section", undefined, "record-card");
  card.append(element("h3", "Successor record"));
  const payload = {id:work.id, revision:work.revision};
  if (work.advice.length) {
    const entry = form(card,"File observed lesson",values => send("handler-play-successor",{
      ...payload, operation:"award", advice:values.get("advice"), lesson:values.get("lesson"),
      account:values.get("account"),
    }));
    const advice = field(entry,"advice","Original advice","",[["","Choose"],...work.advice]);
    const lesson = field(entry,"lesson","Completed Play","",[["","Choose"]]);
    advice.required = lesson.required = true;
    advice.addEventListener("change", () =>
      lesson.replaceChildren(new Option("Choose",""),...(work.lessons[advice.value] ?? []).map(([id,label]) => new Option(label,id))));
    input(entry,"account","How the pilot used the advice","",1200);
  } else {
    card.append(element("p","Awaiting a later Play in the original advice scene."));
  }
  if (work.stars.length) {
    const entry = form(card,"Remove Star",values => send("handler-play-successor",{
      ...payload, operation:"remove", star:values.get("star"),
    }));
    const stars = work.stars.map(([id,girl],index) => [
      id, (pilots.find(pilot => pilot.ref.entity === girl)?.label ?? "Original pilot") + " · Star " + (index+1),
    ]);
    field(entry,"star","Recorded Star","",[["","Choose"],...stars]).required = true;
  }
  target.append(card);
}

export const punishmentActions = {
  apply_scene_punishment:"Apply assigned Punishment",
  allow_locked_tag:"Allow rejection of this Tag",
  dive_call:"Answer Call",
  handler_void:"Review Handler Void",
  defeat_medical:"Open medical recovery",
  frame_replacement:"Review Frame replacement",
  snoop_decision:"Open original Snoop decision",
  consume_partake:"Open Let Us Partake",
  specialist_choice:"Open assigned Frame effect",
  changeling_copy:"Adopt a disclosed Identity",
  red_queen_restore:"Restore memory",
  mockingbird_release:"File departure decision",
  mockingbird_end:"End conversation",
  recover_scene_followup:"Resume assigned follow-up",
  resolve_locked_tag:"File your Tag decision",
  followup_entry_bind:"Bind the scene for your Dive",
  followup_entry_dive:"Start the required Dive",
  followup_prisoner_move:"Record prisoner movement",
  followup_prisoner_outcome:"File the breakout outcome",
  recover_punishment_followup:"Recover the original Punishment follow-up",
  dress_performance:"Open assigned Dress Them Down step",
  feedback_activate:"Open Ankou Feedback",
  feedback_choose:"File Feedback decision",
  feedback_purpose:"Answer the request for purpose",
  feedback_identity:"Place the new Identity",
  feedback_reprisal:"Start the assigned reprisal",
  followup_roll:"Roll follow-up",
  followup_decision:"File follow-up decision",
  resolve_void:"Resolve Void threshold",
  propose_punishment_scene:"Record delegated Punishment scene",
  attest_punishment_scene:"Confirm delegated Punishment attendance",
  request_punishment_consult:"Request Handler consultation",
  answer_punishment_consult:"Review Moderate Punishment proposal",
  apply_approved_punishment:"Apply the approved Punishment",
  instruct:"File Punishment instruction", scene:"Record Punishment scene", attest:"Confirm my attendance",
  approve:"Record Handler approval", execute:"File Punishment execution",
  apply_off_duty_punishment:"Apply the assigned Punishment",
  supply_expiry:"Review Supply Drop loss",
  punishment_helpless:"File last Girl Asset review", punishment_frame_loss:"File last Frame Asset review",
  punishment_paired_identity_heat:"Allocate Paired Identity Heat",
  surgery_plan:"File surgery plan", surgery_responses:"File patient responses", surgery_ready:"Complete filed surgery",
};

export function renderHandlerPunishments(target, cards, send, route = "handler-punishment", operation = "") {
  target.replaceChildren();
  for (const card of cards) {
    const record = element("article", undefined, "record-card");
    record.dataset.punishmentCase = card.id;
    record.tabIndex = -1;
    record.append(element("h3", card.instruction || "Punishment instruction"));
    for (const detail of card.instruction_details ?? []) record.append(element("p", detail));
    if (card.scene) record.append(element("p", card.scene));
    target.append(record);
    if (!card.action) {
      if (!card.read_only) record.append(element("p", card.stale ? "The original source or participants need review." : "Waiting for the assigned participant or consequence."));
      continue;
    }
    const sendStep = (answer, step = card.action) => send(route, {id:card.id, revision:card.revision, action:step, answer,
      ...(card.work_revision === undefined ? {} : {work_revision:card.work_revision}),
      ...(card.cast_revision === undefined ? {} : {cast_revision:card.cast_revision}),
      ...(card.game_revision === undefined ? {} : {game_revision:card.game_revision}),
      ...(card.expected === undefined ? {} : {expected:card.expected}),
      ...(card.permission === undefined ? {} : {permission:card.permission})});
    if (card.dress) {
      renderDressPerformance(record, card.dress, sendStep);
    } else if (card.operations) {
      renderVoidOperations(record, card.operations, sendStep, operation);
    } else if (card.fields) {
      followupForm(record, punishmentActions[card.action], card.fields, sendStep);
    } else if (card.decision_fields) {
      renderFollowupDecision(record, card.decision_fields, sendStep);
    } else if (card.action === "recover_scene_followup") {
      record.append(action(punishmentActions[card.action], () => sendStep({action:card.resume_action})));
    } else if (card.fixed_answer || ["followup_roll","mockingbird_end"].includes(card.action)) {
      record.append(action(punishmentActions[card.action], () => sendStep(card.fixed_answer ?? {})));
    } else if (card.action === "propose_punishment_scene") {
      const entry = form(record,punishmentActions[card.action],values => sendStep({summary:values.get("summary")}));
      input(entry,"summary","Scene account","",1200);
    } else if (card.action === "answer_punishment_consult") {
      if (!card.consult_stale) record.append(action("Approve this proposal", () => sendStep({approve:true})));
      record.append(action("Decline this proposal", () => sendStep({approve:false})));
    } else if (["attest_punishment_scene","apply_approved_punishment","recover_punishment_followup"].includes(card.action)) {
      record.append(action(punishmentActions[card.action], () => sendStep({})));
    } else if (["attest","approve","allow_locked_tag"].includes(card.action)) {
      record.append(action(punishmentActions[card.action], () => sendStep(true)));
    } else if (card.action === "scene" || card.action === "execute") {
      const entry = form(record, punishmentActions[card.action], values => sendStep(values.get("account")));
      input(entry, "account", card.action === "scene" ? "Describe the scene you played" : "Describe your actual execution", "", 1200);
    } else if (card.forms) {
      renderPunishmentInstruction(record, card, sendStep);
    } else if (card.surgery) {
      renderSurgery(record, card, sendStep);
    } else if (card.action === "punishment_paired_identity_heat") {
      const entry = form(record, punishmentActions[card.action], values => sendStep({share:Number(values.get("share"))}));
      offDutySelect(entry, "share", "Heat to share with your Pair", Array.from({length:6}, (_, heat) => [heat,String(heat)]), {required:true});
    } else {
      const context = card.action === "punishment_helpless" ? [["inside_frame", "Was the pilot inside a Frame?"]]
        : [["piloting", "Was the pilot operating that Frame?"], ["in_battle", "Was it an actual battle?"]];
      const entry = form(record, punishmentActions[card.action], values => sendStep({
        ...Object.fromEntries(context.map(([key]) => [key, values.get(key) === "yes"])), evidence:values.get("evidence"),
      }));
      for (const [key, label] of context) offDutySelect(entry, key, label, [["yes","Yes"],["no","No"]], {required:true});
      input(entry, "evidence", "Actual context", "", 1200);
    }
  }
}

function renderDressPerformance(record, dress, send) {
  if (dress.phase === "ready") {
    record.append(action("Apply recorded steps", () => send({step:"finish", account:""})));
    return;
  }
  if (dress.contacts.length) record.append(element("p", dress.contacts.join(" · ")));
  const entry = form(record, "File your response", values => send({
    step:values.get("step"), account:values.get("account") ?? "",
  }));
  const step = field(entry, "step", "Your decision", "", [["","Choose"], ...dress.options]);
  step.required = true;
  const account = input(entry, "account", "What took place?", "", 1200, false);
  const update = () => {
    account.disabled = !step.value || step.value === "decline";
    account.required = !account.disabled;
    account.parentElement.hidden = account.disabled;
  };
  step.addEventListener("change", update);
  update();
}

function followupForm(target, label, fields, send) {
  if (fields.some(spec => spec.required && spec.options?.length === 0)) {
    target.append(element("p","A required choice is unavailable. Check the current scene or character."));
    return;
  }
  const entry = form(target,label, values => send(Object.fromEntries(fields
    .filter(spec => values.get(spec.key))
    .map(spec => [spec.key, spec.multiple ? values.getAll(spec.key) : values.get(spec.key)]))));
  for (const spec of fields) {
    if (spec.options) offDutySelect(entry,spec.key,spec.label,spec.options,{required:spec.required,multiple:spec.multiple});
    else if (spec.paragraph) {
      const wrapper = element("label",spec.label,"field");
      const textarea = element("textarea");
      textarea.name = spec.key;
      textarea.required = spec.required;
      textarea.maxLength = 1200;
      textarea.rows = 4;
      wrapper.append(textarea);
      entry.insertBefore(wrapper,entry.lastElementChild);
    }
    else input(entry,spec.key,spec.label,"",1200,spec.required);
  }
  return entry;
}

function renderFollowupDecision(target, fields, send) {
  const entry = form(target,"File decision",values => {
    const answer = {};
    const details = {};
    for (const spec of fields) {
      const choices = values.getAll(spec.key).filter(Boolean);
      if (!choices.length) continue;
      if (spec.key.startsWith("fields.")) details[spec.key.slice(7)] = choices[0];
      else if (spec.key === "flag") answer.flag = choices[0] === "yes";
      else if (spec.paragraph || spec.key === "text") answer[spec.key] = choices[0];
      else answer[spec.key] = choices;
    }
    send({...answer, fields:details});
  });
  for (const spec of fields) {
    if (spec.options.length) offDutySelect(entry,spec.key,spec.label,spec.options,{required:spec.required,multiple:spec.maximum > 1});
    else input(entry,spec.key,spec.label,"",1200,spec.required);
  }
}

export function renderVoidOperations(record, operations, send, preferred = "") {
  const stages = operations.map(operation => {
    const label = operation.label ?? {
      answer:"Answer Apometanoia", begin:"Enter Frame and begin Apometanoia", resist:"Prepare resistance",
      protect:"Ask for protection", accept_protection:"Confirm protective hold", release_protection:"Release protective hold",
      propose_occupancy:"Report cockpit occupancy", confirm_occupancy:"Confirm cockpit occupancy",
      propose_approach:"Report arrival at Frame", confirm_approach:"Confirm arrival at Frame",
      choose_escape:"Choose an escape Asset", escape:"Shape the abandoned Frame",
      abandoned:"Shape the unoccupied Frame", overgrown:"Record the consumed pilot’s fate",
      use_risk_lesson:"Use Risk Factor lesson", save_rebirth:"File rebirth choices", rebirth:"Complete irreversible rebirth",
    }[operation.id] ?? operation.id.replaceAll("_"," ");
    const submit = values => send({operation:operation.id, values});
    const render = panel => {
      if (!operation.fields) {
        enginePayloadForm(panel,label,operation.initial,submit);
        return;
      }
      const entry = followupForm(panel,label,operation.fields,submit);
      if (entry && operation.regrowth) {
        const pairs = [1,2].map(i => [entry.elements.namedItem("frame_" + i), entry.elements.namedItem("replace_" + i)]);
        const updateReplacements = () => {
          let free = operation.regrowth.free;
          for (const [component, replacement] of pairs) {
            const needsReplacement = operation.regrowth.missing.includes(component.value) && free-- <= 0;
            replacement.required = needsReplacement;
            replacement.parentElement.hidden = !needsReplacement;
            if (!needsReplacement) replacement.value = "";
          }
        };
        for (const [component] of pairs) component.addEventListener("change",updateReplacements);
        updateReplacements();
      }
    };
    return {id:operation.id,label,render};
  });
  if (stages.length === 1) stages[0].render(record);
  else actionStages(record,stages,preferred);
}

function renderPunishmentInstruction(record, card, send) {
  let current;
  const entry = form(record, punishmentActions[card.action], values => {
    const answer = {kind:current.kind};
    for (const spec of current.fields) {
      const value = values.get(spec.key);
      if (spec.key === "identities") answer.identities = values.getAll(spec.key);
      else if (spec.key === "disclosed") answer.disclosed = value === "yes";
      else if (spec.key === "asset" && value.startsWith("part:")) answer.body_part = value.slice(5);
      else answer[spec.key] = value;
    }
    const phrase = values.get("conditioning_phrase");
    if (phrase) answer.conditioning_phrase = phrase;
    send(answer, card.consult_moderate && current.severity === "moderate" ? "request_punishment_consult" : card.action);
  });
  const kind = offDutySelect(entry, "kind", "Punishment", card.forms.filter(item => item.available)
    .map(item => [item.id,item.label]), {required:true});
  if (card.conditioning_phrases?.length) {
    offDutySelect(entry, "conditioning_phrase", "Optional Conditioning Phrase to install", card.conditioning_phrases);
  }
  const fields = [];
  kind.addEventListener("change", () => {
    while (fields.length) fields.pop().remove();
    current = card.forms.find(item => item.id === kind.value);
    entry.lastElementChild.textContent = punishmentActions[card.consult_moderate && current?.severity === "moderate" ? "request_punishment_consult" : card.action];
    for (const spec of current?.fields ?? []) {
      const multiple = spec.count > 1;
      const control = spec.options ? offDutySelect(entry, spec.key, spec.label, spec.options, {required:true,multiple})
        : input(entry, spec.key, spec.label, "", spec.size);
      if (multiple) {
        const validate = () => control.setCustomValidity(control.selectedOptions.length === spec.count ? "" : "Choose " + spec.count + " entries.");
        control.addEventListener("change", validate);
        validate();
      }
      fields.push(control.parentElement);
    }
  });
  const unavailable = card.forms.filter(item => !item.available);
  if (unavailable.length) record.append(element("p", "Current prerequisites are missing for " + unavailable.map(item => item.label).join(", ") + "."));
}

function renderSurgery(record, card, send) {
  const data = card.surgery;
  if (data.phase === "ready") {
    record.append(action(punishmentActions[card.action], () => send(true)));
    return;
  }
  if (data.phase === "responses") {
    for (const key of ["room","restraints","tools"]) record.append(element("p", data.plan[key]));
    const response = form(record, punishmentActions[card.action], values => send(Object.fromEntries(values)));
    for (const [key, label] of Object.entries(data.prompts)) input(response, key, label, "", 1200);
    return;
  }
  const plan = form(record, punishmentActions[card.action], values => send({
    options:values.getAll("options"), room:values.get("room"), restraints:values.get("restraints"), tools:values.get("tools"),
    erase_slots:values.getAll("erase_slots").map(Number), forbidden_play:values.get("forbidden_play"),
    new_name:values.get("new_name") ?? "", inflictor_depth:Number(values.get("inflictor_depth") ?? "0"),
    other:values.get("other") ? JSON.parse(values.get("other")) : null, other_depth:Number(values.get("other_depth") ?? "0"),
    memory:values.get("memory") ?? "", identity:values.get("identity") ?? "", replace_identity:values.get("replace_identity"),
  }));
  const labels = {memories:"Erase starting Identities", play:"Remove a Play", name:"Change name", bonds:"Change Bonds", memory:"Implant a memory"};
  const effects = offDutySelect(plan, "options", "Choose one to three effects", data.options.map(value => [value,labels[value]]), {required:true,multiple:true});
  for (const [key,label] of [["room","Room"], ["restraints","Restraints"], ["tools","Tools"]]) input(plan,key,label,"",1200);
  const erase = offDutySelect(plan,"erase_slots","Select two starting Identity slots",
    data.starting.map((name, index) => [index,name]).filter(([index]) => !data.protected_slots.includes(index)), {multiple:true});
  const play = offDutySelect(plan,"forbidden_play","Play to remove",data.plays.map(name => [name,name.replaceAll("_"," ")]));
  const name = input(plan,"new_name","New name (optional)","",32,false);
  const depths = [[0,"No Bond"],[1,"Personal"],[2,"Intense"]];
  const bond = offDutySelect(plan,"inflictor_depth","New Bond with the inflictor",depths);
  const other = offDutySelect(plan,"other","Optional other character",data.actors.map(actor => [JSON.stringify(actor.ref),actor.label]));
  const depth = offDutySelect(plan,"other_depth","Other character’s Bond",depths.slice(1));
  const memory = input(plan,"memory","Implanted memory","",1200,false);
  const identity = input(plan,"identity","New Identity","",120,false);
  const replace = offDutySelect(plan,"replace_identity","Replace an unprotected Identity",
    data.identities.filter(row => !row.protected).map(row => [row.id,row.name]));
  const update = () => {
    const selected = new Set([...effects.selectedOptions].map(option => option.value));
    const memoryChosen = selected.has("memory");
    const binds = selected.has("bonds");
    const replacementRequired = memoryChosen && !selected.has("memories")
      && data.identities.filter(item => !item.protected || item.paired).length >= 4;
    for (const [control, enabled] of [[erase,selected.has("memories")],[play,selected.has("play")],[name,selected.has("name")],
      [bond,binds],[other,binds],[depth,binds && !!other.value],[memory,memoryChosen],[identity,memoryChosen],[replace,replacementRequired]]) {
      toggleField(control, enabled);
    }
    name.required = false;
    other.required = false;
    erase.setCustomValidity(!erase.disabled && erase.selectedOptions.length !== 2 ? "Choose two starting Identity slots." : "");
    effects.setCustomValidity(selected.size > 3 ? "Choose up to three effects." : "");
  };
  for (const control of [effects,erase,other]) control.addEventListener("change",update);
  update();
}

export function renderHandlerSceneChoices(target, cards, send) {
  target.hidden = !Array.isArray(cards);
  target.replaceChildren();
  if (target.hidden) return;
  target.append(element("h2", "Handler decisions"));
  if (!cards.length) target.append(element("p", "No scene decisions are assigned to you."));
  const dialog = document.getElementById("scene-action-dialog");
  const fields = document.getElementById("scene-action-fields");
  const groups = new Map();
  for (const card of cards) {
    const group = groups.get(card.root) ?? [];
    group.push(card);
    groups.set(card.root,group);
  }
  const show = (root, group) => {
    const key = JSON.stringify([root,group]);
    if (dialog.dataset.role === "handler" && dialog.dataset.content === key) return;
    dialog.dataset.role = "handler";
    dialog.dataset.root = root;
    dialog.dataset.content = key;
    if (group.length) dialog.dataset.location = group[0].room_name;
    renderRecordMetadata(document.getElementById("scene-action-record"), {
      location:dialog.dataset.location, state:group.length ? "Action required" : "No decision assigned",
      owner:group.length ? "Handler" : undefined,
    });
    dialog.dispatchEvent(new Event("beneath-source"));
    if (!group.length) {
      fields.replaceChildren(element("p","No further decisions are assigned to you."));
      return;
    }
    const room = group[0];
    const label = playName(room.play);
    document.getElementById("scene-action-title").textContent = label;
    fields.replaceChildren(element("h3",room.room_name));
    const state = {
      choices:group.map(card => card.choice), history:[], handler_owned:true,
    };
    const scoped = (step,payload) => send(step,{...payload,room:room.room});
    if (room.step === "keep-choice") renderKeep(fields, state, scoped);
    else renderSceneAction(fields, {id:room.play}, label, state, scoped);
  };
  if (dialog?.open && dialog.dataset.role === "handler") {
    show(dialog.dataset.root, groups.get(dialog.dataset.root) ?? []);
  }
  for (const [root,group] of groups) {
    const open = action(group[0].room_name + " · " + playName(group[0].play), () => {
      document.getElementById("scene-action-feedback").hidden = true;
      show(root,group);
      if (!dialog.open) dialog.showModal();
    });
    open.setAttribute("aria-haspopup","dialog");
    open.dataset.playDecisions = group.map(card => card.choice.id).join(" ");
    target.append(open);
  }
}

function offDutySelect(form, key, label, options, {required = false, multiple = false} = {}) {
  const choices = multiple ? options : [["", required ? "Choose an option" : "None"], ...options];
  const control = field(form, key, label, "", choices);
  control.required = required;
  control.multiple = multiple;
  if (multiple) control.size = Math.min(5, options.length);
  return control;
}

const yesNo = [["yes", "Yes"], ["no", "No"]];

function renderOffDutyScene(section, scene, send) {
  section.append(element("h3", "Off-Duty scene assignment"));
  const controls = form(section, "File scene choice", values => {
    const kind = values.get("kind");
    const investor = scene.prime.find(item => item.id === values.get("investor"));
    send("choose_scene", {
      kind:kind === "decline" ? null : kind,
      participants:kind === "decline" ? [] : investor ? [investor.controller] : values.getAll("participants"),
      summary:kind === "decline" ? "" : values.get("summary"),
      investor:investor?.actor ?? null,
    });
  });
  const kind = offDutySelect(controls, "kind", "Scene", [
    ...(scene.can_decline ? [["decline", "No optional scene"]] : []), ...scene.options,
    ...(scene.prime.length ? [[scene.prime_kind, "Prime Investment"]] : []),
  ], {required:true});
  const people = offDutySelect(controls, "participants", "Other participants", scene.participants, {multiple:true});
  const summary = input(controls, "summary", "Scene account", "", 1200);
  const investor = scene.prime.length ? offDutySelect(controls, "investor", "Investor",
    scene.prime.map(item => [item.id, item.actor.kind + " " + item.actor.entity]), {required:true}) : null;
  const sync = () => {
    const decline = kind.value === "decline";
    const prime = kind.value === scene.prime_kind;
    people.disabled = decline || prime;
    people.required = !people.disabled;
    people.parentElement.hidden = people.disabled;
    for (const option of people.options) {
      option.selected = (scene.required[kind.value] ?? []).includes(option.value);
    }
    summary.disabled = decline;
    summary.parentElement.hidden = decline;
    if (investor) {
      investor.disabled = !prime;
      investor.parentElement.hidden = !prime;
    }
  };
  kind.addEventListener("change", sync);
  sync();
}

function renderRecovery(section, recovery, send) {
  section.append(element("h3", "Recover your pilot"));
  const controls = form(section, "File recovery", values => send("recover", {
    embrace_tag:values.get("embrace_tag") || null,
    replace_identity:values.get("replace_identity") || null,
    unmark_identity:values.get("unmark_identity") || null,
    repair_assets:values.get("repair_assets") === "yes",
    repairs:recovery.repair_limit && values.get("repair_assets") === "yes" ? {
      girl:values.getAll("girl").filter(Boolean), frame:values.getAll("frame").filter(Boolean),
    } : null,
    modular_replacements:values.getAll("modular").map(asset => ({
      asset, name:values.get("name:" + asset), description:values.get("description:" + asset),
    })),
  }));
  const selectors = [
    ["embrace_tag", "Tag to embrace", recovery.tags],
    ["replace_identity", "Identity to replace, if at capacity", recovery.replace],
    ["unmark_identity", "Identity to unmark", recovery.unmark],
  ];
  for (const [key, label, options] of selectors) {
    if (options.length) offDutySelect(controls, key, label, options);
  }
  const repairs = offDutySelect(controls, "repair_assets", "Repair damaged Assets?", yesNo, {required:true});
  repairs.value = "yes";
  const limited = Object.entries(recovery.damaged).filter(([, options]) => recovery.repair_limit && options.length)
    .map(([family, options]) => offDutySelect(controls, family, "Repair one " + family + " Asset", options));
  const modular = recovery.modular.length ? offDutySelect(controls, "modular", "Modular Build replacements", recovery.modular, {multiple:true}) : null;
  const replacements = recovery.modular.map(([id, label]) => [id,
    input(controls, "name:" + id, "New Asset for " + label, "", 120),
    input(controls, "description:" + id, "Description for " + label, "", 700),
  ]);
  const sync = () => {
    const repair = repairs.value === "yes";
    for (const control of [...limited, ...(modular ? [modular] : [])]) {
      control.disabled = !repair;
      control.parentElement.hidden = !repair;
    }
    const selected = new Set(Array.from(modular?.selectedOptions ?? [], item => item.value));
    for (const [id, ...fields] of replacements) {
      for (const control of fields) {
        control.disabled = !repair || !selected.has(id);
        control.parentElement.hidden = control.disabled;
      }
    }
  };
  repairs.addEventListener("change", sync);
  modular?.addEventListener("change", sync);
  sync();
}

function renderOffDutyWork(section, work, send) {
  section.append(element("h3", work.label));
  if (work.pilot) section.append(element("p", "Pilot · " + work.pilot));
  const reference = {id:work.id, work_revision:work.revision};
  if (work.kind === "show_dog") {
    if (work.summary) section.append(element("p",work.summary));
    renderVoidOperations(section, work.operations, answer => send("show_dog", {...reference,...answer}));
  } else if (work.kind === "disposable_psyche") {
    if (work.phase === "converted") {
      section.append(element("p", "Identities filed · " + work.identities.join(", ")));
    } else if (work.phase === "no_tags") {
      section.append(element("p", "The original Off-Duty record had no Tags to rebuild."));
    } else if (!work.tags.length) {
      section.append(element("p", "Awaiting recovery of the original Tags."));
    } else {
      section.append(element("p", "Choose one to four Tags. Replace only the Identities needed to stay within four slots."));
      const entry = form(section, "File rebuilt Identities", values => send("disposable_psyche", {
        ...reference, tags:values.getAll("tags"), replacements:values.getAll("replacements"),
      }));
      const tags = offDutySelect(entry, "tags", "Original Tags", work.tags, {required:true,multiple:true});
      const replacements = offDutySelect(entry, "replacements", "Replace eligible Identities",
        work.identities, {multiple:true});
      const sync = () => {
        const count = tags.selectedOptions.length;
        const needed = Math.max(0, work.count + count - 4);
        const valid = count > 0 && count <= 4 && needed <= count && needed <= work.identities.length;
        tags.setCustomValidity(valid ? "" : "Select up to four Tags that fit with the eligible replacements.");
        replacements.disabled = replacements.parentElement.hidden = !needed;
        replacements.setCustomValidity(!needed || needed === replacements.selectedOptions.length
          ? "" : "Choose " + needed + " Identities to replace.");
      };
      tags.addEventListener("change", sync);
      replacements.addEventListener("change", sync);
      sync();
    }
  } else if (work.kind === "janus_reward") {
    const controls = form(section, "File Permission review", values => send("review_janus", {
      ...reference, claim:{fulfilled:values.get("fulfilled") === "yes", official:values.get("official"), account:values.get("account")},
    }));
    const fulfilled = offDutySelect(controls, "fulfilled", "Did you demonstrate your Core was harmless?", yesNo, {required:true});
    const official = offDutySelect(controls, "official", "Witness to the demonstration", work.officials, {required:true});
    input(controls, "account", "What happened?", "", 1200);
    const sync = () => {
      official.disabled = fulfilled.value !== "yes";
      official.parentElement.hidden = official.disabled;
    };
    fulfilled.addEventListener("change", sync);
    sync();
  } else if (work.kind === "observation_choice") {
    const controls = form(section, "File consequence choices", values => send("choose_observation", {
      subject:work.subject_id, choices:values.getAll("choices").filter(Boolean),
    }));
    const choices = offDutySelect(controls, "choices", "Choose " + work.count + " consequences", work.options,
      {required:true, multiple:work.count > 1});
    if (work.count > 1) {
      choices.addEventListener("change", () => choices.setCustomValidity(choices.selectedOptions.length === work.count
        ? "" : "Choose exactly " + work.count + " consequences."));
    }
  } else if (work.response_required) {
    section.append(element("p", work.proposal_account));
    const controls = form(section, "File NPC response", values => send("answer_observation", {...reference, accepted:values.get("response") === "yes"}));
    offDutySelect(controls, "response", "Confirm participation as " + work.npc_name + "?", yesNo, {required:true});
  } else {
    const selectors = [["asset", "Void Asset", work.assets], ["npc", "Available NPC", work.npcs],
      ["identity", "Identity to retain", work.identities], ["slot", "Starting slot to replace", work.slots]]
      .filter(([, , options]) => options !== undefined);
    if (selectors.some(([, , options]) => !options.length)) {
      section.append(element("p", "No eligible option is available for this consequence."));
      return;
    }
    const controls = form(section, "File consequence", values => send("apply_observation", {...reference, details:Object.fromEntries(values)}));
    for (const [key, label, options] of selectors) offDutySelect(controls, key, label, options, {required:true});
    if (work.consequence === "public_display_tag") input(controls, "tag", "Tag given by the populace", "", 120);
    input(controls, "account", "What happened?", "", 1200);
  }
}

export function renderOffDuty(target, state, save, preview) {
  target.replaceChildren();
  target.dataset.revision = state ? `${state.revision}:${state.game_revision}` : "";
  target.dataset.period = state?.period ?? "";
  if (!state) return;
  const send = (action, answer) => save("off-duty-followup", {action, answer,
    period:state.period, revision:state.revision, game_revision:state.game_revision});
  if (state.reason) target.append(element("p", state.reason));
  if (state.refresh_rewards) target.append(action("Refresh Frame reward reviews", () => send("refresh_rewards", {})));
  for (const work of state.work) {
    const section = element("section");
    section.dataset.offDutyWork = work.id;
    section.tabIndex = -1;
    renderOffDutyWork(section, work, send);
    target.append(section);
  }
  if (state.scene) renderOffDutyScene(target, state.scene, send);
  for (const scene of state.invitations) {
    const section = element("section");
    section.append(element("h3", scene.label));
    if (scene.pilot) section.append(element("p", "Pilot · " + scene.pilot));
    section.append(element("p", scene.summary));
    if (!scene.confirmed) section.append(action("Confirm my participation", () => send("confirm_scene", {owner:scene.owner})));
    else section.append(element("p", scene.remaining ? "ATTENDANCE FILED · Other countersignatures pending." : "ALL COUNTERSIGNATURES FILED"));
    target.append(section);
  }
  if (state.declined) target.append(element("p", "Optional scene declined."));
  if (state.recovery) renderRecovery(target, state.recovery, send);
  if (state.recovered) target.append(element("p", "RECOVERY FILED"));
  if (state.closing) renderOffDutyClosing(target, state.closing, send,
    answer => preview({period:state.period, revision:state.revision, game_revision:state.game_revision,
      action:"strain_effect_fields",answer}));
}

function toggleField(control, active) {
  control.disabled = !active;
  control.required = active;
  control.parentElement.hidden = !active;
}

function renderOffDutyClosing(target, closing, send, preview) {
  const panel = element("section");
  panel.append(element("h3", closing.handler ? "Final Off-Duty review" : "Handler Off-Duty scene"));
  target.append(panel);
  if (closing.phase === "preparing") {
    renderStrainPreparation(panel, closing.strain, send, preview);
    return;
  }
  if (closing.attendance) {
    const {summary, confirmed, remaining} = closing.attendance;
    panel.append(element("p", summary));
    if (closing.attendance.phrase) panel.append(element("p", closing.attendance.phrase));
    if (closing.attendance.lab) {
      panel.append(element("p", closing.attendance.lab.name), element("p", closing.attendance.lab.description));
    }
    if (!confirmed && closing.attendance.lab_assets) {
      const assets = closing.attendance.lab_assets;
      if (assets.restore.length) {
        const lab = form(panel, "Confirm attendance and Asset choices", values => send("acknowledge_handler_scene", {
          lab: {remove_void:values.get("restore"), replace:values.get("replace") || null},
        }));
        const restore = offDutySelect(lab, "restore", "Girl Asset to clear of Void", assets.restore, {required:true});
        const replace = offDutySelect(lab, "replace", "Replace a different Girl Asset if needed", assets.replace);
        const update = () => {
          for (const option of replace.options) option.disabled = Boolean(option.value && option.value === restore.value);
          if (replace.selectedOptions[0]?.disabled) replace.value = "";
        };
        restore.addEventListener("change", update);
        update();
      } else panel.append(element("p", "This scene needs one eligible Void-touched Girl Asset."));
    } else if (!confirmed) panel.append(action("Confirm my Handler scene attendance", () => send("acknowledge_handler_scene", {})));
    else if (remaining) panel.append(element("p", "Waiting for the other participants to confirm their attendance."));
  } else if (closing.handler && closing.scene_kinds?.length && closing.participants.length) {
    renderHandlerOffDutyScene(panel, closing, send);
  }
  if (!closing.handler) return;
  if (closing.recovery_pending) panel.append(element("p", "Pilot recovery is still pending."));
  if (closing.pending_count) {
    const names = (closing.pending_kinds ?? []).map(kind => kind.replaceAll("_", " "));
    panel.append(element("p", closing.pending_count + " required item(s) pending" + (names.length ? " · " + names.join(", ") : "") + "."));
  }
  if (closing.finish) renderWorldReview(panel, closing.finish, send);
  else if (closing.status_ready) {
    const review = form(panel, "File Cadre Status review", values => send("review_status", {
      order:closing.participants.map((_, index) => values.get("rank-" + index)),
      account:values.get("account"),
    }));
    closing.participants.forEach(([identity], index) => {
      field(review, "rank-" + index, "Status order · " + (index + 1), identity, closing.participants).required = true;
    });
    input(review, "account", "Performance review", "", 1200);
  }
}

function renderStrainPreparation(panel, preparation, send, preview) {
  if (!preparation) return;
  if (preparation.needs_world) {
    actionStages(panel,[{
      label:"Initialize the campaign world for Strain",
      render(setup) {
        setup.append(element("p","Set the board, three bases, at least two cities, three important locations, and the concealed Benevolent Gorgon."));
        enginePayloadForm(setup, "File campaign world", {board:{}, locations:[], secret:{}}, answer => send("strain_world",answer));
      },
    }]);
  }
  for (const card of preparation.cards) {
    const stage = element("article", undefined, "record-card");
    stage.dataset.strainWork = card.id;
    stage.tabIndex = -1;
    stage.append(element("h4", card.label));
    panel.append(stage);
    const submit = (answer = {}) => send(card.action, {id:card.id, revision:card.revision, ...answer});
    if (card.action === "strain_configure") {
      const formEl = form(stage, "File starting Strain", values => send(card.action, {
        scenario:values.get("scenario"), high:values.getAll("high"),
      }));
      offDutySelect(formEl,"scenario","Starting scenario",card.scenarios,{required:true});
      offDutySelect(formEl,"high","Tracks starting High",card.tracks.map(name => [name,name]),{multiple:true});
    } else if (card.action === "strain_prepare") {
      for (const label of card.exemptions) stage.append(element("p","Budget death exemption · " + label));
      const formEl = form(stage, "File trigger review", values => send(card.action, {
        id:card.id, account:values.get("account"),
        facts:Object.fromEntries(card.facts.map(([key]) => [key,values.get(key) === "yes"])),
      }));
      for (const [key,label] of card.facts) offDutySelect(formEl,key,label,yesNo,{required:true});
      input(formEl,"account","Factual trigger review","",1200);
    } else if (card.action === "strain_roll") {
      stage.append(action("Roll and save d6", () => submit()));
    } else if (card.action === "strain_column" || card.action === "strain_endgame") {
      if (card.face) stage.append(element("p","Saved d6 · " + card.face));
      const needsGroup = card.action === "strain_endgame" && card.track === "rebellion";
      if (!card.columns.length || needsGroup && !card.rebel_groups.length) {
        stage.append(element("p","A required Endgame option or active Rebel Group is missing."));
        continue;
      }
      const formEl = form(stage, "File event selection", values => submit({
        column:Number(values.get("column")), faction:values.get("faction"),
      }));
      offDutySelect(formEl,"column","Event",card.columns,{required:true});
      if (needsGroup) offDutySelect(formEl,"faction","Active Rebel Group",card.rebel_groups.map(row => [row.id,row.label]),{required:true});
    } else if (card.action === "strain_effect") {
      if (card.supply) stage.append(element("p","Saved supply outcome · " + card.supply.recipient + " · " + card.supply.resource));
      const entry = element("section");
      const fields = element("div");
      const error = element("p");
      error.setAttribute("role","status");
      const open = action("Open effect form",() => {
        entry.replaceChildren(action("Back to assigned actions",() => entry.replaceChildren(open)),fields,error);
        if (!fields.children.length) load({});
        else fields.querySelector("input,select,textarea")?.focus();
      });
      entry.append(open);
      stage.append(entry);
      const payload = values => ({id:card.id, revision:card.revision, values});
      let pending = 0;
      const load = async (values, focus) => {
        const version = ++pending;
        error.textContent = "Loading effect choices…";
        try {
          const data = await preview(payload(values));
          if (version !== pending || !fields.isConnected) return;
          fields.replaceChildren(element("p",data.instructions));
          renderStrainEffect(fields,data,
            values => send("strain_effect_submit",payload(values)),load,focus);
          error.textContent = "";
        } catch (failure) {
          if (version === pending) error.textContent = failure.message;
        }
      };
    } else stage.append(element("p","Open the original event file to complete this assignment."));
  }
  if (preparation.ready) panel.append(action("Activate prepared Off-Duty", () => send("activate_period", {})));
  else if (!preparation.cards.length) panel.append(element("p","Waiting for assigned preparation consequences."));
}

function renderStrainEffect(target, data, send, preview, focus) {
  const read = values => Object.fromEntries(data.fields.flatMap(spec => {
    const value = spec.options.length ? values.getAll(spec.key).filter(Boolean) : values.get(spec.key);
    return value?.length ? [[spec.key,value]] : [];
  }));
  const entry = form(target,"Apply filed Strain event", values => send(read(values)));
  for (const spec of data.fields) {
    const stored = data.values[spec.key];
    let control;
    if (spec.options.length) {
      const choices = spec.options.filter(([id]) => id !== "pending");
      control = offDutySelect(entry,spec.key,spec.label,choices,{required:spec.required,multiple:spec.maximum > 1});
      for (const option of control.options) option.selected = stored?.includes(option.value) ?? option.value === "";
      if (!choices.length) {
        control.disabled = true;
        control.parentElement.append(element("p","Complete the earlier choices or supply the required campaign record."));
        entry.lastElementChild.disabled = true;
      }
      control.addEventListener("change", () => {
        entry.lastElementChild.disabled = true;
        preview(read(new FormData(entry)),spec.key);
      });
    } else {
      control = input(entry,spec.key,spec.label,stored ?? "",2400,spec.required);
      if (spec.paragraph) {
        const area = element("textarea");
        Object.assign(area,{id:control.id,name:control.name,value:control.value,required:control.required,maxLength:2400,rows:3});
        control.replaceWith(area);
        control = area;
      }
    }
    if (focus === spec.key) control.focus();
  }
}

function enginePayloadForm(target, label, initial, send) {
  const entry = form(target, label, () => {
    let value;
    try {
      value = JSON.parse(body.value);
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
    } catch {
      body.setCustomValidity("Enter a JSON object with the source decision fields.");
      body.reportValidity();
      return;
    }
    send(value);
  });
  const caption = element("label", "Source effect fields (JSON)");
  const body = element("textarea");
  body.required = true;
  body.rows = 6;
  body.value = JSON.stringify(initial, null, 2);
  body.addEventListener("input", () => body.setCustomValidity(""));
  caption.append(body);
  entry.insertBefore(caption, entry.lastElementChild);
}

function renderHandlerOffDutyScene(panel, closing, send) {
  const scene = form(panel, "File Handler Off-Duty scene", values => {
    const kind = values.get("kind");
    const context = values.has("entity") ? {
      entity:values.get("entity"), operation:values.get("operation"),
      deprogram_tags:values.getAll("tags"),
    } : null;
    send("set_handler_scene", {
      kind, participants:values.getAll("participants"), summary:values.get("summary"),
      recipient:values.get("recipient"), context,
      ...(kind === "scientist_lab" ? {lab:{name:values.get("lab_name"), description:values.get("lab_description")}} : {}),
      ...(kind === "trainer_conditioning" ? {conditioning_phrase:values.get("conditioning_phrase")} : {}),
    });
  });
  scene.dataset.handlerSceneForm = "";
  const sceneType = offDutySelect(scene, "kind", "Handler scene", closing.scene_kinds.map(kind => [kind,
    ({scientist_lab:"Head to the Lab", trainer_conditioning:"Conditioning Phrases"})[kind] ?? kind.replaceAll("_", " ")]), {required:true});
  const people = offDutySelect(scene, "participants", "Participating pilots", closing.participants, {required:true,multiple:true});
  const recipient = offDutySelect(scene, "recipient", "Affected pilot", []);
  const entity = offDutySelect(scene, "entity", "Original NPC or prisoner", []);
  const operation = offDutySelect(scene, "operation", "Employment decision", []);
  const tags = offDutySelect(scene, "tags", "Actual NPC Tags", [], {multiple:true});
  const labName = input(scene, "lab_name", "New Void Asset name", "", 80);
  const labDescription = input(scene, "lab_description", "New Void Asset description", "", 1200);
  const phrase = offDutySelect(scene, "conditioning_phrase", "Phrase to install", closing.conditioning_phrases ?? []);
  input(scene, "summary", "Scene account", "", 1200);
  function options(control, rows, multiple = false) {
    const selected = new Set([...control.selectedOptions].map(option => option.value));
    control.replaceChildren(...(multiple ? [] : [new Option("Choose", "")]),
      ...rows.map(([key, label]) => new Option(label,key,false,selected.has(key))));
  }
  const update = () => {
    const kind = sceneType.value;
    const employment = kind === "npc_employment";
    const prisoner = kind === "prisoner";
    const participants = new Set([...people.selectedOptions].map(option => option.value));
    options(recipient, closing.participants.filter(([id]) => participants.has(id)));
    const custody = closing.prisoners.filter(row => participants.has(row.custodian) || row.custodian === closing.handler_id);
    options(entity, closing.npcs.filter(npc => employment || prisoner && npc.prisoner)
      .concat(prisoner ? custody : []).map(row => [row.id,row.label]));
    const employee = closing.npcs.find(row => row.id === entity.value);
    const operations = ["hire","fire","chastise","request"];
    if (employee?.employment === "foundation" && employee.tags.length) operations.push("deprogram");
    options(operation, operations.map(value => [value,value]));
    options(tags, employee?.tags ?? [], true);
    toggleField(recipient, ["permission","punish","exploit"].includes(kind));
    toggleField(entity, employment || prisoner);
    toggleField(operation, employment);
    toggleField(tags, employment && operation.value === "deprogram");
    toggleField(labName, kind === "scientist_lab");
    toggleField(labDescription, kind === "scientist_lab");
    toggleField(phrase, kind === "trainer_conditioning");
    const privatePair = ["scientist_lab", "trainer_conditioning"].includes(kind);
    people.setCustomValidity(privatePair && participants.size !== 1 ? "Choose one attending Girl." : "");
  };
  for (const control of [sceneType, people, entity, operation]) control.addEventListener("change", update);
  update();
}

function renderWorldReview(panel, world, send) {
  const review = form(panel, "Apply world review and end Off-Duty", values => {
    const moves = world.moves.map(move => ({gorgon:move.id, destination:JSON.parse(values.get(move.id + "-step"))}));
    const changes = world.changes.map(change => {
      const read = name => values.get(change.id + "-" + name);
      const destination = read("goal");
      let goal = null;
      if (destination === "cell") goal = {kind:"cell", cell:read("cell").split(",").map(Number)};
      else if (destination) {
        const split = destination.indexOf(":");
        goal = {kind:destination.slice(0, split), entity_id:destination.slice(split + 1)};
      }
      return {id:change.id, class:read("class"), goal, protect:read("protect"), leader:read("leader"), group:read("group") === "yes", account:read("account")};
    });
    send("finish_period", {moves, changes});
  });
  for (const move of world.moves) {
    offDutySelect(review, move.id + "-step", "Move " + move.label,
      move.cells.map(cell => [JSON.stringify(cell), "Square " + cell.join(", ")]), {required:true});
  }
  for (const change of world.changes) {
    const choose = (key, label, values, required = false) => offDutySelect(review, change.id + "-" + key, label, values, {required});
    const variant = choose("class", "New Class for " + change.label, world.classes.map(name => [name,name]), true);
    const goal = choose("goal", "Actual goal", world.goals);
    const cell = input(review, change.id + "-cell", "Goal square (x, y)", "", 40, false);
    cell.pattern = "-?[0-9]+\\s*,\\s*-?[0-9]+";
    const protect = choose("protect", "Protective Asset", change.assets);
    const leader = choose("leader", "Compatible Gorgon to follow", change.leaders);
    const group = choose("group", "Group of Sprites", [["yes","Yes"],["no","No"]]);
    input(review, change.id + "-account", "Class change account", "", 1200);
    const update = () => {
      const directed = variant.value === "directed";
      const sprite = variant.value === "sprite";
      toggleField(goal, directed);
      toggleField(cell, directed && goal.value === "cell");
      toggleField(protect, directed);
      toggleField(leader, sprite);
      toggleField(group, sprite);
    };
    variant.addEventListener("change", update);
    goal.addEventListener("change", update);
    update();
  }
}

function enrollmentField(form, path) {
  if (!form || !Array.isArray(path)) return null;
  const [name, index, part] = path;
  if (name === "girl_assets" || name === "frame_assets") {
    const prefix = name === "girl_assets" ? "girl" : "frame";
    const choices = [0, 1].map(slot => form.elements.namedItem(prefix + slot)).filter(Boolean);
    const submitted = choices.filter(choice => choice.value);
    const choice = submitted[index ?? 0] ?? choices[index ?? 0];
    return part === "description" && choice ? form.elements.namedItem(choice.name + "-description") : choice;
  }
  if (name === "npc_bonds") {
    const prefix = part === "name" ? "npc_name" : part === "feelings" ? "npc_feelings" : "npc_slot";
    return form.elements.namedItem(prefix + (index === 1 ? "2" : ""));
  }
  if (name === "prior_missions") {
    const rows = Array.from(form.elements).filter(control => control.name.startsWith("mission_"));
    return Number.isInteger(index) ? rows.filter(row => row.value !== "")[index] ?? rows[0]
      : rows.find(row => row.value === "") ?? rows[0];
  }
  if (name === "pair_asset_descriptions") return form.elements.namedItem("pair_description_" + (index ?? 0));
  if (name === "girl_details" || name === "fanbase" || name === "dna_basis") {
    const group = form.querySelector("[data-enrollment-specialist]");
    return group?.querySelector(".field :is(input,select,textarea)");
  }
  return typeof name === "string" ? form.elements.namedItem(name) : null;
}

export function createEnrollment(dialog, trigger, artwork, send, refresh) {
  const body = dialog.querySelector("#enrollment-record");
  const scroll = dialog.querySelector("#enrollment-scroll");
  const identity = dialog.querySelector("#enrollment-identity");
  const feedback = dialog.querySelector("#enrollment-feedback");
  const errors = dialog.querySelector("#enrollment-errors");
  const submits = dialog.querySelector("#enrollment-submit");
  const recordState = dialog.querySelector("#enrollment-state");
  const tabs = [...dialog.querySelectorAll("[data-enrollment-tab]")];
  let sections;
  let primary = {};
  let step;
  let shown = false;
  let stage;
  let pendingStep;
  const marked = new Set();

  function clearErrors() {
    errors.replaceChildren();
    for (const control of marked) control.removeAttribute("aria-invalid");
    marked.clear();
  }

  function showErrors(message, entries = []) {
    clearErrors();
    const jump = control => {
      control.scrollIntoView({block:"center", inline:"nearest"});
      control.focus({preventScroll:true});
    };
    const form = primary[step]?.form;
    let first;
    for (const entry of entries) {
      if (typeof entry?.message !== "string") continue;
      const row = element("li", entry.message);
      const control = entry.control ?? enrollmentField(form, entry.path);
      if (control instanceof HTMLElement && !control.disabled && control.getClientRects().length) {
        const label = control.labels?.[0]?.textContent?.trim();
        row.replaceChildren(action(label ? label + " — " + entry.message : entry.message, () => jump(control)));
        control.setAttribute("aria-invalid", "true");
        marked.add(control);
        first ??= control;
      }
      errors.append(row);
    }
    feedback.textContent = errors.children.length ? "" : message;
    if (first) jump(first);
  }

  function select(name) {
    if (name !== step) {
      scroll.scrollTop = 0;
      clearErrors();
    }
    step = name;
    for (const tab of tabs) {
      const current = tab.dataset.enrollmentTab === step;
      if (current) tab.setAttribute("aria-current", "step");
      else tab.removeAttribute("aria-current");
    }
    for (const [name, panel] of Object.entries(sections)) panel.hidden = name !== step;
    submits.replaceChildren(...(primary[step] ? [primary[step]] : []));
  }

  function open() {
    if (!dialog.open) dialog.showModal();
    body.querySelector("section:not([hidden]) input")?.focus();
  }

  function dossierComplete() {
    return sections?.dossier.querySelector("form")?.matches(":valid");
  }

  for (const tab of tabs) tab.addEventListener("click", () => select(tab.dataset.enrollmentTab));
  trigger.addEventListener("click", open);
  dialog.addEventListener("invalid", event => {
    const form = primary[step]?.form;
    if (!form || event.target.form !== form) return;
    event.preventDefault();
    const invalid = [...form.querySelectorAll("input:invalid, select:invalid, textarea:invalid")];
    if (event.target === invalid[0]) {
      showErrors("", invalid.map(control => ({control, message:control.validationMessage})));
    }
  }, true);

  function update(state, inboxBonds) {
    trigger.hidden = !state.enrollment;
    if (!state.enrollment) {
      if (dialog.open) {
        dialog.close();
        document.querySelector('[data-folder="profile"]').click();
      }
      return false;
    }
    stage = state.stage;
    recordState.textContent = state.recovery_notice ? "CONFIRM FRAME RECORD" : stage === "profile" ? "CALLSIGN REQUIRED"
      : state.review.saved ? "AWAITING ACTIVATION"
      : state.review.ready ? "READY FOR REVIEW"
      : state.bonds.some(bond => !bond.incoming && bond.state === "pending") ? "COUNTERSIGNATURE PENDING"
      : "DRAFT";
    trigger.textContent = stage === "profile" && !state.recovery_notice ? "Create pilot" : "Resume enrollment";
    sections = Object.fromEntries(tabs.map(tab => [tab.dataset.enrollmentTab, element("section")]));
    for (const tab of tabs) tab.hidden = !((tab.dataset.enrollmentTab === "callsign") === (stage === "profile"));
    const heading = name => element("h3", name);
    sections.callsign.append(heading("Register callsign"));
    sections.dossier.append(heading("Pilot and Frame dossier"));
    sections.bond.append(heading("Starting Bond"));
    const file = element("div", undefined, "enrollment-identity");
    const personnel = element("div");
    personnel.append(element("h2", state.callsign || "Create pilot"));
    if (state.callsign) {
      const preview = element("figure", undefined, "enrollment-portrait");
      const choose = action("Select profile picture", () => {
        artwork.open("pilot", state.enrollment.owner_id, state.enrollment.portrait, state.callsign, updatePortrait);
      });
      choose.className = "link-button";
      choose.setAttribute("aria-haspopup", "dialog");
      function updatePortrait(id) {
        state.enrollment.portrait = id;
        choose.textContent = id ? "Change profile picture" : "Select profile picture";
        artwork.picture(preview, id);
      }
      updatePortrait(state.enrollment.portrait);
      file.append(preview);
      personnel.append(choose);
    }
    file.append(personnel);
    identity.replaceChildren(file);

    const refreshControl = action("Synchronize terminal", async () => {
      refreshControl.disabled = true;
      feedback.textContent = "Reading personnel record…";
      try {
        await refresh();
        feedback.textContent = "Personnel record current.";
      } catch (error) {
        feedback.textContent = error.message;
        refreshControl.disabled = false;
      }
    });
    const wizard = {sections};
    renderPlayerSetup(body, state, send, inboxBonds, wizard);
    sections.bond.append(refreshControl);
    primary = {};
    for (const [name, panel] of Object.entries(sections)) {
      const form = panel.querySelector("form");
      const submit = form?.querySelector(':scope > button[type="submit"]');
      if (submit) {
        form.id = "enrollment-" + name + "-form";
        submit.setAttribute("form", form.id);
        primary[name] = submit;
      }
    }
    if (wizard.reviewAction) primary.review = wizard.reviewAction;
    clearErrors();
    const next = pendingStep ?? step ?? (dossierComplete() ? "bond" : "dossier");
    pendingStep = null;
    select(stage === "profile" ? "callsign" : next === "callsign" ? "dossier" : next);
    if (!shown) {
      shown = true;
      open();
    }
    return true;
  }

  function saved(command) {
    if (command === "profile") pendingStep = "dossier";
    if (command === "build" && dossierComplete()) pendingStep = "bond";
    if (command === "select-bond") pendingStep = "review";
  }

  return {update, saved, open, clearErrors, showErrors};
}

export function renderPlayerSetup(target, state, send, bondTarget = target, wizard) {
  target.replaceChildren();
  if (bondTarget !== target) bondTarget.replaceChildren();
  if (state.stage === "handler") return;
  const sheet = element("article");
  target.append(sheet);
  if (state.stage === "active") {
    const scene = state.scene;
    if (!scene.joined) {
      sheet.append(action("Join scene", () => send("join-scene", {})));
    }
  } else {
    const callsignPanel = wizard?.sections.callsign ?? sheet;
    const buildPanel = wizard?.sections.dossier ?? sheet;
    const bondPanel = wizard?.sections.bond ?? sheet;
    const reviewPanel = wizard?.sections.review ?? sheet;
    if (state.handler_pilot_notice) (state.stage === "profile" ? callsignPanel : buildPanel).append(element("p",state.handler_pilot_notice,"terminal-notice"));
    if (wizard) sheet.append(...Object.values(wizard.sections));
    if (state.stage === "profile") {
      if (state.recovery_notice) callsignPanel.append(element("p",state.recovery_notice,"terminal-notice"));
      const profile = form(callsignPanel, "File callsign", values => send("profile", {
        revision: state.revision, callsign: values.get("callsign"),
        ...(state.options.girls ? {
          girl_playbook:values.get("girl_playbook"), frame_playbook:values.get("frame_playbook"),
        } : {}),
      }));
      input(profile, "callsign", "Callsign", state.callsign ?? "", 32);
      if (state.options.girls) {
        const girl = field(profile, "girl_playbook", "Girl playbook", state.options.girl, Object.entries(state.options.girls));
        const frame = field(profile, "frame_playbook", "Frame playbook", state.options.frame, Object.entries(state.options.frames));
        girl.required = frame.required = true;
      }
    } else {
      const {draft, options, review} = state;
      const girl = options.girl, frame = catalog.frame_rules_aliases[options.frame] ?? options.frame;
      const bonded = girl === "BONDED";
      const pairNames = state.enrollment?.pair_names ?? [];
      const details = structuredClone(draft);
      const extra = element("section");
      extra.dataset.enrollmentSpecialist = "";
      const build = form(buildPanel, "File enrollment draft", values => send("build", {
        revision: state.revision,
        character_revision: state.character_revision,
        ...(wizard ? {pair_token:draft.pair_source_token, shared_tokens:draft.shared_tokens} : {}),
        draft: {
          frame_name: values.get("frame_name"),
          girl_appearance: values.get("girl_appearance"),
          frame_appearance: values.get("frame_appearance"),
          girl_assets: bonded ? [] : assets(values, "girl"),
          frame_assets: assets(values, "frame"),
          void_asset: values.get("void_asset") || null,
          npc_bonds: [{
            slot: Number(values.get("npc_slot")),
            name: values.get("npc_name"),
            feelings: values.get("npc_feelings"),
          }, ...(values.get("npc_name2") ? [{
            slot:Number(values.get("npc_slot2")), name:values.get("npc_name2"),
            feelings:values.get("npc_feelings2"),
          }] : [])],
          ...(wizard ? {
            dna_basis:details.dna_basis,
            fanbase:details.fanbase,
            girl_details:details.girl_details,
            pair_asset_descriptions:pairNames.map((name, index) => ({
              name, description:values.get("pair_description_" + index) ?? "",
            })),
          } : {}),
          ...(girl === "NEWGIRL" ? {
            prior_missions:(state.enrollment?.cadre ?? []).flatMap(member => {
              const value = values.get("mission_" + member.id);
              return value ? [{user_id:member.id, character_revision:member.revision, missions:Number(value)}] : [];
            }),
            cadre_discussed:values.has("cadre_discussed"),
          } : {}),
        },
      }));
      // Required fields indicate when the dossier can advance. HarpyEngine reviews
      // completeness separately, so this form can file an unfinished draft.
      build.noValidate = true;
      input(build, "frame_name", "Frame name", draft.frame_name, 80);
      input(build, "girl_appearance", "Pilot appearance", draft.girl_appearance, 700);
      input(build, "frame_appearance", "Frame appearance", draft.frame_appearance, 700);
      if (!bonded) picks(build, "girl", "Pilot", options.girl_assets, draft.girl_assets);
      picks(build, "frame", "Frame", options.frame_assets, draft.frame_assets);
      if (bonded && !pairNames.length) build.insertBefore(element("p", "Your bonded counterpart selects your two source Assets. You then describe them here."), build.lastElementChild);
      for (const [index,name] of pairNames.entries()) {
        input(build,"pair_description_" + index,name + " description",
          draft.pair_asset_descriptions.find(item => item.name === name)?.description ?? "",700,false);
      }
      if (girl === "MOCKINGBIRD") {
      const voidAsset = field(build, "void_asset", "Void-altered pilot asset", draft.void_asset ?? "", [
        ["", "Choose one of your pilot assets"], ...options.girl_assets.map(value => [value, value]),
      ]);
      voidAsset.required = true;
      if (wizard) {
        const pilotAssets = ["girl0","girl1"].map(name => build.elements.namedItem(name));
        const listSelectedAssets = () => {
          const selected = voidAsset.value;
          const choices = [...new Set(pilotAssets.map(asset => asset.value).filter(Boolean))];
          voidAsset.replaceChildren(new Option("Choose one of your pilot assets", ""), ...choices.map(value => new Option(value, value)));
          voidAsset.value = choices.includes(selected) ? selected : "";
        };
        for (const asset of pilotAssets) asset.addEventListener("change", listSelectedAssets);
        listSelectedAssets();
      }
      }
      const npc = draft.npc_bonds[0];
      field(build, "npc_slot", "NPC Bond role", String(npc?.slot ?? 0),
        options.npc_roles.map((value, index) => [index, value]));
      input(build, "npc_name", "NPC name", npc?.name ?? "", 80, false);
      input(build, "npc_feelings", "Feelings about the NPC", npc?.feelings ?? "", 500, false);
      if (wizard) {
        const second = draft.npc_bonds[1];
        field(build, "npc_slot2", "Second NPC Bond role", String(second?.slot ?? (npc?.slot === 1 ? 0 : 1)),
          options.npc_roles.map((value,index) => [index,value]));
        input(build, "npc_name2", "Second NPC name", second?.name ?? "", 80, girl === "OLDGEN");
        input(build, "npc_feelings2", "Feelings about the second NPC", second?.feelings ?? "", 500, false);
        const renderSpecialized = () => {
          details.npc_bonds = ["","2"].filter(suffix => build.elements["npc_name" + suffix].value.trim())
            .map(suffix => ({slot:Number(build.elements["npc_slot" + suffix].value), name:build.elements["npc_name" + suffix].value}));
          extra.replaceChildren();
          renderPlaybookFields(extra, extra, girl, frame, details, (key,value) => { details[key] = value; },
            () => {}, renderSpecialized);
        };
        build.insertBefore(extra,build.lastElementChild);
        for (const name of ["npc_slot","npc_slot2","npc_name","npc_name2"]) {
          build.elements[name].addEventListener("change", renderSpecialized);
        }
        renderSpecialized();
        if (girl === "NEWGIRL") {
          const previous = new Map(draft.prior_missions.map(item => [String(item.user_id), item.missions]));
          for (const member of state.enrollment.cadre) {
            field(build,"mission_" + member.id,"Prior missions with " + member.callsign,
              previous.has(member.id) ? String(previous.get(member.id)) : "",
              [["","Choose"],["0","We’ve never had a mission together."],["1","We’ve had one mission together."]]);
          }
          const discussed = input(build,"cadre_discussed","I discussed this history with the current Cadre","",undefined,false);
          discussed.type = "checkbox";
          discussed.checked = draft.cadre_discussed;
        }
      }

      if (wizard) renderStartingBonds(bondPanel, state, send, true);
      if (state.bond_setup) {
        renderBondComposer(bondPanel, state.bond_setup, send);
      } else if (state.bond_target && !state.bonds.some(bond => !bond.incoming)) {
        const bond = form(bondPanel, "Propose starting Bond", values => send("bond", {
          source_revision: state.bond_target.source_revision,
          target_revision: state.bond_target.target_revision,
          prompt: Number(values.get("prompt")),
          context: values.get("context"),
        }));
        field(bond, "prompt", "Bond with invited pilot", "0",
          options.bond_prompts.map((value, index) => [index, value]));
        input(bond, "context", "Bond context", "", 500, false);
      }
      if (state.bot_enrollment) {
        const bot = state.bot_enrollment;
        const terminal = element("section",undefined,"record-card terminal-panel");
        terminal.append(element("h3","Foundation / Handler enrollment"),
          element("p",bot.status,"eyebrow"),element("p",bot.description));
        if (review.status) terminal.append(element("p","Status filed · " + review.status));
        for (const note of bot.notes ?? []) terminal.append(element("p",note));
        if (bot.pending_choices) terminal.append(element("p","COUNTERSIGNATURE PENDING · Open Enrollment assignments to accept or decline the Handler's proposal."));
        if (bot.can_request) {
          terminal.append(action("Request Handler setup",() => send("bot-enrollment",{character_revision:bot.character_revision,context:bot.context})));
          if (bot.declined_choices && !bot.pending_choices) terminal.append(action("Request another Handler offer",() => send("bot-enrollment",{character_revision:bot.character_revision,context:bot.context,retry_declined:true})));
        }
        reviewPanel.append(terminal);
      }
      reviewPanel.append(element("h3", "Activation review"));
      if (review.ready) {
        reviewPanel.append(element("p", "Assigned status · " + review.status));
        reviewPanel.append(element("p", "Starting identities · " + review.identities.join(", ")));
      }
      if (review.issues.length) {
        const issues = element("ul");
        for (const issue of review.issues) issues.append(element("li", issue));
        reviewPanel.append(issues);
      }
      if (review.ready) {
        const next = review.saved
          ? action("Activate pilot", () => send("activate", {fingerprint: review.fingerprint}))
          : action("File activation review", () => send("review", {
              revision: review.revision, fingerprint: review.fingerprint,
            }));
        if (wizard) wizard.reviewAction = next;
        else reviewPanel.append(next);
      }
    }
  }
  renderStartingBonds(bondTarget, {...state, bonds:[...state.bonds, ...(state.bond_history ?? [])]}, send);
}

export function startingBondStatus(bond, active) {
  if (bond.state === "accepted") return "Countersigned";
  if (bond.state === "declined") return "Declined";
  if (bond.state === "withdrawn") return "Withdrawn";
  if (!bond.incoming) return "Awaiting " + (bond.counterpart || "recipient countersignature");
  return active ? "Your response required" : "Your countersignature required";
}

function renderStartingBonds(bondTarget, state, send, emphasize = false) {
  if (!state.bonds.length) return;
  const records = element("div", undefined, "starting-bond-records");
  let next;
  for (const bond of state.bonds) {
    const record = element("article", undefined, "starting-bond-record");
    record.dataset.mailFile = "bond:" + bond.id;
    record.tabIndex = -1;
    const header = element("header");
    const controls = element("div", undefined, "actions");
    const direction = bond.incoming ? "Incoming starting Bond" : "Outgoing starting Bond";
    header.append(element("h3", bond.counterpart ? direction + " / " + bond.counterpart : direction),
      element("p", startingBondStatus(bond, state.stage === "active"), "eyebrow"));
    record.append(header);
    record.append(element("p", bond.prompt + (bond.context ? " · " + bond.context : "")));
    if (bond.incoming && bond.state === "pending") {
      const decisions = state.bond_setup && state.stage === "active" ? ["decline"] : ["accept", "decline"];
      for (const decision of decisions) {
        const control = action(decision === "accept" ? "Accept Bond" : "Decline Bond",
          () => send("bond-decision", {id: bond.id, revision: bond.revision, decision}));
        controls.append(control);
        if (decision === "accept") next ??= control;
      }
    }
    if (state.bond_setup && !bond.incoming && bond.state === "pending") {
      controls.append(action("Withdraw proposal", () => send("bond-decision", {
        id:bond.id, revision:bond.revision, decision:"withdraw",
      })));
    }
    if (state.select_starting_bond && bond.state === "accepted") {
      if (state.draft.starting_bond_id === bond.id) {
        record.append(element("p", "Primary Bond on file", "eyebrow"));
      } else {
        const use = action("Use as starting Bond", () => send("select-bond", {
          id:bond.id, revision:state.revision, character_revision:state.character_revision,
        }));
        controls.append(use);
        if (bond.incoming && !state.draft.starting_bond_id) next ??= use;
      }
    }
    if (controls.children.length) record.append(controls);
    records.append(record);
  }
  if (emphasize && next) next.className = "primary";
  bondTarget.append(records);
}

function renderBondComposer(target, setup, send) {
  const count = element("p", `Starting Bond slots · ${2 - setup.slots} / 2 in use`);
  count.className = "eyebrow";
  target.append(count, element("p", "Activation requires one confirmed starting Bond. A second Bond is optional."));
  if (!setup.slots) return;
  if (!setup.targets.length) {
    target.append(element("p", "No eligible pilots. A recipient must have a saved callsign, an available slot, and an unfinished enrollment."));
    return;
  }
  const outgoing = form(target, "Propose starting Bond", values => {
    const recipient = setup.targets.find(pilot => pilot.id === values.get("recipient"));
    if (!recipient) return;
    send("bond", {
      target:recipient.id,
      source_revision:setup.source_revision,
      target_revision:recipient.revision,
      prompt:Number(values.get("prompt")),
      context:values.get("context"),
    });
  });
  field(outgoing, "recipient", "Recipient", "", [
    ["", "Select a pilot"], ...setup.targets.map(pilot => [pilot.id, pilot.callsign]),
  ]).required = true;
  field(outgoing, "prompt", "Starting prompt", "0", setup.prompts.map((prompt, index) => [index,prompt]));
  input(outgoing, "context", "Bond context (optional)", "", 500, false);
}

export function renderPilotBondSetup(target, state, send) {
  if (!state.bond_setup) return;
  const panel = element("section");
  panel.className = "pilot-bond-panel";
  panel.append(element("h3", "Starting Bonds"));
  renderBondComposer(panel, state.bond_setup, send);
  renderStartingBonds(panel, state, send);
  target.append(popupAction("Starting Bonds",panel,"starting-bonds:" + state.mailbox));
}

const setupLabels = {
  court:"Red Queen Court assignment", callsign:"Mentor callsign",
  princess_peer:"Princess standard · bonded pilot", princess_handler:"Princess standard · Handler",
  vatgrown_handler:"Vatgrown investor desires · Handler",
};

export function renderEnrollmentChoices(target, work, send) {
  target.replaceChildren();
  if (!work) return;
  const submit = payload => send("creation-choice", payload);
  for (const request of work.requests) {
    const record = element("article", undefined, "record-card");
    record.dataset.setupRequest = request.id;
    record.tabIndex = -1;
    const choice = request.choice;
    const detail = choice.role || choice.callsign || choice.custom
      || work.standards[choice.slot] || choice.slots?.map(slot => work.desires[slot]).join(", ");
    record.append(element("h3",setupLabels[request.kind]), element("p", detail),
      element("p", request.state === "pending" ? "COUNTERSIGNATURE PENDING" : "COUNTERSIGNED","eyebrow"));
    for (const decision of request.decisions) {
      const label = {accept:"Countersign",decline:"Decline",withdraw:"Withdraw"}[decision];
      record.append(action(label, () => submit({
        operation:"decide", family:request.family, id:request.id, revision:request.revision, decision,
      })));
    }
    target.append(record);
  }
  for (const proposal of work.proposals) {
    const panel = element("section");
    panel.append(element("h3", setupLabels[proposal.kind] + " · " + proposal.callsign));
    const editor = form(panel, "File your choice", values => {
      const choice = proposal.kind === "court" ? {role:values.get("role")}
        : proposal.kind === "callsign" ? {callsign:values.get("callsign")}
        : proposal.kind === "vatgrown_handler" ? {slots:values.getAll("desires").map(Number)}
        : {slot:Number(values.get("standard")), custom:values.get("custom") ?? ""};
      submit({operation:"propose",kind:proposal.kind,target:proposal.target,context:proposal.context,choice});
    });
    if (proposal.kind === "court") {
      offDutySelect(editor,"role","Choose an external Court role",work.roles.map(role => [role,role]),{required:true});
    } else if (proposal.kind === "callsign") {
      input(editor,"callsign","Mentor-assigned callsign","",32);
    } else if (proposal.kind === "vatgrown_handler") {
      offDutySelect(editor,"desires","Choose one or two investor desires",work.desires.map((name,i) => [i,name]),{required:true,multiple:true});
    } else {
      const standard = offDutySelect(editor,"standard","Standard",work.standards.map((name,i) => [i,name]),{required:true});
      const custom = input(editor,"custom","Custom standard","",160,false);
      const sync = () => toggleField(custom,standard.value === "9");
      standard.addEventListener("change",sync);
      sync();
    }
    target.append(panel);
  }
  for (const pair of work.pairs) {
    const panel = element("section");
    panel.append(element("h3","Choose Pair Assets · " + pair.callsign));
    const editor = form(panel,"File Pair selections",values => submit({
      operation:"pair", id:pair.bond_id, revision:pair.revision, bond_revision:pair.bond_revision,
      choice:{names:[values.get("first"),values.get("second")]},
    }));
    const choices = [["","Choose an Asset"], ...work.pair_assets.map(name => [name,name])];
    field(editor,"first","First Girl Asset",pair.names[0] ?? "",choices).required = true;
    field(editor,"second","Second Girl Asset",pair.names[1] ?? "",choices).required = true;
    target.append(panel);
  }
  if (work.mentors.length) {
    const panel = element("section");
    panel.append(element("h3","Assign a Mentor"));
    const editor = form(panel,"File Mentor assignment",values => {
      const chosen = key => {
        const role = work.mentors.find(item => item.id === values.get(key));
        return {user_id:role.id,character_revision:role.revision};
      };
      submit({operation:"mentor",revision:work.handler_revision,newgirl:chosen("newgirl"),mentor:chosen("mentor")});
    });
    offDutySelect(editor,"newgirl","Newgirl",work.mentors.filter(item => item.newgirl).map(item => [item.id,item.callsign]),{required:true});
    offDutySelect(editor,"mentor","Mentor",work.mentors.map(item => [item.id,item.callsign]),{required:true});
    target.append(panel);
  }
  if (!target.children.length) target.append(element("p","No enrollment choices are assigned to you."));
}
