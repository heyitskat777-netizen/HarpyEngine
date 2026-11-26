function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function label(value) {
  return value?.replaceAll("_", " ");
}

function addList(parent, title, values) {
  if (!values?.length) return;
  const list = element("ul");
  list.append(...values.map(value => element("li", value)));
  parent.append(element("h3", title), list);
}

function renderSheet(parent, record) {
  const register = element("dl");
  register.className = "record-register";
  for (const [key, value] of [
    ["Record type", record.kind], ["Status", record.status],
    ["Girl", label(record.girl)], ["Frame", label(record.frame)],
    ["Frame name", record.frame_name], ["Heat", record.heat],
    ["Jobs", record.jobs?.map(label).join(", ")],
    ["Gorgon class", label(record.gorgon_class)],
    ["Types", record.types?.map(label).join(", ")],
    ["Core", typeof record.core_exposed === "boolean" ? record.core_exposed ? "Exposed" : "Shielded" : null],
  ]) {
    if (value == null || value === "") continue;
    const row = element("div");
    row.append(element("dt", key), element("dd", value));
    register.append(row);
  }
  parent.replaceChildren(register);
  if (record.description) parent.append(element("p", record.description));
  if (record.frame_appearance) {
    parent.append(element("h3", "Frame appearance"), element("p", record.frame_appearance));
  }
  addList(parent, "Identities", record.identities?.map(item => item.name + (item.marked ? " · Marked" : "")));
  addList(parent, "Tags", record.tags?.map(item => item.label + (item.marked ? " · Marked" : "")));
  addList(parent, "Assets", record.assets?.map(item => [
    item.name, label(item.family), item.destroyed ? "Destroyed" : item.damaged ? "Damaged" : null,
    item.void ? "Void-touched" : null, item.description,
  ].filter(Boolean).join(" · ")));
  addList(parent, "Core conditions", record.core_conditions);
  if (record.core_weakness) {
    parent.append(element("h3", "Core weakness"), element("p", record.core_weakness));
  }
  addList(parent, "Advancements", record.advancements);
  addList(parent, "Retained Plays", record.retained_plays?.map(label));
}

export function mountFacilitatorDossiers(read) {
  const search = document.getElementById("dossier-search");
  const type = document.getElementById("dossier-kind");
  const refresh = document.getElementById("dossier-refresh");
  const feedback = document.getElementById("dossier-feedback");
  const list = document.getElementById("dossier-list");
  const dialog = document.getElementById("dossier-dialog");
  const title = document.getElementById("dossier-title");
  const body = document.getElementById("dossier-sheet");
  let records = [];
  let visible = false;
  let revision = 0;

  function render() {
    const filter = search.value.trim().toLocaleLowerCase();
    const matches = records.filter(row => (!type.value || row.kind === type.value) && [
      row.name, row.kind, row.girl, row.frame, row.frame_name, ...(row.jobs ?? []),
    ].some(value => label(value)?.toLocaleLowerCase().includes(filter)));
    list.replaceChildren(...matches.map(record => {
      const item = element("li");
      const button = element("button", record.name);
      button.type = "button";
      button.setAttribute("aria-haspopup", "dialog");
      button.addEventListener("click", () => {
        title.textContent = record.name;
        renderSheet(body, record);
        dialog.showModal();
      });
      const register = element("span", [record.kind, record.status].join(" · "));
      item.append(button, register);
      return item;
    }));
    feedback.textContent = matches.length ? `${matches.length} ${matches.length === 1 ? "dossier" : "dossiers"}`
      : records.length ? "No dossiers match the filters." : "No character sheets are on file.";
  }

  function clear() {
    if (dialog.open) dialog.close();
    records = [];
    title.textContent = "Campaign dossier";
    body.replaceChildren();
    list.replaceChildren();
  }

  async function load() {
    const request = ++revision;
    clear();
    search.disabled = type.disabled = refresh.disabled = true;
    feedback.textContent = "Retrieving campaign dossiers…";
    try {
      const data = await read();
      if (!visible || request !== revision) return;
      records = data.dossiers;
      const selected = type.value;
      const kinds = [...new Set(records.map(row => row.kind))].sort();
      type.replaceChildren(new Option("All record types", ""), ...kinds.map(kind => new Option(kind, kind)));
      if (kinds.includes(selected)) type.value = selected;
      search.disabled = type.disabled = false;
      render();
    } catch (error) {
      if (visible && request === revision) feedback.textContent = error.message;
    } finally {
      if (visible && request === revision) refresh.disabled = false;
    }
  }

  search.addEventListener("input", render);
  type.addEventListener("change", render);
  refresh.addEventListener("click", load);
  dialog.addEventListener("close", () => body.replaceChildren());
  return open => {
    visible = open;
    if (open) load();
    else {
      ++revision;
      clear();
      feedback.textContent = "";
    }
  };
}
