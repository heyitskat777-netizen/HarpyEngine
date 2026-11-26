export function mailSpool(inbox, list, reader, badge, assignmentsBadge, pictureSender) {
  const groups = new Map();
  const tabs = [...inbox.querySelectorAll("[data-dispatch-folder]")];
  const decisionCount = document.getElementById("decision-count");
  const waitingCount = document.getElementById("waiting-count");
  const historyCount = document.getElementById("history-count");
  const emptyLabels = {
    assigned: "No actions assigned to you.",
    waiting: "Nothing awaiting a response.",
    history: "No dispatch records filed.",
  };
  let identity;
  let callsign = "You";
  let selected;
  let folder = "assigned";
  let deliveries = new Map();
  let viewed = new Set();
  let openedBy;
  const folderOf = entry => entry.required && entry.owned !== false ? "assigned"
    : entry.required || entry.waiting ? "waiting" : "history";
  const allEntries = () => [...groups.values()].flat();

  function mark(id) {
    viewed = new Set([...viewed, id].slice(-180));
    if (identity) {
      try { localStorage.setItem("foundation-mail:" + identity, JSON.stringify([...viewed])); } catch {}
    }
  }

  function render() {
    const entries = allEntries();
    const visible = entries.filter(entry => folderOf(entry) === folder);
    const unread = entries.filter(entry => !viewed.has(entry.id));
    const focused = list.contains(document.activeElement) ? document.activeElement.dataset.mailId : null;
    decisionCount.textContent = String(entries.filter(entry => folderOf(entry) === "assigned").length);
    waitingCount.textContent = String(entries.filter(entry => folderOf(entry) === "waiting").length);
    historyCount.textContent = unread.filter(entry => folderOf(entry) === "history").length || "";
    historyCount.hidden = !historyCount.textContent;
    if (assignmentsBadge) assignmentsBadge.textContent = decisionCount.textContent;
    for (const tab of tabs) tab.setAttribute("aria-pressed", String(tab.dataset.dispatchFolder === folder));
    const files = [...reader.querySelectorAll("[data-mail-file]")];
    if (!entries.some(entry => entry.file === selected) || !files.some(file => file.dataset.mailFile === selected)) selected = undefined;
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
      const assigned = folderOf(entry) === "assigned";
      row.dataset.required = String(assigned);
      row.dataset.unread = String(!viewed.has(entry.id));
      const state = assigned ? "RESPONSE REQUIRED" : entry.status
        ?? (folder === "waiting" ? "AWAITING " + (entry.owner ?? "ASSIGNED PRINCIPAL") : undefined);
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
        if (label === "To" && deliveries.get(entry.deliveryKey)?.has(value)) {
          const check = document.createElement("span");
          check.className = "dm-delivery-mark";
          check.dataset.confirmed = "true";
          check.setAttribute("role", "img");
          check.setAttribute("aria-label", "Discord confirmed send");
          check.title = "Discord confirmed send";
          check.textContent = " ✓";
          field.append(check);
        }
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
      empty.textContent = emptyLabels[folder];
      list.append(empty);
    }
    badge.textContent = unread.length || "";
    if (focused) focusRow(focused);
  }

  function focusRow(id) {
    const row = id && list.querySelector(`[data-mail-id="${CSS.escape(id)}"]`);
    (row || tabs.find(tab => tab.dataset.dispatchFolder === folder))?.focus({preventScroll:true});
  }

  function filter(next) {
    if (folder === next) return;
    folder = next;
    selected = undefined;
    render();
  }
  for (const tab of tabs) tab.addEventListener("click", () => filter(tab.dataset.dispatchFolder));
  reader.addEventListener("close",() => {
    selected = undefined;
    render();
    if (!inbox.hidden) focusRow(openedBy);
  });

  return {
    identify(next, owner) {
      callsign = owner || "You";
      if (next === identity) return;
      identity = next;
      groups.clear();
      for (const file of reader.querySelectorAll("[data-mail-file]")) file.remove();
      selected = undefined;
      folder = "assigned";
      deliveries.clear();
      viewed = new Set();
      try {
        const stored = JSON.parse(localStorage.getItem("foundation-mail:" + identity) ?? "[]");
        if (Array.isArray(stored)) viewed = new Set(stored.filter(id => typeof id === "string"));
      } catch {}
      render();
    },
    replace(group, entries) { groups.set(group, entries); render(); },
    setDeliveries(next) {
      deliveries = next;
      render();
    },
    hasDeliveryTarget(key, recipient) {
      return allEntries().some(entry => entry.deliveryKey === key && entry.recipient === recipient);
    },
    opened(assigned = false) {
      if (!inbox.hidden) {
        const entries = allEntries();
        if (assigned || entries.some(entry => folderOf(entry) === "assigned")) folder = "assigned";
        else if (entries.some(entry => folderOf(entry) === "history" && !viewed.has(entry.id))) folder = "history";
        else if (entries.some(entry => folderOf(entry) === "waiting")) folder = "waiting";
        else folder = entries.length ? "history" : "assigned";
        selected = undefined;
        render();
      }
    },
  };
}
