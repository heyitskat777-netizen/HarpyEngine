export function artworkUI(send, request) {
  const dialog = document.getElementById("artwork-dialog");
  const title = dialog.querySelector("h2");
  const status = dialog.querySelector("#artwork-state");
  const select = dialog.querySelector("select");
  const preview = dialog.querySelector(".artwork-preview");
  const feedback = dialog.querySelector("[role=status]");
  const save = dialog.querySelector("[data-save-artwork]");
  const images = new Map();
  const pictures = new WeakMap();
  let catalogRequest;
  let editing;

  function catalog() {
    catalogRequest ??= request("catalog").then(response => response.json()).catch(error => {
      catalogRequest = undefined;
      throw error;
    });
    return catalogRequest;
  }

  function imageURL(id) {
    if (!images.has(id)) {
      images.set(id, request(id).then(async response => {
        if (response.headers.get("Content-Type") !== "image/webp") {
          throw new Error("Artwork image is unavailable.");
        }
        return URL.createObjectURL(await response.blob());
      }).catch(error => {
        images.delete(id);
        throw error;
      }));
    }
    return images.get(id);
  }

  function picture(target, id, {decorative = false, fallback = "Artwork unavailable."} = {}) {
    const previous = pictures.get(target);
    if (previous?.id === id && previous.decorative === decorative && !previous.failed
        && (!previous.image || previous.image.parentNode === target)) return previous.ready;
    const current = {id,decorative};
    pictures.set(target,current);
    if (!id) {
      target.replaceChildren();
      current.ready = Promise.resolve();
      return current.ready;
    }
    if (!target.querySelector("img")) target.textContent = decorative ? fallback : "";
    current.ready = (async () => {
      const image = document.createElement("img");
      try {
        const entry = (await catalog()).find(item => item.id === id);
        if (!entry) throw new Error("Artwork is no longer in the catalog.");
        image.alt = decorative ? "" : entry.label;
        image.src = await imageURL(id);
        await image.decode();
        if (pictures.get(target) === current) {
          current.image = image;
          target.replaceChildren(image);
        }
      } catch {
        current.failed = true;
        if (pictures.get(target) === current) target.textContent = fallback;
      }
    })();
    return current.ready;
  }

  select.addEventListener("change", () => {
    status.textContent = select.value ? "READY TO FILE" : "CLEAR SELECTION";
    feedback.textContent = "";
    picture(preview, select.value);
  });
  save.addEventListener("click", async () => {
    const current = editing;
    save.disabled = true;
    select.disabled = true;
    status.textContent = "FILING IMAGE";
    feedback.textContent = "";
    try {
      const result = await send("artwork", {
        kind:current.kind, target:current.target, previous:current.previous, artwork:select.value || null,
      }, undefined, !current.onSave);
      current.onSave?.(result.artwork);
      if (editing === current && dialog.open) dialog.close();
    } catch (error) {
      if (editing === current) {
        status.textContent = "SAVE FAILED";
        feedback.textContent = error.message;
      }
    } finally {
      if (editing === current) {
        save.disabled = false;
        select.disabled = false;
      }
    }
  });

  async function open(kind, target, previous, label, onSave) {
    const current = {kind, target, previous:previous ?? null, onSave};
    editing = current;
    title.textContent = "Artwork / " + label;
    select.replaceChildren(new Option("No artwork", ""));
    preview.replaceChildren();
    status.textContent = "READING CATALOG";
    feedback.textContent = "";
    select.disabled = true;
    save.disabled = true;
    dialog.showModal();
    try {
      const entries = await catalog();
      if (editing !== current || !dialog.open) return;
      const groups = new Map();
      for (const entry of entries.filter(item => item.kind === kind)) {
        if (!groups.has(entry.group)) {
          const group = document.createElement("optgroup");
          group.label = entry.group;
          groups.set(entry.group, group);
          select.append(group);
        }
        groups.get(entry.group).append(new Option(entry.label, entry.id));
      }
      select.value = previous && entries.some(item => item.id === previous) ? previous : "";
      picture(preview, select.value);
      status.textContent = select.value ? "IMAGE ON FILE" : "SELECT IMAGE";
      select.disabled = false;
      save.disabled = false;
      select.focus();
    } catch (error) {
      if (editing === current) {
        status.textContent = "CATALOG UNAVAILABLE";
        feedback.textContent = error.message;
      }
    }
  }

  return {picture, open};
}
