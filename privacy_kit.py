#!/usr/bin/env python3
"""
privacy_kit.py - get yourself off people-search sites and keep watching.

  python3 privacy_kit.py setup        # enter your details once (stored locally, chmod 600)
  python3 privacy_kit.py checklist    # opt-out links, in the order that pays off most
  python3 privacy_kit.py letters      # write CCPA / state-privacy deletion emails, one per broker
  python3 privacy_kit.py monitor      # run one exposure scan now (uses Claude Code)
  python3 privacy_kit.py install      # schedule the scan every Monday 8am (macOS launchd)
  python3 privacy_kit.py uninstall    # remove the schedule
  python3 privacy_kit.py test-notify  # send a test Telegram message / notification

Standard library only. Works with the python3 that ships with macOS.
"""

import datetime
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, "privacy-cleanup")
MONITOR_DIR = os.path.join(BASE, "monitor")
IDENTIFIERS = os.path.join(MONITOR_DIR, "identifiers.json")
LAST_HITS = os.path.join(MONITOR_DIR, "last_hits.json")
HISTORY_DIR = os.path.join(MONITOR_DIR, "history")
LOG = os.path.join(MONITOR_DIR, "monitor.log")
LETTERS_DIR = os.path.join(BASE, "letters")
LABEL = "com.%s.privacy-monitor" % re.sub(r"[^A-Za-z0-9]", "", getpass.getuser()).lower()
PLIST = os.path.join(HOME, "Library", "LaunchAgents", LABEL + ".plist")

# ---------------------------------------------------------------------------
# Broker data (researched Oct 2026 - sites change, so verify anything that bounces)
# ---------------------------------------------------------------------------

# Self-serve opt-out forms, highest leverage first.
OPT_OUTS = [
    ("California DROP (CA residents only) - one request hits every registered broker",
     "https://consumer.drop.privacy.ca.gov/",
     "Identity check via Login.gov. Do this FIRST. Brokers must process it every 45 days."),
    ("PeopleConnect - covers Intelius, InstantCheckmate, TruthFinder, USSearch, ZabaSearch",
     "https://suppression.peopleconnect.us/",
     "One suppression covers every brand. Search, find your record, suppress."),
    ("Whitepages", "https://www.whitepages.com/suppression-requests",
     "Paste your listing URL. They verify by calling a phone number - pick one you can answer."),
    ("Spokeo", "https://www.spokeo.com/optout", "Paste listing URL, confirm by email."),
    ("ThatsThem (Spokeo-owned)", "https://thatsthem.com/optout", ""),
    ("TruePeopleSearch", "https://www.truepeoplesearch.com/removal", "CAPTCHA, then pick your record."),
    ("FastPeopleSearch", "https://www.fastpeoplesearch.com/optout", "CAPTCHA, then pick your record."),
    ("SearchPeopleFree", "https://www.searchpeoplefree.com/opt-out", "Asks for DOB + address."),
    ("USPhonebook", "https://www.usphonebook.com/opt-out", ""),
    ("CyberBackgroundChecks", "https://www.cyberbackgroundchecks.com/removal",
     "Heavy Cloudflare - do it by hand in a normal browser."),
    ("PeopleFinders", "https://www.peoplefinders.com/opt-out", "Suppresses display only."),
    ("FamilyTreeNow", "https://www.familytreenow.com/optout", ""),
    ("Advanced Background Checks", "https://www.advancedbackgroundchecks.com/opt-out", ""),
    ("BeenVerified (+ PeopleLooker, NeighborWho, Ownerly, PeopleSmart, NumberGuru)",
     "https://www.beenverified.com/svc/optout/search/optouts",
     "Each sister site has its own opt-out. Cloudflare-heavy."),
    ("Enformion (upstream data for TPS/FPS/USPhonebook/SPF/CBC)", "https://www.enformion.com/opt-out/", ""),
    ("Acxiom", "https://isapps.acxiom.com/optout/optout.aspx", "Marketing data broker."),
    ("LexisNexis Risk", "https://consumer.risk.lexisnexis.com/request", ""),
    ("Equifax / IXI", "https://myprivacy.equifax.com/", ""),
    ("Epsilon", "https://legal.epsilon.com/dsr/", ""),
    ("Data Axle", "https://www.data-axle.com/privacy-rights-request/", ""),
    ("Melissa", "https://apps.melissa.com/user/consumerprivacy.aspx", ""),
]

