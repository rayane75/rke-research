"""Tests de la chaîne démod/framing/analyse sur signaux synthétiques.

On fabrique un OOK PWM connu, on vérifie qu'on retombe sur les bons bits, puis
on valide l'analyse différentielle (champs fixes vs variables).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rke import analyze, demod, framing  # noqa: E402

SYMBOL = 20  # échantillons par unité de temps


def make_pwm_ook(bits: str, symbol: int = SYMBOL) -> np.ndarray:
    """Construit une enveloppe OOK PWM : '1' = haut long/bas court, '0' = inverse."""
    out: list[int] = []
    for _ in range(8):  # préambule réaliste : 8 cycles à la largeur symbole
        out.extend([1] * symbol + [0] * symbol)
    for b in bits:
        if b == "1":
            out.extend([1] * (3 * symbol) + [0] * (1 * symbol))
        else:
            out.extend([1] * (1 * symbol) + [0] * (3 * symbol))
    return np.array(out, dtype=np.uint8)


def test_run_lengths_roundtrip():
    bits = np.array([1, 1, 1, 0, 0, 1], dtype=np.uint8)
    runs = demod.run_lengths(bits)
    assert runs == [(1, 3), (0, 2), (1, 1)]


def test_pwm_decode_recovers_bits():
    payload = "10110010"
    env = make_pwm_ook(payload)
    decoded = framing.bits_from_ook(env)
    assert decoded["pwm"] == payload, decoded


def test_otsu_separates_levels():
    env = np.concatenate([np.full(500, 0.05), np.full(500, 0.9)]).astype(np.float32)
    thr = demod.otsu_threshold(env)
    assert 0.05 < thr < 0.9


def test_field_segmentation_finds_varying_block():
    # 8 bits fixes (série) + 8 bits qui varient + 4 bits fixes (bouton).
    # Valeurs choisies pour que CHAQUE position de l'octet bascule : sinon un bit
    # resté constant serait (à juste titre) classé 'fixe'. C'est le piège réel de
    # l'analyse différentielle — il faut assez de variété dans les captures.
    fixed_serial = "10100101"
    button = "0011"
    counters = [0x55, 0xAA, 0x0F, 0xF0, 0x33, 0xCC, 0x96, 0x69]
    frames = [fixed_serial + format(c, "08b") + button for c in counters]
    reports = analyze.segment_fields(frames)
    kinds = [(r.position, r.length, r.kind) for r in reports]
    assert kinds[0] == (0, 8, "fixed"), kinds
    varying = [r for r in reports if r.kind == "varying"]
    assert len(varying) == 1 and varying[0].length == 8, kinds


def test_guess_scheme_flags_plain_counter():
    frames = ["10100101" + format(c, "08b") for c in range(8)]
    reports = analyze.segment_fields(frames)
    assert "COMPTEUR" in analyze.guess_scheme(reports).upper()
