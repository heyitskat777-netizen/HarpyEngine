import {facilityLabels, markTerrain, playCard, playRail, renderRecordMetadata, sheetPlayCaption, terrainNames} from "/foundation-ui.js";
import {closePopup, popupAction, renderDraftDialog, showSelectionText} from "/popup-ui.js";
import {renderRiskChoice, renderTagDecision} from "/player-setup.js";

const orderChoices = new Set(["order_response", "order_disobey"]);
const tagChoices = new Set(["tag_window", "tag_resolution", "tag_marker_selection", "tag_marker_agreement",
  "actor_tag_selection", "actor_tag_agreement"]);
const encounterCommands = new Set(["open", "join", "place", "review-placement",
  "create-enemy", "add-enemy", "start-turns", "end-turn", "close-turns", "choice", "assault-review", "core-review", "disobey_orders", "frame-work"]);

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function label(text, control) {
  const wrapper = node("label", text, "field");
  control.setAttribute("aria-label", text);
  wrapper.append(control);
  if (control.tagName === "SELECT") showSelectionText(control,wrapper);
  return wrapper;
}

function select(options, placeholder) {
  const control = node("select");
  const empty = node("option", placeholder);
  empty.value = "";
  control.append(empty);
  for (const [value, name] of options) {
    const option = node("option", name);
    option.value = value;
    control.append(option);
  }
  control.required = true;
  return control;
}

function word(id) {
  return id.replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
}

function playTitle(id) {
  return {all_out_assault:"All-Out Assault", go_for_the_core:"Go for the Core", keep_your_head:"Keep Your Head", check_sensors:"Check Sensors", receive_orders:"Receive Orders", disobey_orders:"Disobey Orders", living_battery:"Living Battery", put_someone_beneath_you:"Put Someone Beneath You"}[id] ?? word(id);
}

function rollText(play) {
  return `Roll ${play.receipt.faces.join(" + ")} · Total ${play.result?.total ?? play.receipt.pre_total}`;
}

function account(title) {
  const input = node("textarea");
  input.maxLength = 1200;
  input.required = true;
  return [label(title, input), input];
}

