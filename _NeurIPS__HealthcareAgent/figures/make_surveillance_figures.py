from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "dataset" / "surveilance"
FIG_DIR = ROOT / "_NeurIPS__HealthcareAgent" / "figures"


plt.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def bit(value: str) -> bool:
    return str(value).strip() in {"1", "true", "True"}


def save_overlap_coverage() -> None:
    overlap_rows = read_csv(DATASET_DIR / "derived_core_overlap_distribution.csv")
    pattern_rows = read_csv(DATASET_DIR / "derived_core_overlap_top_patterns.csv")

    counts = [int(row["positive_core_family_count_24h"]) for row in overlap_rows]
    pct = [float(row["pct_stays"]) for row in overlap_rows]
    cum = np.cumsum(pct)

    families = [
        "Infect",
        "Sepsis",
        "AKI2/3",
        "Olig",
        "Resp",
        "Vaso",
        "GCS≤8",
        "Lac≥4",
        "pH≤7.2",
        "INR≥2",
    ]

    top_patterns = []
    for row in pattern_rows:
        if row["stays"] == "0":
            continue
        active = [int(row[col]) for col in row.keys() if col in {
            "infection",
            "sepsis",
            "aki_stage23",
            "oliguria",
            "respiratory_support",
            "vasoactive_support",
            "gcs_le_8",
            "lactate_ge_4",
            "ph_le_7_20",
            "inr_ge_2",
        }]
        if sum(active) == 0:
            continue
        top_patterns.append(
            {
                "matrix": active,
                "pct": float(row["pct_stays"]),
            }
        )
        if len(top_patterns) >= 8:
            break

    heat = np.array([row["matrix"] for row in top_patterns], dtype=float)

    fig = plt.figure(figsize=(12, 4.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.05, 1.2], wspace=0.35)

    ax1 = fig.add_subplot(gs[0, 0])
    bar_color = "#2F6DB2"
    line_color = "#C44E52"
    ax1.bar(counts, pct, color=bar_color, width=0.8)
    ax1.set_xlabel("Active surveillance families by 24h")
    ax1.set_ylabel("Percent of ICU stays")
    ax1.set_title("Coverage and overlap in the full 48h cohort")
    ax1.set_xticks(counts)
    ax1.set_ylim(0, max(pct) * 1.2)

    ax1b = ax1.twinx()
    ax1b.plot(counts, cum, color=line_color, marker="o", linewidth=2)
    ax1b.set_ylabel("Cumulative coverage (%)", color=line_color)
    ax1b.tick_params(axis="y", colors=line_color)
    ax1b.set_ylim(0, 105)
    ax1b.axhline(91.49, color=line_color, linestyle="--", linewidth=1, alpha=0.7)
    ax1b.text(
        6.2,
        93.5,
        "91.5% have ≥1 family",
        color=line_color,
        fontsize=9,
    )

    ax2 = fig.add_subplot(gs[0, 1])
    im = ax2.imshow(heat, cmap="Blues", aspect="auto", vmin=0, vmax=1)
    ax2.set_xticks(range(len(families)))
    ax2.set_xticklabels(families, rotation=35, ha="right")
    ax2.set_yticks(range(len(top_patterns)))
    ax2.set_yticklabels([f"{row['pct']:.1f}%" for row in top_patterns])
    ax2.set_xlabel("Core surveillance families")
    ax2.set_ylabel("Most common non-empty overlap patterns")
    ax2.set_title("Representative overlap patterns")
    for i in range(heat.shape[0]):
        for j in range(heat.shape[1]):
            ax2.text(
                j,
                i,
                "1" if heat[i, j] > 0 else "0",
                ha="center",
                va="center",
                color="white" if heat[i, j] > 0.5 else "#3A3A3A",
                fontsize=8,
            )

    fig.tight_layout()
    fig.savefig(FIG_DIR / "surveillance_overlap_coverage.pdf", bbox_inches="tight")
    plt.close(fig)


