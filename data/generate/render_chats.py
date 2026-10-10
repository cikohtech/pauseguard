"""Render eval and demo evidence with Playwright (DATA_SPEC §4 "Screenshot renderer").

    python render_chats.py                  # data/eval/drafts.jsonl -> data/eval/img|pdf/
    python render_chats.py --demo           # data/generate/demo_evidence.json -> data/demo/
    python render_chats.py --only ev_0003 --out /tmp/preview

Chat, SMS and email evidence becomes a 1080×1920 phone screenshot (a 360×640 CSS viewport at
device scale 3). The styling is generic on purpose: no messaging app, bank or mail brand. Documents
(invoices, letters, tenancy agreements) become A4 PDFs. Long threads shrink their font until they
fit the screen, so no evidence is cut off. Needs the `datagen` dependency group and
`playwright install --only-shell chromium`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_schema import IMAGE_FORMATS, Document, DraftRecord, Email, Evidence  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO / "data" / "eval"
DEMO_SPEC = Path(__file__).resolve().parent / "demo_evidence.json"

FONT_STACK = (
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", '
    '"Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif'
)
AVATAR_COLOURS = ["#5B6CF0", "#E06C5A", "#2F9E8F", "#C2843A", "#8E5BD0", "#3C8DD8", "#D0577F"]
LINK_RE = re.compile(
    r"((?:https?://)?(?:[a-z0-9-]+\.)+example(?:/[^\s，。、）)]*)?|[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.example)",
    re.I,
)
GROUP_SENDER_RE = re.compile(r"^([^:：\n]{1,28})[:：]\s*(.+)$", re.S)


# --- Small helpers ------------------------------------------------------------------------------


def esc(text: str) -> str:
    """Escape, keep line breaks, and underline .example links and emails like a phone app does."""
    out = []
    pos = 0
    for m in LINK_RE.finditer(text):
        out.append(html.escape(text[pos : m.start()]))
        out.append(f'<span class="link">{html.escape(m.group(0))}</span>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out).replace("\n", "<br>")


def initials(name: str) -> str:
    words = [w for w in re.split(r"[\s·|–\-()（）]+", name) if w and not w.startswith("+")]
    if not words:
        return "#"
    first = words[0]
    if re.match(r"[一-鿿]", first):
        return first[0]
    return "".join(w[0] for w in words[:2]).upper()


def colour(name: str) -> str:
    return AVATAR_COLOURS[int(hashlib.sha1(name.encode()).hexdigest(), 16) % len(AVATAR_COLOURS)]


def is_zh(ev: Evidence) -> bool:
    blob = json.dumps(ev.model_dump(), ensure_ascii=False)
    return len(re.findall(r"[一-鿿]", blob)) > 20


def clock(ev: Evidence) -> str:
    times = [b.time for b in ev.messages if b.time]
    if times:
        h, m = times[-1].split(":")
        mins = (int(h) * 60 + int(m) + 3) % (24 * 60)
        return f"{mins // 60}:{mins % 60:02d}"
    if ev.email:
        hm = re.search(r"(\d{1,2}):(\d{2})", ev.email.date)
        if hm:
            return f"{int(hm.group(1))}:{hm.group(2)}"
    return "10:24"


def money(x: float) -> str:
    return f"S${x:,.2f}"


# --- Phone screens (chat, SMS, email) -----------------------------------------------------------

PHONE_CSS = """
:root { --fs: 14.5px; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 360px; height: 640px; overflow: hidden; }
body { font-family: FONT; font-size: var(--fs); color: #1b1f24;
  -webkit-font-smoothing: antialiased; }