# Brokers with a working privacy email - these get a deletion letter.
LETTER_TARGETS = [
    ("enformion", "Enformion / EnformionGO", "support@enformion.com",
     "TruePeopleSearch, FastPeopleSearch, USPhonebook, SearchPeopleFree and CyberBackgroundChecks"),
    ("truepeoplesearch", "TruePeopleSearch", "support@truepeoplesearch.com", ""),
    ("fastpeoplesearch", "FastPeopleSearch", "support@fastpeoplesearch.com", ""),
    ("usphonebook", "USPhonebook", "support@usphonebook.com", ""),
    ("searchpeoplefree", "SearchPeopleFree", "support@searchpeoplefree.com", ""),
    ("cyberbackgroundchecks", "CyberBackgroundChecks", "support@cyberbackgroundchecks.com", ""),
    ("familytreenow", "FamilyTreeNow", "support@familytreenow.com", ""),
    ("peopleconnect", "PeopleConnect", "privacy@peopleconnect.us",
     "Intelius, InstantCheckmate, TruthFinder, USSearch and ZabaSearch"),
    ("spokeo", "Spokeo", "privacy@spokeo.com", "ThatsThem"),
    ("whitepages", "Whitepages", "support@whitepages.com", ""),
    ("beenverified", "BeenVerified", "support@beenverified.com",
     "PeopleLooker, NeighborWho, Ownerly, PeopleSmart and NumberGuru"),
    ("mylife", "MyLife", "membersupport@mylife.com", ""),
    ("epsilon", "Epsilon", "privacy@epsilon.com", ""),
    ("cotality", "Cotality (formerly CoreLogic)", "privacy@cotality.com", ""),
    ("data_axle", "Data Axle", "privacyteam@data-axle.com", ""),
    ("melissa", "Melissa", "ConsumerRequest@melissa.com", ""),
]