def save_pairwise_overlap_heatmap() -> None:
    path = DATASET_DIR / "checkpoint_truth_all.csv"
    families = [
        ("Infect", lambda r: bit(r["infection_family_active"])),
        ("Sepsis", lambda r: bit(r["sepsis_alert"])),
        ("AKI2/3", lambda r: bit(r["aki_stage2"]) or bit(r["aki_stage3"])),
        ("Olig", lambda r: bit(r["oliguria_6h"]) or bit(r["severe_oliguria_or_anuria"])),
        ("Resp", lambda r: bit(r["resp_support_hfnc_or_niv"]) or bit(r["resp_support_invasive_vent"])),
        ("Vaso", lambda r: bit(r["vasoactive_support_any"]) or bit(r["vasoactive_multi_agent_or_high_intensity"])),
        ("GCS≤8", lambda r: bit(r["gcs_severe_impairment_le_8"])),
        ("Lac≥4", lambda r: bit(r["severe_hyperlactatemia_ge_4"])),
        ("pH≤7.2", lambda r: bit(r["severe_acidemia_ph_le_7_20"])),
        ("INR≥2", lambda r: bit(r["coagulopathy_inr_ge_2"])),
    ]

    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            if row["t_hour"] != "24":
                continue
            rows.append([fn(row) for _, fn in families])

    data = np.array(rows, dtype=float)
    n = data.shape[0]
    overlap = (data.T @ data) / n * 100.0
    labels = [name for name, _ in families]

    # Also export the matrix as a CSV for reproducibility and doc references.
    out_csv = DATASET_DIR / "derived_core_pairwise_overlap_24h.csv"
    with out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["family"] + labels)
        for idx, label in enumerate(labels):
            writer.writerow([label] + [f"{val:.2f}" for val in overlap[idx]])

    fig, ax = plt.subplots(figsize=(8.5, 7.2))
    im = ax.imshow(overlap, cmap="Blues", vmin=0, vmax=float(overlap.max()))
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_title("Raw pairwise overlap by 24h in the full 48h cohort")

    for i in range(overlap.shape[0]):
        for j in range(overlap.shape[1]):
            value = overlap[i, j]
            ax.text(
                j,
                i,
                f"{value:.1f}",
                ha="center",
                va="center",
                fontsize=8,
                color="white" if value > overlap.max() * 0.45 else "#1F1F1F",
            )

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("% of ICU stays with both families active by 24h")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "surveillance_pairwise_overlap_raw.pdf", bbox_inches="tight")
    plt.close(fig)


def save_family_coverage_proof() -> None:
    path = DATASET_DIR / "checkpoint_truth_all.csv"
    families = [
        ("Infect", lambda r: bit(r["infection_family_active"])),
        ("Sepsis", lambda r: bit(r["sepsis_family_active"])),
        ("Renal", lambda r: bit(r["renal_family_active"])),
        ("Resp", lambda r: bit(r["respiratory_family_active"])),
        ("Hemodynamic", lambda r: bit(r["hemodynamic_family_active"])),
        ("Neuro", lambda r: bit(r["neurologic_family_active"])),
        ("Metabolic", lambda r: bit(r["metabolic_family_active"])),
        ("Coagulation", lambda r: bit(r["coagulation_family_active"])),
    ]

    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            if row["t_hour"] != "24":
                continue
            rows.append({name: fn(row) for name, fn in families})

    n = len(rows)
    prevalence = []
    for name, _ in families:
        pct = sum(r[name] for r in rows) / n * 100.0
        prevalence.append((name, pct))

    prevalence_sorted = sorted(prevalence, key=lambda x: x[1], reverse=True)

    # Greedy set-cover style cumulative coverage.
    remaining = list(range(n))
    selected: list[str] = []
    covered = np.zeros(n, dtype=bool)
    greedy_curve = []
    unused = {name for name, _ in families}
    while unused:
        best_name = None
        best_gain = -1
        for name in unused:
            gain = sum((not covered[i]) and rows[i][name] for i in range(n))
            if gain > best_gain:
                best_gain = gain
                best_name = name
        assert best_name is not None
        unused.remove(best_name)
        selected.append(best_name)
        for i in range(n):
            covered[i] = covered[i] or rows[i][best_name]
        greedy_curve.append((best_name, covered.mean() * 100.0))

    # Export summary CSVs for doc reuse.
    with (DATASET_DIR / "core_family_prevalence_24h.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["family", "pct_stays_24h"])
        for name, pct in prevalence_sorted:
            writer.writerow([name, f"{pct:.2f}"])

    with (DATASET_DIR / "core_family_greedy_union_24h.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["step", "family_added", "cumulative_pct_stays_covered"])
        for idx, (name, pct) in enumerate(greedy_curve, start=1):
            writer.writerow([idx, name, f"{pct:.2f}"])

    fig = plt.figure(figsize=(12, 4.8))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.15], wspace=0.3)

    ax1 = fig.add_subplot(gs[0, 0])
    labels = [name for name, _ in prevalence_sorted][::-1]
    vals = [pct for _, pct in prevalence_sorted][::-1]
    ax1.barh(labels, vals, color="#3B73B9")
    ax1.set_xlabel("% of ICU stays with family active by 24h")
    ax1.set_title("Per-family coverage")
    ax1.grid(axis="x", linestyle=":", alpha=0.35)
    for idx, val in enumerate(vals):
        ax1.text(val + 0.8, idx, f"{val:.1f}", va="center", fontsize=9)

    ax2 = fig.add_subplot(gs[0, 1])
    x = np.arange(1, len(greedy_curve) + 1)
    y = [pct for _, pct in greedy_curve]
    names = [name for name, _ in greedy_curve]
    ax2.plot(x, y, color="#C44E52", marker="o", linewidth=2.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=30, ha="right")
    ax2.set_ylabel("Cumulative % of stays covered by ≥1 selected family")
    ax2.set_xlabel("Greedy family-addition order")
    ax2.set_title("Most ICU stays are covered after adding a few families")
    ax2.set_ylim(0, 100)
    ax2.grid(axis="y", linestyle=":", alpha=0.35)
    ax2.axhline(y[-1], color="#C44E52", linestyle="--", linewidth=1, alpha=0.7)
    ax2.text(x[-1] - 1.6, y[-1] - 5.0, f"All 8 families: {y[-1]:.1f}%", color="#C44E52", fontsize=9)

    fig.tight_layout()
    fig.savefig(FIG_DIR / "surveillance_family_coverage.pdf", bbox_inches="tight")
    plt.close(fig)


