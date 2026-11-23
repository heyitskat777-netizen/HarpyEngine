const markerPrefix = "foundation-handover:";
const seenReceiptLimit = 100;

function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function button(label, action, primary = false) {
  const control = element("button", label, primary ? "primary" : undefined);
  control.type = "button";
  control.addEventListener("click", action);
  return control;
}

function entryId(value) {
  return Number.isSafeInteger(value) && value > 0 ? value : 0;
}

function receiptIds(receipts = []) {
  return Array.isArray(receipts) ? receipts.filter(id => typeof id === "string" && id) : [];
}

function marker(entry, receipts) {
  return {entry:entryId(entry), receipts:receiptIds(receipts).slice(-seenReceiptLimit)};
}

function loadMarkers(key) {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "[]");
    return new Map(saved.map(([room, value]) => [room, marker(value.entry, value.receipts)]));
  } catch {
    return new Map();
  }
}

function mergeMarkers(previous, next) {
  return marker(Math.max(previous?.entry ?? 0, next.entry), [
    ...new Set([...(previous?.receipts ?? []), ...next.receipts]),
  ]);
}

function activityTime(value) {
  if (Number.isFinite(value)) return value * 1000;
  const parsed = typeof value === "string" ? Date.parse(value) : NaN;
  return Number.isFinite(parsed) ? parsed : 0;
}

function receiptCursor(receipt) {
  return receipt.id + ":" + (receipt.state ?? "") +
    (Number.isSafeInteger(receipt.revision) ? ":" + receipt.revision : "");
}

export function handoverSceneRows(player, markers = new Map()) {
  const rooms = player?.directory?.rooms ?? [];
  const places = new Map((player?.directory?.locations ?? []).map(place => [place.id, place.name]));
  const receiptsByRoom = new Map();
  for (const receipt of player?.scene_mail ?? []) {
    if (!receiptsByRoom.has(receipt.room)) receiptsByRoom.set(receipt.room, []);
    receiptsByRoom.get(receipt.room).push(receipt);
  }
  return rooms.filter(room => room.joined && room.archived_at == null).map(room => {
    const saved = markers.get(room.id);
    const seenReceipts = new Set(saved?.receipts);
    const receipts = receiptsByRoom.get(room.id) ?? [];
    const entries = player.handover_dialogue?.[room.id] ?? [];
    const timeline = [
      ...entries.filter(entry => entryId(entry.id)).map(entry => ({
        source:{entry:entry.id}, author:entry.callsign, portrait:entry.portrait,
        time:activityTime(entry.created), unread:entry.id > (saved?.entry ?? 0),
      })),
      ...receipts.map(receipt => ({
        source:{receipt:receipt.id}, author:"HarpyEngine", bot:true,
        time:activityTime(receipt.updated ?? receipt.created), unread:!seenReceipts.has(receiptCursor(receipt)),
      })),
    ].sort((a,b) => b.time - a.time || (b.source.entry ?? 0) - (a.source.entry ?? 0));
    const unread = timeline.filter(item => item.unread);
    const pending = receipts.flatMap(receipt => (receipt.pending ?? []).map(choice => ({
      receipt:receipt.id, id:choice.id, play:receipt.play, kind:choice.kind,
    })));
    const waiting = [...new Set(receipts.flatMap(receipt => {
      if (receipt.state === "complete" || receipt.state === "aborted") return [];
      if (receipt.waiting_on?.length) return receipt.waiting_on;
      return (receipt.pending ?? []).map(choice => choice.owner === "handler" ? "Handler" : player.callsign);
    }).filter(Boolean))];
    return {
      id:room.id, name:room.name, location:room.location_name || places.get(room.location) || "Unassigned",
      latest:timeline[0], firstUnread:unread.at(-1)?.source, unread:unread.length, pending, waiting,
    };
  }).sort((a,b) => (b.latest?.time ?? 0) - (a.latest?.time ?? 0) || a.name.localeCompare(b.name));
}

