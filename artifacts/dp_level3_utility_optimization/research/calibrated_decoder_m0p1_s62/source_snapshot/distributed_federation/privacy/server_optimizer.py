"""FedOpt postprocessing. This API accepts one already-noisy aggregate only."""
from dataclasses import dataclass
import math
import numpy as np
from .mechanism import vector, restore


@dataclass(frozen=True)
class ServerConfig:
    name: str = 'fedavg'
    learning_rate: float = 1.0
    beta1: float = 0.9
    beta2: float = 0.99
    epsilon: float = 0.001

    def __post_init__(self):
        if self.name not in ('fedavg', 'fedavgm', 'fedadam', 'fedyogi'):
            raise ValueError('Unknown server optimizer')
        if not all(math.isfinite(v) for v in (self.learning_rate, self.beta1, self.beta2, self.epsilon)):
            raise ValueError('Nonfinite server optimizer setting')
        if self.learning_rate <= 0 or self.epsilon <= 0 or not 0 <= self.beta1 < 1 or not 0 <= self.beta2 < 1:
            raise ValueError('Invalid server optimizer setting')


class ServerOptimizer:
    def __init__(self, config=ServerConfig()):
        self.config = config
        self.m = self.v = None
        self.steps = 0

    def apply(self, base, noisy_aggregate):
        """Both inputs are public models; individual contributions are unavailable."""
        if set(base) != set(noisy_aggregate) or any(base[k].shape != noisy_aggregate[k].shape for k in base):
            raise ValueError('Aggregate schema mismatch')
        cfg = self.config
        if cfg.name == 'fedavg' and cfg.learning_rate == 1:
            self.steps += 1
            return {k: v.detach().clone() for k, v in noisy_aggregate.items()}
        start = vector(base)
        delta = vector(noisy_aggregate) - start
        if self.m is None:
            self.m = np.zeros_like(delta)
            self.v = np.zeros_like(delta)
        if self.m.shape != delta.shape:
            raise ValueError('Server optimizer dimension changed')
        self.steps += 1
        if cfg.name == 'fedavg':
            update = delta
        elif cfg.name == 'fedavgm':
            self.m = cfg.beta1 * self.m + delta
            update = self.m
        else:
            self.m = cfg.beta1 * self.m + (1-cfg.beta1) * delta
            square = delta ** 2
            if cfg.name == 'fedadam':
                self.v = cfg.beta2 * self.v + (1-cfg.beta2) * square
            else:
                self.v -= (1-cfg.beta2) * square * np.sign(self.v-square)
            update = self.m / (np.sqrt(self.v) + cfg.epsilon)
        return restore(start + cfg.learning_rate * update, base)
