# Fundação Âncora — Funding Radar

A self-contained funding-intelligence hub on GitHub. It hosts a dashboard, and
on a schedule it searches Portuguese/EU affordable-housing funding sources with
the Claude API, scores each for fit against Âncora's mandate, and commits new
opportunities back into the dashboard.

Everything lives in this one repo — **hosting, scheduling, and data**. No
external server, no desktop app needs to be running.

## What's in here

| File | Purpose |
|------|---------|
| `index.html` | The dashboard (GitHub Pages serves this). Grant data lives in its `DEFAULT_GRANTS` array. |
| `radar.py` | The radar: calls Claude (with web search) and injects new opportunities into `index.html`. |
| `.github/workflows/radar.yml` | Scheduled GitHub Action that runs `radar.py` and commits the result. |
| `requirements.txt` | Python dependency (`anthropic`). |

## One-time setup

1. **Create the repo** and push these files (default branch `main`).

2. **Add the API key.** In the repo: *Settings → Secrets and variables → Actions
   → New repository secret*
   - Name: `ANTHROPIC_API_KEY`
   - Value: an Anthropic API key (from console.anthropic.com). This is what pays
     for the smart search/scoring; usage per run is small.

3. **Enable Pages.** *Settings → Pages → Build and deployment → Source:
   Deploy from a branch → Branch: `main` / root.* Your dashboard will be at
   `https://<owner>.github.io/<repo>/`.

4. **Confirm Actions can write.** *Settings → Actions → General → Workflow
   permissions → Read and write permissions.* (The workflow also declares
   `permissions: contents: write`.)

## How it runs

- **Schedule:** the workflow triggers on the **1st and 15th of each month at
  06:00 UTC** (GitHub cron is UTC and has no native "bi-weekly"; `1,15` is the
  closest stable equivalent). Edit the `cron:` line in `radar.yml` to change it.
- **Manual run:** *Actions → Funding Radar → Run workflow.*
- Each run: `radar.py` reads the current `DEFAULT_GRANTS`, asks Claude for new
  opportunities not already tracked, injects them, updates the "Last radar run"
  date, and the Action commits `index.html`. Pages redeploys automatically.
- **Data & audit trail:** the grant list is the `DEFAULT_GRANTS` array in
  `index.html`; git history is your log of every run.

## Important caveats

- **GitHub pauses idle schedules.** If the repo gets no commits for 60 days,
  GitHub disables scheduled Actions. Since each radar run commits, an active
  radar stays alive — but if it goes quiet, re-enable it from the Actions tab.
- **Injection anchor.** `radar.py` injects specifically before the
  `];\nlet grants=[...DEFAULT_GRANTS];` line. Do not change that line, and never
  inject with a global `];` replace — the first `];` in the file closes the
  themes array and a global replace corrupts the dashboard.
- **Model.** Defaults to `claude-sonnet-5`; override with a `RADAR_MODEL` env
  var / secret if desired.
- **Cost & keys belong to the recipient.** Whoever owns this repo owns the API
  key and its usage.

## Local test (optional)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python radar.py
```