# Sites the weekly monitor checks directly (in addition to general web search).
MONITOR_SITES = [
    "truepeoplesearch.com", "fastpeoplesearch.com", "searchpeoplefree.com", "usphonebook.com",
    "cyberbackgroundchecks.com", "whitepages.com", "spokeo.com", "thatsthem.com",
    "peoplefinders.com", "beenverified.com", "intelius.com", "instantcheckmate.com",
    "truthfinder.com", "familytreenow.com", "advancedbackgroundchecks.com", "mylife.com",
    "radaris.com", "nuwber.com", "clustrmaps.com", "peekyou.com", "zabasearch.com",
    "addresses.com", "411.com", "411locate.com", "publicrecordsnow.com", "neighborwho.com",
    "peoplelooker.com", "smartbackgroundchecks.com", "fastbackgroundcheck.com", "officialusa.com",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg):
    """Log without personal details - counts and statuses only."""
    line = "%s  %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    try:
        os.makedirs(MONITOR_DIR, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def write_private(path, text):
    """Write a file readable only by you (chmod 600), dir chmod 700."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    os.chmod(d, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def load_ids():
    if not os.path.exists(IDENTIFIERS):
        sys.exit("No identifiers yet. Run:  python3 privacy_kit.py setup")
    mode = os.stat(IDENTIFIERS).st_mode & 0o777
    if mode & 0o077:
        os.chmod(IDENTIFIERS, 0o600)
        log("tightened identifiers.json permissions to 600")
    with open(IDENTIFIERS) as f:
        return json.load(f)


def ask(prompt, default=""):
    suffix = " [%s]" % default if default else ""
    val = input("%s%s: " % (prompt, suffix)).strip()
    return val or default


def ask_list(prompt, default=None):
    default = default or []
    print("%s (one per line, blank line to finish)" % prompt)
    if default:
        print("  current: %s  (blank line keeps these)" % "; ".join(default))
    items = []
    while True:
        v = input("  > ").strip()
        if not v:
            break
        items.append(v)
    return items or default


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def cmd_setup():
    old = {}
    if os.path.exists(IDENTIFIERS):
        with open(IDENTIFIERS) as f:
            old = json.load(f)
        print("Updating existing %s\n" % IDENTIFIERS)
    print("Everything you type stays in %s (chmod 600).\n"
          "It is only ever sent to Claude when the monitor runs, and to Telegram if you set that up.\n" % IDENTIFIERS)

    ids = {
        "full_name": ask("Full legal name (e.g. Jane Marie Doe)", old.get("full_name", "")),
        "name_variants": ask_list("Other names you're listed under (nicknames, middle initial, maiden name)",
                                  old.get("name_variants")),
        "city": ask("Current city", old.get("city", "")),
        "state": ask("State (2 letters)", old.get("state", "CA")).upper(),
        "birth_year": ask("Birth year (helps tell you apart from namesakes; optional)", old.get("birth_year", "")),
        "emails": ask_list("Email addresses", old.get("emails")),
        "phones": ask_list("Phone numbers (current and old)", old.get("phones")),
        "addresses": ask_list("Street addresses (current and past, e.g. '123 Main St, Oakland CA')",
                              old.get("addresses")),
        "contact_email": "",
        "notify": old.get("notify", {"telegram_bot_token": "", "telegram_chat_id": ""}),
    }
    ids["contact_email"] = ask("Email to send deletion letters from / receive replies",
                               old.get("contact_email") or (ids["emails"][0] if ids["emails"] else ""))

    if input("\nSet up Telegram alerts for the weekly monitor? (y/N) ").strip().lower() == "y":
        print("  1. In Telegram, message @BotFather -> /newbot -> copy the token.\n"
              "  2. Send any message to your new bot.\n"
              "  3. Paste the token below; the chat id is found automatically.")
        token = ask("  Bot token", ids["notify"].get("telegram_bot_token", ""))
        chat_id = ids["notify"].get("telegram_chat_id", "")
        if token and not chat_id:
            chat_id = find_chat_id(token)
            print("  chat id: %s" % (chat_id or "not found - message your bot first, then rerun setup"))
        ids["notify"] = {"telegram_bot_token": token, "telegram_chat_id": chat_id}

    write_private(IDENTIFIERS, json.dumps(ids, indent=2))
    print("\nSaved %s (chmod 600).\nNext:  python3 privacy_kit.py checklist" % IDENTIFIERS)


def find_chat_id(token):
    try:
        with urllib.request.urlopen("https://api.telegram.org/bot%s/getUpdates" % token, timeout=20) as r:
            data = json.load(r)
        for upd in reversed(data.get("result", [])):
            msg = upd.get("message") or upd.get("edited_message")
            if msg:
                return str(msg["chat"]["id"])
    except Exception as e:  # noqa: BLE001
        print("  Telegram lookup failed: %s" % e)
    return ""


# ---------------------------------------------------------------------------
# checklist
# ---------------------------------------------------------------------------

def cmd_checklist():
    print("OPT-OUT CHECKLIST - work top to bottom. Keep a note of what you submitted and when.\n")
    for i, (name, url, note) in enumerate(OPT_OUTS, 1):
        print("%2d. %s\n    %s" % (i, name, url))
        if note:
            print("    - %s" % note)
    print("\nTips:\n"
          "  - Use a normal browser window; CAPTCHAs and Cloudflare block automation.\n"
          "  - If a password manager's autofill popup hijacks the form, disable it for that site.\n"
          "  - Most sites confirm by email - click those links the same day; they expire.\n"
          "  - Listings take 24-72h to drop. Recheck in a week (the monitor does this for you).\n"
          "Then:  python3 privacy_kit.py letters")


# ---------------------------------------------------------------------------
# letters
# ---------------------------------------------------------------------------

def letter_text(ids, company, downstream):
    name = ids["full_name"]
    variants = [v for v in ids.get("name_variants", []) if v.lower() != name.lower()]
    email = ids.get("contact_email") or (ids.get("emails") or [""])[0]
    ca = ids.get("state", "").upper() == "CA"

    also = ""
    if downstream:
        also = ", including information you supply to %s" % downstream

    if ca:
        subject = "CCPA Request to Delete and Opt Out of Sale/Sharing - %s" % name
        intro = ("I am a California resident. Under the California Consumer Privacy Act, as amended by the "
                 "CPRA (Cal. Civ. Code § 1798.100 et seq.), I am making the following requests about all "
                 "personal information you hold on me%s:" % also)
        reqs = ("1. Request to delete (§ 1798.105): Delete all personal information you have collected about me. "
                "Tell any service providers, contractors and third parties to whom you have sold or shared it "
                "to delete it as well.\n\n"
                "2. Request to opt out of sale and sharing (§ 1798.120): Do not sell or share my personal "
                "information with any third party, now or in the future.\n\n"
                "3. Request to limit (§ 1798.121): Limit any use or disclosure of my sensitive personal "
                "information to what § 1798.121 permits.")
        verify = ("If you need more information to verify my identity, tell me exactly what you need and why, "
                  "and use it only for verification, as § 1798.130(a)(7) requires. If you claim an exemption "
                  "for any category of data, such as publicly available information under § 1798.140(v)(2), "
                  "identify the category and the exemption. Then delete or suppress everything else, including "
                  "email addresses, phone numbers, inferences, relatives and associates.")
        deadline = ("Please confirm receipt within 10 business days and complete this request within 45 calendar "
                    "days, as § 1798.130 requires. If you do not, I will file a complaint with the California "
                    "Privacy Protection Agency and the California Attorney General.\n\n"
                    "I have also submitted a deletion request through the California DROP platform "
                    "(Delete Act, SB 362).")
    else:
        subject = "Request to Delete Personal Data and Opt Out of Sale - %s" % name
        intro = ("I am a resident of %s. Under my state's consumer privacy law, and under the CCPA and similar "
                 "laws where they apply to your business, I am making the following requests about all personal "
                 "information you hold on me%s:" % (ids.get("state") or "the United States", also))
        reqs = ("1. Delete all personal data you have collected about me, and tell anyone you have sold or "
                "shared it with to delete it as well.\n\n"
                "2. Do not sell or share my personal data, or use it for targeted advertising or profiling, now "
                "or in the future.\n\n"
                "3. Remove any public listing or profile about me from your websites and any affiliated sites.")
        verify = ("If you need more information to verify my identity, tell me exactly what you need and use it "
                  "only for verification. If you claim an exemption for any category of data, identify the "
                  "category and the exemption, then delete or suppress everything else, including email "
                  "addresses, phone numbers, inferences, relatives and associates.")
        deadline = ("Please confirm receipt and complete this request within 45 days. If you do not, I will "
                    "file a complaint with my state Attorney General.")

    ident = "Name: %s" % name
    if variants:
        ident += " (also listed as %s)" % " or ".join(variants)
    ident += "\nCity: %s, %s" % (ids.get("city", ""), ids.get("state", ""))
    if email:
        ident += "\nEmail: %s" % email

    body = ("To the Privacy Team at %s:\n\n%s\n\n%s\n\n"
            "Identifying information, provided only so you can locate my records:\n%s\n\n"
            "%s\n\n%s\n\nSincerely,\n%s\n%s\n" % (company, intro, reqs, ident, verify, deadline, name, email))
    return subject, body


def cmd_letters():
    ids = load_ids()
    os.makedirs(LETTERS_DIR, exist_ok=True)
    os.chmod(LETTERS_DIR, 0o700)
    rows = []
    for i, (slug, company, to, downstream) in enumerate(LETTER_TARGETS, 1):
        subject, body = letter_text(ids, company, downstream)
        fn = "%02d_%s.txt" % (i, slug)
        write_private(os.path.join(LETTERS_DIR, fn), "To: %s\nSubject: %s\n\n%s" % (to, subject, body))
        mailto = "mailto:%s?subject=%s&body=%s" % (
            to, urllib.parse.quote(subject), urllib.parse.quote(body))
        rows.append('<li><a href="%s">%s</a> <small>&lt;%s&gt;</small></li>' % (mailto, company, to))

    html = ("<!doctype html><meta charset=utf-8><title>Deletion letters</title>"
            "<style>body{font:16px system-ui;max-width:640px;margin:40px auto;padding:0 16px}"
            "li{margin:10px 0}</style><h1>Deletion letters</h1>"
            "<p>Click each link - it opens a ready-to-send email in your mail app. "
            "Send from the address listed in the letter. Mark today's date: companies have 45 days to answer.</p>"
            "<ol>%s</ol>" % "\n".join(rows))
    write_private(os.path.join(LETTERS_DIR, "index.html"), html)

    due = (datetime.date.today() + datetime.timedelta(days=45)).isoformat()
    print("Wrote %d letters to %s" % (len(rows), LETTERS_DIR))
    print("Open %s to send them with one click each." % os.path.join(LETTERS_DIR, "index.html"))
    print("Response deadline if you send today: %s - put it on your calendar." % due)
    if ids.get("state", "").upper() == "CA":
        print("Unanswered by then? File at https://privacy.ca.gov/submit-a-complaint/ccpa-complaints/")
    if sys.platform == "darwin" and input("Open it now? (Y/n) ").strip().lower() != "n":
        subprocess.call(["open", os.path.join(LETTERS_DIR, "index.html")])


# ---------------------------------------------------------------------------
# monitor
# ---------------------------------------------------------------------------

MONITOR_PROMPT = """You are running an unattended weekly privacy scan for the person below. Find every web page \
that currently exposes THIS person's personal details (not a namesake). Be thorough but only report real matches.

PERSON
- Name: {full_name}
- Also known as: {variants}
- City/State: {city}, {state}
- Birth year: {birth_year}
- Emails: {emails}
- Phones: {phones}
- Addresses: {addresses}

HOW TO SEARCH
1. Web-search each name variant together with the city, e.g. "{full_name}" {city}.
2. Web-search each email, each phone (try formats 555-123-4567 and (555) 123-4567) and each street address in quotes.
3. For each of these people-search sites, search `site:<domain> "<name>"` and, where a result looks like a profile, \
fetch it to confirm: {sites}
4. If a fetch is blocked (Cloudflare/CAPTCHA), still report the search result if its snippet clearly matches \
(say "unverified" in the evidence).

A page counts as a HIT only if it shows this person's name together with at least one of: their city, an email, \
a phone, an address, or an age/birth year consistent with the above. Pages the person controls (their own social \
profiles, their own website) are not hits. Do not report pages that only say "no results" or "record removed".

OUTPUT
After you finish, print exactly one line that starts with HITS_JSON= followed by a compact JSON array. \
Each item: {{"url": "...", "site": "domain", "exposes": ["name","phone","address","email","age","relatives"], \
"evidence": "<=120 chars, what you saw"}}. Print HITS_JSON=[] if nothing was found. Print nothing after that line."""


def fmt(lst):
    return "; ".join(lst) if lst else "(none)"


def run_claude(ids):
    claude = shutil.which("claude") or os.path.join(HOME, ".local", "bin", "claude")
    if not os.path.exists(claude):
        raise RuntimeError("claude CLI not found - install Claude Code: https://claude.com/claude-code")
    prompt = MONITOR_PROMPT.format(
        full_name=ids["full_name"], variants=fmt(ids.get("name_variants")),
        city=ids.get("city", ""), state=ids.get("state", ""), birth_year=ids.get("birth_year") or "(unknown)",
        emails=fmt(ids.get("emails")), phones=fmt(ids.get("phones")), addresses=fmt(ids.get("addresses")),
        sites=", ".join(MONITOR_SITES))
    # Read-only web tools only: the scan can search and fetch, nothing else.
    proc = subprocess.run(
        [claude, "-p", prompt, "--allowedTools", "WebSearch,WebFetch", "--output-format", "text"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=45 * 60, cwd=MONITOR_DIR)
    out = proc.stdout or ""
    m = None
    for line in reversed(out.splitlines()):
        if line.strip().startswith("HITS_JSON="):
            m = line.strip()[len("HITS_JSON="):]
            break
    if m is None:
        raise RuntimeError("scan returned no HITS_JSON line (exit %s): %s" % (
            proc.returncode, (proc.stderr or out)[-300:].strip()))
    hits = json.loads(m)
    if not isinstance(hits, list):
        raise RuntimeError("HITS_JSON was not a list")
    return [h for h in hits if isinstance(h, dict) and h.get("url")]


def norm_url(u):
    p = urllib.parse.urlsplit(u.strip())
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return urllib.parse.urlunsplit(("https", host, p.path.rstrip("/").lower(), p.query, ""))


def cmd_monitor():
    ids = load_ids()
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.chmod(MONITOR_DIR, 0o700)
    log("scan started")
    try:
        hits = run_claude(ids)
    except Exception as e:  # noqa: BLE001 - any failure should alert, never look like a clean week
        log("scan FAILED: %s" % e)
        notify(ids, "Privacy check didn't run this week. Log: %s" % LOG)
        sys.exit(1)

    first_run = not os.path.exists(LAST_HITS)
    previous = set()
    if not first_run:
        with open(LAST_HITS) as f:
            previous = {norm_url(h["url"]) for h in json.load(f)}

    new = [h for h in hits if norm_url(h["url"]) not in previous]
    gone = len(previous - {norm_url(h["url"]) for h in hits})

    stamp = datetime.date.today().isoformat()
    write_private(os.path.join(HISTORY_DIR, "%s.json" % stamp), json.dumps(hits, indent=2))
    write_private(LAST_HITS, json.dumps(hits, indent=2))
    log("scan done: %d hits, %d new, %d gone since last run" % (len(hits), len(new), gone))

    if new:
        notify(ids, format_alert(new, first_run))


def format_alert(new, first_run=False):
    """Plain-language Telegram text: one bullet per site, what it shows, where."""
    def and_join(xs):
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]

    n = len(new)
    head = ("Privacy check: you're listed on %d site%s" if first_run
            else "Privacy check: you showed up on %d new site%s") % (n, "" if n == 1 else "s")
    lines = [head, ""]
    for h in new:
        shows = [x for x in h.get("exposes", []) if x]
        line = "\u2022 %s" % h.get("site", "").replace("www.", "")
        if shows:
            line += " \u2014 shows your %s" % and_join(shows)
        lines.append(line)
        lines.append("  %s" % re.sub(r"^https?://(www\.)?", "", h["url"]))
        if "namesake" in (h.get("evidence") or "").lower() or "unverified" in (h.get("evidence") or "").lower():
            lines.append("  (not confirmed - might be someone else with your name)")
    lines += ["", "To remove: python3 privacy_kit.py checklist"]
    return "\n".join(lines)


def notify(ids, text):
    n = ids.get("notify") or {}
    token, chat = n.get("telegram_bot_token"), n.get("telegram_chat_id")
    if token and chat:
        try:
            data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000],
                                           "disable_web_page_preview": "true"}).encode()
            urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % token, data, timeout=20)
            log("telegram alert sent")
            return
        except Exception as e:  # noqa: BLE001
            log("telegram failed (%s); falling back to local notification" % e)
    if sys.platform == "darwin":
        first = text.splitlines()[0].replace('"', "'")
        subprocess.call(["osascript", "-e",
                         'display notification "%s - details in %s" with title "Privacy monitor"'
                         % (first, HISTORY_DIR)])
    print(text)


def cmd_test_notify():
    notify(load_ids(), "Privacy monitor test - alerts are working.")


# ---------------------------------------------------------------------------
# install / uninstall (macOS launchd)
# ---------------------------------------------------------------------------

def cmd_install():
    if sys.platform != "darwin":
        sys.exit("install uses macOS launchd. On Linux, add a cron line instead:\n"
                 "  0 8 * * 1 %s %s monitor" % (sys.executable, os.path.abspath(__file__)))
    load_ids()
    claude = shutil.which("claude")
    if not claude:
        sys.exit("claude CLI not on PATH - install Claude Code and log in first (run `claude` once).")
    # Copy the script next to the private data so the schedule survives moving/deleting the repo.
    script = os.path.join(MONITOR_DIR, "privacy_kit.py")
    shutil.copy2(os.path.abspath(__file__), script)
    path = ":".join(dict.fromkeys([os.path.dirname(claude), os.path.dirname(sys.executable),
                                   "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]))
    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>{py}</string><string>{script}</string><string>monitor</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>{path}</string></dict>
  <key>WorkingDirectory</key><string>{wd}</string>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
""".format(label=LABEL, py=sys.executable, script=script, path=path, wd=MONITOR_DIR, log=LOG)
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "w") as f:
        f.write(plist)
    uid = os.getuid()
    subprocess.call(["launchctl", "bootout", "gui/%d/%s" % (uid, LABEL)], stderr=subprocess.DEVNULL)
    rc = subprocess.call(["launchctl", "bootstrap", "gui/%d" % uid, PLIST])
    if rc != 0:
        print("launchctl bootstrap failed. Run it yourself:\n  launchctl bootstrap gui/%d %s" % (uid, PLIST))
        sys.exit(rc)
    print("Scheduled: every Monday 08:00 (runs on wake if the Mac was asleep).\n"
          "Run once now to set your baseline:\n"
          "  launchctl kickstart gui/%d/%s\n"
          "Watch it:  tail -f %s" % (uid, LABEL, LOG))


def cmd_uninstall():
    subprocess.call(["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), LABEL)], stderr=subprocess.DEVNULL)
    if os.path.exists(PLIST):
        os.remove(PLIST)
    print("Removed the weekly schedule. Your data in %s was left alone." % BASE)


COMMANDS = {
    "setup": cmd_setup, "checklist": cmd_checklist, "letters": cmd_letters, "monitor": cmd_monitor,
    "install": cmd_install, "uninstall": cmd_uninstall, "test-notify": cmd_test_notify,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0 if len(sys.argv) == 1 else 2)
    COMMANDS[sys.argv[1]]()