def save_decision_prevalence() -> None:
    rows = read_csv(DATASET_DIR / "decision_catalog_feasibility.csv")
    rows = sorted(rows, key=lambda row: float(row["pct_by_24h"]), reverse=True)
    top = rows[:15]

    names = [row["decision_name"] for row in top][::-1]
    pct24 = [float(row["pct_by_24h"]) for row in top][::-1]
    pct48 = [float(row["pct_by_48h"]) for row in top][::-1]
    status = [row["definition_status"] for row in top][::-1]

    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(8.4, 6.1))

    color24 = "#7DB7E8"
    color48 = "#1D4E89"
    ax.barh(y, pct48, color=color48, alpha=0.9, height=0.72, label="Positive by 48h")
    ax.barh(y, pct24, color=color24, alpha=1.0, height=0.42, label="Positive by 24h")

    for idx, name in enumerate(names):
        if status[idx] == "small_extension":
            ax.text(
                pct48[idx] + 0.7,
                idx,
                "ext",
                va="center",
                ha="left",
                fontsize=8,
                color="#7A3E00",
            )

    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlabel("Percent of LOS ≥ 48h ICU stays")
    ax.set_title("Decision prevalence spans common and rare ICU states")
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="x", linestyle=":", alpha=0.35)
    ax.set_xlim(0, max(pct48) * 1.18)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "surveillance_decision_prevalence.pdf", bbox_inches="tight")
    plt.close(fig)