export function tacticalUI(read, send, updateRoster, openPilot, renderFrameWork) {
  const root = document.getElementById("tactical-panel");
  const board = document.getElementById("tactical-grid");
  const controls = document.getElementById("tactical-controls");
  const toolbar = document.getElementById("tactical-toolbar");
  const turnStrip = document.getElementById("tactical-turn-strip");
  const playRecord = document.getElementById("tactical-action-record");
  const receipt = document.getElementById("tactical-receipt");
  const feedback = document.getElementById("tactical-status");
  const menu = document.getElementById("tactical-play-dialog");
  const playDialog = document.getElementById("tactical-action-dialog");
  const playFields = document.getElementById("tactical-action-fields");
  const playFeedback = document.getElementById("tactical-action-status");
  const menuOptions = document.getElementById("tactical-play-options");
  const menuRoster = document.getElementById("tactical-play-roster");
  const menuState = document.getElementById("tactical-play-state");
  let visible = false;
  let generation = 0;
  let timer;
  let working = false;
  let selection;
  let frameSelection;
  let destination;
  let target;
  let lastIntent;
  let state;
  function status(message) {
    feedback.textContent = message;
    playFeedback.textContent = message;
  }
  playDialog.addEventListener("close", () => {
    if (!playDialog.open && visible && state) render();
  });


  function poll() {
    clearTimeout(timer);
    if (visible && !working && (state?.shared || state?.busy) && !state.choices.length) {
      timer = setTimeout(() => reload(), 700);
    }
  }

  async function reload() {
    if (!visible) return;
    const pass = ++generation;
    try {
      let latest = await read();
      if (!visible || pass !== generation) return;
      const move = latest.actions.find(item => item.id === "move");
      if (selection === "move" && move) {
        const previous = state?.actions.find(item => item.id === "move");
        const sameTurn = latest.revision === state?.revision && latest.encounter?.turn === state?.encounter?.turn;
        if (sameTurn && previous?.range.cells && JSON.stringify(previous.actor) === JSON.stringify(move.actor)
          && previous.frame === move.frame) {
          move.range.cells = previous.range.cells;
        } else {
          latest = await read(true);
        }
      }
      if (!visible || pass !== generation) return;
      const changed = JSON.stringify(state) !== JSON.stringify(latest);
      if (menu.open && (state?.busy !== latest.busy || state?.encounter?.turn !== latest.encounter?.turn)) menu.close();
      if (playDialog.open && (state?.busy || state?.choices.length) && !latest.busy && !latest.choices.length) {
        playDialog.close();
      }
      state = latest;
      if (changed) {
        render();
        updateRoster(state.roster ?? [], state.title);
      }
      poll();
      return true;
    } catch (error) {
      if (visible && pass === generation) {
        status(error.message);
        poll();
      }
    }
  }

  function selectPlay(item) {
    selection = item.id;
    if (menu.open) menu.close();
    status("");
    if (!playDialog.open) playDialog.showModal();
    render();
    if (selection === "move") reload();
    playFields.querySelector("form :is(select, input, textarea, button)")?.focus();
  }

  async function submit(path, body) {
    if (working) return;
    working = true;
    clearTimeout(timer);
    const active = [root, playDialog, document.getElementById("utility-dialog")]
      .flatMap(group => [...group.querySelectorAll(":is(button, select, input, textarea):not(:disabled)")]);
    for (const element of active) element.disabled = true;
    if (state.encounter && !encounterCommands.has(path)) body = {...body, turn:state.encounter.turn};
    const payload = JSON.stringify([path, body]);
    if (lastIntent?.payload !== payload) {
      lastIntent = {payload, key:crypto.randomUUID()};
    }
    const old = state;
    status("Saving…");
    try {
      await send(path, body, lastIntent.key);
      status("");
      await reload();
      if (path === "move" && playDialog.open) playDialog.close();
      return true;
    } catch (error) {
      await reload();
      const current = state;
      const saved = current?.declarations?.[selection] ?? current?.declaration;
      const advanced = (["engage", "assault-roll", "core-roll", "check_sensors", "keep_your_head", "flirt", "fulfill", "living_battery", "put_someone_beneath_you"].includes(path) && current?.play?.id && current.play.id !== old?.play?.id)
        || (path === "issue-order" && current?.play?.play === "receive_orders" && current.play.id !== old?.play?.id)
        || (path === "disobey_orders" && current?.refusal?.id && current.refusal.id !== old?.refusal?.id)
        || (path.endsWith("-declare") && saved && saved.id !== (old?.declarations?.[selection] ?? old?.declaration)?.id)
        || (path.endsWith("-review") && saved?.id === body.id && saved.state === "confirmed")
        || (path === "core-expose" && current?.core_exposure_targets && !current.core_exposure_targets.some(actor => actor.id === body.target))
        || (path === "move" && current?.revision !== old?.revision && current?.actors.find(actor => actor.controlled)?.cell?.join() === body.destination.join())
        || (path === "choice" && current?.play?.id && current.play.id === old?.play?.id && !current.choices.some(choice => choice.id === body.id));
      status(advanced ? "" : error.message);
    } finally {
      working = false;
      for (const element of active) element.disabled = false;
      poll();
    }
  }

  function targetsFor(action) {
    return action.targets.map(item => [
      item.id, item.label + (item.separation == null ? "" : ` · ${item.separation} squares away`),
    ]);
  }

  function renderDeclaration(action, form, description, wrapped) {
    const core = action.id === "go_for_the_core";
    const command = core ? "core" : "assault";
    const draft = state.declarations?.[action.id] ?? (core ? null : state.declaration);
    if (draft) {
      renderBoard(null);
      form.append(node("p", draft.target + " · " + draft.account));
      if (draft.state === "confirmed") {
        const heatOptions = state.heat_options ?? [0];
        const heat = select(heatOptions.map(value => [value, String(value)]), "Select Heat");
        heat.value = String(heatOptions[0]);
        form.append(node("p", "Reach confirmed · " + draft.evidence));
        if (draft.learned_rider) form.append(node("p", draft.learned_rider));
        form.append(label("Heat to spend", heat));
        form.append(node("button", "Roll " + action.label, "primary"));
        form.addEventListener("submit", event => {
          event.preventDefault();
          const body = {id:draft.id, sheet_revision:state.sheet_revision, heat:Number(heat.value)};
          submit(command + "-roll", body);
        });
      } else if (state.encounter) {
        form.append(node("p", "Awaiting the Handler’s review of the opening and reach."));
      } else {
        const opening = node("input");
        const reach = node("input");
        const capability = node("input");
        for (const box of [opening, reach]) {
          box.type = "checkbox";
          box.required = true;
        }
        capability.type = "checkbox";
        capability.required = true;
        const [evidenceLabel, evidence] = account("Evidence of opening and reach");
        form.append(
          node("h3", "Test Handler review"),
          label("Confirm the opening", opening),
          label("Confirm the attack can reach", reach),
        );
        if (draft.damaged_weapon) form.append(label("Confirm the damaged Asset can strike the Core", capability));
        form.append(evidenceLabel, node("button", core ? "Confirm Core declaration" : "Confirm assault declaration", "primary"));
        form.addEventListener("submit", event => {
          event.preventDefault();
          const body = {id:draft.id, revision:state.revision, opening:opening.checked, reach:reach.checked, evidence:evidence.value};
          if (core) body.capability = capability.checked;
          submit(command + "-review", body);
        });
      }
      return;
    }
    const opponent = select(targetsFor(action), "Select a target");
    const weapon = select(action.attacking_assets.map(asset => [asset.id, asset.name + (asset.damaged ? " · Damaged" : "")]), "Select an attacking Asset");
    let opposingAsset = select([], "Select an opposing Asset");
    const opposingAssetField = label("Opposing Asset", opposingAsset);
    function updateTarget() {
      target = opponent.value;
      const assets = action.targets.find(entry => entry.id === target)?.assets ?? [];
      const replacement = select(assets.map(asset => [asset.id, asset.name]), "Select an opposing Asset");
      replacement.setAttribute("aria-label", "Opposing Asset");
      opposingAsset.replaceWith(replacement);
      opposingAsset = replacement;
    }
    if (action.targets.some(item => item.id === target)) opponent.value = target;
    updateTarget();
    opponent.addEventListener("change", updateTarget);
    form.append(label("Target", opponent), label("Attacking Asset", weapon));
    if (!core) form.append(opposingAssetField);
    form.append(wrapped, node("button", core ? "Declare Core strike" : "Declare assault", "primary"));
    form.addEventListener("submit", event => {
      event.preventDefault();
      const body = {
        revision:state.revision, target:opponent.value,
        attacking_asset:weapon.value, account:description.value,
      };
      if (!core) body.target_asset = opposingAsset.value;
      submit(command + "-declare", body);
    });
    renderBoard(action, opponent);
  }

  function renderBoard(action, selectCell) {
    board.hidden = !state.board;
    document.getElementById("tactical-map-key").hidden = !state.facility || !state.board;
    if (!state.board) {
      board.replaceChildren();
      return;
    }
    const [minX, minY] = state.board.minimum;
    const [maxX, maxY] = state.board.maximum;
    board.style.setProperty("--columns", maxX - minX + 1);
    board.toggleAttribute("data-facility", Boolean(state.facility));
    const destinations = action?.id === "move" && action.range.cells
      ? new Set(action.range.cells.map(cell => cell.join(","))) : null;
    const cells = [];
    for (let y = minY; y <= maxY; y++) {
      for (let x = minX; x <= maxX; x++) {
        const cell = [x, y];
        const here = state.actors.filter(actor => actor.cell?.join() === cell.join());
        const place = state.locations.find(location => location.cell.join() === cell.join());
        const validActor = here.find(actor => action?.targets?.some(entry => entry.id === actor.id));
        const currentActor = here.some(actor => actor.id === state.encounter?.active_id);
        const square = node("div", undefined, "tactical-square");
        const tile = node("button", undefined, "tactical-cell");
        tile.type = "button";
        tile.dataset.coordinate = cell.join(",");
        const row = state.facility?.floor[y - minY];
        if (row) {
          square.style.gridArea = `${y - minY + 1} / ${x - minX + 1}`;
          markTerrain(tile, row, x - minX);
        }
        if (place) tile.dataset.location = place.kind;
        const terrain = row?.[x - minX];
        const reachable = destinations?.has(cell.join(","));
        const canMoveHere = destinations ? reachable : action?.id === "move" && action.range.kind === "board" && terrain !== "w";
        tile.disabled = !(canMoveHere || validActor);
        tile.toggleAttribute("data-active-unit", currentActor);
        tile.toggleAttribute("data-reachable", Boolean(reachable));
        tile.toggleAttribute("data-valid-target", Boolean(validActor));
        tile.setAttribute("aria-label", ["Cell " + x + ", " + y, terrain !== "." && terrainNames[terrain],
          place?.name, ...here.map(actor => actor.label), currentActor && "Active unit",
          reachable && "Reachable", validActor && "Valid target"].filter(Boolean).join(" · "));
        if (action?.id === "move" && destination?.join() === cell.join() || validActor && target === validActor.id) {
          tile.setAttribute("aria-pressed", "true");
        }
        tile.append(node("span", `${x}, ${y}`, "cell-coordinate"));
        if (place) tile.append(node("span", place.name, "cell-location"));
        tile.addEventListener("click", () => {
          if (validActor) {
            target = validActor.id;
            if (selectCell) {
              selectCell.value = target;
              selectCell.dispatchEvent(new Event("change"));
            }
          } else {
            destination = cell;
            if (selectCell) selectCell.textContent = `Destination · ${x}, ${y}`;
          }
          for (const marked of board.querySelectorAll("[aria-pressed]")) marked.removeAttribute("aria-pressed");
          tile.setAttribute("aria-pressed", "true");
          if (action?.id === "move" && !playDialog.open) selectPlay(action);
        });
        square.append(tile);
        const tokens = node("div", undefined, "tactical-tokens");
        for (const actor of here) {
          const isPilot = !state.encounter?.handler && state.roster?.some(entry => entry.id === actor.id);
          const token = node(isPilot ? "button" : "strong", actor.label, actor.enemy || !actor.controlled ? "opponent-token" : "pilot-token");
          if (isPilot) {
            token.type = "button";
            token.setAttribute("aria-label", "Open pilot file for " + actor.label);
            token.addEventListener("click", () => openPilot(actor.id));
          }
          if (actor.core_exposed) token.append(node("small", " · Core exposed"));
          tokens.append(token);
        }
        if (tokens.childElementCount) square.append(tokens);
        cells.push(square);
      }
    }
    board.replaceChildren(...cells, ...facilityLabels(state.facility?.rooms ?? []));
  }

  function renderAction(action, panel = controls) {
    if (!action) {
      renderBoard(null);
      return;
    }
    const form = node("form");
    form.append(node("p", action.range.label));
    if (action.range.kind === "followup") {
      const [wrapped, description] = account("Describe what your pilot does");
      form.append(wrapped, node("button", "Record follow-through", "primary"));
      form.addEventListener("submit", event => {
        event.preventDefault();
        submit("fulfill", {id:action.obligation, account:description.value});
      });
      renderBoard(null);
      panel.append(form);
      return;
    }
    if (action.range.kind === "order") {
      renderOrder(action, form);
      renderBoard(null);
      panel.append(form);
      return;
    }
    const [wrapped, description] = account(action.trigger || "Describe the movement");
    const button = node("button", action.id === "move" ? "Confirm move" : "Roll " + action.label, "primary");
    if (action.id === "move") {
      const cell = node("p", destination ? "Destination · " + destination.join(", ") : "Select a destination on the grid.");
      form.append(cell, wrapped, button);
      form.addEventListener("submit", event => {
        event.preventDefault();
        if (!destination) {
          feedback.textContent = "Select a destination on the grid.";
          return;
        }
        submit(action.id, {actor:action.actor, frame:action.frame, revision:state.revision, destination, account:description.value});
      });
      renderBoard(action, cell);
    } else if (action.range.kind === "adjudicated") {
      renderDeclaration(action, form, description, wrapped);
    } else if (!action.targets) {
      form.append(wrapped, button);
      form.addEventListener("submit", event => {
        event.preventDefault();
        submit(action.id, {account:description.value, sheet_revision:state.sheet_revision, confirmed:true});
      });
      renderBoard(null);
    } else {
      const opponent = select(targetsFor(action), "Select a target");
      if (action.targets.some(item => item.id === target)) opponent.value = target;
      form.append(label("Target", opponent));
      const beneath = action.id === "put_someone_beneath_you";
      const heat = beneath ? select(state.heat_options.map(value => [value, String(value)]), "Select Heat") : null;
      if (heat) {
        heat.value = String(state.heat_options[0]);
        form.append(label("Heat to spend", heat));
      }
      form.append(wrapped, button);
      form.addEventListener("submit", event => {
        event.preventDefault();
        const selected = action.targets.find(item => item.id === opponent.value);
        if (!selected) return;
        const payload = {target:selected.owner ?? selected.ref, account:description.value, sheet_revision:state.sheet_revision, confirmed:true};
        if (heat) payload.heat = Number(heat.value);
        submit(action.id, payload);
      });
      renderBoard(action, opponent);
    }
    panel.append(form);
  }

  function renderOrder(action, form) {
    const {text, choice} = action.order;
    form.append(node("blockquote", text, "direct-order"));
    if (action.id === "receive_orders") {
      const answer = renderFields(form, choice.schema);
      form.append(node("button", "File order response", "primary"));
      form.addEventListener("submit", event => {
        event.preventDefault();
        submit("choice", {role:choice.role, id:choice.id, revision:choice.revision, answer:answer()});
      });
      return;
    }
    const [descriptionLabel, description] = account("Describe the refusal");
    const heat = select(state.heat_options.map(value => [value, String(value)]), "Select Heat");
    heat.value = String(state.heat_options[0]);
    const witnessed = select([["yes", "Yes"], ["no", "No"]], "Select a witness status");
    form.append(
      descriptionLabel, label("Heat to spend", heat), label("Did a Foundation member witness the refusal?", witnessed),
      node("button", "Roll Disobey Orders", "primary"),
    );
    form.addEventListener("submit", event => {
      event.preventDefault();
      submit(action.id, {
        choice:choice.id, revision:choice.revision, sheet_revision:state.sheet_revision,
        account:description.value, heat:Number(heat.value), witnessed:witnessed.value === "yes", confirmed:true,
      });
    });
  }

  function renderFields(form, schema, questions = [], jsonFields = [], commaSeparatedFields = []) {
    const controls = schema.map(field => {
      let input;
      if (field.paragraph) {
        input = node("textarea");
        input.maxLength = 1200;
      } else {
        input = select(field.options, "Select an option");
        if (field.maximum > 1) {
          input.multiple = true;
          input.firstElementChild.remove();
        }
      }
      input.required = field.required;
      const question = /^fields\.a(\d+)$/.exec(field.key);
      form.append(label(question ? questions[Number(question[1]) - 1] ?? field.label : field.label, input));
      return {field, input};
    });
    return () => {
      const answer = {};
      for (const {field, input} of controls) {
        const value = field.paragraph ? input.value.trim()
          : [...input.selectedOptions].map(option => option.value).filter(Boolean);
        if (field.paragraph ? !value : !value.length) continue;
        if (field.key.startsWith("fields.")) {
          (answer.fields ??= {})[field.key.slice(7)] = jsonFields.includes(field.key)
            ? JSON.stringify(value)
            : commaSeparatedFields.includes(field.key) ? value.join(",") : field.paragraph ? value : value[0];
        } else if (field.key === "flag") {
          answer.flag = value[0] === "yes";
        } else if (field.key === "number") {
          answer.number = Number(value[0]);
        } else if (field.key === "member") {
          answer.member = value[0];
        } else if (field.key === "beneath_extra") {
          answer.options = [...answer.options, ...value];
        } else {
          answer[field.key] = value;
        }
      }
      return answer;
    };
  }

  function handlerForm(form, fields) {
    const play = select(fields.plays.map(item => [item.id, item.label]), "Select a Handler Play");
    const [wrapped, note] = account("Handler’s briefing");
    const [describeLabel, describe] = account("Describe the threat or expectation");
    const [stakesLabel, stakes] = account("State the stakes or consequence");
    function sync() {
      const expanded = Boolean(play.value && play.value !== "brief");
      describeLabel.hidden = stakesLabel.hidden = !expanded;
      describe.disabled = stakes.disabled = !expanded;
    }
    if (fields.plays.some(item => item.id === "brief")) play.value = "brief";
    play.addEventListener("change", sync);
    sync();
    form.append(label("Handler Play", play), wrapped, describeLabel, stakesLabel);
    return () => ({
      play:play.value, account:note.value, game_revision:fields.game_revision,
      ...(play.value === "brief" ? {} : {detail:describe.value, stakes:stakes.value}),
    });
  }

  function renderChoice(choice, panel = controls) {
    const roles = {pilot:"Pilot", handler:state.encounter ? "Handler" : "Test Handler", opponent:"Drill opponent"};
    const body = node("article");
    body.dataset.role = choice.role;
    const save = answer => submit("choice", {role:choice.role, id:choice.id, revision:choice.revision, answer});
    if (tagChoices.has(choice.kind)) {
      renderTagDecision(body, choice, save, roles[choice.role]);
    } else if (choice.risk_operations) {
      renderRiskChoice(body, choice, save);
    } else if (["engage_maneuvers","engage_assault_extra"].includes(choice.kind)) {
      const form = node("form");
      const data = choice.fields;
      const extra = choice.kind === "engage_assault_extra";
      body.append(node("h3", extra ? "Optional earned maneuver" : "Choose maneuvers"));
      if (choice.prompt) body.append(node("p", choice.prompt));
      const assets = data.assets.map(asset => [asset.id, asset.label]);
      const maneuvers = data.maneuvers.map(id => [id, word(id)]);
      const slots = Array.from({length:extra ? data.maximum : data.minimum}, (_, index) => {
        const maneuver = select(maneuvers, extra ? "Decline the extra maneuver" : "Select a maneuver");
        const asset = select(assets, "Select an Asset");
        form.append(label("Maneuver " + (index + 1), maneuver), label("Asset for maneuver " + (index + 1), asset));
        if (extra) {
          maneuver.required = false;
          const sync = () => { asset.disabled = !maneuver.value; };
          maneuver.addEventListener("change", sync);
          sync();
        }
        return {maneuver, asset};
      });
      const damage = data.damage ? select(assets, "Select a used Asset") : null;
      if (damage) form.append(label("Damage a used Asset", damage));
      const vehicle = data.wyvern_vehicles?.length
        ? select(data.wyvern_vehicles.map(item => [item.id, item.label]), "Use the opposing Sprite") : null;
      if (vehicle) {
        vehicle.required = false;
        const target = label("Crushing Bulk vehicle", vehicle);
        const showVehicle = () => {
          target.hidden = !slots.some(slot => slot.maneuver.value === "crush_small");
          if (target.hidden) vehicle.value = "";
        };
        for (const slot of slots) slot.maneuver.addEventListener("change", showVehicle);
        form.append(target);
        showVehicle();
      }
      const [wrapped, description] = account("Resulting circumstances");
      if (extra) description.required = false;
      form.append(wrapped, node("button", extra ? "File earned maneuver" : "Resolve Engage", "primary"));
      form.addEventListener("submit", event => {
        event.preventDefault();
        const selected = slots.filter(slot => slot.maneuver.value);
        save({
          options:selected.map(slot => slot.maneuver.value),
          fields:{...Object.fromEntries(selected.map(slot => [slot.maneuver.value, slot.asset.value])),
            ...(vehicle?.value ? {wyvern_vehicle:vehicle.value} : {})},
          denied:damage ? [damage.value] : [],
          text:description.value,
        });
      });
      body.append(form);
    } else if (choice.kind === "beneath_punishment" && choice.fields?.options.length) {
      const form = node("form");
      const {fields} = choice;
      const punishment = select(fields.options, "Choose an assigned Punishment");
      const [wrapped, tag] = account("Inflicted Tag");
      tag.maxLength = 120;
      const sync = () => {
        wrapped.hidden = tag.disabled = punishment.value !== "quality_time";
      };
      punishment.addEventListener("change", sync);
      sync();
      form.append(label("Punishment", punishment), wrapped, node("button", "Apply assigned Punishment", "primary"));
      form.addEventListener("submit", event => {
        event.preventDefault();
        save({
          kind:punishment.value, tag:tag.disabled ? "" : tag.value,
          revision:fields.revision, game_revision:fields.game_revision,
        });
      });
      body.append(node("h3", "Assigned discipline · " + fields.subject), form);
    } else if (["beneath_defeat", "battle_defeat"].includes(choice.kind)) {
      const form = node("form");
      const [wrapped, note] = account("Describe the actual Defeat");
      form.append(wrapped, node("button", "Roll Defeat", "primary"));
      form.addEventListener("submit", event => {
        event.preventDefault();
        save(choice.kind === "battle_defeat" ? {account:note.value}
          : {account:note.value, sheet_revision:choice.fields.sheet_revision});
      });
      body.append(node("h3", "Required Defeat"), node("p", "Your last usable Frame Asset was damaged. Roll with +1 per undamaged Girl Asset."), form);
    } else if (["escape_play", "beneath_response_play"].includes(choice.kind) || (choice.kind === "handler_brief" && choice.fields)) {
      const form = node("form");
      const escape = choice.kind !== "handler_brief";
      let answer;
      if (escape) {
        const [wrapped, note] = account("Describe how you keep your head");
        form.append(wrapped);
        answer = () => ({play:"keep_your_head", account:note.value, sheet_revision:choice.fields.sheet_revision});
      } else {
        answer = handlerForm(form, choice.fields);
      }
      form.append(node("button", escape ? "Roll Keep Your Head" : "File Handler Play", "primary"));
      form.addEventListener("submit", event => {
        event.preventDefault();
        save(answer());
      });
      body.append(node("h3", escape ? "Response · Keep Your Head" : roles[choice.role] + " · Required Play"), form);
    } else if (choice.schema) {
      const form = node("form");
      const battery = {janus_erase:"Record the Tag result",janus_select:"File battery benefits",janus_answer:"File private response"}[choice.kind];
      const defeat = {defeat_select:"File Defeat consequences", defeat_tag_gift:"File Tag decision", defeat_alternative:"Send Handler offer", defeat_accept_alternative:"File your response to the offer"}[choice.kind];
      const alternative = choice.kind === "defeat_alternative";
      const answer = renderFields(form, choice.schema, choice.questions, battery ? ["fields.identities"] : [], alternative ? ["fields.assets","fields.identities"] : []);
      const ask = choice.kind === "actor_sensors";
      const keep = ["actor_keep", "handler_keep"].includes(choice.kind);
      const refusal = choice.kind.endsWith("_disobey");
      const flirtTitle = {actor_flirt:"Choose a question", target_flirt:"Answer the question", actor_flirt_answer:"Answer the return question", flirt_escape:"Choose a way out", flirt_owe_tag:"Record a Tag", handler_brief:"File Handler brief", followthrough_confirm:"File follow-through decision"}[choice.kind];
      const beneath = {beneath_select:"File confrontation effects", beneath_details:"File your private choice", beneath_pin_response:"File your response"}[choice.kind];
      form.append(node("button", defeat ?? beneath ?? battery ?? flirtTitle ?? (refusal ? "File refusal choice" : keep ? "File Keep Your Head choice" : ask ? "Send sensor questions" : "File sensor answers"), "primary"));
      form.addEventListener("submit", event => {
        event.preventDefault();
        save(answer());
      });
      body.append(node("h3", defeat ? "Defeat · " + defeat : beneath ? "Put Someone Beneath You · " + beneath : battery ? "Living Battery · " + battery : flirtTitle ? "Flirt · " + flirtTitle : refusal ? roles[choice.role] + " · Disobey Orders" : keep ? roles[choice.role] + " · Keep Your Head" : ask ? "Choose sensor questions" : roles[choice.role] + " · Answer sensor questions"));
      if (choice.prompt) body.append(node("p", choice.prompt));
      if (choice.offer) {
        const offer = choice.offer;
        const effects = [
          "Permissions removed · " + offer.permissions,
          offer.assets.length ? "Assets removed · " + offer.assets.join(", ") : null,
          offer.identities.length ? "Identities removed · " + offer.identities.join(", ") : null,
          offer.tag ? "Inflicted Tag · " + offer.tag : null,
          typeof offer.outside_frame === "boolean" ? "Girl Asset loss · " + (offer.outside_frame ? "Outside a Frame" : "Inside a Frame") : null,
          offer.foe ? "Helpless before · " + offer.foe : null,
        ].filter(Boolean);
        body.append(node("p", offer.account), ...effects.map(effect => node("p", effect)));
      }
      body.append(form);
    } else if (choice.kind.startsWith("battle_")) {
      const form = node("form");
      const {fields} = choice;
      const heading = node("h3", roles[choice.role] + " · " + word(choice.kind.replace("battle_", "")));
      body.append(heading, form);
      let answer;
      if (choice.kind === "battle_assault_table") {
        const vote = select([["yes","Yes"],["no","No"]], "Select a ruling");
        const [wrapped, explanation] = account("Explain the table ruling");
        form.append(label("Vast advantage", vote), wrapped);
        answer = () => ({flag:vote.value === "yes", text:explanation.value});
      } else if (["battle_low_damage", "battle_actor_damage", "battle_target_damage"].includes(choice.kind)) {
        const asset = select(fields.assets.map(item => [item.id, item.name]), "Select an Asset");
        form.append(label("Asset to damage", asset));
        answer = () => ({fields:{asset:asset.value}});
      } else if (choice.kind === "battle_handler") {
        const consequence = select(fields.options.map(id => [id, word(id)]), "Select a consequence");
        const extra = select(fields.options.map(id => [id, word(id)]), "No second consequence");
        extra.required = false;
        const [wrapped, accountText] = account("What would be destroyed by collateral damage?");
        accountText.required = false;
        form.append(label("Handler consequence", consequence), label("Second consequence", extra), wrapped);
        answer = () => ({options:[consequence.value, extra.value].filter(Boolean), text:accountText.value});
      } else if (choice.kind === "battle_collateral") {
        const [objectLabel, object] = account("Concrete collateral");
        const [effectLabel, effect] = account("Resulting damage");
        const [reachLabel, reach] = account("How the attack reached it");
        form.append(objectLabel, effectLabel, reachLabel);
        answer = () => ({
          revision:fields.revision, game_revision:fields.game_revision,
          ordinary:object.value, account:effect.value, reach:reach.value,
        });
      } else if (choice.kind === "battle_handler_play" && fields.plays.length) {
        answer = handlerForm(form, fields);
      } else if (choice.kind === "battle_counter") {
        const names = {
          damage_actor_asset:"Damage an attacker Asset",
          make_play_against_actor:"Make a Play against the attacker",
          actor_helpless:"Make the attacker helpless",
          target_dies_with_handler_play:"Make a final Handler Play and die",
        };
        const counters = fields.options.map(id => [id, names[id] ?? word(id)]);
        const first = select([["pass","Decline all counters"], ...counters], "Select a counter");
        const second = select(counters, "No second counter");
        second.required = false;
        second.disabled = true;
        first.addEventListener("change", () => {
          second.disabled = !first.value || first.value === "pass";
          if (second.disabled) second.value = "";
        });
        form.append(label("Core counter", first));
        if (fields.maximum > 1) form.append(label("Second Core counter", second));
        answer = () => first.value === "pass" ? {flag:false} : {options:[first.value, second.value].filter(Boolean)};
      } else if (choice.kind === "battle_counter_play") {
        const play = select(fields.plays.map(item => [item.id, item.label]), "Select a counter Play");
        const [wrapped, note] = account("Describe the counter Play");
        form.append(label("Counter Play", play), wrapped);
        answer = () => ({play:play.value, account:note.value, sheet_revision:fields.sheet_revision});
      }
      if (answer) {
        form.append(node("button", "File " + word(choice.kind.replace("battle_", "")).toLowerCase(), "primary"));
        form.addEventListener("submit", event => {
          event.preventDefault();
          save(answer());
        });
      }
    } else {
      body.append(node("p", roles[choice.role] + " has a pending " + word(choice.kind) + " choice."));
    }
    panel.append(body);
  }

  function encounterForm(title, command, fields, payload, source = state.encounter?.turn ?? state.title) {
    const form = node("form", undefined, "record-card encounter-form");
    form.append(node("h4", title), ...fields);
    const save = node("button", title, "primary");
    save.type = "submit";
    form.append(save);
    const key = "encounter:" + command + ":" + title + ":" + source;
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (await submit(command, payload(new FormData(form)))) closePopup(key);
    });
    controls.append(popupAction(title,form,key));
  }

  function encounterField(name, text, input) {
    input.name = name;
    input.required = true;
    return label(text, input);
  }

  function coordinateFields() {
    return [0, 1].map(axis => {
      const control = node("input");
      control.type = "number";
      control.min = state.board.minimum[axis];
      control.max = state.board.maximum[axis];
      control.value = control.min;
      return control;
    });
  }

  function renderEncounter(encounter) {
    const dispatch = (text, command, data = {revision:state.revision}) => {
      const control = node("button", text);
      control.type = "button";
      control.addEventListener("click", () => submit(command, data));
      toolbar.append(control);
    };
    const status = encounter.running
      ? encounter.active ? `Round ${encounter.round} · ${encounter.active}${encounter.enemy_turn ? " · Enemy turn" : encounter.yours ? " · Your turn" : " · Active pilot"}`
        : "No pilots remain in the current turn order"
      : encounter.placement_pending ? "Awaiting placement review"
        : encounter.joined ? "Preparing encounter" : encounter.can_join ? "Admission open" : "Admission pending";
    turnStrip.hidden = false;
    turnStrip.textContent = status;
    turnStrip.toggleAttribute("data-your-turn", Boolean(encounter.yours && encounter.running));
    if (encounter.running) {
      if (encounter.can_end_turn) dispatch("End turn", "end-turn");
      if (encounter.can_close) dispatch("Close turns", "close-turns");
      if (encounter.expose_core) {
        const confirmed = node("input");
        confirmed.type = "checkbox";
        encounterForm("Expose my Core", "core-expose", [
          encounterField("account","Describe exposing your Core",node("textarea")),
          encounterField("confirmed","I confirm I am exposing my own Frame Core",confirmed),
        ], values => ({
          revision:state.revision, target:encounter.expose_core, confirmed:values.has("confirmed"), account:values.get("account"),
        }),encounter.expose_core);
      }
      for (const review of encounter.attack_reviews ?? []) {
        const core = review.play === "go_for_the_core";
        const checkbox = (name, text) => {
          const input = node("input");
          input.name = name;
          input.type = "checkbox";
          return label(text, input);
        };
        encounterForm("File " + review.label + " review", core ? "core-review" : "assault-review", [
          node("p", review.actor + " → " + review.target),
          node("p", review.account),
          checkbox("opening","Confirm the opening"),
          checkbox("reach","Confirm the attack can reach"),
          ...(core ? [checkbox("capability","Confirm the damaged Asset can strike the Core")] : []),
          encounterField("evidence","Evidence of opening and reach",node("textarea")),
        ], values => ({
          id:review.id, revision:state.revision, opening:values.has("opening"), reach:values.has("reach"),
          evidence:values.get("evidence"), ...(core ? {capability:values.has("capability")} : {}),
        }),review.id);
      }
      return;
    }
    if (encounter.can_open && encounter.facility_options?.length) {
      encounterForm("Open Battlefield", "open", [
        encounterField("facility","Facility plan",select(encounter.facility_options.map(site => [site.id,site.name]),"Select a facility")),
      ], values => ({revision:state.revision, facility:values.get("facility")}));
      return;
    }
    if (encounter.can_open && !encounter.has_world) {
      const locations = node("textarea");
      locations.value = "North Base\nCentral Base\nEast Base\nArcadia\nNew Edmonton\nM-96\nFirst Side\nChreston";
      const bases = select([["0","First base"],["1","Second base"],["2","Third base"]], "Select a base");
      encounterForm("Open Battlefield", "open", [
        node("p", "Set up the campaign’s 10 × 10 map. Class 0 details are visible to the Handler."),
        encounterField("locations","Three bases, two cities, and three important locations, one name per line",locations),
        encounterField("name","Private Class 0 name",node("input")),
        encounterField("type","Class 0 type",select(encounter.gorgon_types.map(kind => [kind,word(kind)]),"Choose a type")),
        encounterField("base","Class 0 starting base",bases),
        encounterField("assets","Two Class 0 Assets, one per line",node("textarea")),
        encounterField("weakness","Class 0 Core weakness",node("textarea")),
      ], values => ({
        revision:state.revision, name:values.get("name"), type:values.get("type"), base:Number(values.get("base")),
        locations:values.get("locations").split(/\r?\n/).map(value => value.trim()),
        assets:values.get("assets").split(/\r?\n/).map(value => value.trim()), weakness:values.get("weakness"),
      }));
      return;
    }
    if (encounter.can_open) dispatch("Open Battlefield", "open");
    if (encounter.can_join) dispatch("Enter Battlefield", "join", {});
    if (!encounter.joined) {
      controls.append(node("p", encounter.entry_blocker ?? (encounter.can_join
        ? "Entering moves your pilot from its current active scene."
        : "The Handler opens Battlefield admission when the map is ready.")));
      return;
    }
    if (encounter.can_add_enemies) {
      const [x, y] = coordinateFields();
      encounterForm("Create opposing NPC", "create-enemy", [
        encounterField("name","Enemy name",node("input")),
        encounterField("x","Enemy column (x)",x),
        encounterField("y","Enemy row (y)",y),
        encounterField("account","Describe the opposing NPC",node("textarea")),
      ], values => ({
        revision:state.revision, name:values.get("name"), cell:[Number(values.get("x")), Number(values.get("y"))], account:values.get("account"),
      }));
      if (encounter.enemies.length) {
        encounterForm("Deploy existing enemy", "add-enemy", [
          encounterField("target","Enemy",select(encounter.enemies.map(enemy => [enemy.id,enemy.label]),"Choose an enemy")),
        ], values => ({revision:state.revision,target:values.get("target")}));
      }
    }
    if (encounter.can_place) {
      const bounds = coordinateFields();
      encounterForm("Propose starting position", "place", [
        encounterField("x","Starting column (x)",bounds[0]),
        encounterField("y","Starting row (y)",bounds[1]),
        encounterField("mode","Pilot position",select([["piloting","Piloting"],["outside_frame","Outside Frame"]],"Choose a position")),
        encounterField("account","Describe the starting position",node("textarea")),
      ], values => ({
        revision:state.revision, cell:[Number(values.get("x")), Number(values.get("y"))],
        mode:values.get("mode"), account:values.get("account"),
      }));
    }
    if (encounter.placement_pending) controls.append(node("p", "Starting position awaiting Handler review."));
    for (const pending of encounter.reviews) {
      encounterForm("File position review", "review-placement", [
        node("p", `${pending.label} · ${pending.cell.join(", ")} · ${word(pending.mode)}`),
        node("p", pending.account),
        encounterField("decision","Position ruling",select([["accept","Approve position"],["decline","Decline position"]],"Choose a ruling")),
        encounterField("account","Position review notes",node("input")),
      ], values => ({id:pending.id, revision:pending.revision, decision:values.get("decision"), account:values.get("account")}),pending.id);
    }
    if (encounter.ready.length) controls.append(node("p", "Ready for turns · " + encounter.ready.join(", "), "encounter-status"));
    if (encounter.can_start) dispatch("Start turns", "start-turns");
  }

  function render() {
    renderDraftDialog(playDialog,JSON.stringify(["battlefield",selection,state?.revision,
      state?.play?.id,state?.choices.map(choice => [choice.id,choice.revision])]),renderContent);
  }

  function renderContent() {
    document.getElementById("tactical-title").textContent = state.title;
    const action = state.actions.find(item => item.id === selection)
      ?? state.actions.find(item => item.id === (Object.keys(state.declarations ?? {})[0] ?? (state.declaration ? "all_out_assault" : "move")));
    controls.replaceChildren();
    playFields.replaceChildren();
    toolbar.replaceChildren();
    receipt.replaceChildren();
    if (state.encounter) renderEncounter(state.encounter);
    else turnStrip.hidden = true;
    const own = state.roster?.find(pilot => pilot.controlled)?.label ?? "You";
    const owners = state.choices.map(choice => ({pilot:own, handler:"Handler", opponent:"Drill opponent"})[choice.role]);
    renderRecordMetadata(playRecord, {
      location:state.facility?.name ?? state.title,
      state:state.choices.length ? "Action required" : state.play?.state === "complete" && !selection ? "Filed"
        : state.busy ? "Play in progress" : "Play instructions",
      owner:[...new Set(owners.filter(Boolean))].join(" · "),
    });
    if (state.play?.receipt) {
      receipt.append(node("h3", playTitle(state.play.play) + " receipt"), node("p", rollText(state.play)));
      if (state.play.result?.maneuvers) {
        receipt.append(node("p", "Resolved · " + Object.keys(state.play.result.maneuvers).map(word).join(", ")));
        if (state.play.result.damaged?.length) receipt.append(node("p", "ASSET DAMAGE FILED · A used Asset was damaged."));
      }
      if (["all_out_assault", "go_for_the_core", "keep_your_head"].includes(state.play.play) && state.play.state === "complete") {
        receipt.append(node("p", "Resolved · " + word(state.play.result.tier)));
        for (const hit of state.impacts) receipt.append(node("p", hit.actor + " · " + hit.asset + " damaged"));
        if (state.play.result.ruling) receipt.append(node("p", state.play.result.ruling));
        if (state.target_ended) receipt.append(node("p", "CASUALTY FILED · Target deceased."));
      }
      if (state.play.play === "check_sensors" && state.play.state === "complete") {
        for (const answer of Object.values(state.play.result.answers)) receipt.append(node("p", answer));
      }
      if (state.play.play === "flirt" && state.play.state === "complete") {
        receipt.append(node("p", "Resolved · " + word(state.play.result.tier)));
        for (const answer of [state.play.result.target_answer, state.play.result.actor_answer]) {
          if (answer) receipt.append(node("p", answer));
        }
      }
      if (state.play.play === "living_battery" && state.play.state === "complete") {
        receipt.append(node("p", "Resolved · " + word(state.play.result.tier)));
        if (state.play.result.brain_answer) receipt.append(node("p", state.play.result.brain_answer));
      }
      if (state.play.play === "put_someone_beneath_you" && state.play.state === "complete") {
        receipt.append(node("p", "Resolved · " + word(state.play.result.tier)));
        if (state.play.result.beneath_effects?.length) {
          receipt.append(node("p", "Effects · " + state.play.result.beneath_effects.map(word).join(", ")));
        }
      }
    }
    if (state.counter?.receipt) {
      receipt.append(node("h3", "Counter · " + playTitle(state.counter.play)), node("p", rollText(state.counter)));
    }
    if (state.beneath_response?.receipt) {
      const response = state.beneath_response;
      const heading = response.play === "defeat" ? "Defeat receipt" : "Confrontation response · " + playTitle(response.play);
      receipt.append(node("h3", heading), node("p", rollText(response)));
      if (response.play === "defeat" && response.state === "complete") {
        receipt.append(node("p", "Defeat resolved · " + word(response.result.tier)));
      }
    }
    if (state.play?.play === "flirt_followthrough" && typeof state.play.result?.confirmed === "boolean") {
      receipt.append(node("h3", "Flirt Follow-through"));
      receipt.append(node("p", state.play.result.confirmed ? "Follow-through confirmed · Bond improved" : "Follow-through declined · Obligation still open"));
      if (state.play.result.response) receipt.append(node("p", state.play.result.response));
    }
    if (state.flirt_escape?.receipt) {
      receipt.append(node("h3", "Escape · Keep Your Head"), node("p", rollText(state.flirt_escape)));
    }
    if (state.play?.play === "receive_orders" && (state.play.result || state.refusal?.receipt)) {
      receipt.append(node("h3", "Direct order"), node("p", state.order_text));
      if (state.play.result?.response) receipt.append(node("p", "Response · " + word(state.play.result.response)));
      if (state.refusal?.receipt) {
        receipt.append(node("h3", "Disobey Orders receipt"), node("p", rollText(state.refusal)));
        const outcome = state.refusal.result;
        if (outcome) {
          receipt.append(node("p", outcome.can_disobey ? "Refusal succeeded" : "Refusal halted"));
          if (typeof outcome.handler_knows === "boolean") {
            receipt.append(node("p", outcome.handler_knows ? "Handler discovered the refusal" : "Handler did not discover the refusal"));
          }
        }
      }
    }
    if (state.history.length) {
      const history = node("div");
      for (const play of state.history) {
        const rolled = play.refusal ?? play;
        const result = rolled.receipt ? rollText(rolled) + " · " + word(rolled.result.tier) : word(play.result?.response ?? "resolved");
        history.append(node("p", playTitle(play.play) + " · " + result));
        if (play.beneath_response?.play === "defeat" && play.beneath_response.receipt) {
          history.append(node("p", "Defeat · " + rollText(play.beneath_response) + " · " + word(play.beneath_response.result.tier)));
        }
      }
      receipt.append(popupAction("Past Battlefield Plays",history,"battlefield-history"));
    }
    if (state.wyvern_response?.receipt) {
      receipt.append(node("p", "Wyvern replacement · " + playTitle(state.wyvern_response.play) + " · " + rollText(state.wyvern_response)));
    }
    if (state.actions.length || state.roster?.length) {
      const availableMove = state.actions.find(item => item.id === "move");
      if (availableMove) {
        const move = node("button", availableMove.label);
        move.type = "button";
        move.setAttribute("aria-pressed", String(action?.id === "move"));
        move.addEventListener("click", () => { selection = "move"; render(); reload(); });
        toolbar.append(move);
      }
      const plays = state.actions.filter(item => item.id !== "move");
      for (const available of plays) {
        const direct = node("button",available.label);
        direct.type = "button";
        direct.setAttribute("aria-haspopup","dialog");
        direct.dataset.tacticalPlay = available.id;
        direct.addEventListener("click",() => selectPlay(available));
        toolbar.append(direct);
      }
      const play = node("button", "Sheet Plays");
      play.type = "button";
      play.disabled = (!plays.length && (state.busy || !state.roster?.length));
      play.setAttribute("aria-haspopup", "dialog");
      play.setAttribute("aria-controls", menu.id);
      play.addEventListener("click", () => {
        const roster = state.roster ?? [];
        const rosterPicker = select(roster.map(item => [item.id, item.label + " · " + item.frame]), "Select a character");
        rosterPicker.value = roster.find(item => item.controlled)?.id ?? roster[0]?.id ?? "";
        function showCharacter() {
          const character = roster.find(item => item.id === rosterPicker.value);
          const ready = character?.controlled || !roster.length ? plays : [];
          menuState.textContent = ready.length ? "SELECT PLAY" : character && !character.controlled ? "SHEET REFERENCE" : "NO READY PLAY";
          menuOptions.replaceChildren();
          const catalog = new Map((character?.plays ?? []).map(item => [item.id, item]));
          const entries = ready.map(item => {
            const play = {...catalog.get(item.id), ...item};
            catalog.delete(item.id);
            const row = playCard(play, sheetPlayCaption(play, item.range.label), () => selectPlay(item));
            row.setAttribute("aria-haspopup","dialog");
            return {play, row};
          });
          for (const play of catalog.values()) {
            const caption = !character.controlled ? "Sheet reference"
              : play.blocked ? "Blocked on this sheet"
              : play.id === "go_for_the_core" && state.core_exposure_targets?.length ? "Requires an exposed Core"
              : "Unavailable in this encounter";
            entries.push({play, row:playCard(play, sheetPlayCaption(play, caption))});
          }
          if (entries.length) {
            const rail = playRail(entries, ready[0]?.category);
            menuOptions.append(rail);
          }
        }
        menuRoster.replaceChildren();
        if (roster.length) menuRoster.append(label("Character", rosterPicker));
        rosterPicker.addEventListener("change", showCharacter);
        showCharacter();
        menu.showModal();
      });
      toolbar.append(play);
      for (const candidate of state.core_exposure_targets ?? []) {
        const expose = node("button", "Expose Core · " + candidate.label);
        expose.type = "button";
        expose.title = "Use the drill opponent’s willing exposure";
        expose.addEventListener("click", () => submit("core-expose", {revision:state.revision, target:candidate.id}));
        toolbar.append(expose);
      }
    }
    const panel = playDialog.open ? playFields : controls;
    if (state.frame_work?.length) {
      const frame = node("button", "Frame controls");
      frame.type = "button";
      frame.setAttribute("aria-haspopup", "dialog");
      frame.addEventListener("click", () => {
        frameSelection = undefined;
        selection = "frame-work";
        status("");
        if (!playDialog.open) playDialog.showModal();
        render();
      });
      toolbar.append(frame);
    }
    if (playDialog.open && selection === "frame-work") {
      document.getElementById("tactical-action-title").textContent = "Frame controls";
      const cards = (state.frame_work ?? []).filter(card => !frameSelection || card.id === frameSelection);
      renderFrameWork(playFields, cards, submit, "frame-work");
      if (!cards.length) playFields.append(node("p", "No Frame decisions are currently assigned here."));
      const rouseOrCounter = state.choices.filter(choice => !orderChoices.has(choice.kind));
      for (const choice of rouseOrCounter) renderChoice(choice, playFields);
      renderBoard(null);
      return;
    }
    const printedPlay = state.busy || state.choices.length ? state.play?.play : selection;
    document.getElementById("tactical-action-title").textContent = printedPlay
      ? playTitle(printedPlay) : "Battlefield Play";
    if (state.busy && !state.choices.length) {
      panel.append(node("p", "AWAITING RULING"));
    }
    if (!action && state.actions.some(item => item.range.kind === "order")) {
      controls.append(node("p", "Open Play to respond to the current order."));
    }
    if (playDialog.open) {
      renderAction(action, panel);
      for (const choice of state.choices) {
        if (!orderChoices.has(choice.kind)) renderChoice(choice, panel);
      }
    } else {
      renderBoard(action?.id === "move" ? action : null);
    }
    if (!playDialog.open && state.choices.some(choice => !orderChoices.has(choice.kind))) {
      const resume = node("button", "Open assigned choices");
      resume.type = "button";
      resume.addEventListener("click", () => {
        status("");
        playDialog.showModal();
        render();
      });
      toolbar.append(resume);
    }
    if (state.can_issue_order) {
      const form = node("form");
      const [wrapped, order] = account("Direct order to your pilot");
      form.append(wrapped, node("button", "Issue drill order", "primary"));
      form.addEventListener("submit", event => {
        event.preventDefault();
        submit("issue-order", {text:order.value});
      });
      controls.append(popupAction("Test Handler · Issue drill order",form,"drill-order"));
    }
  }

  return {
    async openFramePlay(id) {
      if (!await reload()) return;
      if (!state.frame_work?.some(card => card.id === id && card.operations?.length)) {
        throw new Error("This Frame record changed. Refresh Battlefield.");
      }
      frameSelection = id;
      selection = "frame-work";
      status("");
      if (!playDialog.open) playDialog.showModal();
      render();
    },
    async openPlay(id) {
      if (!await reload()) return;
      const action = state.actions.find(item => item.id === id && item.id !== "move");
      if (action) selectPlay(action);
      else {
        status("This Play is no longer cleared for the current tactical record.");
        feedback.tabIndex = -1;
        feedback.focus();
      }
    },
    show(open) {
      if (visible === open) return;
      visible = open;
      root.hidden = !open;
      clearTimeout(timer);
      if (open) reload();
      else {
        if (menu.open) menu.close();
        if (playDialog.open) playDialog.close();
        generation++;
      }
    },
    reload,
  };
}
