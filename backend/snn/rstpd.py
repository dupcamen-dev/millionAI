import math
import numpy as np

class RSTDPEngine:
    def __init__(self, lr=0.01, tau=24.0):
        self.lr = lr
        self.lr_0 = lr
        self.decay = math.exp(-1.0 / tau)
        self.reward_k = 10.0
        self.fee_pct = 0.002
        self.micro_lr_scale = 0.1
        self.total_pnl = 0.0
        self.trades = 0
        self.wins = 0
        self.trades_total = 0

    def accumulate(self, eligibility, input_vec, output):
        n = min(len(eligibility), len(input_vec))
        for i in range(n):
            dt = output - 0.5
            eligibility[i] += input_vec[i] * dt * math.exp(-abs(dt))

    def decay_trace(self, eligibility):
        eligibility *= self.decay

    def micro_reward(self, nucleus, eligibility, prev_pnl, curr_pnl):
        change = curr_pnl - prev_pnl
        reward = math.tanh(self.reward_k * 0.3 * change)
        nucleus[:len(eligibility)] += self.lr * self.micro_lr_scale * eligibility * reward
        return reward

    def commit(self, nucleus, eligibility, pnl_pct, side):
        net = pnl_pct * side - self.fee_pct
        reward = math.tanh(self.reward_k * net)
        nucleus[:len(eligibility)] += self.lr * eligibility * reward
        eligibility.fill(0)
        return reward, net

    def commit_stats(self, net_pnl):
        self.total_pnl += net_pnl
        self.trades += 1
        self.trades_total += 1
        if net_pnl > 0:
            self.wins += 1
        self.lr = self.lr_0 / (1.0 + 0.01 * self.trades_total)

    def set_tau(self, tau_candles):
        self.decay = math.exp(-1.0 / tau_candles)

    def adaptive_tau(self, atr, atr_median):
        if atr_median > 1e-8:
            vol = atr / atr_median
            tau = 24.0 * (1.0 + vol)
            self.set_tau(max(tau, 4.0))

    def state_dict(self):
        return {"lr": self.lr, "tau": -1.0 / math.log(max(self.decay, 1e-10)), "trades": self.trades, "wins": self.wins, "total_pnl": self.total_pnl}
