# MedFlow AI: Evaluation of tools from the Instagram reel dataset

Prepared 2026-10-20. Source: `dataset_instagram-reel-scraper_2026-10-21_01-10-49-285 (1).json` (18 reels, transcript + caption). The other file in Downloads holds the same 18 transcripts without captions.

**Method.** I read all 18 reels and pulled out every named tool and technique. I checked each GitHub project against the GitHub API (stars, created and last-push dates, license, archived flag) and read its README for install method, runtime requirements and data handling. I treated the reels' claims as unverified until a README or the repo backed them up. Nothing was installed and no project files were touched.

**Dataset quality.** 4 of the 18 transcripts are non-English or unrelated to their captions (reels 2, 3, 11, 15), so for those only the caption counts. 4 reels are marked `#sponsored` / `#manuspartner` (reels 4, 10, 15, plus the Manus pitch in reel 10). Several reels are "comment X for the link" lead-gen posts. Reel 17 (Gemini 2.0 image generation) is outdated and off-topic.

---

## 1. Everything mentioned, verified

Stars and dates come from the GitHub API on 2026-10-20. "Fit" means fit for Flask + Jinja2 + vanilla JS + JSON storage, inside 8 days.

### Coding quality and architecture

| Tool (reel) | Verified source | Stars / last push / license | What it actually is | Fit |
|---|---|---|---|---|
| Karpathy skills (7) | multica-ai/andrej-karpathy-skills (formerly forrestchang) | 221k / 2026-04-20 / no license file | One `CLAUDE.md` with 4 principles: think first, simplicity, surgical changes, goal-driven verification | **High.** Plain text, nothing to run |
| Ponytail (1, 2) | DietrichGebert/ponytail | 170k / 2026-10-18 / MIT | "Lazy senior dev" skill plus a status band, hooks, `/ponytail-review`, `/ponytail-audit`, and a local usage board | Medium. Good idea, but it overlaps Karpathy and adds hooks and a UI band |
| Superpowers (1, 2) | obra/superpowers (in the official marketplace) | 303k / 2026-10-20 / MIT | Full methodology: brainstorm, spec, plan, TDD, then hours-long autonomous subagent runs | Medium-low for 8 days. Heavy process; the visual companion loads a logo from the vendor's site by default (README calls this "telemetry") |
| Matt Pocock skills, incl. "Grill me" (2, 7) | mattpocock/skills | 299k / 2026-10-19 / MIT | 38 separate SKILL.md files; `grill-me`, `tdd`, `handoff`, `code-review` are useful on their own | **High if cherry-picked** (copy 2 files) |
| Addy Osmani agent-skills (2, 7) | addyosmani/agent-skills | 109k / 2026-10-13 / MIT | 25 skills + 9 lifecycle commands (spec, TDD, review, ship) | Medium. Good quality, but it duplicates Matt Pocock's set; pick one author |
| Everything Claude Code (6) | affaan-m/ECC (renamed) | 285k / 2026-10-20 / MIT | 71 agents, 311 skills, 97 command shims, hooks, memory, "continuous learning"; paid tier for private repos | **Avoid.** Massive surface area. The "270k stars" claim checks out; the hackathon story is unverified |
| AutoHarness (1) | tigerless-labs/autoharness | 10k / 2026-10-15 / MIT | Watches your sessions and writes new skills into `.claude/skills/` automatically | Avoid. Instructions you never reviewed end up steering the agent |
| Caveman (7) | JuliusBrussee/caveman | 114k / 2026-10-20 / Apache-2.0 | Terse output style + token-reducing proxy ("six rocks", all on after install) | Avoid. You want clear explanations while learning the code; the proxy is one more moving part |
| I Have ADHD (2, 7) | ayghri/i-have-adhd | 58k / 2026-10-19 / MIT | Output-format skill: action first, numbered steps | Low. Personal taste; doesn't change code quality |

### Frontend / UI

