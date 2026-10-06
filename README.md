# data-broker-cleanup

Get your name, phone, address and email off people-search sites (Whitepages, Spokeo, TruePeopleSearch and the rest), send legal deletion requests to the brokers that feed them, and get a weekly alert if you show up again.

One Python file, no installs. Your details stay on your machine in a file only you can read.

## What you need

- A Mac (the weekly schedule uses launchd; everything else works on Linux too)
- `python3` (already on macOS)
- [Claude Code](https://claude.com/claude-code), logged in, for the weekly monitor only
- About 2 hours for the first pass, mostly clicking confirmation emails

## Do it

```bash
git clone https://github.com/rlinder00/data-broker-cleanup
cd data-broker-cleanup

python3 privacy_kit.py setup       # your names, emails, phones, addresses (+ optional Telegram alerts)
python3 privacy_kit.py checklist   # opt-out links in priority order - work through them in a browser
python3 privacy_kit.py letters     # 16 deletion emails, one click each to send
python3 privacy_kit.py install     # weekly scan, Mondays 8am
```

### 1. Setup

Asks for every name variant you're listed under (nicknames, middle initial, maiden name), current and old phones, emails and addresses. Old ones matter: brokers keep them all. Saved to `~/privacy-cleanup/monitor/identifiers.json` with `chmod 600`.

### 2. Opt-out forms (the checklist)

Order matters:

1. **California DROP** (CA residents): one request goes to every registered data broker, and they have to re-process it every 45 days. Do this first.
2. **PeopleConnect**: one suppression covers Intelius, InstantCheckmate, TruthFinder, USSearch and ZabaSearch.
3. **Whitepages**: verifies by phone call.
4. Then the rest: Spokeo, TruePeopleSearch, FastPeopleSearch, SearchPeopleFree, USPhonebook, PeopleFinders, BeenVerified, and so on.

Things that will trip you up:
- **CAPTCHAs and Cloudflare.** Use a normal browser window. Bots get blocked.
- **Password-manager popups.** 1Password's inline menu can steal clicks on these forms. Turn it off for the site if a button won't respond.
- **Confirmation emails expire.** Click them the same day.
- **Listings take 24 to 72 hours to drop.**

### 3. Deletion letters

`letters` writes one email per broker to `~/privacy-cleanup/letters/` and an `index.html` where each link opens a ready-to-send email. If you live in California the letters cite the CCPA/CPRA sections; anywhere else they cite your state's privacy law generically.

The letters include only your name, city and email. Don't volunteer your address or birthday; make them ask.

Companies have **45 days** to respond. Put the date on your calendar. If a company ignores you and you're in California, file at <https://privacy.ca.gov/submit-a-complaint/ccpa-complaints/>. Elsewhere, file with your state Attorney General.

### 4. Weekly monitor

`install` schedules `privacy_kit.py monitor` for every Monday at 8am. If the Mac is asleep then, it runs when the Mac wakes. Each run:

1. runs `claude -p` with **only** web search and web fetch allowed, so it can't touch your files;
2. searches every name variant, email, phone and address, plus ~30 people-search sites;
3. compares the results with last week's;
4. alerts you **only about new pages**. The first run is your baseline and lists everything.

Alerts go to Telegram if you set it up in `setup` (make a bot with @BotFather, message it once, paste the token). Without Telegram you get a macOS notification. A failed scan also sends an alert, so a silent week means a clean week.

```bash
python3 privacy_kit.py monitor                                      # run a scan now
tail -f ~/privacy-cleanup/monitor/monitor.log                       # watch it (no personal details are logged)
python3 privacy_kit.py test-notify                                  # check alerts work
python3 privacy_kit.py uninstall                                    # stop the schedule
```

Each scan uses your Claude Code plan/credits (one agent run of a few minutes per week).

## Where your data goes

| What | Where | Who sees it |
|---|---|---|
| Your identifiers | `~/privacy-cleanup/monitor/identifiers.json` (600) | You, and Claude during the weekly scan |
| Scan results | `~/privacy-cleanup/monitor/history/` (600) | You |
| Alerts | Telegram (optional) | You, via your own bot |
| Letters | Your mail app | The broker you send each one to |

Nothing is committed to this repo. Don't fork it and add your file.

## Good to know

- **Public records are exempt.** Property and voter records count as "publicly available" under the CCPA, so people-search sites suppress them as a courtesy rather than deleting them. Emails, phones and inferred data are fully covered.
- **Some sites are dead or seized** (Radaris, PeekYou, ClustrMaps, Nuwber as of Oct 2026). The monitor still checks them in case they come back.
- **Expect relistings.** Brokers re-scrape. That's what the monitor is for: when it pings you, rerun that site's opt-out.
- Broker URLs and emails were checked in October 2026. If one bounces, search "<broker> privacy request" and open a PR.

Not legal advice.
