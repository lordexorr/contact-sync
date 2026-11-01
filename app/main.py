"""Contact Sync add-on: the page in Home Assistant's sidebar, and the daily check."""
import asyncio
import html
import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiohttp import web

from . import apply, check, google, notify, photos, review
from .settings import load_options

log = logging.getLogger("contact_sync")

PORT = 8099
INGRESS_PROXY = "172.30.32.2"
esc = html.escape


class State:
    """What the page keeps between requests."""

    def __init__(self, options: dict, tz: ZoneInfo):
        self.options = options
        self.tz = tz
        hour, minute = options["daily_check_time"].split(":")
        self.check_time = time(int(hour), int(minute))
        self.check_task: asyncio.Task | None = None
        self.check_error: str | None = None
        self.google_sign_in: dict | None = None
        self.flash: tuple[str, str] | None = None
        self.apply_task: asyncio.Task | None = None
        self.progress: apply.Progress | None = None

    @property
    def checking(self) -> bool:
        return self.check_task is not None and not self.check_task.done()

    @property
    def applying(self) -> bool:
        return self.apply_task is not None and not self.apply_task.done()

    @property
    def google_configured(self) -> bool:
        return bool(self.options["google_client_id"] and self.options["google_client_secret"])


STATE = web.AppKey("state", State)


@web.middleware
async def ingress_only(request: web.Request, handler):
    # Home Assistant's ingress proxy is the only client this page should ever have.
    if request.remote != INGRESS_PROXY:
        raise web.HTTPForbidden()
    return await handler(request)


def home_tz() -> ZoneInfo:
    """Home Assistant's time zone, which the Supervisor passes to every add-on as TZ."""
    try:
        return ZoneInfo(os.environ["TZ"])
    except Exception:  # missing, or not a zone name tzdata knows
        log.warning("TZ isn't a usable time zone (%r); using UTC", os.environ.get("TZ"))
        return ZoneInfo("UTC")


def next_check_at(state: State) -> datetime:
    now = datetime.now(state.tz)
    day = now.date() if now.time() < state.check_time else now.date() + timedelta(days=1)
    return datetime.combine(day, state.check_time, tzinfo=state.tz)


def start_check(state: State, daily: bool = False) -> None:
    # A check started during an apply waits for it to finish.
    if not state.checking:
        state.check_error = None
        job = daily_check if daily else check.run_check
        state.check_task = asyncio.create_task(asyncio.to_thread(job, state.options))
        state.check_task.add_done_callback(lambda task: _record_failure(state, task))


def daily_check(options: dict) -> None:
    """The scheduled check, then the daily notification when something is waiting."""
    check.run_check(options)
    if options["notify"] and (message := review.waiting_message(options)):
        notify.send(options["notify"], "Contact Sync", message)


def _record_failure(state: State, task: asyncio.Task) -> None:
    if task.cancelled() or task.exception() is None:
        return
    err = task.exception()
    log.error("Check failed", exc_info=err)
    state.check_error = (
        f"The check at {fmt_time(datetime.now(state.tz))} failed ({type(err).__name__}: {err}). "
        "Details are in the add-on's log."
    )


async def daily_checks(state: State) -> None:
    # The wall clock is read every 30 seconds instead of sleeping until the check time, so clock
    # corrections and DST changes can't move or repeat the check. Starting up after today's check
    # time never runs a check; the next one is tomorrow's.
    now = datetime.now(state.tz)
    started_on = now.date() if now.time() >= state.check_time else None
    log.info("Daily check at %s (%s)", state.check_time.strftime("%H:%M"), state.tz)
    while True:
        now = datetime.now(state.tz)
        if started_on != now.date() and now.time() >= state.check_time:
            started_on = now.date()
            start_check(state, daily=True)
        await asyncio.sleep(30)


async def scheduler(app: web.Application):
    task = asyncio.create_task(daily_checks(app[STATE]))
    yield
    task.cancel()


# --- Requests ---

