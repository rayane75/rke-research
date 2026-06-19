"""Démodulation bas niveau : OOK/ASK et FSK.

La plupart des télécommandes RKE utilisent de l'OOK/ASK (présence/absence de
porteuse) ou de la 2-FSK. On fournit les deux primitives plus une estimation
de la durée symbole, sans présumer du codage de ligne (PWM/Manchester), géré
dans `framing.py`.
"""

from __future__ import annotations

import numpy as np


def magnitude(iq: np.ndarray) -> np.ndarray:
    """Enveloppe d'amplitude (utile pour l'OOK)."""
    return np.abs(iq)


def smooth(x: np.ndarray, window: int) -> np.ndarray:
    """Moyenne glissante par somme cumulée : O(n) quelle que soit la fenêtre.

    Indispensable pour les grandes fenêtres (détection de bursts sur plusieurs
    millions d'échantillons) où `np.convolve` exploserait en O(n*window).
    """
    if window <= 1:
        return x.astype(np.float32)
    w = int(window)
    cumsum = np.cumsum(np.concatenate(([0.0], x.astype(np.float64))))
    moving = (cumsum[w:] - cumsum[:-w]) / w  # longueur n-w+1
    out = np.empty(x.shape[0], dtype=np.float32)
    left = (w - 1) // 2
    out[:left] = moving[0]
    out[left : left + moving.shape[0]] = moving
    out[left + moving.shape[0] :] = moving[-1]
    return out


def otsu_threshold(env: np.ndarray, bins: int = 256) -> float:
    """Seuil d'Otsu : sépare 'porteuse présente' de 'silence' sans réglage manuel."""
    hist, edges = np.histogram(env, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2.0
    total = hist.sum()
    if total == 0:
        return float(env.mean())
    weight_bg = np.cumsum(hist)
    weight_fg = total - weight_bg
    mean_bg = np.cumsum(hist * centers)
    sum_total = mean_bg[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        mu_bg = mean_bg / weight_bg
        mu_fg = (sum_total - mean_bg) / weight_fg
        between = weight_bg * weight_fg * (mu_bg - mu_fg) ** 2
    between = np.nan_to_num(between)
    return float(centers[int(np.argmax(between))])


def carrier_threshold(env: np.ndarray, k: float = 0.5) -> float:
    """Seuil basé sur le plancher de bruit (robuste aux captures clairsemées).

    Otsu suppose deux populations comparables ; sur une capture où 98 % est du
    bruit et 2 % de la porteuse, il échoue. Ici on situe le plancher (médiane =
    bruit) et le niveau porteuse (haut percentile), et on place le seuil entre
    les deux : `floor + k*(peak - floor)`.
    """
    floor = float(np.percentile(env, 50.0))
    peak = float(np.percentile(env, 99.5))
    if peak <= floor:
        return float(env.mean())
    return floor + k * (peak - floor)


def ook_bits(iq: np.ndarray, fs: float, smooth_us: float = 5.0) -> np.ndarray:
    """Enveloppe OOK seuillée -> tableau binaire (porteuse on/off) par échantillon."""
    env = magnitude(iq)
    window = max(1, int(fs * smooth_us * 1e-6))
    env = smooth(env, window)
    thr = carrier_threshold(env)
    return (env > thr).astype(np.uint8)


def instantaneous_freq(iq: np.ndarray, fs: float) -> np.ndarray:
    """Fréquence instantanée (Hz) — base de la démodulation FSK."""
    phase = np.unwrap(np.angle(iq))
    return np.diff(phase) * fs / (2.0 * np.pi)


def fsk_bits(iq: np.ndarray, fs: float, smooth_us: float = 2.0) -> np.ndarray:
    """2-FSK : signe de la fréquence instantanée lissée -> binaire par échantillon."""
    freq = instantaneous_freq(iq, fs)
    window = max(1, int(fs * smooth_us * 1e-6))
    freq = smooth(freq, window)
    return (freq > np.median(freq)).astype(np.uint8)


def run_lengths(bits: np.ndarray) -> list[tuple[int, int]]:
    """Compresse un train binaire en (valeur, longueur). Base du décodage de ligne."""
    if bits.size == 0:
        return []
    change = np.flatnonzero(np.diff(bits)) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [bits.size]))
    return [(int(bits[s]), int(e - s)) for s, e in zip(starts, ends)]


def estimate_symbol_samples(runs: list[tuple[int, int]]) -> int:
    """Estime la durée d'UN symbole, robuste à une distribution bimodale.

    Sur du vrai RF, les longueurs de paliers forment deux populations : un nuage
    de micro-runs de bruit, et les vrais symboles (longs). Prendre un bas
    percentile global tombe dans le bruit. On fixe donc une échelle à partir du
    HAUT de la distribution (p90 ≈ un vrai palier), on barre tout ce qui est sous
    une fraction de cette échelle (bruit), puis on prend le plus court des
    paliers réels ≈ la largeur symbole.
    """
    lengths = np.array([length for _, length in runs if length > 0], dtype=np.float64)
    if lengths.size == 0:
        return 0
    scale = float(np.percentile(lengths, 90))
    gate = max(2.0, 0.25 * scale)
    real = lengths[lengths >= gate]
    if real.size == 0:
        return max(1, int(round(scale)))
    return max(1, int(round(float(np.percentile(real, 10)))))


def find_bursts(
    carrier_on: np.ndarray,
    fs: float,
    gate_ms: float = 3.0,
    min_ms: float = 2.0,
    active_frac: float = 0.15,
) -> list[tuple[int, int]]:
    """Isole les trames : régions où la porteuse est active, séparées par du silence.

    On lisse le signal porteuse (0/1) sur une fenêtre `gate_ms` plus large que le
    plus long silence INTRA-trame, mais plus courte que les silences INTER-trames.
    Une région où l'activité moyenne dépasse `active_frac` et qui dure au moins
    `min_ms` est une trame candidate.
    """
    window = max(1, int(fs * gate_ms * 1e-3))
    activity = smooth(carrier_on.astype(np.float32), window)
    active = (activity > active_frac).astype(np.uint8)
    min_len = int(fs * min_ms * 1e-3)
    bursts: list[tuple[int, int]] = []
    pos = 0
    for val, length in run_lengths(active):
        if val == 1 and length >= min_len:
            bursts.append((pos, pos + length))
        pos += length
    return bursts


def merge_short_runs(runs: list[tuple[int, int]], min_run: int) -> list[tuple[int, int]]:
    """Supprime les paliers plus courts que `min_run` (bruit) et recolle les voisins.

    Un glitch de 1 échantillon devient un palier de longueur 1 qui ferait croire à
    un symbole minuscule. On les jette puis on fusionne les paliers adjacents de
    même valeur — ce qui restitue les vrais symboles longs traversés par du bruit.
    """
    kept = [(val, length) for val, length in runs if length >= min_run]
    if not kept:
        return []
    merged: list[list[int]] = [list(kept[0])]
    for val, length in kept[1:]:
        if val == merged[-1][0]:
            merged[-1][1] += length
        else:
            merged.append([val, length])
    return [(val, length) for val, length in merged]
