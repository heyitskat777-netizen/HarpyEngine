export function mailSpool(inbox, list, reader, badge, assignmentsBadge, pictureSender) {
  const groups = new Map();
  const allDispatches = document.getElementById("dispatch-all");
  const decisionFilter = document.getElementById("dispatch-decisions");
  const decisionCount = document.getElementById("decision-count");
  let identity;
  let callsign = "You";
  let selected;
  let decisionsOnly = false;
  let viewed = new Set();
  let openedBy;
  const needsDecision = entry => entry.required && entry.owned !== false;
  const filtered = entries => decisionsOnly ? entries.filter(needsDecision) : entries;

  function mark(id) {
    viewed = new Set([...viewed, id].slice(-180));
    if (identity) {
      try { localStorage.setItem("foundation-mail:" + identity, JSON.stringify([...viewed])); } catch {}
    }
  }

  function render() {
    const entries = [...groups.values()].flat().sort((a, b) => Number(needsDecision(b)) - Number(needsDecision(a)));
    const visible = filtered(entries);
    const focused = list.contains(document.activeElement) ? document.activeElement.dataset.mailId : null;
    decisionCount.textContent = String(entries.filter(needsDecision).length);
    if (assignmentsBadge) assignmentsBadge.textContent = decisionCount.textContent;
    allDispatches.setAttribute("aria-pressed", String(!decisionsOnly));
    decisionFilter.setAttribute("aria-pressed", String(decisionsOnly));
    const files = [...reader.querySelectorAll("[data-mail-file]")];
    if (!visible.some(entry => entry.file === selected) || !files.some(file => file.dataset.mailFile === selected)) selected = undefined;
    for (const file of files) file.hidden = file.dataset.mailFile !== selected;
    if (!selected && reader.open) reader.close();
    list.replaceChildren(...visible.map(entry => {
      const row = document.createElement("li");
      const open = document.createElement("button");
      open.type = "button";
      open.className = "mail-entry";
      open.dataset.mailId = entry.id;
      const subject = entry.title ?? entry.subject ?? "Dispatch record";
      open.setAttribute("aria-label", entry.label ?? subject);
      if (entry.file === selected && selected) open.setAttribute("aria-current", "true");
      row.dataset.required = String(Boolean(entry.required));
      row.dataset.unread = String(!viewed.has(entry.id));
      const state = needsDecision(entry) ? "RESPONSE REQUIRED" : entry.required ? "AWAITING " + (entry.owner ?? "ASSIGNED PRINCIPAL") : entry.status;
      for (const [value, role] of [[subject, "subject"], [state, "status"]]) {
        if (!value) continue;
        const text = document.createElement("span");
        text.className = "mail-" + role;
        text.textContent = value;
        open.append(text);
      }
      const metadata = [["From",entry.sender ?? "Foundation operations"]];
      if (entry.recipient) metadata.push(["To",entry.recipient]);
      if (entry.owner || entry.required) metadata.push(["Assigned to",entry.owner ?? callsign]);
      if (entry.location) metadata.push(["Scene",entry.location]);
      const details = document.createElement("span");
      details.className = "mail-metadata";
      for (const [label, value] of metadata) {
        const field = document.createElement("span");
        const title = document.createElement("span");
        title.className = "mail-field";
        title.textContent = label;
        field.append(title);
        if (label === "From") {
          const portrait = pictureSender?.(entry);
          if (portrait) {
            field.className = "mail-sender";
            field.append(portrait);
          }
        }
        field.append(value);
        details.append(field);
      }
      open.append(details);
      open.setAttribute("aria-description", [...metadata.map(([label,value]) => label + " " + value),
        entry.audience && "Distribution " + entry.audience, state,
        viewed.has(entry.id) ? "Retrieved" : "Unretrieved"].filter(Boolean).join(". "));
      if (entry.created != null && Number.isFinite(new Date(entry.created).getTime())) {
        const date = new Date(entry.created);
        const time = document.createElement("time");
        time.className = "mail-timestamp";
        time.dateTime = date.toISOString();
        time.textContent = date.toLocaleString(undefined,{dateStyle:"medium",timeStyle:entry.timeStyle ?? "short"});
        open.append(time);
      }
      open.addEventListener("click", () => {
        mark(entry.id);
        openedBy = entry.id;
        if (entry.file) selected = entry.file;
        render();
        if (entry.open) entry.open();
        else if (entry.file && selected) {
          document.getElementById("mail-reader-title").textContent = entry.title ?? "Dispatch record";
          if (!reader.open) reader.showModal();
          reader.querySelector(`[data-mail-file="${CSS.escape(entry.file)}"]`)?.focus();
        }
      });
      row.append(open);
      return row;
    }));
    if (!visible.length) {
      const empty = document.createElement("li");
      empty.textContent = decisionsOnly ? "NO RESPONSE ASSIGNED" : "MAIL SPOOL EMPTY";
      list.append(empty);
    }
    badge.textContent = entries.filter(entry => !viewed.has(entry.id)).length || "";
    if (focused) list.querySelector(`[data-mail-id="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
  }

  function filter(assigned) {
    if (decisionsOnly === assigned) return;
    decisionsOnly = assigned;
    selected = undefined;
    render();
  }
  allDispatches.addEventListener("click", () => filter(false));
  decisionFilter.addEventListener("click", () => filter(true));
  reader.addEventListener("close",() => {
    selected = undefined;
    render();
    const trigger = openedBy && list.querySelector(`[data-mail-id="${CSS.escape(openedBy)}"]`);
    if (!inbox.hidden) trigger?.focus({preventScroll:true});
  });

  return {
    identify(next, owner) {
      callsign = owner || "You";
      if (next === identity) return;
      identity = next;
      groups.clear();
      for (const file of reader.querySelectorAll("[data-mail-file]")) file.remove();
      selected = undefined;
      decisionsOnly = false;
      viewed = new Set();
      try {
        const stored = JSON.parse(localStorage.getItem("foundation-mail:" + identity) ?? "[]");
        if (Array.isArray(stored)) viewed = new Set(stored.filter(id => typeof id === "string"));
      } catch {}
      render();
    },
    replace(group, entries) { groups.set(group, entries); render(); },
    opened(assigned = false) {
      if (!inbox.hidden) {
        decisionsOnly = assigned;
        selected = undefined;
        render();
      }
    },
  };
}
