"""Analyze benchmark_results.csv and generate tables and figures."""
import argparse, re
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

NEEDED = ["run_label","threads","operations_per_thread","phase","successful",
          "mismatches","errors","elapsed_seconds","throughput_ops_sec",
          "avg_latency_ms","p50_latency_ms","p95_latency_ms","p99_latency_ms"]

def norm(s):
    s = str(s).strip().lower().replace("**","")
    s = s.replace("&#x61;","a").replace("&#x31;","1")
    s = re.sub(r"[^a-z0-9_]", "", s)
    # accommodate headers whose underscores were stripped by formatting
    aliases = {"throughputopssec":"throughput_ops_sec",
               "avglatencyms":"avg_latency_ms"}
    return aliases.get(s,s)

def stores_from_label(label):
    m = re.search(r"(?:^|_)([123])_stores?(?:_|$)", str(label).lower())
    if not m:
        raise ValueError(f"Cannot infer store count from run_label: {label}")
    return int(m.group(1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="benchmark_results.csv")
    ap.add_argument("--output-dir", default="benchmark_analysis")
    args = ap.parse_args()
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.input)
    df.columns = [norm(c) for c in df.columns]
    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns {missing}; found {list(df.columns)}")
    numeric = [c for c in NEEDED if c not in ("run_label","phase")]
    for c in numeric: df[c] = pd.to_numeric(df[c], errors="coerce")
    df["phase"] = df["phase"].astype(str).str.upper()
    df["stores"] = df["run_label"].map(stores_from_label)
    df["expected"] = df["threads"] * df["operations_per_thread"]

    problems = []
    if len(df) != 90: problems.append(f"Expected 90 rows, found {len(df)}")
    if (df.successful != df.expected).any(): problems.append("Some rows have unexpected successful-operation counts")
    if df.errors.fillna(0).sum() != 0: problems.append("Errors are nonzero")
    if df.mismatches.fillna(0).sum() != 0: problems.append("Mismatches are nonzero")
    counts = df.groupby(["threads","stores","phase"]).size()
    if len(counts) != 18 or not (counts == 5).all():
        problems.append("Expected five trials for every thread/store/phase combination")

    keys = ["threads","stores","phase"]
    metrics = ["successful","elapsed_seconds","throughput_ops_sec","avg_latency_ms",
               "p50_latency_ms","p95_latency_ms","p99_latency_ms","errors","mismatches"]
    means = df.groupby(keys)[metrics].mean().reset_index()
    std = df.groupby(keys)[["throughput_ops_sec","avg_latency_ms","p95_latency_ms","p99_latency_ms"]].std().reset_index()
    std = std.rename(columns={c:c+"_std" for c in std.columns if c not in keys})
    summary = means.merge(std,on=keys).sort_values(keys)
    summary.to_csv(out/"summary_by_threads_and_stores.csv",index=False)
    summary.to_markdown(out/"summary_by_threads_and_stores.md",index=False,floatfmt=".2f")

    (out/"validation.txt").write_text(
        f"Rows: {len(df)}\\nSuccessful operations: {int(df.successful.sum())}\\n"
        f"Errors: {int(df.errors.sum())}\\nMismatches: {int(df.mismatches.sum())}\\n"
        f"Status: {'PASS' if not problems else 'CHECK REQUIRED'}\\n"+
        "".join("ISSUE: "+p+"\\n" for p in problems), encoding="utf-8")

    for phase in ["SET","GET"]:
        part = summary[summary.phase == phase]
        for metric, label, filename in [
            ("throughput_ops_sec","Throughput (ops/sec)",f"throughput_{phase.lower()}.png"),
            ("avg_latency_ms","Average latency (ms)",f"avg_latency_{phase.lower()}.png")]:
            fig, ax = plt.subplots(figsize=(8,5))
            for n in sorted(part.stores.unique()):
                d=part[part.stores==n].sort_values("threads")
                ax.plot(d.threads,d[metric],marker="o",linewidth=2,label=f"{n} store(s)")
            ax.set(title=f"{phase} {label}",xlabel="Concurrent client threads",ylabel=label)
            ax.set_xticks([3,10,20]); ax.grid(alpha=.3); ax.legend()
            fig.tight_layout(); fig.savefig(out/filename,dpi=180); plt.close(fig)

        fig, axes = plt.subplots(1,3,figsize=(14,4.5))
        for ax,t in zip(axes,[3,10,20]):
            d=part[part.threads==t].sort_values("stores")
            x=range(len(d)); w=.24
            for i,m in enumerate(["p50_latency_ms","p95_latency_ms","p99_latency_ms"]):
                ax.bar([v+(i-1)*w for v in x],d[m],w,label=m.split("_")[0])
            ax.set_title(f"{phase}: {t} threads")
            ax.set_xticks(list(x),[f"{int(v)} store(s)" for v in d.stores])
            ax.set_ylabel("Latency (ms)"); ax.grid(axis="y",alpha=.25)
        axes[-1].legend(title="Percentile")
        fig.tight_layout(); fig.savefig(out/f"latency_percentiles_{phase.lower()}.png",dpi=180); plt.close(fig)

    report = "# Generated benchmark summary\\n\\n"
    report += f"- Rows: {len(df)}\\n- Successful operations: {int(df.successful.sum()):,}\\n"
    report += f"- Errors: {int(df.errors.sum())}\\n- Mismatches: {int(df.mismatches.sum())}\\n"
    report += f"- Validation: {'PASS' if not problems else 'CHECK REQUIRED'}\\n\\n"
    report += "## Mean values across trials\\n\\n"
    report += summary[keys+["throughput_ops_sec","avg_latency_ms","p50_latency_ms","p95_latency_ms","p99_latency_ms"]].to_markdown(index=False,floatfmt=".2f")
    report += "\\n\\nThread count and total operations increase together (100 operations per thread), so this is an increasing-load experiment, not a fixed-workload comparison.\\n"
    (out/"generated_report.md").write_text(report,encoding="utf-8")
    print((out/"validation.txt").read_text())
    if problems: raise SystemExit(2)

if __name__=="__main__": main()