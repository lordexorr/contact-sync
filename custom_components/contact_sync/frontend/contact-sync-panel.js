// Contact Sync's page in Home Assistant's sidebar. Everything it shows, words included, comes from the
// integration's websocket commands; this lays it out and sends back what's clicked and typed.
import { LitElement, html, css, nothing } from "./lit-core.min.js";

const BASE = "/contact-sync";
const CUSTOM = "__custom__"; // the dropdowns' Custom… and New group… choice, which opens a box to type in
const PENDING = { edit: "Discard my edit", delete: "Don't delete", new: "Discard this new contact" };
const n = (x) => Number(x).toLocaleString();
const enc = encodeURIComponent;

class ContactSyncPanel extends LitElement {
  static get properties() {
    return {
      narrow: { type: Boolean },
      route: { attribute: false },
      _page: { state: true },
      _data: { state: true },
      _error: { state: true },
      _flash: { state: true },
      _toast: { state: true },
      _find: { state: true },
      _open: { state: true },
      _busy: { state: true },
    };
  }

  constructor() {
    super();
    this._data = undefined; // undefined while loading; null when there's nothing yet, before the first check
    this._error = "";
    this._flash = null;
    this._toast = null;
    this._find = "";
    this._open = {}; // which Custom… and New group… boxes are open
    this._busy = false;
    this._form = null;
    this._onPop = () => this._load();
  }