| Tool (reel) | Verified source | Stars / last push / license | What it actually is | Fit |
|---|---|---|---|---|
| Impeccable (2, 12) | pbakaus/impeccable | 84k / 2026-10-20 / Apache-2.0 | One design skill, 24 `/impeccable` commands (`init`, `critique`, `audit`, `polish`…), 61 detector rules for "AI-looking" UI. Grew out of Anthropic's frontend-design skill | **High.** Framework-agnostic; works on Jinja + CSS |
| UI/UX Pro Max (1) | nextlevelbuilder/ui-ux-pro-max-skill | 138k / 2026-10-15 / MIT | Design-rule database + global npm CLI (`uipro`); 22 stacks, closest match is "HTML+Tailwind" | Low-medium. Overlaps Impeccable; global npm install |
| Make Interfaces Feel Better (12) | jakubkrehel/make-interfaces-feel-better | 3.7k / 2026-08-29 / MIT | One small skill: spacing, shadows, hover states, hit areas | Medium. Good, but Impeccable's `polish` covers it. Use as a fallback |
| GSAP skills (12) | greensock/gsap-skills (official) | 17k / 2026-07-29 / MIT | Teaches agents GSAP animation | Low. Adds a JS library; a health dashboard doesn't need scroll animation |
| Transitions.dev (12) | Jakubantalik/transitions.dev | 5.4k / 2026-10-17 | 43 UI transitions + skill | Low. Decorative |
| Watermelon UI (4, 10) | ui.watermelon.sh | — | React/TypeScript component library | **Incompatible** (needs React) |
| Cult UI (4) | nolly-studio/cult-ui | 6.6k / TypeScript | shadcn/ui + Tailwind + Motion (React) | **Incompatible** |
| Skiper UI (4) | not found on GitHub | — | React animation components (website only) | **Incompatible / unverified** |
| Realtime Colors, Godly (10) | websites | — | Palette and font tester; gallery of well-designed sites | Useful as free reference sites; nothing to install |
| Animation style lists (5, 18) | prompts | — | Lists like "glassmorphism, metaballs…" | Avoid on a healthcare UI; they distract and hurt accessibility |
| Diagram Design (1, 2) | cathrynlavery/diagram-design | 59k / 2026-10-20 / MIT | Editorial HTML/SVG diagrams | Optional for the README only |
| Archify (7, "Arcify" in the transcript) | tt-a1i/archify | 86k / 2026-10-20 / MIT | Codebase to interactive diagram | Optional, same role as above; pick at most one |

### Testing and security

| Tool (reel) | Verified source | Stars / last push / license | What it actually is | Fit |
|---|---|---|---|---|
| Cloudflare Security Audit (1, 2) | cloudflare/security-audit-skill | 34k / 2026-09-14 / MIT | 6-phase, multi-agent audit with schema-validated `findings.json`; Node validators | Medium. Credible, but heavy and token-hungry for a ~2k-line Flask app. One run on day 7 at most |
| Strix (8) | usestrix/strix | 70k / 2026-10-21 / Apache-2.0 | AI pentester; needs Docker, its own LLM API key, `curl \| bash` installer; attacks a running app | Avoid for a local demo. Reconsider if the app is ever deployed |
| Open Code Review (1) | alibaba/open-code-review | 48k / 2026-10-20 / Apache-2.0 | Standalone diff reviewer with its own LLM config | Redundant with Claude Code's built-in `/code-review` |
| Built-in `/code-review`, `/security-review` | already in this Claude Code install | — | Review the current diff for bugs and security problems | **High.** Zero install |

### Documentation and agent productivity

| Tool (reel) | Verified source | Stars / last push / license | What it actually is | Fit |
|---|---|---|---|---|
| Handoff.md technique (9) | technique | — | Before `/clear`, write goal, state, active files, changes, failed attempts, next steps to a file; resume from it | **High.** Free, no install |
| Planning with Files (7) | OthmanAdi/planning-with-files | 28k / 2026-10-20 / MIT | Same idea, enforced by hooks that inject `task_plan.md`/`progress.md` every turn | Medium-low. Do it by hand instead; the hook adds noise to every turn |
| Claude Mem (7, 8) | thedotmack/claude-mem | 102k / 2026-10-21 / Apache-2.0 | Captures everything the agent does into a memory service run by a background worker. Installer prompts sign-in to a hosted "CMEM Pro" observer (30-day trial); some IDE installs default to hosted | **Avoid.** Sends session data to a third party by default on some paths; redundant with HANDOFF.md |
| Graphify (2) | Graphify-Labs/graphify | 130k / 2026-10-20 / Apache-2.0 | Codebase to queryable knowledge graph | Avoid. The codebase will be small enough to read directly |
| Claude Code Setup (8) | anthropics/claude-plugins-official/plugins/claude-code-setup | official | Read-only skill that recommends hooks, skills and MCP servers | Low. Safe, but this report does the same job |
| Anthropic skills: docx/pdf/xlsx (7) | anthropics/skills | 183k / 2026-10-09 | Lets Claude produce Office/PDF files | Low. Not an app feature; only useful for writing a demo handout |
| Humanizer (2) | blader/humanizer | 59k / MIT | Rewrites AI-sounding prose | Low. Maybe for the README |
| MCP connectors, read-only principle (13) | technique | — | Connect external services through MCP with read-only scopes | The principle is good. MedFlow needs no MCP server: storage is local JSON |

