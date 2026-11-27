let active;
let context;
let opener;
const panelDrafts = new Map();
const dialogDrafts = new Map();

// Keep long printed choices readable without changing the select's stored values.
export function showSelectionText(control, target, always = false) {
  if (!always && ![...control.options].some(option => option.textContent.length > 70)) return;
  const quote = document.createElement("blockquote");
  quote.className = "printed-bond-prompt";
  const update = () => {
    quote.textContent = [...control.selectedOptions].filter(option => option.value !== "")
      .map(option => option.textContent).join("\n");
    quote.hidden = !quote.textContent;
  };
  control.addEventListener("change",update);
  update();
  target.append(quote);
}

export function closePopup(key) {
  if (active !== key) return;
  active = null;
  panelDrafts.delete(key);
  document.getElementById("utility-dialog").close();
}

export function renderDraftDialog(dialog, key, render) {
  const previous = dialog.dataset.draftKey;
  const values = captureFields(dialog);
  if (previous && values.length) dialogDrafts.set(previous,values);
  render();
  dialog.dataset.draftKey = key;
  restoreFields(dialog,structuredClone(dialogDrafts.get(key) ?? []));
}

function fields(root) {
  return [...root.querySelectorAll("input,select,textarea")].map((control, index) => ({
    control,
    key:(control.name || control.id || control.getAttribute("aria-label") || String(index))
      + (["checkbox","radio"].includes(control.type) ? ":" + control.value : ""),
  }));
}

export function captureFields(root) {
  return fields(root).map(({control,key}) => ({
    key, type:control.type, value:control.value, checked:control.checked,
    selected:control.multiple ? [...control.selectedOptions].map(option => option.value) : undefined,
  }));
}

export function restoreFields(root, saved = []) {
  for (const {control,key} of fields(root)) {
    const index = saved.findIndex(item => item.key === key && item.type === control.type);
    if (index < 0 || control.type === "file" || control.disabled) continue;
    const [item] = saved.splice(index,1);
    if (control.type === "checkbox" || control.type === "radio") control.checked = item.checked;
    else if (control.multiple) {
      for (const option of control.options) option.selected = item.selected.includes(option.value);
    } else if (control.tagName !== "SELECT" || [...control.options].some(option => option.value === item.value)) {
      control.value = item.value;
    }
    control.dispatchEvent(new Event("change",{bubbles:true}));
  }
}

export function popupContext(identity) {
  if (identity === context) return;
  const dialog = document.getElementById("utility-dialog");
  if (dialog?.open) dialog.close();
  active = null;
  panelDrafts.clear();
  dialogDrafts.clear();
  for (const item of document.querySelectorAll("[data-draft-key]")) delete item.dataset.draftKey;
  context = identity;
}

export function popupAction(title, content, key = title, {compact = false} = {}) {
  const dialog = document.getElementById("utility-dialog");
  const body = document.getElementById("utility-fields");
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.textContent = title;
  trigger.setAttribute("aria-haspopup","dialog");
  trigger.dataset.popup = key;
  function show(saved) {
    dialog.classList.toggle("compact-record", compact);
    document.getElementById("utility-title").textContent = title;
    document.getElementById("utility-feedback").textContent = "";
    body.replaceChildren(content);
    for (const form of body.querySelectorAll("form")) form.dataset.popupKey = key;
    restoreFields(body,structuredClone(saved ?? []));
    active = key;
  }
  trigger.addEventListener("click",() => {
    opener = trigger;
    show(panelDrafts.get(key));
    if (!dialog.open) dialog.showModal();
    body.querySelector("input,select,textarea,button")?.focus();
  });
  if (dialog.open && active === key) {
    const saved = captureFields(body);
    queueMicrotask(() => {
      if (dialog.open && active === key && trigger.isConnected) show(saved);
    });
  }
  if (!dialog.dataset.initialized) {
    dialog.dataset.initialized = "true";
    dialog.addEventListener("close",() => {
      if (active) panelDrafts.set(active,captureFields(body));
      active = null;
      body.replaceChildren();
      if (opener?.isConnected) opener.focus();
      else document.querySelector(`[data-popup="${CSS.escape(opener?.dataset.popup ?? "")}"]`)?.focus();
    });
  }
  return trigger;
}