def save_subset_design() -> None:
    rows = read_csv(DATASET_DIR / "benchmark_2k_summary.csv")
    agg: dict[str, dict[str, float]] = defaultdict(
        lambda: {"stays": 0, "mean24": 0.0, "meanmax": 0.0, "alerts": 0, "rare": 0}
    )
    for row in rows:
        layer = row["sampling_layer"]
        stays = int(row["stays"])
        agg[layer]["stays"] += stays
        agg[layer]["mean24"] += stays * float(row["mean_core_family_count_24h"])
        agg[layer]["meanmax"] += stays * float(row["mean_max_active_family_count_any_checkpoint"])
        agg[layer]["alerts"] += int(row["stays_with_any_alert_by48h"])
        agg[layer]["rare"] += int(row["stays_with_any_rare_alert"])

    order = ["core_diversity", "alert_enrichment", "low_signal"]
    labels = ["Core diversity", "Alert enrichment", "Low signal"]
    stays = [agg[key]["stays"] for key in order]
    mean24 = [agg[key]["mean24"] / agg[key]["stays"] for key in order]
    rare_rate = [100 * agg[key]["rare"] / agg[key]["stays"] for key in order]

    x = np.arange(len(order))
    fig, ax1 = plt.subplots(figsize=(7.4, 4.8))
    bars = ax1.bar(x, stays, color=["#8FBBD9", "#E07A5F", "#B8C480"], width=0.58)
    ax1.set_ylabel("Stays in public benchmark")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_title("Soft-balanced 2k benchmark mixes dense and low-signal trajectories")
    for rect, n in zip(bars, stays):
        ax1.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 25, str(n), ha="center", va="bottom", fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(x, mean24, color="#1D4E89", marker="o", linewidth=2, label="Mean active families by 24h")
    ax2.plot(x, rare_rate, color="#A23B72", marker="s", linewidth=2, label="Rare-alert rate (%)")
    ax2.set_ylabel("Complexity / rare-alert rate")

    lines, labels2 = [], []
    for ax in (ax1, ax2):
        lns, lbs = ax.get_legend_handles_labels()
        lines.extend(lns)
        labels2.extend(lbs)
    if lines:
        ax1.legend(lines, labels2, frameon=False, loc="upper right")

    fig.tight_layout()
    fig.savefig(FIG_DIR / "surveillance_subset_design.pdf", bbox_inches="tight")
    plt.close(fig)


def save_state_semantics() -> None:
    checkpoints = np.arange(0, 49, 4)

    persistent = np.array([0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    cumulative = np.array([0, 0, 1, 1, 2, 2, 3, 3, 3, 3, 3, 3, 3])
    interval = np.array([0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0])
    ttl = np.array([0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0])
    composite = persistent * (interval > 0).astype(int) * (ttl > 0).astype(int)

    fig, axes = plt.subplots(5, 1, figsize=(9.0, 6.8), sharex=True)
    panels = [
        (
            "Persistent episode",
            "Sepsis alert: once visible, remains active through the benchmark window",
            persistent,
            ["off", "on"],
            "#3C8DAD",
        ),
        (
            "Cumulative max stage",
            "AKI: expose the worst KDIGO stage reached so far",
            cumulative,
            ["0", "1", "2", "3"],
            "#E07A5F",
        ),
        (
            "Active interval",
            "Ventilation / vasoactives: active only while support overlaps the checkpoint",
            interval,
            ["off", "on"],
            "#6A994E",
        ),
        (
            "Recent measurement + TTL",
            "Lactate / pH / GCS / PF ratio: abnormality expires if no new evidence arrives",
            ttl,
            ["off", "on"],
            "#A23B72",
        ),
        (
            "Composite current state",
            "Septic shock: recomputed each checkpoint from sepsis + support + metabolic evidence",
            composite,
            ["off", "on"],
            "#7B6D8D",
        ),
    ]

    for ax, (title, subtitle, values, labels, color) in zip(axes, panels):
        if values.max() <= 1:
            ax.step(checkpoints, values, where="post", color=color, linewidth=3)
            ax.fill_between(checkpoints, values, step="post", alpha=0.15, color=color)
            ax.set_ylim(-0.15, 1.25)
            ax.set_yticks([0, 1])
            ax.set_yticklabels(labels)
        else:
            ax.step(checkpoints, values, where="post", color=color, linewidth=3)
            ax.scatter(checkpoints, values, color=color, s=18, zorder=3)
            ax.set_ylim(-0.2, 3.35)
            ax.set_yticks([0, 1, 2, 3])
            ax.set_yticklabels(labels)
        ax.set_ylabel(title, rotation=0, labelpad=56, va="center")
        ax.text(0.01, 0.93, subtitle, transform=ax.transAxes, ha="left", va="top", fontsize=9)
        ax.grid(axis="x", linestyle=":", alpha=0.3)
        ax.spines["left"].set_alpha(0.4)
        ax.spines["bottom"].set_alpha(0.4)

    axes[-1].set_xlabel("Hours since ICU admission")
    axes[-1].set_xticks(checkpoints)
    fig.suptitle("Checkpoint labels use different temporal semantics across disease families", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(FIG_DIR / "surveillance_state_semantics.pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    save_overlap_coverage()
    save_pairwise_overlap_heatmap()
    save_family_coverage_proof()
    save_decision_prevalence()
    save_subset_design()
    save_state_semantics()