def go_to(request: web.Request, path: str = "") -> web.HTTPSeeOther:
    # Behind ingress the page lives under /api/hassio_ingress/<token>/, which arrives in this header.
    return web.HTTPSeeOther(request.headers.get("X-Ingress-Path", "") + "/" + path)


async def index(request: web.Request) -> web.Response:
    state = request.app[STATE]
    body = (
        "<h1>Contact Sync</h1>"
        "<p class='muted'>Checks every account daily, and writes nothing until you apply the reviewed changes.</p>"
        f"{take_flash(state)}{review_card(state)}{accounts_card(state)}{icloud_card(state)}{google_card(state)}"
    )
    # No auto-refresh during a Google sign-in: it would wipe the pasted address.
    return page(request, body, refresh=state.checking and not state.google_sign_in)


async def check_now(request: web.Request) -> web.Response:
    state = request.app[STATE]
    if not state.applying:  # applying checks every account itself
        start_check(state)
    raise go_to(request)


async def review_page(request: web.Request) -> web.Response:
    state = request.app[STATE]
    try:
        content = review.page_body(review.current_plan(state.options))
    except Exception:
        log.exception("Couldn't put the review together")
        content = "<h1>Review</h1><p class='bad'>Couldn't put the review together. Details are in the add-on's log.</p>"
    return page(request, f"<p><a href='./'>← Contact Sync</a></p>{take_flash(state)}{content}")


# The review page saves each click in the background and reloads itself, so these answer with no content.

async def review_match(request: web.Request) -> web.Response:
    form = await request.post()
    review.decide_match(str(form.get("pair", "")), str(form.get("decision", "")))
    return web.Response(status=204)


async def review_duplicate(request: web.Request) -> web.Response:
    form = await request.post()
    review.decide_duplicate(str(form.get("id", "")), str(form.get("decision", "")))
    return web.Response(status=204)


async def review_pick(request: web.Request) -> web.Response:
    form = await request.post()
    review.pick(str(form.get("conflict", "")), str(form.get("choice", "")))
    return web.Response(status=204)


async def review_label(request: web.Request) -> web.Response:
    form = await request.post()
    review.pick(str(form.get("id", "")), str(form.get("label", "")))
    return web.Response(status=204)


async def review_skip(request: web.Request) -> web.Response:
    form = await request.post()
    review.set_skip(str(form.get("id", "")), bool(form.get("keep")))
    return web.Response(status=204)


async def review_reset(request: web.Request) -> web.Response:
    review.reset()
    request.app[STATE].flash = ("ok", "Every match, choice and skip is forgotten.")
    raise go_to(request, "review")


async def apply_page(request: web.Request) -> web.Response:
    state = request.app[STATE]
    if state.applying:
        raise go_to(request, "result")
    person = request.query.get("person") or None
    try:
        content = review.apply_body(review.current_plan(state.options), person, state.checking)
    except Exception:
        log.exception("Couldn't put the Apply page together")
        content = "<h1>Apply changes</h1><p class='bad'>Couldn't work out the changes. Details are in the add-on's log.</p>"
    return page(request, f"<p><a href='review'>← Review</a></p>{take_flash(state)}{content}", refresh=state.checking)


async def apply_start(request: web.Request) -> web.Response:
    state = request.app[STATE]
    form = await request.post()
    if state.checking:
        state.flash = ("error", "A check is running. Apply once it has finished.")
        raise go_to(request, "review")
    if not state.applying:
        state.progress = apply.Progress()
        state.apply_task = asyncio.create_task(asyncio.to_thread(
            apply.run, state.options, str(form.get("person", "")) or None, str(form.get("token", "")), state.tz,
            state.progress))
    raise go_to(request, "result")


async def result_page(request: web.Request) -> web.Response:
    state = request.app[STATE]
    content = review.result_body(apply.load_result(), state.progress if state.applying else None,
                                 lambda stamp: fmt_time(datetime.fromisoformat(stamp).astimezone(state.tz)))
    return page(request, f"<p><a href='./'>← Contact Sync</a></p>{content}", refresh=state.applying)