function mountActionFooter(dialog, statusId) {
  const heading = dialog.querySelector(":scope > .record-heading");
  const status = document.getElementById(statusId);
  const body = document.createElement("div");
  body.className = "dialog-action-body";
  body.append(...[...dialog.childNodes].filter(node => node !== heading && node !== status));
  const footer = document.createElement("footer");
  footer.className = "dialog-action-footer";
  const feedback = document.createElement("div");
  const validation = document.createElement("p");
  validation.setAttribute("role", "status");
  validation.className = "dialog-validation";
  if (status) feedback.append(status);
  feedback.append(validation);
  const action = document.createElement("button");
  action.type = "button";
  action.className = "primary";
  footer.append(feedback, action);
  dialog.append(body,footer);
  dialog.classList.add("dialog-with-actions");
  footer.hidden = true;
  let form;
  let submit;

  function update() {
    const candidates = dialog.open ? [...body.querySelectorAll("button")].filter(button =>
      button.type === "submit" && button.form && button.form.method !== "dialog"
      && !button.closest("[hidden], details:not([open])")) : [];
    const inForm = candidates.filter(button => button.form === form);
    const next = candidates.length === 1 ? candidates[0] : inForm.length === 1 ? inForm[0] : null;
    if (next !== submit) {
      submit?.removeAttribute("data-footer-submit");
      submit = next;
      submit?.setAttribute("data-footer-submit", "");
      validation.textContent = "";
    }
    action.hidden = !submit;
    if (submit) {
      action.textContent = submit.textContent;
      action.disabled = submit.disabled;
    }
    footer.hidden = !dialog.open || !(submit || validation.textContent || (status?.textContent && !status.hidden));
  }

  new MutationObserver(update).observe(body, {
    subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:["hidden", "disabled", "open"],
  });
  if (status) new MutationObserver(update).observe(status, {
    subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:["hidden"],
  });
  dialog.addEventListener("beforetoggle", () => queueMicrotask(update));
  dialog.addEventListener("focusin", event => {
    if (event.target.form && body.contains(event.target)) {
      form = event.target.form;
      update();
    }
  });
  dialog.addEventListener("close", () => {
    if (dialog.open) return;
    form = undefined;
    update();
  });
  dialog.addEventListener("invalid", event => {
    if (event.target.form !== submit?.form || validation.textContent) return;
    validation.textContent = event.target.validationMessage;
    update();
  }, true);
  dialog.addEventListener("input", () => {
    validation.textContent = "";
    update();
  });
  action.addEventListener("click", () => submit?.click());
}

for (const [id, status] of [
  ["scene-action-dialog", "scene-action-feedback"],
  ["tactical-action-dialog", "tactical-action-status"],
  ["utility-dialog", "utility-feedback"],
  ["handler-plays-dialog", "handler-play-feedback"],
  ["sheet-reset-dialog", "sheet-reset-feedback"],
  ["mail-reader", ""],
]) {
  const dialog = document.getElementById(id);
  if (dialog) mountActionFooter(dialog, status);
}
if (window.visualViewport) {
  const sizeDialogs = () => document.documentElement.style.setProperty("--activity-dialog-height", window.visualViewport.height + "px");
  sizeDialogs();
  window.visualViewport.addEventListener("resize", sizeDialogs);
}

for (const dialog of document.querySelectorAll("dialog")) {
  let trigger;
  let label;
  let fromComms;
  dialog.addEventListener("beforetoggle",event => {
    if (event.newState !== "open") return;
    trigger = document.activeElement;
    label = trigger?.getAttribute("aria-label") ?? trigger?.textContent;
    fromComms = Boolean(trigger?.closest("#communications-desk"));
  });
  dialog.addEventListener("close",() => {
    if (document.querySelector("dialog[open]")) return;
    const target = trigger?.isConnected && trigger.getClientRects().length ? trigger : [...document.querySelectorAll("button")].find(
      button => button.getClientRects().length && (button.getAttribute("aria-label") ?? button.textContent) === label);
    const fallback = fromComms ? document.getElementById("communications-toggle")
      : document.querySelector('[data-folder][aria-current="page"]');
    (target ?? fallback)?.focus();
  });
}
