"""Quick SNN backtest for asset selection — runs on historical klines."""

import gc
import math

import numpy as np

from snn.encoding import encode_ohlcv, SENSORY, BUY_N, SELL_N, TOTAL_N
from snn.neuron import TradingNeuron
from snn.rstpd import RSTDPEngine


def quick_backtest(data, lr=0.01, tau=24.0, sl=0.05, tp=0.12, fee=0.002, use_micro=True, init_weights=None, leverage=1):
    if init_weights:
        neurons = [TradingNeuron(nucleus=np.array(w, dtype=np.float32)) for w in init_weights]
    else:
        neurons = [TradingNeuron() for _ in range(TOTAL_N)]
    rstdp = RSTDPEngine(lr=lr, tau=tau)
    split = int(len(data) * 0.8)
    vol_hist = []
    pnls = []
    for phase, start, end in [("train", 5, split), ("test", split, len(data))]:
        pos = 0
        entry_price = 0.0
        prev_pnl = 0.0
        has_prev = False
        trades = 0
        wins = 0
        pnl_sum = 0.0
        phase_pnls = []
        for c in range(start, end):
            o, h, l, cl, v = data[c]
            spikes = encode_ohlcv(o, h, l, cl, v, vol_hist)
            neg = -spikes
            for i in range(BUY_N):
                neurons[i].forward(spikes)
            for i in range(SELL_N):
                neurons[BUY_N + i].forward(neg)
            buy = max(n.output for n in neurons[:BUY_N]) if neurons else 0
            sell = max(n.output for n in neurons[BUY_N:]) if len(neurons) > BUY_N else 0
            th = neurons[0].threshold if neurons else 0.3
            action = 1 if buy > th and buy >= sell else (-1 if sell > th and sell > buy else 0)
            if pos == 0:
                if action:
                    pos = action
                    entry_price = cl
                    has_prev = False
                else:
                    for n in neurons:
                        rstdp.decay_trace(n.eligibility)
                    # Hebbian idle: reinforce firing patterns
                    for i, n in enumerate(neurons):
                        inp = spikes if i < BUY_N else neg
                        if n.output > 0:
                            n.nucleus[:SENSORY] += 0.001 * inp[:SENSORY] * n.output
            else:
                pnl_raw = (cl - entry_price) / entry_price
                curr = pnl_raw if pos == 1 else -pnl_raw
                curr_levered = curr * leverage
                for i, n in enumerate(neurons):
                    inp = spikes if i < BUY_N else neg
                    rstdp.accumulate(n.eligibility, inp, n.output)
                if use_micro and has_prev:
                    for n in neurons:
                        rstdp.micro_reward(n.nucleus, n.eligibility, prev_pnl, curr_levered)
                prev_pnl = curr_levered
                has_prev = True
                for n in neurons:
                    rstdp.decay_trace(n.eligibility)
                close = 0
                if sl > 0 and curr_levered <= -sl:
                    close = 1
                elif tp > 0 and curr_levered >= tp:
                    close = 1
                elif (pos == 1 and action == -1) or (pos == -1 and action == 1):
                    close = 1
                if close:
                    for n in neurons:
                        _, net = rstdp.commit(n.nucleus, n.eligibility, pnl_raw, pos)
                    rstdp.commit_stats(net)
                    pos = 0
                    has_prev = False
                    trades += 1
                    pnl_sum += curr_levered
                    phase_pnls.append(curr_levered)
                    if curr_levered > 0:
                        wins += 1
        if phase == "test":
            pnls = phase_pnls
            tr = trades
            tw = wins
            tp = pnl_sum
    avg_pnl = tp / max(tr, 1)
    std_pnl = np.std(pnls) if len(pnls) > 1 else abs(avg_pnl) + 0.001
    wr = tw / max(tr, 1)
    risk_score = wr * avg_pnl * math.sqrt(max(tr, 1)) / max(std_pnl, 0.001)
    trained_weights = [n.nucleus.copy() for n in neurons]
    gc.collect()
    return {
        "trades": tr,
        "wins": tw,
        "total_pnl": tp,
        "avg_pnl": avg_pnl,
        "std_pnl": std_pnl,
        "winrate": wr,
        "risk_score": risk_score,
        "weights": trained_weights,
    }