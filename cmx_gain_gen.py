#!/usr/bin/env python3
"""
CMX gain slide generator.

Model (request-space):
  X = concurrency (requests), displayed on axis as capacity GB = requests * AVG_SIZE
  Y = throughput (reqs/sec)
  Rising line slope = 1/T_BETWEEN_STEPS  (45° in request-space)

  A : (RECOMPUTE*T,  RECOMPUTE)     — all three lines turn up here
  B : (HBM/AVG_SIZE, HBM/(AVG_SIZE*T)) — "without CMX" drops to RECOMPUTE here
  C : (B_x + CMX_BW/AVG_SIZE*T,  B_y + CMX_BW/AVG_SIZE) — "with CMX" drops to CMX_BW/AVG_SIZE here
  D : (SOL*T,        SOL)           — "infinite HBM" merges into SOL here

Parameters:
  T_BETWEEN_STEPS_SEC  : time between steps (s)
  CMX_BW_GB            : CMX bandwidth (GB/s per GPU)
  HBM_DRAM_SIZE_GB     : HBM DRAM size (GB)
  RECOMPUTE_REQ_SEC    : recompute throughput (reqs/sec)
  SOL_REQ_SECOND       : speed-of-light throughput (reqs/sec)
  AVG_AGENT_CAP_SIZE_IN_GB   : average request KV-cache size (GB/req)

Derived:
  CMX_T_GB    = CMX_BW_GB * T_BETWEEN_STEPS_SEC   (Little's Law CMX capacity, GB)
  CMX_REQ_SEC = CMX_BW_GB / AVG_AGENT_CAP_SIZE_IN_GB    (CMX-bound throughput, reqs/sec)
  gain_ratio  = CMX_T_GB  / HBM_DRAM_SIZE_GB      (= CE/BG when y_C < SOL)

Usage:
  python3 cmx_gain_gen.py T_BETWEEN_STEPS_SEC CMX_BW_GB HBM_DRAM_SIZE_GB \\
                          RECOMPUTE_REQ_SEC SOL_REQ_SECOND AVG_AGENT_CAP_SIZE_IN_GB \\
                          [--output path.png]

Example:
  python3 cmx_gain_gen.py 60 4 300 1 12.5 0.8
  # HBM=300 → y_B=6.25, y_C=11.25 < SOL=12.5 → gain = 240/300 = 80%
"""

import argparse
import os
import sys
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch


