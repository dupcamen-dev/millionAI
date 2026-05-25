"""Hyperparameter sweep for crypto SNN backtest.

Random search over lr, tau, threshold, stop_loss, take_profit.
Runs backtest.exe for each config, parses output, reports top results.

Usage:
    python sweep.py [--n 30] [--parallel 4] [--seed 42]
"""
import subprocess, re, sys, os, random, json
from concurrent.futures import ProcessPoolExecutor, as_completed

BACKTEST = os.path.join(os.path.dirname(__file__), "backtest.exe")
DATA     = os.path.join(os.path.dirname(__file__), "../../data/btcusdt_5m.bin")
PROJ     = '-DARCHIVE_PROJ_FN(i,j,l)=((float)((int)((i)*13^(j)*7^(l)*5)%31-15)/15.0f)'

# Parameter ranges
PARAMS = {
    "lr":   [0.001, 0.003, 0.005, 0.01, 0.03, 0.05, 0.1],
    "tau":  [3, 6, 12, 24, 48],
    "thresh": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    "sl":   [0.03, 0.04, 0.05, 0.06, 0.07, 0.10],
    "tp":   [0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30],
}

# Regexes for parsing output
RE_METRICS = {
    "test_trades":  re.compile(r"Test trades:\s+(\d+)"),
    "winrate":      re.compile(r"Winrate:\s+([\d.]+)%"),
    "net_pnl":      re.compile(r"Net PnL:\s+([\d.\-]+)%"),
    "final_eq":     re.compile(r"Final equity:\s+[\d.]+ \(([\d.\-]+)%\)"),
    "sharpe":       re.compile(r"Sharpe \(ann\.\):\s+([\d.]+)"),
    "max_dd":       re.compile(r"Max Drawdown:\s+([\d.]+)%"),
    "buy_hold":     re.compile(r"Buy & Hold:\s+([\d.]+)%"),
}

def run_config(config):
    """Run one backtest config and return metrics."""
    cmd = [
        BACKTEST,
        DATA,
        str(config["lr"]), str(config["tau"]), str(config["thresh"]),
        "0.002",  # fee
        str(config["sl"]), str(config["tp"]),
        "1",  # quiet
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return None

    metrics = {"config": config}
    for key, regex in RE_METRICS.items():
        m = regex.search(output)
        if m:
            metrics[key] = float(m.group(1))
        else:
            metrics[key] = None

    # Parse training PnL too
    m = re.search(r"Training:.*?total PnL=([\d.\-]+)%", output)
    metrics["train_pnl"] = float(m.group(1)) if m else None

    return metrics

def main():
    n_configs = 30
    if len(sys.argv) > 1 and sys.argv[1].startswith("--n="):
        n_configs = int(sys.argv[1].split("=")[1])
    seed = 42
    random.seed(seed)

    # Generate random configs
    configs = []
    for _ in range(n_configs):
        configs.append({
            "lr":      random.choice(PARAMS["lr"]),
            "tau":     random.choice(PARAMS["tau"]),
            "thresh":  random.choice(PARAMS["thresh"]),
            "sl":      random.choice(PARAMS["sl"]),
            "tp":      random.choice(PARAMS["tp"]),
        })

    # Run in parallel
    print(f"Running {n_configs} configs...")
    results = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_config, c): c for c in configs}
        for i, f in enumerate(as_completed(futures), 1):
            r = f.result()
            if r and r.get("test_trades") and r["test_trades"] >= 3:
                results.append(r)
            sys.stdout.write(f"\r  {i}/{n_configs} complete")
            sys.stdout.flush()

    if not results:
        print("\nNo valid results (need >=3 test trades)")
        return

    # Sort by test PnL
    results.sort(key=lambda r: r.get("net_pnl") or -999, reverse=True)

    print(f"\n\nTop 10 configs by test PnL:\n")
    header = f"{'Rank':<6} {'lr':<8} {'tau':<6} {'thr':<6} {'sl':<6} {'tp':<6} {'train%':<8} {'test%':<8} {'win%':<6} {'trades':<6} {'DD%':<6} {'Sharpe':<8}"
    print(header)
    print("-" * len(header))
    for rank, r in enumerate(results[:10], 1):
        c = r["config"]
        print(
            f"{rank:<6} "
            f"{c['lr']:<8.4f} "
            f"{c['tau']:<6.1f} "
            f"{c['thresh']:<6.2f} "
            f"{c['sl']:<6.2f} "
            f"{c['tp']:<6.2f} "
            f"{r.get('train_pnl', 0):<8.2f} "
            f"{r['net_pnl']:<8.2f} "
            f"{r['winrate']:<6.1f} "
            f"{r['test_trades']:<6.0f} "
            f"{r['max_dd']:<6.2f} "
            f"{r['sharpe']:<8.1f}"
        )

    # Save all results
    with open("sweep_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nAll results saved to sweep_results.json")

    # Best config for multi-seed
    best = results[0]
    print(f"\n=== BEST CONFIG ===")
    print(json.dumps(best["config"], indent=2))
    print(f"Test PnL: {best['net_pnl']:.2f}%")
    print(f"Winrate: {best['winrate']:.1f}%")

if __name__ == "__main__":
    main()
