export function communicationsUI(request, onUpdate, artwork, refreshDelivery) {
  const panel = document.getElementById("communications");
  const list = document.getElementById("communications-contacts");
  const desk = document.getElementById("communications-desk");
  const unread = document.getElementById("communications-unread");
  const toggle = document.getElementById("communications-toggle");
  const dialog = document.getElementById("communication-dialog");
  const back = document.getElementById("communication-back");
  const history = document.getElementById("communication-history");
  const form = document.getElementById("communication-form");
  const message = document.getElementById("communication-message");
  const feedback = document.getElementById("communication-feedback");
  const submit = form.querySelector("button[type=submit]");
  const refresh = document.getElementById("communication-refresh");
  const participants = document.getElementById("communication-participants");
  const participantCards = new Map();
  const rows = new Map();
  let senderRecord;
  let active;
  let sequence = 0;
  let identity;
  let contacts = [];
  let seen = {};
  let deliveries = new Map();
  let returnTo;
  const threads = new Map();

  const isUnread = contact => contact.latest_message > (seen[contact.id] ?? 0);

  function paintUnread() {
    const any = contacts.some(isUnread);
    unread.hidden = !any;
    toggle.setAttribute("aria-label", any ? "Comms, unread transmissions" : "Comms");
    for (const button of list.querySelectorAll("[data-contact]")) {
      const contact = contacts.find(item => item.id === button.dataset.contact);
      const latest = contact && isUnread(contact);
      button.toggleAttribute("data-unread", Boolean(latest));
      if (latest) button.setAttribute("aria-description", "Unread transmissions");
      else button.removeAttribute("aria-description");
    }
  }

  function markRead(thread, lastIncoming) {
    if (!identity || lastIncoming <= (seen[thread.id] ?? 0)) return;
    seen[thread.id] = lastIncoming;
    try { localStorage.setItem("foundation-comms:" + identity, JSON.stringify(seen)); } catch {}
    paintUnread();
  }

  function paintDeliveries() {
    for (const [id, record] of rows) {
      record.delivery.hidden = !record.outgoing || deliveries.get(id) !== "sent";
    }
  }

  function portrait(target, person) {
    const initials = (person.label ?? "?").trim().split(/\s+/).map(word => word[0]).slice(0,2).join("").toUpperCase();
    target.setAttribute("aria-label",(person.label ?? "Personnel") + " portrait");
    target.setAttribute("role","img");
    target.dataset.portrait=person.portrait ?? "";
    if (person.portrait && artwork) artwork.picture(target,person.portrait,{decorative:true,fallback:initials});
    else {
      artwork?.picture(target,null);
      target.textContent=person.bot ? "HE" : initials;
    }
  }

  function party(direction,person) {
    if (!participants) return;
    let card=participantCards.get(direction);
    if (!card) {
      const root=document.createElement("section");root.className="communication-party";
      const avatar=document.createElement("span");avatar.className="dialogue-portrait";
      const copy=document.createElement("div");
      const label=document.createElement("span");label.className="eyebrow";label.textContent=direction;
      const name=document.createElement("strong");copy.append(label,name);root.append(avatar,copy);
      card={root,avatar,name};participantCards.set(direction,card);
    }
    portrait(card.avatar,person);card.name.textContent=person.label;
    return card.root;
  }

  function showParties(sender,recipient) {
    if (participants) participants.replaceChildren(party("From",sender ?? {label:"Personnel record"}),party("To",recipient));
  }

  async function load(thread, scroll = false) {
    const read = ++sequence;
    const {entries,sender,recipient} = await request(thread.id);
    if (thread !== active || read !== sequence) return;
    if (sender) senderRecord=sender;
    showParties(senderRecord,recipient ?? thread);
    const atBottom = history.scrollHeight - history.scrollTop - history.clientHeight <= 2;
    const priorScroll = history.scrollTop;
    if (!entries.length) {
      const empty = document.createElement("li");
      empty.textContent = "Channel log empty.";
      history.replaceChildren(empty);
      return;
    }
    history.replaceChildren(...entries.map(entry => {
      let record=rows.get(String(entry.id));
      if (!record) {
        const item=document.createElement("li");item.className="dialogue-entry";item.dataset.message=String(entry.id);
        const author=document.createElement("div");author.className="dialogue-author";
        const avatar=document.createElement("span");avatar.className="dialogue-portrait";
        const name=document.createElement("strong");author.append(avatar,name);
        const body=document.createElement("p");item.append(author,body);
        const delivery = document.createElement("small");
        delivery.className = "communication-delivery";
        delivery.textContent = "✓ Discord alert sent";
        delivery.hidden = true;
        item.append(delivery);
        record={item,avatar,name,body,delivery};rows.set(String(entry.id),record);
      }
      record.outgoing = (entry.author_id ?? entry.sender) === senderRecord?.id;
      portrait(record.avatar,{label:entry.callsign,portrait:entry.portrait});
      record.name.textContent=entry.callsign;record.body.textContent=entry.body;
      return record.item;
    }));
    paintDeliveries();
    history.scrollTop = scroll ? history.scrollHeight : thread.restoreScroll ?? (atBottom ? history.scrollHeight : priorScroll);
    delete thread.restoreScroll;
    markRead(thread, Math.max(0, ...entries.filter(entry =>
      (entry.author_id ?? entry.sender) === (recipient?.id ?? thread.id)).map(entry => entry.id)));
    if (thread.message !== undefined) {
      const entry = history.querySelector(`[data-message="${CSS.escape(String(thread.message))}"]`);
      if (entry) {
        entry.tabIndex = -1;
        entry.focus({preventScroll:true});
        entry.scrollIntoView({block:"nearest"});
      }
      delete thread.message;
    }
  }

  async function reload(thread, scroll) {
    try {
      await load(thread, scroll);
    } catch (error) {
      if (thread === active) feedback.textContent = error.message;
    }
  }

  function open(contact, message, options = {}) {
    const key = contact.id + (options.draftKey ? ":" + options.draftKey : "");
    const previous = threads.get(key);
    active = previous ?? {...contact, intent:null, draft:options.draft ?? "",pending:false};
    Object.assign(active,contact,{message});
    threads.set(key,active);
    returnTo = desk.open ? {id:contact.id, scroll:desk.scrollTop} : null;
    back.hidden = !returnTo;
    active.restoreScroll = previous?.scroll;
    document.getElementById("communication-title").textContent = contact.label;
    showParties(senderRecord,contact);
    feedback.textContent = active.feedback ?? "";
    history.replaceChildren();
    document.getElementById("communication-message").value = active.draft;
    document.getElementById("communication-message").readOnly = active.pending;
    submit.disabled = active.pending;
    if (!dialog.open) dialog.showModal();
    reload(active, previous?.scroll == null);
    refreshDelivery();
  }

  dialog.addEventListener("close", () => {
    if (dialog.open) return;
    if (active) active.scroll = history.scrollTop;
    active = null;
    if (desk.open && returnTo) {
      list.querySelector(`[data-contact="${CSS.escape(returnTo.id)}"]`)?.focus({preventScroll:true});
      desk.scrollTop = returnTo.scroll;
    }
    returnTo = null;
  });
  back.addEventListener("click", () => dialog.close());
  message.addEventListener("input",() => {
    if (active) active.draft = message.value;
  });
  refresh.addEventListener("click", () => {
    if (!active || active.pending) return;
    feedback.textContent = "";
    reload(active);
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!active || active.pending) return;
    const thread = active;
    const text = message.value.trim();
    if (!text) return;
    if (thread.intent?.text !== text) thread.intent = {text, key:crypto.randomUUID()};
    thread.pending = true;
    thread.feedback = "TRANSMITTING…";
    feedback.textContent = thread.feedback;
    message.readOnly = true;
    submit.disabled = true;
    try {
      const result = await request(thread.id, {
        method:"POST",
        headers:{"Content-Type":"application/json","Idempotency-Key":thread.intent.key},
        body:JSON.stringify({text}),
      });
      if (thread.draft.trim() === text) thread.draft = "";
      thread.intent = null;
      thread.feedback = "TRANSMISSION FILED";
      if (thread !== active) return;
      message.value = thread.draft;
      feedback.textContent = thread.feedback;
      await reload(thread, true);
      if (result.dm_receipt) refreshDelivery();
    } catch (error) {
      thread.feedback = error.message + " Retry this transmission to check the same record.";
      if (thread === active) feedback.textContent = thread.feedback;
    } finally {
      thread.pending = false;
      if (thread === active) {
        submit.disabled = false;
        message.readOnly = false;
      }
    }
  });

  function renderContacts() {
    const order = new Map([...list.querySelectorAll("[data-contact]")].map((button,index) => [button.dataset.contact,index]));
    const focused = document.activeElement?.closest("[data-contact]")?.dataset.contact;
    const sorted = [...contacts].sort((a,b) => desk.open && order.size
      ? (order.get(a.id) ?? Infinity) - (order.get(b.id) ?? Infinity)
      : Number(isUnread(b)) - Number(isUnread(a)) || (b.latest_message ?? 0) - (a.latest_message ?? 0));
    list.replaceChildren(...sorted.map(contact => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const name = document.createElement("strong");
      const role = document.createElement("span");
      const image = document.createElement("span");
      button.type = "button";
      button.dataset.contact = contact.id;
      button.setAttribute("aria-haspopup", "dialog");
      name.className = "contact-name";
      name.textContent = contact.label;
      name.title = contact.label;
      role.className = "eyebrow";
      role.textContent = contact.bot ? "Handler · Bot" : contact.role === contact.label ? "Foundation command" : contact.role;
      image.className = "dialogue-portrait";
      portrait(image,contact);
      image.removeAttribute("aria-label");
      image.setAttribute("aria-hidden", "true");
      button.append(image,name,role);
      button.addEventListener("click", () => open(contact));
      item.append(button);
      return item;
    }));
    paintUnread();
    if (focused) list.querySelector(`[data-contact="${CSS.escape(focused)}"]`)?.focus({preventScroll:true});
  }
  desk.addEventListener("beforetoggle", event => {
    if (event.newState === "open") renderContacts();
  });

  function update(nextContacts, mailbox) {
    if (identity !== mailbox) {
      if (dialog.open) dialog.close();
      active = null;
      sequence++;
      threads.clear();
      rows.clear();participantCards.clear();senderRecord=undefined;participants?.replaceChildren();
      list.replaceChildren();
      deliveries.clear();
      seen = {};
      try { seen = JSON.parse(localStorage.getItem("foundation-comms:" + mailbox) ?? "{}") ?? {}; } catch {}
      message.value = "";
      identity = mailbox;
    }
    contacts = nextContacts ?? [];
    panel.hidden = !nextContacts;
    onUpdate(contacts);
    renderContacts();
    if (active && !contacts.some(contact => contact.id === active.id)) dialog.close();
    for (const [key,thread] of threads) {
      if (!contacts.some(contact => contact.id === thread.id)) threads.delete(key);
    }
  }

  return {open, update, reading:() => dialog.open, setDeliveries(receipts) {
    deliveries = new Map(receipts.map(receipt => [String(receipt.record), receipt.recipients[0]?.status]));
    paintDeliveries();
  }};
}