def generate(T_BETWEEN_STEPS_SEC, CMX_BW_GB, HBM_DRAM_SIZE_GB,
             RECOMPUTE_REQ_SEC, SOL_REQ_SECOND, AVG_AGENT_CAP_SIZE_IN_GB,
             output=None):

    T   = T_BETWEEN_STEPS_SEC
    AVG = AVG_AGENT_CAP_SIZE_IN_GB

    # ── Derived quantities ──────────────────────────────────────────────
    CMX_T_GB    = CMX_BW_GB * T                    # GB  (Little's Law)
    CMX_REQ_SEC = CMX_BW_GB / AVG                  # reqs/sec when CMX-bound
    gain_ratio  = CMX_T_GB  / HBM_DRAM_SIZE_GB     # = CE/BG when y_C < SOL

    # Slope of rising line: 1/T in request-space = 1/(AVG*T) in GB-space
    slope = 1.0 / (AVG * T)                        # (reqs/sec) per GB

    # Key x positions in GB (= concurrency_requests * AVG)
    x_A_GB = RECOMPUTE_REQ_SEC / slope             # = RECOMPUTE * AVG * T
    x_B_GB = HBM_DRAM_SIZE_GB                      # HBM spill point
    x_C_GB = HBM_DRAM_SIZE_GB + CMX_T_GB           # CMX capacity exhausted
    x_D_GB = SOL_REQ_SECOND   / slope              # = SOL * AVG * T  (blue hits SOL)

    # Key y positions
    y_A = RECOMPUTE_REQ_SEC
    y_B = x_B_GB * slope                           # = HBM / (AVG * T)
    y_C = x_C_GB * slope                           # = y_B + CMX_REQ_SEC  (may exceed SOL)
    y_D = SOL_REQ_SECOND

    # ── Print results ───────────────────────────────────────────────────
    print()
    print('=== CMX Performance Gain ===')
    print(f'  T_BETWEEN_STEPS_SEC  : {T} s')
    print(f'  CMX_BW_GB            : {CMX_BW_GB} GB/s per GPU')
    print(f'  HBM_DRAM_SIZE_GB     : {HBM_DRAM_SIZE_GB} GB')
    print(f'  AVG_AGENT_CAP_SIZE_IN_GB   : {AVG} GB/req')
    print(f'  RECOMPUTE_REQ_SEC    : {RECOMPUTE_REQ_SEC} reqs/sec')
    print(f'  SOL_REQ_SECOND       : {SOL_REQ_SECOND} reqs/sec')
    print()
    print(f'  CMX_T_GB  (Little)   : {CMX_T_GB:.1f} GB')
    print(f'  CMX_REQ_SEC          : {CMX_REQ_SEC:.2f} reqs/sec')
    print(f'  y_B (spill point)    : {y_B:.2f} reqs/sec')
    print(f'  y_C (CMX peak)       : {y_C:.2f} reqs/sec')
    print(f'  gain_ratio (CE/BG)   : {gain_ratio*100:.1f}%')
    print()

    # ── Validation ──────────────────────────────────────────────────────
    warnings = []
    if not (RECOMPUTE_REQ_SEC < CMX_REQ_SEC < SOL_REQ_SECOND):
        warnings.append(
            f'  Recompute throughput ({RECOMPUTE_REQ_SEC} reqs/sec) should be smaller than '
            f'CMX throughput ({CMX_REQ_SEC:.2f} reqs/sec) that should be smaller than '
            f'SOL ({SOL_REQ_SECOND} reqs/sec)')
    if not (y_B > RECOMPUTE_REQ_SEC):
        cmx_vs_recompute = CMX_REQ_SEC / RECOMPUTE_REQ_SEC
        warnings.append(
            f'  Spill point B ({y_B:.2f} reqs/sec) is below RECOMPUTE ({RECOMPUTE_REQ_SEC} reqs/sec) — '
            f'it\'s better to recompute than to use HBM-DRAM; '
            f'gain = CMX_BW(reqs/sec) / RECOMPUTE = {CMX_REQ_SEC:.2f} / {RECOMPUTE_REQ_SEC} = {cmx_vs_recompute:.2f}x')
    if not (y_B < SOL_REQ_SECOND):
        warnings.append(
            f'  Spill point B ({y_B:.2f} reqs/sec) >= SOL ({SOL_REQ_SECOND} reqs/sec) — '
            f"HBM-DRAM is sufficient, don't need CMX")
    if warnings:
        print('\033[1;31m\n  ██ DEGENERATE CASE ██\033[0m')
        for w in warnings:
            print(f'\033[31m{w}\033[0m')
        print()
        sys.exit(1)

    # ── Chart parameters ────────────────────────────────────────────────
    # If CMX capacity extends past D (SOL point), C merges into D — no benefit beyond SOL
    x_C_eff   = min(x_C_GB, x_D_GB)
    y_C_actual = min(y_C, SOL_REQ_SECOND)   # = SOL when C is capped at D
    sol_limited = (x_C_GB > x_D_GB)         # True when C was moved left to D

    X_MAX  = HBM_DRAM_SIZE_GB + CMX_T_GB * 4.5
    DROP   = CMX_T_GB * 1.2
    y_max  = SOL_REQ_SECOND * 1.12
    dy     = y_B * 0.016   # small offset so coincident lines are both visible

    # ── Plot setup ───────────────────────────────────────────────────────
    plt.rcParams['mathtext.fontset'] = 'cm'
    plt.rcParams['font.family'] = 'serif'
    fig, ax = plt.subplots(figsize=(12, 7), facecolor='white')
    fig.subplots_adjust(left=0.10, right=0.92, top=0.88, bottom=0.17)

    BLUE  = '#4A90D9'
    GREEN = '#76b900'
    gray  = '#777'

    ax.set_xlim(0, X_MAX)
    ax.set_ylim(0, y_max)
    ax.set_xlabel('Occupied KV Cache Capacity', fontsize=11)
    ax.set_ylabel('Throughput  (reqs/sec)', fontsize=11)
    ax.set_title('CMX Gain Analysis', fontsize=14, fontweight='bold', pad=14)
    ax.grid(True, alpha=0.2)

    # ── Dotted gray 45° line from (0,0) to point A ───────────────────────
    ax.plot([0, x_A_GB], [0, y_A], color='#888', lw=2.0, linestyle='--', zorder=4)

    # ── Segment 0→A: all three flat at RECOMPUTE (offset bands) ─────────
    ax.plot([0, x_A_GB], [y_A+dy, y_A+dy], color=BLUE,    lw=2.5)
    ax.plot([0, x_A_GB], [y_A,    y_A],    color=GREEN,   lw=2.5)
    ax.plot([0, x_A_GB], [y_A-dy, y_A-dy], color='black', lw=2.5)

    # ── Segment A→B: all three rise together (offset bands) ─────────────
    C_rise = np.linspace(x_A_GB, x_B_GB, 200)
    y_rise = y_A + slope * (C_rise - x_A_GB)
    ax.plot(C_rise, y_rise+dy, color=BLUE,    lw=2.5)
    ax.plot(C_rise, y_rise,    color=GREEN,   lw=2.5)
    ax.plot(C_rise, y_rise-dy, color='black', lw=2.5)

    # ── Segment B→C_eff: blue and green rise together, capped at SOL ────────
    # (x_C_eff = min(x_C_GB, x_D_GB): if CMX capacity extends past D, C merges into D)
    C_bc  = np.linspace(x_B_GB, x_C_eff, 200)
    y_bc  = np.minimum(y_B + slope * (C_bc - x_B_GB), SOL_REQ_SECOND)
    ax.plot(C_bc, y_bc+dy, color=BLUE,  lw=2.5, label='infinite HBM')
    ax.plot(C_bc, y_bc,    color=GREEN, lw=2.5, label='with CMX')

    # ── After B: black drops to RECOMPUTE ───────────────────────────────
    ax.plot([x_B_GB, x_B_GB+DROP],  [y_B, y_A],   color='black', lw=2.5)
    ax.plot([x_B_GB+DROP, X_MAX],   [y_A, y_A],   color='black', lw=2.5, label='without CMX')

    # ── Green: if sol_limited, stay flat at SOL from x_C_eff to original x_C_GB ──
    if sol_limited:
        ax.plot([x_C_eff, x_C_GB], [SOL_REQ_SECOND, SOL_REQ_SECOND], color=GREEN, lw=2.5)
    # ── Green drops at original x_C_GB ───────────────────────────────────
    ax.plot([x_C_GB, x_C_GB+DROP], [y_C_actual, CMX_REQ_SEC], color=GREEN, lw=2.5)
    ax.plot([x_C_GB+DROP, X_MAX],  [CMX_REQ_SEC, CMX_REQ_SEC], color=GREEN, lw=2.5)

    # ── After C_eff: blue continues to SOL (if not already there) ────────
    if x_D_GB > x_C_eff:
        C_solo = np.linspace(x_C_eff, min(x_D_GB, X_MAX), 200)
        ax.plot(C_solo, y_B + slope*(C_solo - x_B_GB), color=BLUE, lw=2.5)
    x_flat_start = max(x_C_eff, x_D_GB)
    if x_flat_start < X_MAX:
        ax.plot([x_flat_start, X_MAX], [SOL_REQ_SECOND, SOL_REQ_SECOND], color=BLUE, lw=2.5)

    # ── Reference lines ──────────────────────────────────────────────────
    ax.axhline(y=y_A,           color='black', lw=1.5, linestyle=':', alpha=0.7)
    ax.text(X_MAX*0.99, y_A + y_max*0.012, 'recompute', ha='right', fontsize=10, color='black')
    ax.axhline(y=CMX_REQ_SEC,   color=GREEN,  lw=1.5, linestyle=':', alpha=0.7)
    ax.text(X_MAX*0.99, CMX_REQ_SEC + y_max*0.012, r'$CMX_{BW}$', ha='right', fontsize=10, color=GREEN)
    ax.axhline(y=SOL_REQ_SECOND, color=BLUE,  lw=1.8, linestyle=':', alpha=0.85)
    ax.text(X_MAX*0.99, SOL_REQ_SECOND + y_max*0.012, 'SOL', ha='right', fontsize=10, color=BLUE, fontweight='bold')

    # ── Vertical spill markers ────────────────────────────────────────────
    ax.axvline(x=x_B_GB,  color='#888', lw=1.5, linestyle=':')
    ax.axvline(x=x_C_GB,  color='#aaa', lw=1.5, linestyle=':')

    # ── Custom x-ticks: capacity (GB) + concurrency (req), evenly spaced + key points ──
    magnitude = 10 ** np.floor(np.log10(X_MAX / 6))
    raw_step  = X_MAX / 6
    step      = round(raw_step / magnitude) * magnitude
    regular   = np.arange(0, X_MAX + step * 0.5, step)

    # Key points that must appear
    key_xs = [x_A_GB, x_B_GB, x_C_GB]
    if x_D_GB <= X_MAX * 0.97:
        key_xs.append(x_D_GB)

    # Merge, sort, drop duplicates and ticks too close to a neighbour (< 4% of step)
    merged = sorted(set([round(t, 6) for t in list(regular) + key_xs]))
    ticks  = [merged[0]]
    for t in merged[1:]:
        if t - ticks[-1] > step * 0.04:
            ticks.append(t)

    ax.set_xticks(ticks)
    ax.set_xticklabels(
        [f'{x:.0f} GB\n{x/AVG:.0f} agents' for x in ticks],
        fontsize=8, ha='center'
    )

    # ── Key-point dots ────────────────────────────────────────────────────
    ax.plot(x_A_GB,  y_A,        'o', color=gray,    ms=7, zorder=6)
    ax.plot(x_B_GB,  y_B,        'o', color='black', ms=8, zorder=5)
    # C dot for gain: at x_C_eff (= D when sol_limited)
    ax.plot(x_C_eff, y_C_actual, 'o', color=BLUE,    ms=8, zorder=5)
    ax.plot(x_C_eff, y_B,        'o', color=gray,    ms=7, zorder=6)
    ax.plot(x_B_GB,  0,          'o', color=gray,    ms=7, zorder=7, clip_on=False)
    ax.plot(x_B_GB,  0,          'v', color='#555',  ms=8, zorder=6, clip_on=False)
    ax.plot(x_C_GB,  0,          'v', color='#555',  ms=8, zorder=6, clip_on=False)
    # D dot only when it is separate from C
    if x_D_GB <= X_MAX and not sol_limited:
        ax.plot(x_D_GB, SOL_REQ_SECOND, 'o', color=BLUE, ms=8, zorder=5)

    # ── Point labels ──────────────────────────────────────────────────────
    lx = X_MAX * 0.022
    ly = y_max * 0.025
    ax.text(x_A_GB  - lx*1.0, y_A          + ly, 'A',              fontsize=12, fontweight='bold', color=gray, zorder=7)
    ax.text(x_B_GB  - lx*1.4, y_B          + ly, 'B',              fontsize=12, fontweight='bold', color=gray, zorder=7)
    # C label at x_C_eff; "C,D" when merged
    c_label = 'C,D' if sol_limited else 'C'
    ax.text(x_C_eff + lx*0.5, y_C_actual   + ly, c_label,          fontsize=12, fontweight='bold', color=gray, zorder=7)
    if x_D_GB <= X_MAX and not sol_limited:
        ax.text(x_D_GB - lx*2.0, SOL_REQ_SECOND + ly, 'D',         fontsize=12, fontweight='bold', color=gray, zorder=7)
    ax.text(x_C_eff + lx*0.5, y_B          + ly, 'E',              fontsize=12, fontweight='bold', color=gray, zorder=7)
    ax.text(x_B_GB  - lx*1.4, y_max*0.022,       'G',              fontsize=12, fontweight='bold', color=gray, zorder=7)

    # ── CMX_BW·T span label inside the graph ─────────────────────────────
    span_y = y_max * 0.06
    ax.annotate('', xy=(x_C_GB, span_y), xytext=(x_B_GB, span_y),
                arrowprops=dict(arrowstyle='<->', color='#555', lw=1.5))
    ax.text((x_B_GB + x_C_GB)/2, span_y + y_max*0.03,
            r"$CMX_{BW} \cdot T_{between\_steps}$  (Little's Law)",
            fontsize=9, color='#555', ha='center', va='bottom', zorder=5)

    # ── Arrows ────────────────────────────────────────────────────────────
    ax.annotate('', xy=(x_B_GB, 0), xytext=(0, 0),
                arrowprops=dict(arrowstyle='<->', color='black', lw=2.5))
    ax.annotate('', xy=(x_B_GB, y_B), xytext=(x_B_GB, 0),
                arrowprops=dict(arrowstyle='<->', color='#c0392b', lw=2.0))
    # B→E horizontal line (always drawn)
    ax.annotate('', xy=(x_C_eff, y_B), xytext=(x_B_GB, y_B),
                arrowprops=dict(arrowstyle='<->', color='#333', lw=2.0))
    # CE vertical arrow at x_C_eff (= D when sol_limited, = C when not)
    ax.annotate('', xy=(x_C_eff, y_C_actual), xytext=(x_C_eff, y_B),
                arrowprops=dict(arrowstyle='<->', color='#c0392b', lw=2.5))

    # Actual gain as drawn: CE/BG using effective C
    gain_actual = (y_C_actual - y_B) / y_B

    if not sol_limited:
        x0   = X_MAX * 0.02
        ym_b = y_max * 0.72
        bw   = X_MAX * 0.302
        foff = y_max * 0.033
        fcx  = x0 + bw * 0.76
        bh   = y_max * 0.22
        ax.add_patch(FancyBboxPatch((x0 - X_MAX*0.005, ym_b - bh/2), bw, bh,
                     boxstyle='round,pad=0.1', facecolor='#fff0f0',
                     edgecolor='#c0392b', lw=1.5, zorder=3))
        ax.text(x0, ym_b + foff*0.6, r'$\mathrm{gain\_ratio} = CE/BG =$',
                fontsize=9, color='#c0392b', va='center', ha='left', zorder=5)
        ax.text(fcx, ym_b + foff*0.6 + foff, r'$CMX_{BW} \cdot T_{between\_steps}$',
                fontsize=8, color='black', va='center', ha='center', zorder=5)
        ax.plot([x0 + bw*0.53, x0 + bw*0.99], [ym_b + foff*0.6, ym_b + foff*0.6],
                '-', color='#555', lw=1.2, zorder=6)
        ax.text(fcx, ym_b + foff*0.6 - foff, r'$HBM\_DRAM\_SIZE$',
                fontsize=8, color='black', va='center', ha='center', zorder=5)
        ax.plot([x0 - X_MAX*0.003, x0 + bw*0.97], [ym_b - foff*0.8, ym_b - foff*0.8],
                '-', color='#c0392b', lw=0.8, alpha=0.5, zorder=4)
        ax.text(x0 + bw*0.5, ym_b - foff*2.1,
                f'$\\rightarrow$ {gain_ratio*100:.1f}\\%',
                fontsize=11, fontweight='bold', color='#c0392b', va='center', ha='center', zorder=5)
    else:
        # sol_limited: C merged into D — show gain result only
        x0   = X_MAX * 0.02
        ym_b = y_max * 0.72
        bw   = X_MAX * 0.302
        bh   = y_max * 0.13
        ax.add_patch(FancyBboxPatch((x0 - X_MAX*0.005, ym_b - bh/2), bw, bh,
                     boxstyle='round,pad=0.1', facecolor='#fff0f0',
                     edgecolor='#c0392b', lw=1.5, zorder=3))
        ax.text(x0 + bw*0.5, ym_b,
                f'$\\mathrm{{gain\_ratio}} = CE/BG \\rightarrow {gain_actual*100:.1f}\\%$',
                fontsize=11, fontweight='bold', color='#c0392b',
                va='center', ha='center', zorder=5)

    ax.legend(loc='upper left', fontsize=10, frameon=True)

    if output is None:
        output = os.path.expanduser(
            f'~/Desktop/cmx_gain_T{int(T)}_BW{CMX_BW_GB}_HBM{int(HBM_DRAM_SIZE_GB)}.png')
    plt.savefig(output, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'Saved to {output}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Generate CMX gain slide')
    p.add_argument('--T_BETWEEN_STEPS_SEC',  type=float, required=True, help='Time between steps (s)')
    p.add_argument('--CMX_BW_GB',            type=float, required=True, help='CMX bandwidth (GB/s per GPU)')
    p.add_argument('--HBM_DRAM_SIZE_GB',     type=float, required=True, help='HBM DRAM size (GB)')
    p.add_argument('--RECOMPUTE_REQ_SEC',    type=float, required=True, help='Recompute throughput (reqs/sec)')
    p.add_argument('--SOL_REQ_SECOND',       type=float, required=True, help='Speed-of-light throughput (reqs/sec)')
    p.add_argument('--AVG_AGENT_CAP_SIZE_IN_GB',   type=float, required=True, help='Average request KV-cache size (GB/req)')
    p.add_argument('--output', '-o',         type=str,   default=None,  help='Output PNG path')
    a = p.parse_args()
    generate(a.T_BETWEEN_STEPS_SEC, a.CMX_BW_GB, a.HBM_DRAM_SIZE_GB,
             a.RECOMPUTE_REQ_SEC, a.SOL_REQ_SECOND, a.AVG_AGENT_CAP_SIZE_IN_GB,
             a.output)