### Deployment / infrastructure / other

| Tool (reel) | Verified source | Notes | Fit |
|---|---|---|---|
| Free LLM API (8) | tashfeenahmed/freellmapi (38k, MIT) | Routes requests across 34 providers' free tiers. You sign up for each provider yourself; the "7 billion tokens" figure is per month, summed across those free tiers. Pulls a self-updating model catalog from a remote feed | **Avoid.** Your code and prompts go to whichever free provider answers, under that provider's data and training terms |
| OmniRoute (1) | diegosouzapw/OmniRoute (79k, MIT) | Same category: one endpoint, 375 providers, Docker | **Avoid**, same reasons |
| CC Switch (7) | farion1231/cc-switch (147k, MIT) | Desktop app that switches and rewrites configs for many coding agents | Avoid. You use one agent |
| Walker (1) | not found | "Run a fleet of agents" | Unverified. Fleets of agents work against your constraints anyway |
| Agent Reach (8, 16) | Panniantong/Agent-Reach (100k, MIT) | Scrapes Twitter/Reddit/Instagram etc., partly via cookies you export yourself | Avoid. Irrelevant, and a terms-of-service risk |
| Manus (4, 10, 15) | sponsored | Hosted AI app builder, separate from Claude Code | Avoid. Sponsored pitch; would replace your stack |
| Perplexity / PostHog / Context.dev (14) | ChatGPT connectors | Research, analytics, scraping | Avoid. PostHog would send usage data to a third party; not needed for a local demo |
| Universal Modder (1) | rehan-remade/universal-modder | Mods PC games | Irrelevant |
| Gemini 2.0 image generator (17) | — | Outdated by 2026 | Irrelevant |

---

## 2. Ranking: the plausible candidates

Scored 1–5 (5 = best). "Install" and "Maint." are scored for *ease* and *low risk*, so higher is better everywhere.

| Rank | Tool / technique | Benefit | Install ease | Maint. (low risk) | 8-day fit | Total |
|---|---|---|---|---|---|---|
| 1 | Project `CLAUDE.md` using the Karpathy principles | 5 | 5 | 5 | 5 | **20** |
| 2 | PLAN.md + HANDOFF.md + `/clear` | 4 | 5 | 5 | 5 | **19** |
| 3 | Built-in `/code-review` + `/security-review` | 4 | 5 | 5 | 5 | **19** |
| 4 | `grill-me` + `tdd` (2 files from mattpocock/skills) + pytest | 4 | 4 | 4 | 5 | **17** |
| 5 | Impeccable (project-scoped) | 5 | 3 | 4 | 4 | **16** |
| 6 | Make Interfaces Feel Better (Impeccable fallback) | 3 | 4 | 4 | 4 | 15 |
| 7 | Ponytail (instead of Karpathy, not with it) | 4 | 3 | 3 | 4 | 14 |
| 8 | Cloudflare security-audit (one run, day 7) | 3 | 3 | 4 | 3 | 13 |
| 9 | Addy Osmani agent-skills (instead of Pocock) | 3 | 3 | 4 | 3 | 13 |
| 10 | Diagram Design or Archify (README diagram) | 2 | 3 | 4 | 3 | 12 |
| 11 | Superpowers | 4 | 4 | 3 | 2 | 13* |
| — | Everything else | ≤2 | — | — | — | Skip |

