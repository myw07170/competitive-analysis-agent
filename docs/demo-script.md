# Demo Video Script

A suggested ~3-minute walkthrough for the submission video.

## Setup (off-camera, before recording)

1. `cd backend && python main.py` — backend on `:8000`.
2. `cd frontend && pnpm dev` — frontend on `:5173`.
3. Set `VOLC_MOCK=1` if you don't want live LLM calls during recording. The same UI works either way.
4. Open `http://127.0.0.1:5173` in a clean browser window.

## Scene 1 — Project intro (0:00 – 0:20)

> "This is a multi-agent competitive-analysis system. A user picks a product and a market — China or the US — and four specialized AI agents collaborate to produce a structured, source-traceable competitive report. The interface, the prompts, and the output all switch language based on the market."

Show: the home screen, the form, the market chips.

## Scene 2 — Start an analysis (0:20 – 0:45)

Type `Notion` in the product field. Click the 🇺🇸 US market chip. Click "Start analysis".

> "I'm asking it to analyze Notion against US competitors. Watch the DAG."

The DAG animates: `identify` lights up, then `collect`, then `analyze`, then `write`, then `qc`.

## Scene 3 — The feedback loop (0:45 – 1:15)

When QC fires, point at the visualization.

> "Notice the QC agent didn't approve on the first pass — it found two pricing tiers with only one source each. That's below our threshold. So the DAG re-routes back to the Collector with the specific findings injected into its next prompt. The Collector reruns, this time targeting the gaps."

Show: the dashed red `rework` edge highlighting, the second pass of `collect` running.

> "On the second iteration, QC approves. This is a real loop — the second-pass output is measurably different from the first, not a pseudo-loop."

## Scene 4 — Report tour (1:15 – 2:00)

The report opens automatically. Walk through the tabs.

1. **Report tab** — executive summary + market overview + function / pricing / user comparison + SWOT + recommendations. All in English because we picked the US market.
2. **Competitors tab** — per-competitor cards. Click a pricing tier's source badge to show that prices are traced to a real URL.
3. **Sources tab** — flat list of every source used. Each is a clickable link.
4. **Run metrics** (top of the page) — schema completeness, total tokens, QC iterations, rework count. These are the business-loop KPIs.

## Scene 5 — Trace replay (2:00 – 2:30)

Click the **Trace** tab.

> "Every agent decision is recorded. I can click any row to see the exact prompt, the exact input, and the exact JSON output. This is the audit trail — useful for debugging, useful for compliance, useful for tuning."

Click a `collector.gather_competitor` row, expand the response, scroll through the JSON.

## Scene 6 — Switch language (2:30 – 2:50)

Back to home. Type `飞书`. Click 🇨🇳 China. Start.

> "Same code path, different market. Interface and report switch to Chinese, the search backend switches to a CN-tuned provider, and the agents draw on a different set of allowed source domains."

Watch the same DAG animate.

## Scene 7 — Wrap (2:50 – 3:00)

> "Four agents. Real feedback loop. Strict schema. Source-traceable output. Pluggable markets. Observable end-to-end. That's the system."

## Talking points if asked

* **Why LangGraph?** State machine + conditional edges + visualization. The `rework` edge being a first-class graph element is what makes the loop auditable.
* **Why Pydantic?** Structured messaging between agents has to be enforced — natural-language hand-offs lose accuracy at every hop.
* **Why mock mode?** Robust demos, offline development, regression tests that don't hit the network.
* **How would you extend to a new market?** Three small files; the docs (`docs/extension.md`) walk through it in detail. No changes to agents or orchestrator.