export function createShiftHandover(target, {openScene, openReceipt, openInvitation, artwork, playName, decisionName}) {
  const heading = element("header", undefined, "handover-heading");
  const pilot = element("p", undefined, "eyebrow");
  const title = element("h2", "Shift Handover");
  const intro = element("div", undefined, "handover-section-heading");
  const unread = element("span", undefined, "eyebrow");
  const sceneList = element("ul", undefined, "handover-rows");
  const secondary = element("section", undefined, "handover-secondary");
  heading.append(pilot,title);
  intro.append(element("h3", "Scene activity"), unread);
  target.append(heading,intro,sceneList,secondary);
  target.classList.add("handover");
  let player;
  let mailbox;
  let visible = true;
  let markers = new Map();
  let rendered;

  function portrait(author, art, bot = false) {
    const initials = Array.from(author?.trim() || "").slice(0,2).join("") || "·";
    const image = element("span", bot ? undefined : initials, "handover-portrait dialogue-portrait");
    image.setAttribute("aria-hidden","true");
    if (bot) image.append(element("span", undefined, "handover-insignia"));
    else if (art) artwork?.picture(image, art, {decorative:true,fallback:initials});
    return image;
  }

  function rowFor(room) {
    const row = element("li", undefined, "handover-row");
    row.dataset.handoverRoom = room.id;
    const details = element("div", undefined, "handover-details");
    const copy = element("div", undefined, "handover-copy");
    const meta = element("p", room.location, "handover-meta");
    const recent = room.latest;
    if (recent?.author) meta.append(document.createTextNode(" · " + recent.author + (recent.bot ? " · Bot" : "")));
    if (recent?.time) {
      const date = new Date(recent.time);
      const time = element("time", date.toLocaleString(undefined, {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"}));
      time.dateTime = date.toISOString();
      meta.append(document.createTextNode(" · "),time);
    }
    copy.append(element("h4", room.name),meta);
    const status = [room.unread ? room.unread + " new" : undefined,
      room.waiting.length ? "Waiting on " + room.waiting.join(", ") : undefined]
      .filter(Boolean).join(" · ");
    if (status) copy.append(element("p", status, "eyebrow handover-status"));
    details.append(portrait(recent?.author,recent?.portrait,recent?.bot),copy);
    const actions = element("div", undefined, "handover-actions");
    if (room.pending.length) {
      const choice = room.pending[0];
      const label = "Review " + playName(choice.play);
      const review = button(label, () => openReceipt(room.id, choice.receipt, choice.id), true);
      review.dataset.handoverAction = "review";
      review.setAttribute("aria-label", label + " · " + decisionName(choice.kind) + " · " + room.name);
      actions.append(review);
    }
    const label = room.firstUnread ? "Read from first unread" : room.latest ? "Resume scene" : "Open scene";
    const open = button(label, () => openScene(room.id, room.firstUnread ?? {}), !room.pending.length && room.unread > 0);
    open.dataset.handoverAction = "open";
    open.setAttribute("aria-label", label + " · " + room.name);
    actions.append(open);
    row.append(details,actions);
    return row;
  }

  function invitationRow(invite) {
    const row = element("li", undefined, "handover-row");
    const details = element("div", undefined, "handover-copy");
    details.append(element("h4", invite.name),element("p", "Waiting on your response", "eyebrow"));
    const review = button("Review invitation", () => openInvitation(invite));
    review.dataset.handoverInvite = invite.id;
    review.setAttribute("aria-label","Review invitation · " + invite.name);
    row.append(details,review);
    return row;
  }

  function render() {
    if (!player || !visible) return;
    const rooms = handoverSceneRows(player, markers);
    const invites = player.scene_invites ?? [];
    const handlerChoices = player.handler_choices ?? [];
    const label = player.stage === "active"
      ? [player.callsign, player.profile?.status, player.profile?.frame_name ?? player.profile?.frame].filter(Boolean).join(" · ")
      : player.callsign || (player.stage === "handler" ? "Handler" : "");
    const signature = JSON.stringify([player.mailbox, label, rooms, invites, handlerChoices]);
    if (signature === rendered) return;
    rendered = signature;
    const focused = document.activeElement;
    const focusedRoom = focused?.closest("[data-handover-room]")?.dataset.handoverRoom;
    const focusedAction = focused?.dataset.handoverAction;
    const focusedInvite = focused?.dataset.handoverInvite;
    pilot.textContent = label;
    pilot.hidden = !label;
    const count = rooms.reduce((sum,room) => sum + room.unread,0);
    unread.textContent = count + " unread " + (count === 1 ? "entry" : "entries");
    intro.hidden = !rooms.length && player.stage === "handler";
    sceneList.hidden = intro.hidden;
    sceneList.replaceChildren(...(rooms.length ? rooms.map(rowFor) : [
      element("li", "Your joined scenes will appear here.", "handover-empty"),
    ]));
    secondary.replaceChildren();
    if (invites.length) {
      const list = element("ul", undefined, "handover-rows");
      list.append(...invites.map(invitationRow));
      secondary.append(element("h3", invites.length === 1 ? "Scene invitation" : "Scene invitations"),list);
    }
    if (handlerChoices.length) {
      const list = element("ul", undefined, "handover-rows");
      for (const card of handlerChoices) {
        const row = element("li", undefined, "handover-row");
        const details = element("div", undefined, "handover-copy");
        details.append(element("h4", playName(card.play)),
          element("p", card.room_name || "Scene operations","handover-meta"));
        row.append(details,button("Review " + decisionName(card.choice.kind),
          () => openReceipt(card.room, card.root, card.choice.id),true));
        list.append(row);
      }
      secondary.append(element("h3","Handler assignments"),list);
    } else if (player.stage === "handler" && !rooms.length) {
      secondary.append(element("p","No pending Handler assignments.","handover-empty"));
    }
    if (focusedRoom && focusedAction) {
      const row = [...sceneList.children].find(item => item.dataset.handoverRoom === focusedRoom);
      row?.querySelector(`[data-handover-action="${focusedAction}"]`)?.focus({preventScroll:true});
    } else if (focusedInvite) {
      [...secondary.querySelectorAll("[data-handover-invite]")]
        .find(control => control.dataset.handoverInvite === focusedInvite)?.focus({preventScroll:true});
    }
  }

  return {
    update(record) {
      if (mailbox !== record.mailbox) {
        mailbox = record.mailbox;
        markers = mailbox ? loadMarkers(markerPrefix + mailbox) : new Map();
        rendered = undefined;
        sceneList.replaceChildren();
        secondary.replaceChildren();
        pilot.textContent = "";
      }
      player = record;
      render();
    },
    setVisible(value) {
      visible = value;
      if (visible) render();
    },
    markRead(roomId, entries, receipts = []) {
      if (!player?.directory?.rooms.some(room => room.id === roomId && room.joined && room.archived_at == null)) return;
      const current = marker(Math.max(0,...entries.map(entry => entryId(entry.id))),receipts.map(receiptCursor));
      const previous = markers.get(roomId);
      const combined = mergeMarkers(previous,current);
      if (combined.entry === (previous?.entry ?? 0)
        && combined.receipts.every((id,index) => id === previous?.receipts[index])) return;
      markers.set(roomId,combined);
      if (mailbox) {
        const key = markerPrefix + mailbox;
        const stored = loadMarkers(key);
        for (const [room, seen] of markers) stored.set(room,mergeMarkers(stored.get(room),seen));
        markers = stored;
        try { localStorage.setItem(key,JSON.stringify([...markers])); } catch {}
      }
      render();
    },
  };
}