async def thumb(request: web.Request) -> web.StreamResponse:
    path = photos.THUMB_DIR / request.match_info["name"]
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


async def google_start(request: web.Request) -> web.Response:
    state = request.app[STATE]
    if state.google_configured:
        state.google_sign_in = {**google.start_sign_in(state.options["google_client_id"]), "busy": False}
    raise go_to(request)


async def google_finish(request: web.Request) -> web.Response:
    state = request.app[STATE]
    pasted = str((await request.post()).get("url", ""))
    attempt = state.google_sign_in
    if attempt is None:
        state.flash = ("error", "That sign-in is no longer open, possibly because the add-on restarted. "
                                "Press Connect a Google account to start again.")
        raise go_to(request)
    if attempt["busy"]:  # a second click on Connect while the first is still talking to Google
        raise go_to(request)
    attempt["busy"] = True
    try:
        account = await asyncio.to_thread(
            google.finish_sign_in, pasted, attempt,
            state.options["google_client_id"], state.options["google_client_secret"],
        )
        await asyncio.to_thread(check.save_google_account, account)
    except google.GoogleError as err:
        message = str(err)
    except Exception as err:
        log.exception("Google sign-in failed")
        message = f"Sign-in failed ({type(err).__name__}: {err}). Press Cancel, then start again."
    else:
        if state.google_sign_in is attempt:
            state.google_sign_in = None
        state.flash = ("ok", f"Connected {account['email']}. Press Check now to read its contacts.")
        raise go_to(request)
    # Unless it was cancelled meanwhile, the attempt stays open so a corrected address can be pasted.
    attempt["busy"] = False
    state.flash = ("error", message)
    raise go_to(request)


async def google_cancel(request: web.Request) -> web.Response:
    request.app[STATE].google_sign_in = None
    raise go_to(request)


async def google_remove(request: web.Request) -> web.Response:
    email = str((await request.post()).get("email", ""))
    await asyncio.to_thread(check.remove_google_account, email)
    request.app[STATE].flash = ("ok", f"Disconnected {email} and deleted its saved contacts.")
    raise go_to(request)


# --- Page ---

