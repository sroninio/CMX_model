# CMX Gain Calculator — Project Context

## What This Is
An interactive HTML tool (`cmx_gain.html`) that models the throughput gain from adding CMX (a memory tier between HBM and network) to a GPU cluster running agentic AI workloads. Built with Plotly.js, no build step needed — just open in a browser.

## Physics Model

### Core Idea
The system is modeled as a diagonal line: `y = slope * x`, where:
- `x` = memory capacity (GB)
- `y` = throughput (reqs/sec)
- `slope = 1 / (AVG_agent_size * total_Ttools_avg)`

Adding CMX extends the capacity from HBM along the diagonal until hitting SOL (Speed-of-Light, the GPU compute ceiling).

### Key Points on the Chart
- **H** (was B/G): x = HBM. Where the system sits without CMX.
- **B**: same as H — the divergence point on the diagonal.
- **C**: x = HBM + CMX_T_GB_eff. Where the system lands with CMX (capped by min of Little's Law and ratio bound).
- **E**: directly below C at height y_B. Used to show the gain CE/BH.
- **S**: where the blue (infinite HBM) line meets SOL = (x_D_GB, SOL). Also marked on X axis.
- **R** on X axis: ratio bound = HBM + HBM * ratio / (1 - ratio)
- **L** on X axis: HW bound = HBM + CMX_BW * CMX_Ttools_avg (Little's Law)

### Three Special Cases
1. `hbm_sufficient`: y_B >= SOL — HBM alone reaches SOL, CMX not needed
2. `hbm_small`: y_B < RECOMP — HBM is so small the system hits recompute ceiling first
3. normal: RECOMP <= y_B < SOL — standard case

### CMX Capacity
- `CMX_cap_littles = CMX_BW * CMX_Ttools_avg` (Little's Law — HW bound)
- `CMX_cap_ratio = HBM * CMX_RATIO / (1 - CMX_RATIO)` (ratio constraint)
- `CMX_T_GB_eff = min(CMX_cap_littles, CMX_cap_ratio)` — actual C position
- `CMX_T_GB = CMX_cap_littles` — used for BE arrow span and HW bound line

### Validity
- **Not valid**: `CMX_cap_ratio > CMX_T_GB` (ratio bound right of HW bound — need higher CMX BW)
- **Not optimal**: `CMX_cap_ratio < CMX_T_GB` AND not sol_limited (could move more data to CMX)

## Ttools Distribution (Key Innovation)
Instead of manually setting `total_Ttools_avg`, `CMX_RATIO`, and `CMX_Ttools_avg`, the user specifies a **discrete histogram** of tool latencies:

| % of requests | Ttools (s) |
|---|---|
| 50 | 0 |
| 50 | 120 |

Then sets a **threshold τ**: requests with `Ttools > τ` go to CMX.
Plus **fraction at exactly τ** (0–1): what fraction of requests at exactly τ also go to CMX.

From these, the tool auto-computes:
- `total_Ttools_avg = Σ(pct × lat) / 100`
- `CMX_RATIO = Σpct(lat > τ) / 100 + tau_frac * Σpct(lat == τ) / 100`
- `CMX_Ttools_avg = weighted avg of CMX-bound latencies`

**Auto Optimize** button: sweeps all τ candidates × fractions 0.00–1.00, finds config maximizing reqs/sec (skipping invalid configs).

## Input Parameters
- `CMX_BW_GB` (GB/s per GPU): default 4
- `HBM_DRAM_SIZE_GB` (GB): default 300
- `RECOMPUTE_REQ_SEC` (reqs/s): default 1
- `GPU_SOL_REQ_SECONDS` (reqs/s): default 20
- `AVG_AGENT_CAP_SIZE_IN_GB` (GB): default 0.8
- Histogram: 50%@0s, 50%@120s (default)
- τ threshold: 0 (default)
- fraction at exactly τ: 0.15 (default)

## Chart Annotations
**X axis points**: H (HBM), R (ratio bound, orange), L (HW bound, grey dash-dot), S (SOL point, blue)

**Y axis labels**: recompute, CMX_BW (green), SOL (blue) — at x=-0.04 (paper coords)

**Vertical lines**: at H, C, R (orange dash-dot), L (grey dash-dot), S (blue dot)

**Distances info box** (blue, below formula box):
- 0 ↔ H = HBM
- 0 ↔ S = SOL × AVG × total_Ttools_avg (SOL capacity bound)
- H ↔ R = HBM × ratio / (1−ratio) (CMX ratio capacity bound)
- H ↔ L = CMX_BW × CMX_Ttools_avg (CMX BW bound, Little's law)

**Formula box**: shows `gain_ratio = CE/BH` with appropriate formula per case.

## File Structure
```
/Users/rspiegelman/Desktop/cmx-gain/
  cmx_gain.html       — main tool (Plotly.js via CDN)
  CONTEXT.md          — this file
```

**GitHub**: `https://github.com/sroninio/CMX_model` (main branch)

## Related Files (Desktop, not in repo)
- `bw_slide.py` — slide 1 of CMX deck (bandwidth diagram)
- `pareto_convergence.py` — Pareto frontier convergence slide
- `cmx_cost_opt.py` — cost optimization 3-panel slide
- `cmx_sweep.py` — CMX sweep 6×2 grid

## What's Commented Out
- Messi photo (line ~54 in HTML)
- Efficiency View second chart (JS block + div, near end of file)

## Possible Next Steps (not started)
- Re-enable / improve the Efficiency View
- Add CDF visualization of the Ttools histogram
- Export to PowerPoint-friendly version (axis numbers already toggleable via branch)
- Connect to real simulation data from `res_for_draw_pareto.txt`
