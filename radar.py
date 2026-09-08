#!/usr/bin/env python3
"""
Funding Radar for Fundação Âncora.

Runs inside GitHub Actions on a schedule. Uses the Claude API (with the
server-side web_search tool) to look across Portugal/EU affordable-housing
funding sources, judge fit against Âncora's mandate, and emit NEW opportunity
objects that are injected into index.html's DEFAULT_GRANTS array.

Requires env var ANTHROPIC_API_KEY (set as a GitHub Actions secret).
"""

import datetime
import json
import os
import re
import sys

import anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = os.path.join(HERE, "index.html")
MODEL = os.environ.get("RADAR_MODEL", "claude-sonnet-5")

# ---- Âncora context -------------------------------------------------------
ORG_BRIEF = """
Fundação Âncora is a Portuguese foundation building a permanent limited-profit
affordable-RENTAL housing system for the professional middle class (household
income ~EUR 1,200-2,500/month), under binding rules (permanence, cost-indexed
rents, full reinvestment). It mobilises public AND private capital, in
partnership with municipalities, social operators and the private sector.
Model: new construction on municipal land (surface rights), rehabilitation of
municipal/vacant buildings, and change-of-use conversions; energy-efficient /
sustainable building. Priority cities: Lisboa, Oeiras, Cascais, Sintra, Evora,
Coimbra, Porto. Target: 1,000 homes in 5 years -> 100,000-unit stock by 2045.
Surface grants, LOANS, guarantees, blended finance and impact investment all
count -- the model is capital mobilisation, not only grants.
"""

SOURCES = [
    "IHRU / Portal da Habitacao — https://www.portaldahabitacao.pt/",
    "1.º Direito — https://www.portaldahabitacao.pt/1.%C2%BA-direito",
    "PRR / Recuperar Portugal (housing RE-C02) — https://recuperarportugal.gov.pt/",
    "European Affordable Housing Plan — https://housing.ec.europa.eu/european-affordable-housing-plan_en",
    "Pan-European Housing Investment Platform — https://housing.ec.europa.eu/pan-european-housing-investment-platform_en",
    "EU Funding & Tenders Portal (New European Bauhaus, Horizon, cohesion) — https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
    "EIB Affordable & Sustainable Housing — https://www.eib.org/en/projects/topics/sustainable-cities-regions/urban-development/affordable-and-sustainable-housing",
    "Council of Europe Development Bank (CEB) — https://coebank.org/en/sectors/affordable-housing/",
    "Banco Portugues de Fomento / InvestEU — https://www.bpfomento.pt/",
    "Fundacao Calouste Gulbenkian (impact finance) — https://gulbenkian.pt/",
    "Portugal Inovacao Social / Portugal 2030 — https://pis.portugal2030.pt/",
    "Housing news monitors — https://news.fundsforngos.org/tag/housing/ and OECD/press",
]

VALID_THEMES = {"housing", "env", "cso", "women", "children", "water", "education", "health"}


def read_dashboard():
    with open(DASHBOARD, encoding="utf-8") as f:
        return f.read()


def existing_state(html):
    names = re.findall(r"name:'((?:[^'\\]|\\.)*)'", html)
    ids = [int(x) for x in re.findall(r"\{id:(\d+),\s*status:", html)]
    max_id = max(ids) if ids else 0
    return names, max_id


