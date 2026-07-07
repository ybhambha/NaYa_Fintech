# Market Risk VaR Demo — Atoti (ActiveViam)

An FRTB-aligned market-risk demonstration built on **Atoti 0.9**, showing how a
real-time OLAP aggregation engine handles the measures that a spreadsheet
cannot: **VaR, Expected Shortfall, Component VaR, PnL Attribution, sensitivities
netting, and Basel backtesting** — all recomputed live at every level of
aggregation.

## The point of the demo

Value-at-Risk is **non-additive**: the firm's VaR is *not* the sum of its desks'
VaRs, because losses in different books offset (diversification). You cannot
pre-compute and store desk-level VaRs and add them up — the quantile has to be
recomputed on the aggregated loss distribution at *every* node you drill to.

This demo makes that concrete by putting two behaviours side by side on one
dashboard:

- **VaR / ES** — non-additive. Desk numbers deliberately *don't* sum to the firm
  total. The gap is diversification.
- **Sensitivities** — additive. Delta nets cleanly across desks (one desk's short
  offsets another's long).

Same underlying trade data, two opposite aggregation behaviours — which is
exactly why market risk needs an engine that recomputes quantiles on the fly
rather than a spreadsheet that only adds.

## Architecture

Every cube is built from **one shared set of trade-level P&L sub-vectors**,
decomposed by the FRTB risk taxonomy (risk class → risk factor → tenor). Because
all cubes draw from the same positions, their desk-level numbers reconcile to the
cent.

| Cube | Grain | Purpose |
|------|-------|---------|
| **Market Risk VaR** | Booking (Entity → Desk → Book → Trade) | VaR, ES, Component VaR, backtesting |
| **VaR by risk** | Risk class × Risk factor × Tenor | The non-additive slice-and-dice view |
| **PnL Explain** | Effect × Risk factor × Greek | P&L attribution (market data / carry / FX / unexplained) |
| **Sensitivities** | Book × Risk factor × Tenor | Additive Greek roll-up and cross-desk netting |

Key measure design (Market Risk VaR cube):

- `VaR 99% = -quantile(Σ PnL vectors, 0.01)` — vectors are **summed first, then**
  the quantile is taken (the non-additive step).
- `ES 97.5% = -mean(n_lowest(Σ PnL vectors, 7))` — FRTB's Expected Shortfall
  measure (⌈0.025 × 250⌉ = 7 tail scenarios).
- `Component VaR` fixes the firm's tail scenario via `quantile_index` and
  decomposes it across desks — the *additive* cousin of VaR that sums exactly to
  the firm number.

## Notebook structure

- **Part 1** — Synthetic data: five reconciled tables built from shared risk
  sub-vectors (seeded, so runs are reproducible).
- **Part 2** — Session start, load tables, join the shared Trades dimension.
- **Part 3** — Market Risk VaR cube: headline diversification (3a), day-over-day
  VaR (3b), scenario tail drill (3c), Component VaR (3d), incremental VaR (3e),
  Basel backtesting (3f).
- **Part 4** — PnL Explain cube and drill-down / market-data attribution (4a).
- **Part 5** — VaR slice-and-dice: the stacked tables that *don't* sum, plus a
  reconciliation showing desk VaR is identical via Booking and via Risk class.
- **Part 6** — Sensitivities slice-and-dice: the stacked tables that *do* sum,
  with cross-desk GIRR Delta netting.
- **Part 7** — Interactive dashboard and demo script.

## Requirements

- **Python 3.11**
- **Java 21, 64-bit** — required by the Atoti Server (the embedded JVM). This is
  the most common setup snag: if the wrong Java is on `PATH`, the session fails
  to start.
- **~16 GB RAM** recommended.
- `atoti[jupyterlab]` (0.9.x)

## Running it

```bash
conda create -n mr_atoti python=3.11 -y
conda activate mr_atoti
pip install "atoti[jupyterlab]"
jupyter lab
```

Then, **from the `ActiveViamDemo` folder**, open `market_risk_full_demo.ipynb`
and run cells top to bottom. Launch Jupyter from this folder so the relative
`content/` path resolves correctly.

**Important:** run the notebook through **Part 6 before opening the Part 7
dashboard.** Measures are added to the cube incrementally across cells, so the
dashboard only sees the measures whose cells have executed. A partial run leaves
dashboard tiles empty.

## Notes

- **Data is synthetic and seeded.** Re-running regenerates identical numbers, so
  the dashboard is reproducible.
- **Dashboards persist across restarts** via the `content/` user-content store (an
  embedded H2 database). This folder is git-ignored — dashboards are recreated by
  re-running the notebook, not versioned. The *data* is in-memory only, so after a
  restart you re-run the notebook to rebuild the cubes, then reopen the saved
  dashboard.
- **Single-writer content store.** Only one live session may hold `content/` at a
  time. If a previous session's JVM is still alive (e.g. after a kernel restart
  without a clean `session.close()`), you'll hit a "database may be already in
  use" lock — kill the stray `java` process and re-run.

---

*Prototype / demonstration built for illustrating modern market-risk aggregation
patterns. Synthetic data only.*
