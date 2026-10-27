"""Replace-one client adjacency. Equal weights only.

The ring contains rounded Gaussian shares, NOT an exact aggregate Gaussian.
Its conservative ideal-Gaussian bound uses postprocessing of the changed client's Gaussian share:
rho <= n/(2*m*m), not the unjustified ideal 1/(2*m*m). See PRIVACY_ARCHITECTURE.md.
All mathematical Gaussian claims assume ideal sampling; machine RNG is computational.
"""
from dataclasses import dataclass
import math
import secrets
import numpy as np
import torch

MODES = ('none', 'option_a', 'secure_central_dp', 'distributed_dp')

@dataclass(frozen=True)
class Privacy:
    mode: str = 'none'
    clip: float = 1.0
    multiplier: float = 0.0
    delta: float = 1e-6
    expected_clients: int = 3
    min_noise_contributors: int = 3
    scale: int = 2**24
    entropy: str = 'production'
    research_seed: int = 42

    def __post_init__(self):
        if self.mode not in MODES or not math.isfinite(self.clip) or self.clip <= 0:
            raise ValueError('Invalid privacy mode or clipping bound')
        if not math.isfinite(self.multiplier) or self.multiplier < 0 or not 0 < self.delta < 1:
            raise ValueError('Invalid Gaussian multiplier/delta')
        if self.expected_clients < 2 or self.min_noise_contributors != self.expected_clients:
            raise ValueError('Only a complete fixed cohort with all noise contributors is supported')
        if self.entropy not in ('production', 'research') or self.scale < 1 or self.scale > 2**32:
            raise ValueError('Invalid entropy policy or fixed-point scale')

    @property
    def secure(self): return self.mode in ('secure_central_dp', 'distributed_dp')

    def parameters(self, dimension):
        # Per-vector deterministic rounding error <= sqrt(d)/(2s).
        error = math.sqrt(dimension) / (2*self.scale) if self.secure else 0.
        effective = self.clip + error
        sensitivity = 2*effective/self.expected_clients
        sigma = self.multiplier*sensitivity
        if self.mode == "option_a":
            sigma = 2*self.clip*self.multiplier/math.sqrt(self.expected_clients)
        return dict(C=self.clip, n=self.expected_clients, dimension=dimension,
                    quantization_l2_bound=error, effective_clip=effective,
                    ideal_sensitivity=2*self.clip/self.expected_clients,
                    sensitivity=sensitivity, accounting_sensitivity=2*self.clip if self.mode=='option_a' else sensitivity, sigma_mean=sigma,
                    sigma_share=sigma*math.sqrt(self.expected_clients),
                    expected_noise_l2=sigma*math.sqrt(dimension))

    def rho(self):
        if self.mode == 'none' or self.multiplier == 0: return math.inf
        factor = self.expected_clients if self.mode == 'distributed_dp' else 1
        return factor/(2*self.multiplier**2)

    def accounting(self, releases):
        rho = releases*self.rho() if releases else 0.
        epsilon = rho+2*math.sqrt(rho*math.log(1/self.delta))
        return dict(releases=releases,rho=rho,epsilon=epsilon,delta=self.delta,
                    bound='encoded_share_postprocessing' if self.mode=='distributed_dp' else 'Gaussian_zCDP',
                    research_only=self.entropy=='research',
                    sampler_assumption='ideal Gaussian; finite-precision sampler is not exact-DP certified')


def vector(state):
    if not state or any(not t.is_floating_point() for t in state.values()):
        raise ValueError('Only floating model parameters may be federated')
    if any(not torch.isfinite(t).all() for t in state.values()): raise ValueError('Nonfinite model')
    return torch.cat([state[k].detach().cpu().double().reshape(-1) for k in sorted(state)]).numpy()


def restore(values, base):
    result, offset = {}, 0
    for k in sorted(base):
        count = base[k].numel()
        result[k] = torch.from_numpy(np.asarray(values[offset:offset+count]).copy()).reshape_as(base[k]).to(base[k].dtype)
        offset += count
    if offset != len(values): raise ValueError('Model dimension mismatch')
    return result


def clip_vector(delta, bound):
    delta = np.asarray(delta, dtype=np.float64)
    if not np.isfinite(delta).all(): raise ValueError('Nonfinite update')
    norm = np.linalg.norm(delta)
    return delta*min(1.,bound/max(norm,1e-300))


def gaussian(size, sigma, cfg, run_id, round_id, client):
    if sigma == 0: return np.zeros(size)
    if cfg.entropy == 'research':
        import hashlib
        domain = f'{cfg.research_seed}/{run_id}/{round_id}/{client}'.encode()
        seed = int.from_bytes(hashlib.sha256(domain).digest(),'big')
    else:
        # OS CSPRNG uniforms and Box-Muller; private entropy is never persisted.
        count=(size+1)//2
        bits=np.frombuffer(secrets.token_bytes(count*16),dtype=np.uint64).reshape(2,count)
        uniforms=((bits >> 11).astype(np.float64)+.5)/(2**53)
        radius=np.sqrt(-2*np.log(uniforms[0]))
        angle=2*np.pi*uniforms[1]
        return (np.column_stack((radius*np.cos(angle),radius*np.sin(angle))).reshape(-1)[:size])*sigma
    return np.random.Generator(np.random.PCG64(seed)).normal(0,sigma,size)


def encode(x, scale):
    rounded = np.rint(np.asarray(x,dtype=np.float64)*scale)
    # Deterministic wrap on an astronomically large Gaussian tail is postprocessing,
    # not data-dependent rejection/truncation. Typical coordinates fit in int64.
    if not np.isfinite(rounded).all(): raise ValueError('Nonfinite encoded value')
    if np.max(np.abs(rounded), initial=0) < 2**62:
        return rounded.astype(np.int64).view(np.uint64)
    return np.array([int(v) % (2**64) for v in rounded],dtype=np.uint64)


def decode(x, scale):
    return np.asarray(x,dtype=np.uint64).view(np.int64).astype(np.float64)/scale


def client_contribution(local, base, cfg, run_id, round_id, client):
    delta = vector(local)-vector(base)
    if cfg.mode == 'none': return delta
    clipped = clip_vector(delta,cfg.clip)
    if cfg.mode == 'option_a':
        # Old baseline: full client-level replace-one Gaussian, ordinary transport.
        return clipped+gaussian(len(delta),2*cfg.clip*cfg.multiplier,cfg,run_id,round_id,client)
    quantized = encode(clipped,cfg.scale)
    if cfg.mode == 'distributed_dp':
        sigma = cfg.parameters(len(delta))['sigma_share']
        noise = encode(gaussian(len(delta),sigma,cfg,run_id,round_id,client),cfg.scale)
        return np.add(quantized,noise,dtype=np.uint64)
    return quantized


def aggregate(contributions, base, cfg, run_id, round_id):
    if len(contributions) != cfg.expected_clients: raise ValueError('Incomplete cohort; no fallback')
    if cfg.secure:
        total = np.zeros_like(contributions[0],dtype=np.uint64)
        for item in contributions: total = np.add(total,item,dtype=np.uint64)
        mean = decode(total,cfg.scale)/len(contributions)
        if cfg.mode == 'secure_central_dp':
            mean += gaussian(len(mean),cfg.parameters(len(mean))['sigma_mean'],cfg,run_id,round_id,'central')
    else:
        mean = np.mean(contributions,axis=0)
    return restore(vector(base)+mean,base)
