"""Test d'intégration : IQ bruité -> burst -> bits.

Reproduit ce qui casse sur du vrai RF (silence, bruit, offset de porteuse) et
vérifie que la chaîne complète (seuillage -> bursts -> débruitage -> décodage)
récupère une charge utile connue. C'est la preuve que le code est bon,
indépendamment de la qualité d'une capture réelle.
"""

from __future__ import annotations

import numpy as np

from rke import demod, framing

FS = 2_000_000  # 2 Msps


def make_ook_iq(
    bits: str,
    symbol: int = 500,
    preamble: int = 16,
    gap: int = 20_000,
    snr_db: float = 15.0,
    f_off_hz: float = 1500.0,
    seed: int = 0,
) -> np.ndarray:
    """Génère un IQ OOK : préambule + PWM, noyé dans silence + bruit gaussien."""
    rng = np.random.default_rng(seed)
    level: list[int] = []
    for _ in range(preamble):
        level += [1] * symbol + [0] * symbol
    for b in bits:
        if b == "1":
            level += [1] * (3 * symbol) + [0] * symbol
        else:
            level += [1] * symbol + [0] * (3 * symbol)
    envelope = np.concatenate([np.zeros(gap), np.array(level, dtype=np.float64), np.zeros(gap)])
    n = envelope.size
    carrier = np.exp(2j * np.pi * f_off_hz * np.arange(n) / FS)
    noise_amp = 10 ** (-snr_db / 20.0)
    noise = noise_amp * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return (envelope * carrier + noise).astype(np.complex64)


def test_pipeline_recovers_payload_from_noisy_iq():
    payload = "1010010111000011"  # A5C3
    samples = make_ook_iq(payload)
    carrier = demod.ook_bits(samples, FS)
    bursts = framing.decode_capture(carrier, FS)

    assert bursts, "aucun burst détecté dans un signal pourtant présent"
    assert any(payload in b["pwm"] for b in bursts), [b["pwm"] for b in bursts]


def test_symbol_estimate_is_close_to_truth():
    samples = make_ook_iq("11001010", symbol=400, seed=3)
    carrier = demod.ook_bits(samples, FS)
    bursts = framing.decode_capture(carrier, FS)

    assert bursts
    best = max(bursts, key=lambda b: sum(c != "?" for c in b["pwm"]))
    # tolérance large : on veut le bon ordre de grandeur, pas l'exactitude
    assert 320 <= best["symbol_samples"] <= 480, best["symbol_samples"]