.screen { width: 360px; height: 640px; display: flex; flex-direction: column; background: #fff; }
.status { height: 24px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 14px; font-size: 12px; font-weight: 600; flex: none; }
.status .icons { display: flex; gap: 5px; align-items: center; }
.bars { display: flex; gap: 1.5px; align-items: flex-end; height: 10px; }
.bars i { width: 3px; background: currentColor; border-radius: 1px; display: block; }
.batt { width: 22px; height: 10px; border: 1.5px solid currentColor; border-radius: 3px;
  padding: 1px; position: relative; }
.batt::after { content: ""; position: absolute; right: -3.5px; top: 2.5px; width: 2px;
  height: 3.5px; background: currentColor; border-radius: 0 1px 1px 0; }
.batt b { display: block; height: 100%; width: 72%; background: currentColor; border-radius: 1px; }
.avatar { border-radius: 50%; color: #fff; display: flex; align-items: center;
  justify-content: center; font-weight: 600; flex: none; }
.link { color: #1a6fd8; text-decoration: underline; }
.composer { flex: none; display: flex; align-items: center; gap: 8px; padding: 8px 10px 14px; }
.composer .field { flex: 1; height: 36px; border-radius: 18px; padding: 0 14px; display: flex;
  align-items: center; font-size: 14px; }
.composer .send { width: 36px; height: 36px; border-radius: 50%; flex: none; display: flex;
  align-items: center; justify-content: center; color: #fff; font-size: 16px; }
.body { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

/* chat */
.chat .status { background: #263243; color: #fff; }
.chat .top { background: #263243; color: #fff; height: 56px; display: flex; align-items: center;
  gap: 10px; padding: 0 12px 0 6px; flex: none; }
.chat .top .back { font-size: 28px; line-height: 1; width: 18px; opacity: .9; }
.chat .top .avatar { width: 38px; height: 38px; font-size: 15px; }
.chat .top .who { min-width: 0; flex: 1; }
.chat .top .name { font-size: 15.5px; font-weight: 600; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.chat .top .sub { font-size: 11.5px; opacity: .75; margin-top: 1px; }
.chat .top .act { font-size: 18px; opacity: .85; letter-spacing: 10px; }
.chat .body { background: #E9EDF2; padding: 10px 10px 4px; justify-content: flex-end; }
.chat .row { display: flex; margin: 2px 0; }
.chat .row.me { justify-content: flex-end; }
.chat .bubble { max-width: 80%; padding: 6px 9px 5px; border-radius: 12px; line-height: 1.35;
  box-shadow: 0 1px 1px rgba(20,30,50,.08); word-wrap: break-word; overflow-wrap: anywhere; }
.chat .them .bubble { background: #fff; border-top-left-radius: 4px; }
.chat .me .bubble { background: #D6E6FF; border-top-right-radius: 4px; }
.chat .row + .row.me, .chat .row + .row.them { margin-top: 4px; }
.chat .sender { font-size: .82em; font-weight: 700; margin-bottom: 1px; }
.chat .t { font-size: 10.5px; color: #6b7685; float: right; margin: 6px 0 -2px 10px; }
.chat .day { align-self: center; background: rgba(38,50,67,.12); color: #3a4656; font-size: 11.5px;
  padding: 3px 10px; border-radius: 10px; margin: 6px auto; }
.chat .composer { background: #E9EDF2; }
.chat .composer .field { background: #fff; color: #9aa3ae; }
.chat .composer .send { background: #263243; }

/* sms */
.sms .status { color: #111; }
.sms .top { flex: none; display: flex; flex-direction: column; align-items: center;
  padding: 2px 0 8px; border-bottom: 1px solid #e6e6ea; background: #f7f7f9; position: relative; }
.sms .top .back { position: absolute; left: 10px; top: 10px; font-size: 26px; color: #2f7bf6; }
.sms .top .avatar { width: 44px; height: 44px; font-size: 17px; background: #9aa1ab; }
.sms .top .name { font-size: 12.5px; margin-top: 4px; font-weight: 500; }
.sms .body { padding: 10px 12px 4px; justify-content: flex-end; }
.sms .meta { text-align: center; color: #8a8f98; font-size: 11px; margin: 4px 0 8px; }
.sms .meta b { font-weight: 600; }
.sms .row { display: flex; margin: 3px 0; }
.sms .row.me { justify-content: flex-end; }
.sms .bubble { max-width: 78%; padding: 8px 12px; border-radius: 18px; line-height: 1.35;
  overflow-wrap: anywhere; }
.sms .them .bubble { background: #E9E9EB; }
.sms .me .bubble { background: #2F7BF6; color: #fff; }
.sms .me .link { color: #fff; }
.sms .composer .field { border: 1px solid #d5d7dc; color: #9aa0a8; }
.sms .composer .send { background: #c9ccd2; }

/* email */
.mail .status { color: #111; }
.mail .bar { flex: none; height: 44px; display: flex; align-items: center;
  justify-content: space-between; padding: 0 14px; color: #2f6fd6; font-size: 15px;
  border-bottom: 1px solid #eceef1; }
.mail .bar .tools { letter-spacing: 14px; color: #5f6b7a; font-size: 15px; }
.mail .body { padding: 14px 16px 8px; }
.mail .subject { font-size: 1.32em; font-weight: 700; line-height: 1.25; margin-bottom: 12px; }
.mail .from { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 14px; }
.mail .from .avatar { width: 38px; height: 38px; font-size: 14px; }
.mail .from .meta { flex: 1; min-width: 0; font-size: .86em; color: #5f6b7a; line-height: 1.35; }
.mail .from .meta b { color: #1b1f24; font-size: 1.08em; }
.mail .from .date { font-size: 11px; color: #8a93a0; margin-top: 2px; }
.mail p { line-height: 1.45; margin-bottom: 10px; }
.mail .foot { margin-top: 10px; padding-top: 8px; border-top: 1px solid #eef0f3; color: #9aa3ae;
  font-size: 10.5px; line-height: 1.35; }
.mail .foot p { margin-bottom: 4px; line-height: 1.35; }
"""

STATUS_BAR = """<div class="status"><span>{time}</span><span class="icons">
<span class="bars"><i style="height:3px"></i><i style="height:5px"></i><i style="height:7px"></i>
<i style="height:10px"></i></span><span style="font-size:10.5px">5G</span>
<span class="batt"><b></b></span></span></div>"""


def _page(cls: str, lang: str, inner: str) -> str:
    css = PHONE_CSS.replace("FONT", FONT_STACK)
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><style>{css}</style>'
        f'</head><body><div class="screen {cls}">{inner}</div></body></html>'
    )


def chat_html(ev: Evidence) -> str:
    assert ev.header is not None
    zh = is_zh(ev)
    group = bool(ev.header.subtitle and re.search(r"members|成员|位成员", ev.header.subtitle))
    rows = []
    for b in ev.messages:
        if b.who == "day":
            rows.append(f'<div class="day">{esc(b.text)}</div>')
            continue
        text, sender = b.text, ""
        if group and b.who == "them" and (m := GROUP_SENDER_RE.match(b.text)):
            sender = (
                f'<div class="sender" style="color:{colour(m.group(1))}">{esc(m.group(1))}</div>'
            )
            text = m.group(2)
        t = f'<span class="t">{b.time}</span>' if b.time else ""
        rows.append(
            f'<div class="row {b.who}"><div class="bubble">{sender}{esc(text)}{t}</div></div>'
        )
    name = ev.header.name
    inner = (
        STATUS_BAR.format(time=clock(ev))
        + '<div class="top"><span class="back">‹</span>'
        + f'<div class="avatar" style="background:{colour(name)}">'
        + f"{html.escape(initials(name))}</div>"
        + f'<div class="who"><div class="name">{html.escape(name)}</div>'
        + f'<div class="sub">{html.escape(ev.header.subtitle or "")}</div></div>'
        + '<span class="act">✆ ⋮</span></div>'
        + f'<div class="body">{"".join(rows)}</div>'
        + '<div class="composer"><div class="field">'
        + ("输入消息" if zh else "Message")
        + '</div><div class="send">➤</div></div>'
    )
    return _page("chat", "zh-Hans" if zh else "en", inner)


def sms_html(ev: Evidence) -> str:
    assert ev.header is not None
    zh = is_zh(ev)
    rows = []
    first = next((b.time for b in ev.messages if b.time), None)
    label = "短信" if zh else "Text Message"
    today = "今天" if zh else "Today"
    rows.append(f'<div class="meta"><b>{label}</b><br>{today} {first or ""}</div>')
    for b in ev.messages:
        if b.who == "day":
            rows.append(f'<div class="meta">{esc(b.text)}</div>')
        else:
            rows.append(f'<div class="row {b.who}"><div class="bubble">{esc(b.text)}</div></div>')
    name = ev.header.name
    avatar = "👤" if name.startswith("+") else html.escape(initials(name))
    inner = (
        STATUS_BAR.format(time=clock(ev))
        + f'<div class="top"><span class="back">‹</span><div class="avatar">{avatar}</div>'
        + f'<div class="name">{html.escape(name)} ›</div></div>'
        + f'<div class="body">{"".join(rows)}</div>'
        + f'<div class="composer"><div class="field">{label}</div><div class="send">↑</div></div>'
    )
    return _page("sms", "zh-Hans" if zh else "en", inner)


def email_html(ev: Evidence) -> str:
    e: Email = ev.email  # type: ignore[assignment]
    zh = is_zh(ev)
    paras = "".join(f"<p>{esc(p)}</p>" for p in e.body)
    foot = "".join(f"<p>{esc(p)}</p>" for p in e.footer)
    inner = (
        STATUS_BAR.format(time=clock(ev))
        + f'<div class="bar"><span>‹ {"收件箱" if zh else "Inbox"}</span>'
        + '<span class="tools">⌫ ⚑ ⋯</span></div>'
        + '<div class="body">'
        + f'<div class="subject">{esc(e.subject)}</div>'
        + f'<div class="from"><div class="avatar" style="background:{colour(e.from_name)}">'
        + f"{html.escape(initials(e.from_name))}</div>"
        + f'<div class="meta"><b>{html.escape(e.from_name)}</b><br>&lt;{esc(e.from_addr)}&gt;<br>'
        + f"{'发送至' if zh else 'to'} {esc(e.to)}"
        + f'<div class="date">{html.escape(e.date)}</div></div></div>'
        + paras
        + (f'<div class="foot">{foot}</div>' if foot else "")
        + "</div>"
    )
    return _page("mail", "zh-Hans" if zh else "en", inner)


# Shrink the base font until the content fits, so no evidence is cut off mid-thread. Overflow
# above a bottom-anchored (flex-end) list isn't counted in scrollHeight, so measure top-anchored.
FIT_JS = """() => {
  const body = document.querySelector('.body');
  body.style.justifyContent = 'flex-start';
  let fs = 14.5;
  const fits = () => body.scrollHeight <= body.clientHeight + 1;
  const root = document.documentElement;
  while (!fits() && fs > 10) { fs -= 0.25; root.style.setProperty('--fs', fs + 'px'); }
  const ok = fits();
  body.style.justifyContent = '';
  return {fs, fits: ok};
}"""


# --- Documents (PDF) ----------------------------------------------------------------------------

DOC_CSS = """
@page { size: A4; margin: 16mm 17mm 16mm 17mm; }
* { box-sizing: border-box; }
body { font-family: FONT; color: #1d232b; font-size: 10.5pt; line-height: 1.5; margin: 0; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
  border-bottom: 2.5px solid ACCENT; padding-bottom: 12px; margin-bottom: 16px; }
.brand { display: flex; gap: 12px; align-items: center; }
.mark { width: 44px; height: 44px; border-radius: 10px; background: ACCENT; color: #fff;
  font-weight: 700; font-size: 17pt; display: flex; align-items: center;
  justify-content: center; flex: none; }
.issuer { font-size: 15pt; font-weight: 700; line-height: 1.2; }
.lines { color: #5d6875; font-size: 8.8pt; line-height: 1.4; }
.title { text-align: right; }
.title h1 { font-size: 16pt; margin: 0 0 4px; color: ACCENT; letter-spacing: .3px; }
.title .meta { font-size: 9pt; color: #5d6875; }
.to { margin-bottom: 14px; font-size: 10pt; }
.to .lbl { color: #5d6875; font-size: 8.5pt; text-transform: uppercase; letter-spacing: .6px; }
p { margin: 0 0 9px; }
table { width: 100%; border-collapse: collapse; margin: 14px 0 6px; font-size: 10pt; }
th { text-align: left; background: #f1f3f6; color: #3d4652; font-weight: 600; padding: 7px 9px;
  font-size: 9pt; }
td { padding: 7px 9px; border-bottom: 1px solid #e6e9ee; }
td.amt, th.amt { text-align: right; white-space: nowrap; }
tr.total td { font-weight: 700; border-bottom: none; border-top: 2px solid #1d232b; }
.pay { margin-top: 14px; border: 1px solid #d9dee5; border-radius: 6px; padding: 10px 14px;
  background: #fafbfc; }
.pay h3 { margin: 0 0 6px; font-size: 9pt; text-transform: uppercase; letter-spacing: .6px;
  color: #5d6875; }
.pay div { display: flex; gap: 10px; font-size: 10pt; }
.pay div span:first-child { color: #5d6875; min-width: 120px; }
.sign { margin-top: 26px; }
.sign .line { width: 240px; border-top: 1px solid #1d232b; margin-bottom: 4px; }
.foot { margin-top: 22px; color: #6d7783; font-size: 8.3pt; border-top: 1px solid #e6e9ee;
  padding-top: 8px; }
.foot p { margin: 0 0 3px; }
"""


def doc_html(d: Document) -> str:
    zh = bool(re.search(r"[一-鿿]", d.title + "".join(d.body)))
    accent = colour(d.issuer)
    css = DOC_CSS.replace("FONT", FONT_STACK).replace("ACCENT", accent)
    lines = "<br>".join(esc(x) for x in d.issuer_lines)
    meta = []
    if d.ref:
        meta.append(f"{'编号' if zh else 'Ref'}: {esc(d.ref)}")
    meta.append(f"{'日期' if zh else 'Date'}: {esc(d.date)}")
    to = ""
    if d.to_lines:
        lbl = ("双方" if zh else "Parties") if d.kind == "tenancy" else ("致" if zh else "To")
        parties = "<br>".join(esc(x) for x in d.to_lines)
        to = f'<div class="to"><div class="lbl">{lbl}</div>{parties}</div>'
    body = "".join(f"<p>{esc(p)}</p>" for p in d.body)
    table = ""
    if d.items:
        desc, amt = ("项目", "金额") if zh else ("Description", "Amount")
        rows = "".join(
            f'<tr><td>{esc(i.description)}</td><td class="amt">'
            f"{money(i.amount) if i.amount is not None else ''}</td></tr>"
            for i in d.items
        )
        if d.total is not None:
            rows += (
                f'<tr class="total"><td>{"总额" if zh else "Total"}</td>'
                f'<td class="amt">{money(d.total)}</td></tr>'
            )
        table = f'<table><tr><th>{desc}</th><th class="amt">{amt}</th></tr>{rows}</table>'
    pay = ""
    if d.payment:
        rows = "".join(
            f"<div><span>{esc(k)}</span><span>{esc(v)}</span></div>" for k, v in d.payment.items()
        )
        pay = f'<div class="pay"><h3>{"付款资料" if zh else "Payment details"}</h3>{rows}</div>'
    sign = (
        f'<div class="sign"><div class="line"></div>{esc(d.signature)}</div>' if d.signature else ""
    )
    foot = "".join(f"<p>{esc(p)}</p>" for p in d.footer)
    return (
        f'<!doctype html><html lang="{"zh-Hans" if zh else "en"}"><head><meta charset="utf-8">'
        f"<style>{css}</style></head><body>"
        f'<div class="head"><div class="brand"><div class="mark">{html.escape(initials(d.issuer))}'
        f'</div><div><div class="issuer">{esc(d.issuer)}</div><div class="lines">{lines}</div>'
        f'</div></div><div class="title"><h1>{esc(d.title)}</h1><div class="meta">'
        f"{'<br>'.join(meta)}</div></div></div>"
        f"{to}{body}{table}{pay}{sign}"
        f"{f'<div class=foot>{foot}</div>' if foot else ''}"
        "</body></html>"
    )


# --- Rendering ----------------------------------------------------------------------------------


def evidence_html(ev: Evidence) -> str:
    return {"chat": chat_html, "sms": sms_html, "email": email_html}[ev.format](ev)


async def render(jobs: list[tuple[Evidence, Path]]) -> list[str]:
    """Render every (evidence, output path) pair; returns warnings (e.g. text shrunk a lot)."""
    from playwright.async_api import async_playwright

    warnings: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        phone = await browser.new_context(
            viewport={"width": 360, "height": 640}, device_scale_factor=3
        )
        paper = await browser.new_context()
        for ev, out in jobs:
            out.parent.mkdir(parents=True, exist_ok=True)
            if ev.format in IMAGE_FORMATS:
                page = await phone.new_page()
                await page.set_content(evidence_html(ev), wait_until="load")
                fit = await page.evaluate(FIT_JS)
                if not fit["fits"]:
                    warnings.append(f"{out.name}: content does not fit even at 10px")
                elif fit["fs"] < 12:
                    warnings.append(f"{out.name}: font shrunk to {fit['fs']}px to fit")
                await page.screenshot(path=str(out), full_page=False)
            elif ev.format == "pdf":
                assert ev.document is not None
                page = await paper.new_page()
                await page.set_content(doc_html(ev.document), wait_until="load")
                await page.pdf(path=str(out), format="A4", print_background=True)
            else:
                continue
            await page.close()
        await browser.close()
    return warnings


def evidence_path(case_id: str, ev: Evidence, root: Path = EVAL_DIR) -> Path | None:
    if ev.format in IMAGE_FORMATS:
        return root / "img" / f"{case_id}.png"
    if ev.format == "pdf":
        return root / "pdf" / f"{case_id}.pdf"
    return None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="render data/generate/demo_evidence.json")
    ap.add_argument("--only", nargs="*", help="case IDs to render (default: all)")
    ap.add_argument("--out", type=Path, help="output root (default: data/eval)")
    ap.add_argument("--force", action="store_true", help="re-render a frozen eval set")
    args = ap.parse_args(argv)

    jobs: list[tuple[Evidence, Path]] = []
    frozen = REPO / "eval" / "TEST_SPLIT_HASH"
    if not args.demo and args.out is None and frozen.exists() and not args.force:
        # Chromium stamps a creation date into PDFs, so re-rendering breaks the frozen hash.
        sys.exit(f"the eval set is frozen ({frozen.relative_to(REPO)}); use --out or --force")
    if args.demo:
        spec = json.loads(DEMO_SPEC.read_text(encoding="utf-8"))
        for item in spec["files"]:
            out = (args.out or REPO) / item["output"]
            ev = Evidence.model_validate(item["evidence"])
            jobs.append((ev, out))
            if item.get("text_output"):  # the same chat as text, for "paste the message" demos
                text = "\n".join(b.text for b in ev.messages if b.who == "them")
                txt = (args.out or REPO) / item["text_output"]
                txt.parent.mkdir(parents=True, exist_ok=True)
                txt.write_text(text + "\n", encoding="utf-8")
    else:
        with (EVAL_DIR / "drafts.jsonl").open(encoding="utf-8") as f:
            records = [DraftRecord.model_validate_json(line) for line in f if line.strip()]
        for r in records:
            if args.only and r.slot.id not in args.only:
                continue
            path = evidence_path(r.slot.id, r.draft.evidence, args.out or EVAL_DIR)
            if path:
                jobs.append((r.draft.evidence, path))
    warnings = asyncio.run(render(jobs))
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"rendered {len(jobs)} files")


if __name__ == "__main__":
    main()