def ask_claude(existing_names, max_id):
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    today = datetime.date.today().isoformat()
    prompt = f"""You are the Funding Intelligence Agent for Fundação Âncora.

{ORG_BRIEF}

Today is {today}. Search the web across these sources for NEW affordable-housing
funding opportunities (grants, loans, guarantee lines, framework facilities,
calls, platforms) relevant to Âncora that are NOT already tracked:

{chr(10).join('- ' + s for s in SOURCES)}

Already tracked (do NOT repeat these, or close variants):
{chr(10).join('- ' + n for n in existing_names)}

Return ONLY a JSON array (no prose, no markdown fences) of new opportunities.
Each element must be an object with exactly these keys:
  id          integer, starting at {max_id + 1} and incrementing
  status      one of "interesting","reviewing","inprogress","watching"
              (reviewing if a dated deadline is within 60 days; inprogress if within 30; watching if relationship-based/no open call; else interesting)
  name        string
  funder      string
  deadline    human-readable string
  deadlineDate  "YYYY-MM-DD" or "" if rolling/unknown
  funding     display string e.g. "EUR 50,000,000"
  fundingNum  integer euros (approx-convert other currencies), or 0
  themes      array using only: {sorted(VALID_THEMES)} (most items are ["housing"] or ["housing","env"])
  fit         integer 1-5 (5 = squarely on Âncora's limited-profit affordable-rental mandate in a priority city)
  fitDesc     string, specific and actionable
  url         string
  notes       string (caveats, contacts, access route)

If nothing new is found, return []."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 12}],
        messages=[{"role": "user", "content": prompt}],
    )
    # Concatenate any text blocks in the final assistant message.
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return text


def parse_grants(text, max_id):
    # Be forgiving: strip code fences and grab the outermost JSON array.
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    m = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        print(f"Could not parse model JSON: {e}", file=sys.stderr)
        return []
    clean = []
    next_id = max_id + 1
    for g in data:
        if not isinstance(g, dict) or "name" not in g:
            continue
        g["id"] = next_id
        next_id += 1
        g["themes"] = [t for t in g.get("themes", ["housing"]) if t in VALID_THEMES] or ["housing"]
        try:
            g["fit"] = max(1, min(5, int(g.get("fit", 3))))
        except (TypeError, ValueError):
            g["fit"] = 3
        clean.append(g)
    return clean


def to_js(g):
    def s(v):
        return json.dumps(v, ensure_ascii=False)
    return (
        "  {id:%d, status:%s, name:%s, funder:%s, deadline:%s, deadlineDate:%s, "
        "funding:%s, fundingNum:%d, themes:%s, fit:%d, fitDesc:%s, url:%s, notes:%s},"
        % (
            g["id"], s(g.get("status", "interesting")), s(g["name"]), s(g.get("funder", "")),
            s(g.get("deadline", "")), s(g.get("deadlineDate", "")), s(g.get("funding", "")),
            int(g.get("fundingNum", 0) or 0), s(g["themes"]).replace('"', "'"),
            g["fit"], s(g.get("fitDesc", "")), s(g.get("url", "")), s(g.get("notes", "")),
        )
    )


def inject(html, grants):
    today = datetime.date.today().strftime("%-d %b %Y")
    block = "\n  // -- Radar: %s --\n" % today + "\n".join(to_js(g) for g in grants) + "\n"
    # Anchor on the DEFAULT_GRANTS close specifically (NOT a global "];").
    anchor = "];\nlet grants=[...DEFAULT_GRANTS];"
    if anchor not in html:
        raise SystemExit("Could not find DEFAULT_GRANTS close anchor in index.html")
    html = html.replace(anchor, block + anchor, 1)
    # Refresh the header run date.
    html = re.sub(r"Last radar run: [^·]*",
                  "Last radar run: %s " % datetime.date.today().strftime("%-d %B %Y"),
                  html, count=1)
    return html


def main():
    html = read_dashboard()
    names, max_id = existing_state(html)
    print(f"{len(names)} opportunities tracked, highest id {max_id}.")
    text = ask_claude(names, max_id)
    grants = parse_grants(text, max_id)
    if not grants:
        print("No new opportunities found this run.")
        return
    html = inject(html, grants)
    with open(DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Injected {len(grants)} new opportunit(y/ies):")
    for g in grants:
        print(f"  #{g['id']} {g['name']} — {g.get('deadline','')}")


if __name__ == "__main__":
    main()
