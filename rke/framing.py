"""Décodage de ligne et extraction de trame.

À partir des paliers (run-lengths) issus de la démodulation OOK, on reconnaît
le codage : PWM (largeur d'impulsion, très courant en RKE) ou Manchester.
On isole aussi le préambule (suite régulière en tête de trame) pour
synchroniser et découper la charge utile.
"""

from __future__ import annotations

import numpy as np

from .demod import (
    estimate_symbol_samples,
    find_bursts,
    merge_short_runs,
    run_lengths,
)


def quantize_runs(runs: list[tuple[int, int]], symbol: int) -> list[tuple[int, int]]:
    """Convertit chaque palier en (valeur, nombre de symboles entiers)."""
    if symbol <= 0:
        return []
    return [(val, max(1, int(round(length / symbol)))) for val, length in runs]


def decode_pwm(quantized: list[tuple[int, int]], short: int = 1, long_: int = 3) -> str:
    """Décodage PWM/PPM classique des fobs.

    Convention fréquente : un bit = un haut suivi d'un bas. Haut court + bas long
    = '0' ; haut long + bas court = '1'. On lit les paires (haut, bas).
    """
    bits = []
    pairs = []
    # regroupe en paires haut/bas
    i = 0
    while i < len(quantized) - 1:
        hi_val, hi_len = quantized[i]
        lo_val, lo_len = quantized[i + 1]
        if hi_val == 1 and lo_val == 0:
            pairs.append((hi_len, lo_len))
            i += 2
        else:
            i += 1
    for hi_len, lo_len in pairs:
        # En PWM/PPM la période est ~constante : la durée du HAUT porte le bit,
        # le BAS n'est que le complément (et peut fusionner avec le silence en fin
        # de trame). On décide donc sur le haut ; le bas reste consultable.
        if hi_len >= long_:
            bits.append("1")
        elif hi_len <= short:
            bits.append("0")
        else:
            # haut ~2 symboles : réellement ambigu, on le marque
            bits.append("?")
    return "".join(bits)


def decode_manchester(quantized: list[tuple[int, int]]) -> str:
    """Décodage Manchester : transition au milieu du bit (01 -> '1', 10 -> '0').

    On déplie les paliers en symboles puis on lit par paires de demi-bits.
    """
    symbols = []
    for val, count in quantized:
        symbols.extend([val] * count)
    bits = []
    for i in range(0, len(symbols) - 1, 2):
        a, b = symbols[i], symbols[i + 1]
        if a == 0 and b == 1:
            bits.append("1")
        elif a == 1 and b == 0:
            bits.append("0")
        else:
            bits.append("?")
    return "".join(bits)


def find_preamble(quantized: list[tuple[int, int]], min_repeats: int = 8) -> int:
    """Indice du premier palier après un préambule (alternance régulière 1010...).

    Renvoie 0 si aucun préambule franc n'est détecté.
    """
    count = 0
    for idx, (_val, length) in enumerate(quantized):
        if length == 1:
            count += 1
            if count >= min_repeats:
                # avance jusqu'à la fin de la zone d'unités
                j = idx
                while j < len(quantized) and quantized[j][1] == 1:
                    j += 1
                return j
        else:
            count = 0
    return 0


def _denoise_runs(runs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Jette les paliers trop courts (bruit) relativement à l'échelle des vrais
    paliers (p90), pas à la médiane — qui est elle-même polluée par le bruit."""
    if not runs:
        return runs
    lengths = np.array([length for _, length in runs], dtype=np.float64)
    gate = max(2, int(0.20 * np.percentile(lengths, 90)))
    return merge_short_runs(runs, gate)


def bits_from_ook(ook: np.ndarray) -> dict:
    """Pipeline OOK complet -> dict avec runs, symbole estimé, et bits PWM/Manchester.

    On renvoie les deux décodages : c'est à l'analyste de regarder lequel donne
    une trame cohérente (peu de '?', longueur stable entre captures).
    """
    runs = _denoise_runs(run_lengths(ook))
    symbol = estimate_symbol_samples(runs)
    quantized = quantize_runs(runs, symbol)
    start = find_preamble(quantized)
    payload = quantized[start:] if start else quantized
    return {
        "symbol_samples": symbol,
        "preamble_end": start,
        "pwm": decode_pwm(payload),
        "manchester": decode_manchester(payload),
    }


def decode_capture(carrier_on: np.ndarray, fs: float) -> list[dict]:
    """Découpe une capture en bursts et décode chaque trame isolément.

    C'est l'entrée pour du VRAI signal : une capture longue contient surtout du
    silence et quelques trames. On isole chaque trame, on la décode séparément,
    et on annote sa position et sa durée.
    """
    results: list[dict] = []
    for start, end in find_bursts(carrier_on, fs):
        decoded = bits_from_ook(carrier_on[start:end])
        decoded["burst"] = (int(start), int(end))
        decoded["span_ms"] = round((end - start) / fs * 1e3, 2)
        results.append(decoded)
    return results