  // Not a reactive property: Home Assistant hands over a new hass with every state change in the house.
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this.isConnected) this._load();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener("popstate", this._onPop);
    if (this._hass) this._load();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("popstate", this._onPop);
    clearTimeout(this._timer);
  }

  updated(changed) {
    if (changed.has("route") && this._hass && location.pathname + location.search !== this._loaded) this._load();
  }

  // --- Loading and moving between pages ---

  async _load(refresh = false) {
    clearTimeout(this._timer);
    const where = location.pathname + location.search;
    this._loaded = where;
    const path = location.pathname.slice(BASE.length).replace(/\/$/, "") || "/";
    const person = new URLSearchParams(location.search).get("person") || "";
    const pages = {
      "/": ["home", { type: "contact_sync/home" }, 5000],
      "/review": ["review", { type: "contact_sync/review" }],
      "/contacts": ["contacts", { type: "contact_sync/contacts" }],
      "/contact": ["contact", { type: "contact_sync/contact", person }],
      "/edit": ["form", { type: "contact_sync/form", person }],
      "/new": ["form", { type: "contact_sync/form" }],
      "/apply": ["apply", { type: "contact_sync/apply_page", person }, 5000],
      "/result": ["result", { type: "contact_sync/result" }, 5000],
    };
    const [page, msg, every] = pages[path] || pages["/"];
    if (!refresh) {
      this._page = page;
      this._data = undefined;
      this._error = "";
    }
    let data;
    try {
      data = await this._hass.callWS(msg);
    } catch (err) {
      if (this._loaded === where) this._error = err.message || err.code || String(err);
      return;
    }
    if (this._loaded !== where) return; // moved on meanwhile
    if (page === "apply" && data && data.applying) {
      this._go("/result", { replace: true });
      return;
    }
    this._data = data;
    if (page === "form" && !refresh) this._form = this._formState(data);
    // While a check or an apply runs, the page follows along.
    const running = data && (data.checking || data.applying || data.running);
    if (every && running) this._timer = setTimeout(() => this._load(true), every);
  }

  _go(path, { flash = null, replace = false } = {}) {
    this._flash = flash;
    if (replace) history.replaceState(null, "", BASE + path);
    else history.pushState(null, "", BASE + path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace } }));
    window.scrollTo(0, 0);
    this._load();
  }

  _link(path, text, cls = "") {
    return html`<a class=${cls} href=${BASE + path} @click=${(e) => this._follow(e, () => this._go(path))}>${text}</a>`;
  }

  // A page elsewhere in Home Assistant.
  _haLink(path, text) {
    return html`<a href=${path} @click=${(e) => this._follow(e, () => {
      history.pushState(null, "", path);
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    })}>${text}</a>`;
  }

  _follow(e, go) {
    if (e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; // a new tab, as the browser does it
    e.preventDefault();
    e.stopPropagation();
    go();
  }

  async _call(msg) {
    return this._hass.callWS(msg);
  }

  // A choice on the review page, saved the moment it's made. The page then shows the review as it is now.
  async _decide(kind, args) {
    let saved = true;
    try {
      await this._call({ type: "contact_sync/decide", kind, args });
      this._showToast("Saved", false);
    } catch (err) {
      saved = false;
      this._showToast("Couldn't save that. Try again.", true);
    }
    await this._load(true);
    if (!saved) {
      await this.updateComplete;
      this._resync();
    }
  }

  // After a choice that couldn't be saved, every tick, choice and dropdown shows what's saved again. Otherwise they'd
  // keep what was clicked, since the page drawn from the unchanged review has nothing new to set them to.
  _resync() {
    for (const box of this.shadowRoot.querySelectorAll("input[data-on]")) box.checked = box.dataset.on === "1";
    for (const list of this.shadowRoot.querySelectorAll("select[data-value]")) list.value = list.dataset.value;
  }

  // The button is drawn again for whatever takes this item's place once the review is shown again, so it's enabled
  // again after saving.
  async _click(e, kind, args) {
    const button = e.currentTarget;
    button.disabled = true;
    await this._decide(kind, args);
    button.disabled = false;
  }

  _showToast(text, bad) {
    clearTimeout(this._toastTimer);
    this._toast = { text, bad };
    this._toastTimer = setTimeout(() => {
      this._toast = null;
    }, 2000);
  }

  _setOpen(key, open) {
    this._open = Object.assign({}, this._open, { [key]: open });
    if (open) this.updateComplete.then(() => {
      const box = this.shadowRoot.querySelector(`[data-custom="${CSS.escape(key)}"] input`);
      if (box) box.focus();
    });
  }

  // Saves what was typed in an open Custom… or New group… box.
  _saveTyped(e, key, kind, args, field) {
    const box = e.currentTarget.closest(".custom").querySelector("input");
    const text = box.value.trim();
    if (!text) return;
    e.currentTarget.disabled = true;
    this._setOpen(key, false);
    this._decide(kind, Object.assign({}, args, { [field]: text }));
  }

  _typedBox(key, max, placeholder, save) {
    return html`<span class="custom" data-custom=${key}>
      <input type="text" maxlength=${max} placeholder=${placeholder} @keydown=${(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          e.currentTarget.nextElementSibling.click();
        }
      }}><button @click=${save}>Save</button></span>`;
  }

  // --- Layout ---

  render() {
    return html`
      <div class="toolbar">
        <ha-menu-button .hass=${this._hass} .narrow=${this.narrow}></ha-menu-button>
        <div class="title">Contact Sync</div>
      </div>
      <main>
        ${this._error ? html`<div class="flash error">${this._error}</div>` : nothing}
        ${this._data === undefined ? (this._error ? nothing : html`<p class="muted">Loading…</p>`) : this._body()}
      </main>
      ${this._toast ? html`<div class="toast ${this._toast.bad ? "error" : ""}">${this._toast.text}</div>` : nothing}`;
  }

  _body() {
    const d = this._data;
    switch (this._page) {
      case "review": return this._review(d);
      case "contacts": return this._contacts(d);
      case "contact": return this._contact(d);
      case "form": return this._formPage(d);
      case "apply": return this._applyPage(d);
      case "result": return this._result(d);
      default: return this._home(d);
    }
  }

  _flashBox() {
    return this._flash ? html`<div class="flash ${this._flash[0]}">${this._flash[1]}</div>` : nothing;
  }

  // Undecided items on top, decided ones folded away, where the other choice is still a click away.
  _section(title, intro, waiting, decided) {
    return html`<section class="card"><h2>${title}</h2>${intro}
      ${waiting.length ? waiting : html`<p class="muted">Nothing left to decide.</p>`}
      ${decided.length ? html`<details class="fold"><summary>Decided (${decided.length})</summary>${decided}</details>` : nothing}
    </section>`;
  }

  _thumb(url, cls = "") {
    return url ? html`<img class="thumb ${cls}" src=${url} alt="">` : nothing;
  }

  // One copy of a contact, with everything it holds, for the side-by-side cards.
  _copy(c, heading) {
    return html`<div><div class="muted">${heading}</div><b>${c.name}</b>${this._thumb(c.thumb)}
      ${c.lines.map((line) => html`<div>${line}</div>`)}
      ${c.updated ? html`<div class="muted">${c.updated}</div>` : nothing}</div>`;
  }

  _pendingButtons(key, pending) {
    if (!pending) return nothing;
    return html`${pending !== "delete" ? this._link(`/edit?person=${enc(key)}`, "Edit", "button secondary") : nothing}
      <button class="secondary" @click=${(e) => this._discard(e, key)}>${PENDING[pending]}</button>`;
  }

  async _discard(e, key) {
    e.currentTarget.disabled = true;
    await this._call({ type: "contact_sync/discard", person: key });
    this._go("/contacts", { flash: ["ok", "Discarded. Nothing was written to any account."] });
  }

  // --- The Contact Sync page ---

  _home(d) {
    const busy = d.applying ? "Applying…" : d.checking ? "Checking…" : "";
    const accounts = d.accounts
      ? html`<div class="scroll"><table><thead><tr><th>Account</th><th class="num">Contacts</th><th class="num">Groups</th><th>Status</th></tr></thead>
          <tbody>${d.accounts.length ? d.accounts.map((a) => this._accountRow(a))
            : html`<tr><td colspan="4" class="muted">No accounts set up yet.</td></tr>`}</tbody></table></div>
          <p class="muted">Last checked ${d.checked}.</p>`
      : html`<p class="muted">Not checked yet.</p>`;
    return html`<h1>Contact Sync</h1>
      <p class="muted">Checks every account daily, and writes nothing until you apply the reviewed changes.</p>
      ${this._flashBox()}
      <section class="card"><h2>Accounts</h2>
        ${d.check_error ? html`<p class="bad">${d.check_error}</p>` : nothing}
        ${accounts}
        <div class="row"><button ?disabled=${!!busy} @click=${this._checkNow}>${busy || "Check now"}</button>
          <span class="muted">Next daily check ${d.next_check}.</span></div>
        <p class="muted">${d.set_up ? "Accounts are added and removed" : "Add each iCloud and Google account"} under
          ${this._haLink("/config/integrations/integration/contact_sync", "Contact Sync in Devices & services")}.</p>
      </section>
      ${this._reviewCard(d)}`;
  }

  _accountRow(a) {
    const login = a.login && a.login !== a.name ? html`<div class="muted">${a.login}</div>` : nothing;
    return html`<tr><td>${a.service} · ${a.name}${login}</td>
      ${a.error ? html`<td class="num">–</td><td class="num">–</td><td><span class="bad">${a.error}</span></td>`
        : html`<td class="num">${n(a.contacts)}</td><td class="num">${n(a.groups)}</td><td><span class="ok">Connected</span></td>`}</tr>`;
  }

  async _checkNow(e) {
    e.currentTarget.disabled = true;
    await this._call({ type: "contact_sync/check" });
    this._load(true);
  }

  _reviewCard(d) {
    const r = d.review;
    const body = !r.ready ? html`<p class="muted">Nothing to review until the first check has run.</p>`
      : html`${r.waiting ? html`<p>${r.waiting}</p>`
          : html`<p class="ok">${r.matches}</p>${r.kept ? html`<p class="muted">${r.kept}</p>` : nothing}`}
        <div class="row">${this._link("/review", "Open the review", "button")}${this._link("/contacts", "Contacts", "button secondary")}</div>`;
    const last = d.applying ? html`<p>Applying changes… ${this._link("/result", "Follow it")}</p>`
      : d.last_apply ? html`<p class="muted">Last applied ${d.last_apply.when}: ${d.last_apply.summary}. ${this._link("/result", "Details")}</p>`
      : nothing;
    return html`<section class="card"><h2>Review</h2>${body}${last}</section>`;
  }

  // --- The review ---

  _review(d) {
    const top = html`<p>${this._link("/", "← Contact Sync")}</p>${this._flashBox()}<h1>Review</h1>`;
    if (!d) return html`${top}<p class="muted">Nothing to review until the first check has run.</p>`;
    return html`${top}
      <p class="muted">Nothing is written to any account until you apply. Everything you choose is saved as you click it,
        and kept for later checks.</p>
      <p>${d.counts}</p>
      ${d.warnings.map((w) => html`<div class="flash error">${w}</div>`)}
      ${d.suggestions.length || d.decided_matches.length ? this._suggestions(d) : nothing}
      ${d.duplicates.length ? this._duplicates(d) : nothing}
      ${d.extras.length ? this._extras(d) : nothing}
      ${d.conflicts.length ? this._conflicts(d) : nothing}
      ${d.ungrouped.length ? this._ungrouped(d) : nothing}
      ${d.people.length || d.groups.length ? this._changes(d) : nothing}
      ${d.can_apply ? html`<div class="row">${this._link("/apply", "Apply changes…", "button")}</div>` : nothing}
      <section class="card"><h2>Start over</h2><p class="muted">Forget every match, choice and skip made on this page.</p>
        <details class="fold"><summary>Forget my decisions…</summary>
          <p>Every row you unticked comes back ticked, every possible match is asked again, and every value you picked
            goes back to the one marked. Nothing is written to any account until you apply.</p>
          <button class="secondary" @click=${this._reset}>Yes, forget my decisions</button></details></section>`;
  }

  async _reset(e) {
    e.currentTarget.disabled = true;
    await this._call({ type: "contact_sync/decide", kind: "reset" });
    this._go("/review", { flash: ["ok", "Every match, choice and skip is forgotten."], replace: true });
  }

  _suggestions(d) {
    const labels = { same: "Same person", different: "Different people" };
    const waiting = d.suggestions.map((s) => html`<div class="item"><p class="muted">${s.reason}</p>
      <div class="pair">${s.contacts.map((c) => this._copy(c, c.account))}</div>
      <div class="row"><button class="match" @click=${(e) => this._click(e, "match", { pair: s.id, decision: "same" })}>Same person</button>
        <button class="match secondary" @click=${(e) => this._click(e, "match", { pair: s.id, decision: "different" })}>Different people</button></div></div>`);
    const decided = d.decided_matches.map((s) => {
      const other = s.decision === "same" ? "different" : "same";
      return html`<div class="item"><div class="pair">${s.contacts.map((c) => this._copy(c, c.account))}</div>
        <div class="row"><span class="muted">You said: ${labels[s.decision]}.</span>
          <button class="match secondary" @click=${(e) => this._click(e, "match", { pair: s.id, decision: other })}>Change to ${labels[other]}</button></div></div>`;
    });
    return this._section(`Possible matches (${d.suggestions.length} to decide)`, nothing, waiting, decided);
  }

  _duplicates(d) {
    const card = (x) => html`<div class="item"><b>${x.person}</b> · ${x.copies.length} cards in ${x.account}
      <div class="pair">${x.copies.map((c) => this._copy(c, c.kept ? "Kept if merged" : "Another card"))}</div>
      <div class="row">${x.choice ? html`<span class="muted">${x.choice === "merge" ? "Merging into one card." : "Keeping every card."}</span>` : nothing}
        ${[["merge", "Merge into one"], ["keep", "Keep both"]].filter(([value]) => value !== x.choice).map(([value, text]) =>
          html`<button class=${value === "merge" ? "dup" : "dup secondary"} @click=${(e) => this._click(e, "duplicate", { id: x.id, decision: value })}>${text}</button>`)}
      </div></div>`;
    const waiting = d.duplicates.filter((x) => !x.choice).map(card);
    return this._section(`Duplicates within one account (${waiting.length} to decide)`,
      html`<p class="muted">The same person more than once in one account. <b>Merge into one</b> moves everything from the
        other cards onto the one with the most details, including details Contact Sync doesn't otherwise use, then deletes
        the others when you apply. <b>Keep both</b> leaves them as they are. Until you choose, applying leaves the extra
        cards alone.</p>`,
      waiting, d.duplicates.filter((x) => x.choice).map(card));
  }

  _extras(d) {
    const card = (x) => html`<div class="item"><b>${x.person}</b><div class="scroll"><table><tbody>${x.entries.map((e) => {
      const options = (e.kind === "company" ? [["main", "Main company"]] : []).concat([["notes", "Move to Notes"], ["delete", "Delete"]]);
      return html`<tr><td>${e.text}<div class="muted">${e.current ? "Every account" : `Only in ${e.accounts.join(", ")}`}</div></td>
        <td>${options.map(([value, text]) => html`<label class="option"><input type="radio" class="extra" name=${e.id} .checked=${e.choice === value} data-on=${e.choice === value ? "1" : "0"}
          @change=${() => this._decide("extra", { id: e.id, choice: value })}> ${text}</label>`)}</td></tr>`;
    })}</tbody></table></div></div>`;
    const waiting = d.extras.filter((x) => !x.complete).map(card);
    return this._section(`Details only Google can hold (${waiting.length} to decide)`,
      html`<p class="muted">iCloud has room for one company and job title and no location. For each person, choose the main
        company, which every account will show, and move each other detail to Notes or delete it. Until everything about a
        person is chosen, these details stay as they are.</p>`,
      waiting, d.extras.filter((x) => x.complete).map(card));
  }

  // Until a value is picked, nothing is selected and the value that will be used is marked, so any click counts as a
  // decision. Leave as they are unticks the value's row, and picking a value after it ticks the row again.
  _conflicts(d) {
    const item = (c) => {
      const left = !!c.left;
      const options = c.options.map((o) => html`<label class="option">
        <input type="radio" class="pick" data-conflict=${c.id} name=${"choice-" + c.id} .checked=${c.decided && !left && o.key === c.chosen}
          data-on=${c.decided && !left && o.key === c.chosen ? "1" : "0"}
          @change=${() => this._decide("pick", { conflict: c.id, choice: o.key, seen: c.seen, row: left ? c.row : "" })}>
        ${o.thumb ? this._thumb(o.thumb) : html`<span>${o.value}</span>`}<span class="muted">${o.accounts.join(", ")}</span>
        ${!c.decided && !left && o.key === c.chosen ? html`<span class="muted">· used unless you pick another</span>` : nothing}</label>`);
      const leave = c.row ? html`<label class="option"><input type="radio" class="leave" data-id=${c.row} name=${"choice-" + c.id} .checked=${left} data-on=${left ? "1" : "0"}
          @change=${() => this._decide("skip", { id: c.row, keep: false, seen: c.row_seen })}>
        <span>Leave as they are</span><span class="muted">each account keeps its own</span></label>` : nothing;
      const waits = c.required && !c.decided
        ? html`<p class="muted">${c.waiting || "Until you choose, every account keeps its own order."}</p>` : nothing;
      return html`<div class="item"><b>${c.person}</b> · ${c.field}${options}${leave}${waits}</div>`;
    };
    const waiting = d.conflicts.filter((c) => !(c.decided || c.left)).map(item);
    return this._section(`Different values (${waiting.length} to decide)`,
      html`<p class="muted">Pick the value every account should have, or <b>Leave as they are</b> to keep each account's own.</p>`,
      waiting, d.conflicts.filter((c) => c.decided || c.left).map(item));
  }

  _ungrouped(d) {
    const card = (u) => {
      const key = "group:" + u.id;
      const open = !!this._open[key];
      const said = u.groups.length ? `Joins ${u.groups.join(", ")} when you apply.` : u.decided ? "Staying in no group." : "";
      return html`<div class="item">${this._copy(u.contact, "")}<div class="row">
        ${said ? html`<span class="muted">${said}</span>` : nothing}
        <select class="group" data-value=${open ? CUSTOM : u.chosen} @change=${(e) => this._groupChosen(e, key, u.id)}>
          <option value="" .selected=${!open && !u.chosen}>Choose a group</option>
          ${d.group_choices.map((g) => html`<option .value=${g} .selected=${!open && g === u.chosen}>${g}</option>`)}
          <option value=${CUSTOM} .selected=${open}>New group…</option></select>
        ${open ? this._typedBox(key, 60, "Group name", (e) => this._saveTyped(e, key, "group", { id: u.id }, "group")) : nothing}
        ${u.decided && !u.groups.length ? nothing
          : html`<button class="no-group secondary" @click=${(e) => this._click(e, "group", { id: u.id, group: "" })}>No group</button>`}
        ${this._link(`/edit?person=${enc(u.id)}`, "Edit", "button secondary")}</div></div>`;
    };
    const waiting = d.ungrouped.filter((u) => !u.decided).map(card);
    return this._section(`Not in a group (${waiting.length} to decide)`,
      html`<p class="muted">Choose a group, and applying adds them to it in every account. <b>No group</b> stops asking
        about them, unless they join a group and later leave it. For more than one group, use <b>Edit</b>. Until you
        choose, they stay as they are.</p>`,
      waiting, d.ungrouped.filter((u) => u.decided).map(card));
  }

  _groupChosen(e, key, id) {
    const value = e.target.value;
    this._setOpen(key, value === CUSTOM);
    if (value && value !== CUSTOM) this._decide("group", { id, group: value });
  }

  // A comparison table per person, and one for groups. Rows still waiting first; unticked rows folded away under
  // Ignored, where ticking one brings it back.
  _changes(d) {
    const tables = (skipped) => d.people.map((p) => this._table(p.name, d.columns, p.rows.filter((r) => r.skipped === skipped),
      skipped ? nothing : this._personFooter(p), false))
      .concat([this._table("Groups", d.columns, d.groups.filter((r) => r.skipped === skipped), nothing, false)])
      .filter((t) => t !== nothing);
    const waiting = tables(false);
    const ignored = tables(true);
    return html`<section class="card"><h2>Changes</h2>
      <p class="muted">Each table shows what every account has now, and in the green last column what all of them will have
        after the sync. Struck-through values would be replaced or removed, and values marked + would be added. Untick a
        row to leave every account as it is. In a list, untick a value to leave it out of every account.</p>
      <p class="muted">Something deleted from one account since the last sync is deleted from the others too. In a list
        such a value starts unticked: tick it to keep it everywhere instead.</p>
      ${waiting.length ? waiting : html`<p class="muted">Nothing waiting.</p>`}
      ${ignored.length ? html`<details class="fold"><summary>Ignored (${n(d.ignored)})</summary>
        <p class="muted">Tick a row to bring it back.</p>${ignored}</details>` : nothing}</section>`;
  }

  _personFooter(p) {
    if (p.held) return html`<p class="muted">Waiting on a possible match above. Answer it to apply this person's changes.</p>`;
    const buttons = this._pendingButtons(p.key, p.pending);
    if (!p.can_apply) return buttons === nothing ? nothing : html`<div class="row">${buttons}</div>`;
    return html`<div class="row">${this._link(`/apply?person=${enc(p.key)}`, `Apply just ${p.name}…`, "button secondary")}${buttons}</div>`;
  }

  // readonly tables are to see, on a card or an Apply page: ticks and labels are changed in the review.
  _table(title, columns, rows, footer, readonly) {
    if (!rows.length) return nothing;
    return html`<div class="item"><b>${title}</b><div class="scroll"><table class="compare">
      <thead><tr><th></th>${columns.map((c) => html`<th>${c}</th>`)}<th>After sync</th></tr></thead>
      <tbody>${rows.map((r) => this._row(r, columns, readonly))}</tbody></table></div>${footer}</div>`;
  }

  _row(r, columns, readonly) {
    return html`<tr><th><label><input type="checkbox" class="skip" data-id=${r.id} .checked=${!r.skipped} data-on=${r.skipped ? "0" : "1"} ?disabled=${readonly}
        @change=${(e) => this._decide("skip", { id: r.id, keep: e.target.checked, seen: r.seen || "" })}> ${r.title}</label></th>
      ${columns.map((c) => html`<td>${this._cell(r.cells[c] || [])}</td>`)}
      <td class="after">${this._after(r.after, readonly)}</td></tr>`;
  }

  // An account's current values: struck through when the sync replaces or removes them, "+" for values it would gain,
  // "−" for members a group would lose, a note on an empty cell the sync would fill, and plain notes.
  _cell(items) {
    return items.map((i) => {
      const state = i.state || "";
      if ("thumb" in i) return this._thumb(i.thumb, state);
      if (state === "old") return html`<div class="old">${i.text}</div>`;
      if (state === "new") return html`<div class="new">+ ${i.text}</div>`;
      if (state === "gone") return html`<div class="gone">− ${i.text}</div>`;
      if (state === "note") return html`<div class="muted">${i.text}</div>`;
      if (state === "add") return html`<div>${i.text} <span class="new">· will be added</span></div>`;
      return html`<div>${i.text}</div>`;
    });
  }

  _after(a, readonly) {
    if (a.kind === "photo") return this._thumb(a.thumb);
    if (a.kind === "values") {
      // One box per value: unticked means every account ends up without it.
      return a.items.map((i) => html`<label class="value"><input type="checkbox" class="skip" data-id=${i.id} .checked=${i.kept} data-on=${i.kept ? "1" : "0"} ?disabled=${readonly}
          @change=${(e) => this._decide("skip", { id: i.id, keep: e.target.checked, seen: "" })}> ${i.text}</label>
        ${i.note ? html`<div class="muted note">${i.note}</div>` : nothing}`);
    }
    if (a.kind === "label") {
      // Custom… opens a box for typing any label; iCloud and Google both keep custom labels as typed.
      const key = "label:" + a.id;
      const open = !readonly && !!this._open[key];
      return html`<select class="label" data-value=${open ? CUSTOM : a.chosen} ?disabled=${readonly} @change=${(e) => this._labelChosen(e, key, a)}>
          ${a.options.map(([value, text]) => html`<option .value=${value} .selected=${!open && value === a.chosen}>${text}</option>`)}
          <option value=${CUSTOM} .selected=${open}>Custom…</option></select>
        ${open ? this._typedBox(key, 40, "Label", (e) => this._saveTyped(e, key, "label", { id: a.id, seen: a.seen }, "label")) : nothing}`;
    }
    return html`<div>${a.value}</div>${a.details ? html`<details><summary class="muted">Details</summary>${a.details}</details>` : nothing}`;
  }

  _labelChosen(e, key, a) {
    const value = e.target.value;
    this._setOpen(key, value === CUSTOM);
    if (value !== CUSTOM) this._decide("label", { id: a.id, label: value, seen: a.seen });
  }

  // --- Applying ---

  _applyPage(d) {
    if (!d) return html`<h1>Apply changes</h1><p class="muted">Nothing to apply until the first check has run.</p>`;
    const top = html`<p>${this._link("/review", "← Review")}</p>${this._flashBox()}<h1>${d.title}</h1>`;
    const back = this._link("/review", "Back to the review");
    const notes = d.notes.map((note) => html`<p class="muted">${note}</p>`);
    const buttons = this._pendingButtons(d.person, d.pending);
    const discard = buttons === nothing ? nothing : html`<div class="row">${buttons}</div>`;
    if (d.empty) return html`${top}${notes}<p>Nothing to apply.</p>${discard}<p>${back}</p>`;
    if (d.checking) return html`${top}<p class="muted">A check is running. This page is ready once it finishes.</p>`;
    return html`${top}${this._table("What changes", d.columns, d.changes, nothing, true)}${this._totals(d.totals)}${notes}
      <p>When you press <b>Apply now</b>, Contact Sync:</p><ol>${d.steps.map((step) => html`<li>${step}</li>`)}</ol>
      <div class="row"><button ?disabled=${this._busy} @click=${() => this._applyNow(d)}>Apply now</button>${back}</div>${discard}`;
  }

  _totals(rows) {
    return html`<div class="scroll"><table><thead><tr><th>Account</th><th class="num">Contacts added</th><th class="num">Updated</th>
      <th class="num">Deleted</th><th>Groups</th><th>Group members</th></tr></thead>
      <tbody>${rows.map((t) => html`<tr><td>${t.account}</td><td class="num">${n(t.added)}</td><td class="num">${n(t.updated)}</td>
        <td class="num">${n(t.deleted)}</td><td>${t.groups}</td><td>${t.members}</td></tr>`)}</tbody></table></div>`;
  }

  async _applyNow(d) {
    this._busy = true;
    try {
      const res = await this._call({ type: "contact_sync/apply", person: d.person, token: d.token });
      if (res.started) this._go("/result");
      else this._go("/review", { flash: ["error", "A check is running. Apply once it has finished."] });
    } finally {
      this._busy = false;
    }
  }

  _result(d) {
    const top = html`<p>${this._link("/", "← Contact Sync")}</p>`;
    if (d.running) {
      return html`${top}<h1>Applying changes…</h1><p>${d.step}${d.count ? ` · ${d.count}` : ""}</p>
        <p class="muted">This page updates itself. Leaving it doesn't stop anything.</p>`;
    }
    if (!d.done) return html`${top}<h1>Apply</h1><p class="muted">Nothing has been applied yet.</p>`;
    return html`${top}<h1>${d.title}</h1><p class="muted">${d.when}</p>
      ${d.message ? html`<p class=${d.bad ? "bad" : "muted"}>${d.message}</p>` : nothing}
      ${d.backup ? html`<p class="muted">Backed up first to <code>${d.backup}</code>, in Home Assistant's config folder.</p>` : nothing}
      ${d.failed.length ? html`<section class="card"><h2>Not made (${n(d.failed.length)})</h2>${this._changeTable(d.failed)}</section>` : nothing}
      ${d.made.length ? html`<section class="card"><h2>Made (${n(d.made.length)}${d.to_check ? ` · ${n(d.to_check)} to check` : ""})</h2>
        ${this._changeTable(d.made)}</section>` : nothing}
      <div class="row">${this._link("/review", "Open the review", "button")}</div>`;
  }

  // A last column says why a change wasn't made, or what to check about one that was.
  _changeTable(changes) {
    const notes = changes.some((c) => c.error || c.warning);
    return html`<div class="scroll"><table><thead><tr><th>Account</th><th>Contact or group</th><th>Change</th>
      ${notes ? html`<th>${changes.some((c) => c.error) ? "Why not" : "Check"}</th>` : nothing}</tr></thead>
      <tbody>${changes.map((c) => html`<tr><td>${c.account}</td><td>${c.subject}</td><td>${c.what}</td>
        ${notes ? html`<td class="bad">${c.error || c.warning || ""}</td>` : nothing}</tr>`)}</tbody></table></div>`;
  }

  // --- Contacts ---

  _lines(items) {
    return items.map((i) => html`<div>${i.text}${i.where ? html` <span class="muted where">${i.where}</span>` : nothing}</div>`);
  }

  _contacts(d) {
    const top = html`<p>${this._link("/", "← Contact Sync")}</p>${this._flashBox()}<h1>Contacts</h1>`;
    if (!d) return html`${top}<p class="muted">Nothing to show until the first check has run.</p>`;
    const words = { edit: "Edit", delete: "Delete", new: "New contact" };
    const find = this._find.toLowerCase().split(/\s+/).filter(Boolean);
    const shown = d.people.filter((p) => find.every((word) => {
      const digits = word.replace(/\D/g, "");
      return p.search.includes(word) || (digits.length >= 3 && p.search.includes(digits));
    }));
    const waiting = d.waiting.length ? html`<section class="card"><h2>Waiting to be applied</h2>
      <p class="muted">Entered here, and not written to any account yet.</p>
      <ul class="plain">${d.waiting.map((w) => html`<li class="row">
        <span>${this._link(`/contact?person=${enc(w.key)}`, w.name)} <span class="muted">· ${words[w.pending]}</span></span>
        <span class="row">${this._link(`/apply?person=${enc(w.key)}`, "Apply…", "button")}${this._pendingButtons(w.key, w.pending)}</span></li>`)}
      </ul></section>` : nothing;
    return html`${top}${waiting}
      <div class="row">${this._link("/new", "New contact", "button")}</div>
      <p class="muted">What the accounts hold today. A value only some accounts have says which.</p>
      <p><input type="search" placeholder="Search by name, company, phone or email" .value=${this._find}
        @input=${(e) => { this._find = e.target.value; }}></p>
      <p class="muted">${n(shown.length)} contacts</p>
      <div class="scroll"><table class="people"><thead><tr><th>Name</th><th>Company</th><th>Phone</th><th>Email</th><th></th></tr></thead>
        <tbody>${shown.map((p) => html`<tr><td>${this._link(`/contact?person=${enc(p.key)}`, p.name)}</td>
          <td>${this._lines(p.company)}</td><td>${this._lines(p.phones)}</td><td>${this._lines(p.emails)}</td>
          <td class="muted">${p.status}</td></tr>`)}</tbody></table></div>`;
  }

  _contact(d) {
    const back = html`<p>${this._link("/contacts", "← Contacts")}</p>`;
    if (!d) return html`${back}<h1>Contact</h1><p class="muted">This contact is no longer here.</p>`;
    return html`${this._flashBox()}${back}<h1>${d.name}${this._thumb(d.thumb)}</h1><p class="muted">${d.intro}</p>
      <div class="scroll"><table class="facts"><tbody>
        ${d.rows.map((r) => html`<tr><th>${r.title}</th><td class=${r.note ? "note-text" : ""}>${r.text}${r.where
          ? html` <span class="muted where">${r.where}</span>` : nothing}</td></tr>`)}
        ${d.google_only ? html`<tr><th>Only in Google</th><td>${d.google_only} ${this._link("/review", "Decide in the review")}</td></tr>` : nothing}
      </tbody></table></div>
      ${d.where ? html`<p class="muted">${d.where}</p>` : nothing}
      ${this._table("What changes", d.columns, d.changes, nothing, true)}
      ${this._actions(d)}`;
  }

  _actions(d) {
    if (d.held) {
      return html`<p>This contact is waiting on a possible match. ${this._link("/review", "Answer it in the review")} first,
        so a change can't land on the wrong person.</p>`;
    }
    const buttons = html`<div class="row">${this._link(`/apply?person=${enc(d.key)}`, "Apply…", "button")}${this._pendingButtons(d.key, d.pending)}</div>`;
    if (d.pending === "delete") return html`<p>Waiting to be deleted from every account.</p>${buttons}`;
    if (d.pending === "new") return html`<p>This new contact is waiting to be applied.</p>${buttons}`;
    const waiting = d.pending ? html`<p>Your edit is waiting to be applied.</p>${buttons}`
      : html`<div class="row">${this._link(`/edit?person=${enc(d.key)}`, "Edit", "button")}</div>`;
    return html`${waiting}<details class="fold"><summary>Delete everywhere…</summary><p>${d.delete}</p>
      <button class="secondary" @click=${(e) => this._delete(e, d.key)}>Delete everywhere…</button></details>`;
  }

  async _delete(e, key) {
    e.currentTarget.disabled = true;
    await this._call({ type: "contact_sync/delete", person: key });
    this._go(`/apply?person=${enc(key)}`);
  }

  // --- The form ---
  // Typing changes this._form in place; adding, removing and moving rows redraws it.

  _formState(d) {
    if (!d || d.missing || d.held) return null;
    const v = JSON.parse(JSON.stringify(d.values));
    for (const [field] of d.layout.lists) v.lists[field] = v.lists[field].map((r) => Object.assign(r, { custom: false, typed: "" }));
    v.groups = v.groups.map((name) => ({ name, custom: false, typed: "" }));
    return v;
  }

  _formPage(d) {
    if (!d) return html`<h1>Contact</h1><p class="muted">Nothing to edit until the first check has run.</p>`;
    if (d.missing) return html`<h1>Contact</h1><p class="muted">This contact is no longer here.</p>`;
    if (d.held) {
      return html`<h1>${d.name}</h1><p>This contact is waiting on a possible match. ${this._link("/review", "Answer it in the review")}
        first, so a change can't land on the wrong person.</p>`;
    }
    const f = this._form;
    const back = d.key ? `/contact?person=${enc(d.key)}` : "/contacts";
    const box = (label, value, set, hint = "") => html`<label>${label}<input type="text" .value=${value} placeholder=${hint}
      @input=${(e) => set(e.target.value)}></label>`;
    return html`<p>${this._link(back, "← Back")}</p><h1>${d.title}</h1>
      ${d.errors.map((e) => html`<div class="flash error">${e}</div>`)}${this._similar(d)}
      <p class="muted">Saving writes nothing to any account. The next page shows what changes in each account, and
        <b>Apply now</b> makes the changes.</p>
      <div class="edit">
        <section class="card"><h2>Name</h2><div class="edit-grid">
          ${d.layout.names.map(([, label], i) => box(label, f.name_parts[i], (v) => { f.name_parts[i] = v; }))}</div></section>
        <section class="card"><h2>Details</h2><div class="edit-grid">
          ${box("Nickname", f.nickname, (v) => { f.nickname = v; })}${box("Company", f.company, (v) => { f.company = v; })}
          ${box("Job title", f.title, (v) => { f.title = v; })}${box("Birthday", f.birthday, (v) => { f.birthday = v; }, d.layout.date_hint)}
        </div></section>
        <section class="card"><h2>Phone numbers, addresses and more</h2>
          <p class="muted">The first in each list is the main one. Use the arrows to change the order.</p>
          ${d.layout.lists.map(([field, title, noun]) => this._listSection(d, field, title, noun))}</section>
        ${this._groupsSection(d)}
        <section class="card"><h2>Notes</h2><textarea rows="5" .value=${f.note} @input=${(e) => { f.note = e.target.value; }}></textarea></section>
        <div class="row"><button ?disabled=${this._busy} @click=${this._save}>${d.similar.length ? "Add anyway" : "Save…"}</button>
          ${this._link(back, "Cancel")}</div>
      </div>`;
  }

  // Who this may duplicate. A contact entered earlier and not applied gets a way to change or discard it.
  _similar(d) {
    if (!d.similar.length) return nothing;
    return html`<div class="flash error">This may already be here:<ul class="plain">${d.similar.map((s) => s.unapplied
      ? html`<li class="row"><span>${s.name}: you entered this contact earlier and haven't applied it, with ${s.why}.</span>
          ${this._pendingButtons(s.key, s.pending)}</li>`
      : html`<li><a href=${`${BASE}/contact?person=${enc(s.key)}`} target="_blank" rel="noopener">${s.name}</a>: ${s.why}</li>`)}
      </ul>To add this one as well, press <b>Add anyway</b>.</div>`;
  }

  _listSection(d, field, title, noun) {
    const rows = this._form.lists[field];
    return html`<h3>${title}</h3><div class="edit-list" data-field=${field}>${rows.map((r, i) => this._listRow(d, field, rows, r, i))}</div>
      <div class="row"><button class="secondary" @click=${() => this._addRow(d, field)}>Add ${"aeiou".includes(noun[0]) ? "an" : "a"} ${noun}</button></div>`;
  }

  _listRow(d, field, rows, r, i) {
    const parts = d.layout.parts;
    const value = field === "addresses"
      ? html`<div class="address-boxes"><textarea rows="2" placeholder=${parts[0][1]} .value=${r.parts[0]}
          @input=${(e) => { r.parts[0] = e.target.value; }}></textarea>
          ${parts.slice(1).map(([, label], j) => html`<input type="text" placeholder=${label} .value=${r.parts[j + 1]}
            @input=${(e) => { r.parts[j + 1] = e.target.value; }}>`)}</div>`
      : html`<input type="text" class="value-box" .value=${r.value} placeholder=${field === "dates" ? d.layout.date_hint : ""}
          @input=${(e) => { r.value = e.target.value; }}>`;
    return html`<div class="edit-row">${this._labelBox(d, field, r)}${value}<span class="row-buttons">
      <button class="secondary" title="Move up" @click=${() => this._move(rows, i, -1)}>↑</button>
      <button class="secondary" title="Move down" @click=${() => this._move(rows, i, 1)}>↓</button>
      <button class="secondary" title="Remove" @click=${() => this._remove(rows, i)}>✕</button></span></div>`;
  }

  // The labels iCloud and Google both have, this value's own if it's another, and Custom…
  _labelBox(d, field, r) {
    const same = (a, b) => a.toLowerCase() === (b || "").toLowerCase();
    const choices = d.labels[field].slice();
    if (r.label && !choices.some((c) => same(c, r.label))) choices.push(r.label);
    return html`<span class="label-choice"><select @change=${(e) => this._choose(r, "label", e.target.value)}>
        <option value="" .selected=${!r.custom && !r.label}>no label</option>
        ${choices.map((c) => html`<option .value=${c} .selected=${!r.custom && same(c, r.label)}>${c}</option>`)}
        <option value=${CUSTOM} .selected=${r.custom}>Custom…</option></select>
      ${r.custom ? html`<input type="text" class="label-custom" maxlength="40" placeholder="Label" .value=${r.typed}
        @input=${(e) => { r.typed = e.target.value; }}>` : nothing}</span>`;
  }

  // A dropdown per group the person is in, each listing every group, with a last choice for a new one.
  _groupsSection(d) {
    const rows = this._form.groups;
    const same = (a, b) => a.toLowerCase() === b.toLowerCase();
    return html`<section class="card"><h2>Groups</h2><p class="muted">Removing someone from a group never deletes the group.</p>
      <div class="edit-list" data-field="groups">${rows.map((g, i) => {
        const choices = d.group_names.slice();
        if (g.name && !choices.some((c) => same(c, g.name))) choices.push(g.name);
        return html`<div class="edit-row"><span class="group-choice"><select @change=${(e) => this._choose(g, "name", e.target.value)}>
            <option value="" .selected=${!g.custom && !g.name}>Choose a group</option>
            ${choices.map((c) => html`<option .value=${c} .selected=${!g.custom && same(c, g.name)}>${c}</option>`)}
            <option value=${CUSTOM} .selected=${g.custom}>New group…</option></select>
          ${g.custom ? html`<input type="text" class="label-custom" maxlength="60" placeholder="Name of the new group" .value=${g.typed}
            @input=${(e) => { g.typed = e.target.value; }}>` : nothing}</span>
          <span class="row-buttons"><button class="secondary" title="Remove" @click=${() => this._remove(rows, i)}>✕</button></span></div>`;
      })}</div>
      <div class="row"><button class="secondary" @click=${() => this._addRow(d, "groups")}>Add a group</button></div></section>`;
  }

  _choose(row, key, value) {
    row.custom = value === CUSTOM;
    if (row.custom) row.typed = "";
    else row[key] = value;
    this.requestUpdate();
    if (row.custom) this.updateComplete.then(() => {
      const box = this.shadowRoot.querySelector("input.label-custom:placeholder-shown");
      if (box) box.focus();
    });
  }

  async _addRow(d, field) {
    if (field === "groups") this._form.groups.push({ name: "", custom: false, typed: "" });
    else {
      this._form.lists[field].push({ label: d.new_row_labels[field], value: "", custom: false, typed: "",
        parts: field === "addresses" ? ["", "", "", "", ""] : [] });
    }
    this.requestUpdate();
    await this.updateComplete;
    const row = this.shadowRoot.querySelector(`.edit-list[data-field="${field}"] .edit-row:last-child`);
    const box = row && (row.querySelector(".value-box, textarea") || row.querySelector("select"));
    if (box) box.focus();
  }

  _move(rows, i, step) {
    const j = i + step;
    if (j < 0 || j >= rows.length) return;
    const row = rows[i];
    rows[i] = rows[j];
    rows[j] = row;
    this.requestUpdate();
  }

  _remove(rows, i) {
    rows.splice(i, 1);
    this.requestUpdate();
  }

  async _save() {
    const d = this._data;
    const f = this._form;
    const lists = {};
    for (const field of Object.keys(f.lists)) {
      lists[field] = f.lists[field].map((r) => ({ label: r.custom ? r.typed.trim() : r.label, value: r.value, parts: r.parts }));
    }
    const entered = { name_parts: f.name_parts, nickname: f.nickname, company: f.company, title: f.title,
      birthday: f.birthday, note: f.note, lists, groups: f.groups.map((g) => (g.custom ? g.typed.trim() : g.name)).filter(Boolean),
      confirmed: d.similar.length > 0 }; // what was entered again after the warning about who it may duplicate
    this._busy = true;
    try {
      const res = await this._call({ type: "contact_sync/save", person: d.key, entered });
      if (res.form) {
        this._data = res.form;
        this._form = this._formState(res.form);
        window.scrollTo(0, 0);
      } else if (res.unchanged) {
        this._go(`/contact?person=${enc(res.saved)}`, { flash: ["ok", "Nothing changed, so nothing is waiting to be applied."] });
      } else {
        this._go(`/apply?person=${enc(res.saved)}`);
      }
    } catch (err) {
      this._error = err.message || err.code || String(err);
    } finally {
      this._busy = false;
    }
  }

  static get styles() {
    return css`
      :host {
        display: block;
        min-height: 100vh;
        background: var(--primary-background-color);
        color: var(--primary-text-color);
        font: 15px/1.5 var(--ha-font-family-body, Roboto, system-ui, sans-serif);
        --muted: var(--secondary-text-color);
        --line: var(--divider-color);
        --accent: var(--primary-color);
        --on-accent: var(--text-primary-color, #fff);
        --ok: var(--success-color, #2e7d32);
        --bad: var(--error-color, #c62828);
        --field: var(--secondary-background-color);
      }
      * { box-sizing: border-box; }
      .toolbar { display: flex; align-items: center; gap: 8px; height: var(--header-height, 56px); padding: 0 12px;
        background: var(--app-header-background-color, var(--primary-color));
        color: var(--app-header-text-color, var(--text-primary-color)); font-size: 20px; }
      main { padding: 16px; }
      h1 { font-size: 22px; margin: 0 0 4px; }
      h2 { font-size: 16px; margin: 0 0 12px; }
      h3 { font-size: 15px; margin: 20px 0 8px; }
      a { color: var(--accent); }
      .card { background: var(--card-background-color); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin: 16px 0; }
      .muted { color: var(--muted); }
      .ok { color: var(--ok); }
      .bad { color: var(--bad); }
      .scroll { overflow-x: auto; }
      table { width: 100%; border-collapse: collapse; }
      th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }
      th { font-size: 13px; font-weight: 600; color: var(--muted); }
      th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
      .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin-top: 12px; }
      ul.plain { list-style: none; margin: 0 0 12px; padding: 0; }
      ul.plain li { justify-content: space-between; margin-top: 0; padding: 6px 0; border-bottom: 1px solid var(--line); }
      ol { padding-left: 20px; }
      ol li { margin-bottom: 8px; }
      button, a.button { display: inline-block; font: inherit; text-decoration: none; padding: 8px 14px; border-radius: 8px;
        border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); cursor: pointer; }
      button.secondary, a.button.secondary { background: transparent; color: var(--accent); }
      button:disabled { opacity: .6; cursor: default; }
      code { font-size: 13px; overflow-wrap: anywhere; }
      input[type=text], input[type=search], textarea { width: 100%; font: inherit; padding: 8px 10px; border: 1px solid var(--line);
        border-radius: 8px; background: var(--field); color: var(--primary-text-color); }
      select { font: inherit; padding: 3px 6px; border: 1px solid var(--line); border-radius: 6px; background: var(--field);
        color: var(--primary-text-color); }
      .flash { margin: 16px 0; padding: 10px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--card-background-color); }
      .flash.ok { border-color: var(--ok); }
      .flash.error { border-color: var(--bad); }
      .item { padding: 12px 0; border-bottom: 1px solid var(--line); }
      .item:last-child { border-bottom: 0; }
      .pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 8px 0; }
      .option { display: flex; align-items: center; gap: 8px; margin: 6px 0; }
      img.thumb { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; vertical-align: middle; margin-left: 8px; }
      details.fold { margin-top: 16px; }
      details.fold > summary { cursor: pointer; font-weight: 600; }
      table.compare th, table.compare td { font-size: 14px; }
      table.compare tbody th { font-weight: normal; min-width: 150px; }
      table.compare td.after { min-width: 180px; background: color-mix(in srgb, var(--ok) 14%, transparent); }
      table.compare td.after select { background: transparent; border-color: var(--ok); }
      .custom { display: flex; gap: 6px; margin-top: 6px; }
      .custom input[type=text] { width: 10em; padding: 3px 6px; }
      .custom button { padding: 3px 10px; }
      .old { text-decoration: line-through; opacity: .55; }
      img.thumb.old { opacity: .4; }
      img.thumb.new { outline: 2px solid var(--ok); outline-offset: 2px; }
      .new { color: var(--ok); }
      .gone { color: var(--bad); }
      .note { font-size: 13px; margin: 0 0 4px 22px; }
      td details { margin-top: 4px; }
      label.value { display: block; }
      .toast { position: fixed; right: 16px; bottom: 16px; padding: 8px 14px; border-radius: 8px; background: var(--ok); color: #fff; }
      .toast.error { background: var(--bad); }
      table.facts th { font-weight: normal; color: var(--muted); width: 220px; font-size: 14px; }
      .note-text { white-space: pre-wrap; }
      .edit-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px 12px; }
      .edit-grid label { display: block; font-size: 14px; }
      .edit-grid input { margin-top: 4px; }
      .edit-row { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 6px; padding: 6px 0; border-bottom: 1px solid var(--line); }
      .label-choice { display: flex; flex-direction: column; gap: 4px; flex: none; width: 150px; }
      .group-choice { display: flex; flex-direction: column; gap: 4px; flex: 1 1 240px; max-width: 420px; }
      .where { font-size: 13px; }
      .edit-row input.value-box { width: auto; flex: 1 1 240px; }
      .address-boxes { flex: 1 1 320px; display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 6px; }
      .address-boxes textarea { grid-column: 1 / -1; }
      .row-buttons { display: flex; gap: 4px; }
      .row-buttons button { padding: 6px 10px; }
    `;
  }
}

customElements.define("contact-sync-panel", ContactSyncPanel);
