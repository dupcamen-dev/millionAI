"""Multi-seed evaluation of best config from sweep.

Runs backtest with 10+ different seeds, reports mean/std.
"""
import subprocess, re, os, sys, json
import numpy as np

BACKTEST = os.path.join(os.path.dirname(__file__), "backtest.exe")
DATA     = os.path.join(os.path.dirname(__file__), "../../data/btcusdt_5m.bin")

# Best working config from sweep (thresh=0.3 for reliable firing)
BEST = dict(lr=0.01, tau=24, thresh=0.3, sl=0.05, tp=0.12, fee=0.002)

RE_METRICS = {
    "test_trades": re.compile(r"Test trades:\s+(\d+)"),
    "winrate":     re.compile(r"Winrate:\s+([\d.]+)%"),
    "test_pnl":    re.compile(r"Net PnL:\s+([\d.\-]+)%"),
    "final_eq":    re.compile(r"Final equity:\s+[\d.]+ \(([\d.\-]+)%\)"),
    "max_dd":      re.compile(r"Max Drawdown:\s+([\d.]+)%"),
    "buy_hold":    re.compile(r"Buy & Hold:\s+([\d.]+)%"),
    "train_pnl":   re.compile(r"Training:.*?total PnL=([\d.\-]+)%"),
    "train_trades": re.compile(r"Training:.*?(\d+) trades"),
    "train_wr":    re.compile(r"Training:.*?winrate=([\d.]+)%"),
}

def run_seed(seed):
    cmd = [
        BACKTEST, DATA,
        str(BEST["lr"]), str(BEST["tau"]), str(BEST["thresh"]),
        str(BEST["fee"]),
        str(BEST["sl"]), str(BEST["tp"]),
        "1", str(seed),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    output = result.stdout + result.stderr

    metrics = {}
    for key, regex in RE_METRICS.items():
        m = regex.search(output)
        metrics[key] = float(m.group(1)) if m else None
    return metrics

def main():
    n_seeds = 10
    if len(sys.argv) > 1:
        n_seeds = int(sys.argv[1])

    print(f"Multi-seed evaluation: {n_seeds} seeds")
    print(f"Config: {json.dumps(BEST)}\n")

    results = []
    for s in range(1, n_seeds + 1):
        r = run_seed(s)
        results.append(r)
        line = f"  Seed {s:2d}: train={r['train_pnl']:+.2f}% ({r['train_trades']:.0f} tr, {r['train_wr']:.1f}%) -> test={r['test_pnl']:+.2f}% ({r['test_trades']:.0f} tr, {r['winrate']:.1f}%) DD={r['max_dd']:.2f}%"
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    # Statistics
    test_pnls = [r["test_pnl"] for r in results if r["test_pnl"] is not None]
    train_pnls = [r["train_pnl"] for r in results if r["train_pnl"] is not None]
    winrates = [r["winrate"] for r in results if r["winrate"] is not None]
    trades = [r["test_trades"] for r in results if r["test_trades"] is not None]
    dds = [r["max_dd"] for r in results if r["max_dd"] is not None]
    bhs = [r["buy_hold"] for r in results if r["buy_hold"] is not None]

    print(f"\n=== RESULTS (n={len(test_pnls)} seeds) ===")
    print(f"{'Metric':<20} {'Mean':>10} {'Std':>10} {'Min':>10} {'Max':>10}")
    print("-" * 60)

    def summary(vals):
        return f"{np.mean(vals):>10.2f} {np.std(vals):>10.2f} {np.min(vals):>10.2f} {np.max(vals):>10.2f}"

    print(f"{'Train PnL %':<20} {summary(train_pnls)}")
    print(f"{'Test PnL %':<20} {summary(test_pnls)}")
    print(f"{'Winrate %':<20} {summary(winrates)}")
    print(f"{'Trades':<20} {summary(trades)}")
    print(f"{'Max DD %':<20} {summary(dds)}")
    print(f"{'Buy&Hold %':<20} {summary(bhs)}")

    # Count how many beat B&H
    beats = sum(1 for r in results if r["test_pnl"] is not None and r["buy_hold"] is not None and r["test_pnl"] > r["buy_hold"])
    print(f"\nBeat Buy & Hold: {beats}/{len(results)}")
    print(f"Positive test PnL: {sum(1 for r in results if r.get('test_pnl', -999) > 0)}/{len(results)}")

    # Save
    with open("multiseed_results.json", "w") as f:
        json.dump({"config": BEST, "results": results}, f, indent=2)
    print(f"\nSaved to multiseed_results.json")

if __name__ == "__main__":
    main()