\*Superpowers is solid software, but its brainstorm-spec-plan-subagent loop adds ceremony and long autonomous runs that eat your 8 days and your tokens. #1, #2 and #4 give you most of its value with far less overhead.

---

## 3. Top five recommendations

### 1. A MedFlow `CLAUDE.md` built on the Karpathy principles
**Why:** The cheapest, highest-value change. It gets Claude to state assumptions, keep code minimal, make surgical edits and verify its work, and it encodes your constraints so you don't have to repeat them.
**Contents (~60 lines):** the four principles, rewritten in your own words (the repo has no license file, so don't copy it verbatim), plus project rules:
- Stack is Flask + Jinja2 + vanilla JS + JSON files. No React/Next.js/database/new dependency without asking.
- All storage goes through one module (e.g. `storage.py`); routes never touch files directly.
- All data is fictional. No real names, addresses or IDs.
- Run `pytest` before saying a task is done.
- Jinja autoescaping stays on; never use `|safe` on user input.

**Workflow fit:** Claude Code reads it automatically every session.

### 2. File-based plan and handoff (the technique from reel 9)
**Why:** Long sessions degrade. A plan on disk survives `/clear` with no plugin, no hooks and no third-party memory service.
**How:** `docs/PLAN.md` holds the 8-day milestone checklist. `docs/HANDOFF.md` follows reel 9's six headings: goal, current state, active files, changes made, failed attempts, next steps. At the end of each feature, or when Claude starts repeating a mistake: "update HANDOFF.md", then `/clear`, then "read docs/HANDOFF.md and continue".

### 3. Built-in `/code-review` and `/security-review`
**Why:** They're already installed. They review your diff for bugs and security issues, so they replace Open Code Review, Strix and most of what the Cloudflare skill would do on a project this size.
**How:** Run `/code-review` before each feature commit. Run `/security-review` at the end of days 4 and 7. Focus areas for MedFlow: path handling in the JSON store, form validation, CSRF on POST forms, `SECRET_KEY` read from the environment, debug mode bound to 127.0.0.1 only.

### 4. `grill-me` + `tdd` from mattpocock/skills, with pytest
**Why:** `grill-me` interviews you before anything is built, so the spec in PLAN.md is right on day 1. `tdd` keeps every feature behind a red-green test. pytest + Flask's test client is the only new dependency, and it's dev-only.
**How:** Copy just those two `SKILL.md` files into `.claude/skills/` after reading them. Don't install the whole 38-skill repo. Tests go first on the JSON storage layer (atomic writes, missing or corrupt file, IDs), then on each route's happy path and one failure path.

### 5. Impeccable for the "polished" part of the MVP
**Why:** The most direct fix for generic AI-looking UI. It's framework-agnostic, so it works on Jinja templates with plain CSS, and its `audit` command covers accessibility and responsiveness, which matter in a health app.
**How:** Run `/impeccable init` once to write `PRODUCT.md` (audience: patients managing appointments and costs; tone: calm, trustworthy). Then use only four commands: `shape` before building a page, `critique` and `polish` after, `audit` on day 7. Keep the output in one `static/css/` design-token file.

---

## 4. Tools to avoid, and why

| Avoid | Reason |
|---|---|
| ECC / "Everything Claude Code" | 71 agents and 311 skills. Overlaps everything, hard to predict which agent triggers when, upsells a paid tier. The opposite of "minimal" |
| Superpowers (full framework) | Good, but process-heavy for 8 days. Its autonomous multi-hour subagent runs conflict with "avoid excessive agents". Loads a vendor-hosted logo by default (README's telemetry note) |
| Claude Mem | Background worker plus a capture-everything design; installer pushes a hosted memory sign-up. Third-party data flow is the wrong default for a healthcare-themed project, even with fictional data. HANDOFF.md does the job |
| Free LLM API, OmniRoute | Send your code and prompts to dozens of free-tier providers with varying data and training terms; self-updating remote catalogs. Promo numbers are aggregates of free tiers you must sign up for yourself |
| Strix | Docker + separate LLM key + `curl \| bash` install, for an app that only runs locally |
| AutoHarness | Writes unreviewed skills into your project automatically |
| Caveman, I Have ADHD | Style tweaks; Caveman also adds a proxy. Clarity matters more than token savings here |
| CC Switch, Walker, agent fleets | Multi-agent orchestration you don't need, and Walker couldn't be verified |
| Watermelon UI, Cult UI, Skiper UI | React/shadcn/Tailwind. Using them means adopting React |
| GSAP skills, Transitions.dev, animation style lists | Extra dependencies and motion that hurt a calm, accessible health UI |
| UI/UX Pro Max | Duplicates Impeccable; global npm CLI; best fit is Tailwind stacks |
| Graphify, Archify (for agent context) | Unnecessary for a small codebase |
| Agent Reach, Context.dev, PostHog, Perplexity, Manus | Scraping, analytics or hosted builders: irrelevant, privacy-adverse, or sponsored |
| Planning with Files plugin | The technique is good; its every-turn hook isn't needed. Do it by hand |

**Rule of thumb:** one design skill, one set of process principles, no memory or proxy services, no extra agents.

---

## 5. Proposed Claude Code workflow for MedFlow AI

**Per-feature loop (repeat for each feature):**
1. **Plan:** in plan mode, "read docs/PLAN.md; plan the Appointments list + create form". Approve or adjust the plan.
2. **Test first (tdd):** write failing pytest tests for the storage functions and routes.
3. **Implement:** the smallest code that passes, following CLAUDE.md.
4. **UI pass:** `/impeccable critique`, then `polish` on the new template.
5. **Verify:** `pytest`; open the page locally; `/code-review` on the diff.
6. **Commit:** one feature per commit, so any bad step is easy to revert.
7. **Handoff:** update HANDOFF.md, `/clear` if the session is long.

**8-day plan:**

| Day | Focus | Claude Code usage |
|---|---|---|
| 1 | Spec + skeleton | `grill-me` to settle scope; write PLAN.md and CLAUDE.md; `/impeccable init`; Flask app factory, base template, `storage.py` with atomic JSON writes (temp file + `os.replace`), fictional seed data |
| 2 | Appointments | CRUD + tests; status (upcoming/past/cancelled) |
| 3 | Medical expenses | CRUD + categories + monthly totals; tests on the money math (store cents as integers) |
| 4 | Price comparison | Fictional `prices.json` (procedure × provider); filter and sort in Jinja; `/security-review` checkpoint |
| 5 | Dashboard | Aggregate cards (next appointment, spend this month, savings found); `impeccable shape/polish` |
| 6 | Optional AI explanations | Behind a feature flag (`MEDFLOW_AI=0` by default); Claude API with fictional data only; a canned fallback so the demo works offline; show a "not medical advice" note; escape model output |
| 7 | Hardening | `/security-review`, `/code-review`, `/impeccable audit` (accessibility, responsiveness); fix only what they find |
| 8 | Demo prep | Reset script for seed data, README with screenshots, demo rehearsal, code freeze |

---

## 6. Installation plan (each step needs your approval)

Nothing below has been run. Each step is its own commit, so it can be reverted alone.

| Step | Action | Writes to | Network / code execution | Approve? |
|---|---|---|---|---|
| 0 | Create `CLAUDE.md`, `docs/PLAN.md`, `docs/HANDOFF.md` (templates I write; Karpathy principles paraphrased) | repo root, `docs/` | none | ☐ |
| 1 | Add `pytest` to `requirements-dev.txt` and install it in the project venv | venv | PyPI | ☐ |
| 2 | Download `grill-me/SKILL.md` and `tdd/SKILL.md` from mattpocock/skills; I show you their contents first, then copy them to `.claude/skills/` | `.claude/skills/` | raw.githubusercontent.com, text only | ☐ |
| 3 | Impeccable: first read its install script and list exactly what it writes, then `npx impeccable install` at the project root (project-scoped, not global) | `.claude/` (to be confirmed before running) | npm package execution | ☐ |
| 4 | `/code-review`, `/security-review` | — | already available | nothing to install |
| 5 (optional, day 7) | Cloudflare security-audit: `npx skills add https://github.com/cloudflare/security-audit-skill --skill security-audit` (project scope), one run, then remove it | `.claude/skills/` | npm package execution | ☐ |

Not planned: any global installs, marketplaces beyond the official one, MCP servers, background services, Docker, or new app runtime dependencies.