def page(request: web.Request, body: str, refresh: bool = False) -> web.Response:
    base = esc(request.headers.get("X-Ingress-Path", "") + "/")
    meta = "<meta http-equiv='refresh' content='5'>" if refresh else ""
    return web.Response(content_type="text/html", text=(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<base href='{base}'>{meta}<title>Contact Sync</title><style>{STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    ))


def take_flash(state: State) -> str:
    flash, state.flash = state.flash, None
    return f"<div class='flash {flash[0]}'>{esc(flash[1])}</div>" if flash else ""


def review_card(state: State) -> str:
    try:
        return review.summary_card(review.current_plan(state.options), apply_line(state))
    except Exception:
        log.exception("Couldn't put the review together")
        return ("<section class='card'><h2>Review</h2><p class='bad'>Couldn't put the review together. "
                "Details are in the add-on's log.</p></section>")


def apply_line(state: State) -> str:
    if state.applying:
        return "<p>Applying changes… <a href='result'>Follow it</a></p>"
    result = apply.load_result()
    if not result:
        return ""
    when = fmt_time(datetime.fromisoformat(result["finished_at"]).astimezone(state.tz))
    return f"<p class='muted'>Last applied {when}: {esc(apply.summary(result))}. <a href='result'>Details</a></p>"


def accounts_card(state: State) -> str:
    status = check.load_status()
    if status:
        rows = "".join(account_row(a) for a in status["accounts"]) or (
            "<tr><td colspan='4' class='muted'>No accounts set up yet.</td></tr>"
        )
        checked = datetime.fromisoformat(status["checked_at"]).astimezone(state.tz)
        summary = (
            "<div class='scroll'><table><thead><tr><th>Account</th><th class='num'>Contacts</th>"
            f"<th class='num'>Groups</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></div>"
            f"<p class='muted'>Last checked {fmt_time(checked)}.</p>"
        )
    else:
        summary = "<p class='muted'>Not checked yet.</p>"
    failure = f"<p class='bad'>{esc(state.check_error)}</p>" if state.check_error else ""
    button = ("<button disabled>Applying…</button>" if state.applying
              else "<button disabled>Checking…</button>" if state.checking else "<button>Check now</button>")
    return (
        f"<section class='card'><h2>Accounts</h2>{failure}{summary}"
        f"<div class='row'><form method='post' action='check'>{button}</form>"
        f"<span class='muted'>Next daily check {fmt_time(next_check_at(state))}.</span></div></section>"
    )


def account_row(a: dict) -> str:
    login = f"<div class='muted'>{esc(a['login'])}</div>" if a["login"] and a["login"] != a["name"] else ""
    if a["error"]:
        counts = "<td class='num'>–</td><td class='num'>–</td>"
        status = f"<span class='bad'>{esc(a['error'])}</span>"
    else:
        counts = f"<td class='num'>{a['contacts']:,}</td><td class='num'>{a['groups']:,}</td>"
        status = "<span class='ok'>Connected</span>"
    return f"<tr><td>{esc(a['service'])} · {esc(a['name'])}{login}</td>{counts}<td>{status}</td></tr>"


def icloud_card(state: State) -> str:
    # iCloud accounts are set on the Configuration tab, where their passwords live, so this only lists them.
    accounts = "".join(
        f"<li class='row'><span>{esc(a['label'] or 'iCloud')}</span>"
        f"<span class='muted'>{esc(a['apple_id'] or 'No Apple ID entered')}</span></li>"
        for a in state.options["icloud_accounts"]
    ) or "<li class='muted'>None added yet.</li>"
    return (
        f"<section class='card'><h2>iCloud accounts</h2><ul class='plain'>{accounts}</ul>"
        "<p class='muted'>Add, change or remove iCloud accounts on the add-on's Configuration tab, "
        "then restart the add-on.</p></section>"
    )


def google_card(state: State) -> str:
    # Connected accounts stay listed even without a client ID and secret, so they can still be disconnected.
    connected = "".join(
        f"<li class='row'><span>{esc(a['email'])}</span><form method='post' action='google/remove'>"
        f"<input type='hidden' name='email' value='{esc(a['email'])}'>"
        "<button class='secondary'>Disconnect</button></form></li>"
        for a in check.google_accounts()
    ) or "<li class='muted'>None connected yet.</li>"
    if not state.google_configured:
        action = (
            "<p class='muted'>Add the client ID and secret in the Google section of the add-on's "
            "Configuration tab, then restart the add-on.</p>"
        )
    elif state.google_sign_in:
        action = (
            "<ol>"
            f"<li><a href='{esc(state.google_sign_in['url'])}' target='_blank' rel='noopener'>Open Google sign-in</a>"
            " and choose the account. If Google says it hasn't verified the app, choose <b>Advanced</b>, then"
            " <b>Go to Contact Sync</b>.</li>"
            "<li>Allow access to contacts. If Google shows a checkbox for contacts, tick it. The browser then"
            " shows a “This site can't be reached” page. That's expected.</li>"
            "<li>Copy the whole address from the browser's address bar and paste it here.</li></ol>"
            "<form method='post' action='google/finish' onsubmit=\"this.querySelector('button').disabled=true\">"
            "<input type='text' name='url' required autocomplete='off' placeholder='http://127.0.0.1:8765/?state=…'>"
            "<div class='row'><button>Connect</button>"
            "<button class='secondary' formaction='google/cancel' formnovalidate>Cancel</button></div></form>"
        )
    else:
        action = "<form method='post' action='google/start'><button>Connect a Google account</button></form>"
    return f"<section class='card'><h2>Google accounts</h2><ul class='plain'>{connected}</ul>{action}</section>"


def fmt_time(dt: datetime) -> str:
    return f"{dt:%a %b} {dt.day}, {dt.hour % 12 or 12}:{dt:%M} {'AM' if dt.hour < 12 else 'PM'}"


STYLE = """
:root{--bg:#f6f6f6;--card:#fff;--text:#1c1c1c;--muted:#6b6b6b;--line:#e2e2e2;--accent:#0b7fc2;--on-accent:#fff;--ok:#2e7d32;--bad:#c62828}
@media (prefers-color-scheme:dark){:root{--bg:#111;--card:#1c1c1c;--text:#e6e6e6;--muted:#9a9a9a;--line:#303030;--accent:#4fb3ef;--on-accent:#06202f;--ok:#66bb6a;--bad:#ef6b6b}}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:820px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:0 0 12px}
a{color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}
.muted{color:var(--muted)}
.ok{color:var(--ok)}
.bad{color:var(--bad)}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:13px;font-weight:600;color:var(--muted)}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin-top:12px}
ul.plain{list-style:none;margin:0 0 12px;padding:0}
ul.plain li{justify-content:space-between;margin-top:0;padding:6px 0;border-bottom:1px solid var(--line)}
ol{padding-left:20px}
ol li{margin-bottom:8px}
button,a.button{display:inline-block;font:inherit;text-decoration:none;padding:8px 14px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:var(--on-accent);cursor:pointer}
button.secondary,a.button.secondary{background:transparent;color:var(--accent)}
code{font-size:13px;overflow-wrap:anywhere}
button:disabled{opacity:.6;cursor:default}
input[type=text]{width:100%;font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text)}
.flash{margin:16px 0;padding:10px 14px;border:1px solid var(--line);border-radius:8px;background:var(--card)}
.flash.ok{border-color:var(--ok)}
.flash.error{border-color:var(--bad)}
.item{padding:12px 0;border-bottom:1px solid var(--line)}
.item:last-child{border-bottom:0}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:8px 0}
ul.changes{list-style:none;margin:6px 0 0;padding:0}
ul.changes li{padding:3px 0}
.option{display:flex;align-items:center;gap:8px;margin:6px 0}
img.thumb{width:48px;height:48px;border-radius:50%;object-fit:cover;vertical-align:middle;margin-left:8px}
li details{margin:2px 0 0 26px}
select{font:inherit;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--text)}
details.fold{margin-top:16px}
details.fold>summary{cursor:pointer;font-weight:600}
table.compare th,table.compare td{font-size:14px}
table.compare tbody th{font-weight:normal;min-width:150px}
table.compare td.after{min-width:180px;background:color-mix(in srgb,var(--ok) 14%,transparent)}
table.compare td.after select{background:transparent;border-color:var(--ok)}
.old{text-decoration:line-through;opacity:.55}
img.thumb.old{opacity:.4}
img.thumb.new{outline:2px solid var(--ok);outline-offset:2px}
.new{color:var(--ok)}
.gone{color:var(--bad)}
.note{font-size:13px;margin:0 0 4px 22px}
td details{margin-top:4px}
label.value{display:block}
.toast{position:fixed;right:16px;bottom:16px;padding:8px 14px;border-radius:8px;background:var(--ok);color:#fff}
.toast.error{background:var(--bad)}
"""


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = web.Application(middlewares=[ingress_only])
    app[STATE] = State(load_options(), home_tz())
    app.add_routes([
        web.get("/", index),
        web.post("/check", check_now),
        web.get("/review", review_page),
        web.post("/review/match", review_match),
        web.post("/review/duplicate", review_duplicate),
        web.post("/review/pick", review_pick),
        web.post("/review/label", review_label),
        web.post("/review/skip", review_skip),
        web.post("/review/reset", review_reset),
        web.get("/apply", apply_page),
        web.post("/apply", apply_start),
        web.get("/result", result_page),
        web.get(r"/thumb/{name:[0-9a-f]+\.jpg}", thumb),
        web.post("/google/start", google_start),
        web.post("/google/finish", google_finish),
        web.post("/google/cancel", google_cancel),
        web.post("/google/remove", google_remove),
    ])
    app.cleanup_ctx.append(scheduler)
    web.run_app(app, port=PORT, access_log=None, print=None)


if __name__ == "__main__":
    main()
