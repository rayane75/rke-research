#!/usr/bin/env python3
"""Vérifie qu'une capture contient bien une trame attendue (préambule régulier).

Retour immédiat après capture : la trame est-elle là, oui ou non ? Évite de
diagnostiquer dans le vide quand la bande (433.92) est encombrée d'autres
signaux. On cherche la signature d'un préambule : une suite d'alternances
régulières à la durée symbole attendue.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rke import demod, iq  # noqa: E402


def longest_regular_run(runs: list[tuple[int, int]], target: float, tol: float = 0.25) -> int:
    """Plus longue suite de paliers consécutifs dont la longueur ≈ target (±tol)."""
    lo, hi = target * (1 - tol), target * (1 + tol)
    best = cur = 0
    for _, length in runs:
        cur = cur + 1 if lo <= length <= hi else 0
        best = max(best, cur)
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="Vérifie la présence d'une trame dans une capture IQ")
    ap.add_argument("file", help="Fichier IQ (.cs8 / .cf32)")
    ap.add_argument("--fs", type=float, default=2e6, help="Fréquence d'échantillonnage (Hz)")
    ap.add_argument("--symbol-us", type=float, default=250.0, help="Durée symbole attendue (µs)")
    ap.add_argument("--min-preamble", type=int, default=10, help="Alternances minimales pour valider")
    args = ap.parse_args()

    samples = iq.load(args.file)

    # Qualité du front-end : un ADC saturé écrête tout et masque le signal.
    mean_power = float((np.abs(samples) ** 2).mean())
    sat = float(np.mean((np.abs(samples.real) > 0.95) | (np.abs(samples.imag) > 0.95)))

    carrier = demod.ook_bits(samples, args.fs)
    runs = demod.run_lengths(carrier)
    target = args.fs * args.symbol_us * 1e-6
    best = longest_regular_run(runs, target)
    bursts = demod.find_bursts(carrier, args.fs)

    print(f"{args.file}")
    print(f"  durée : {samples.size / args.fs:.2f} s | bursts : {len(bursts)}")
    print(f"  niveau : puissance moy {mean_power:.3f} | échantillons saturés {sat * 100:.1f}%")
    if sat > 0.02 or mean_power > 0.1:
        print("  ⚠️  ADC SATURÉ — baisse fortement le gain (essaie -l 8 -g 8) et décale la")
        print("      fréquence de ~200 kHz (-f 434120000) pour fuir le pic DC central.")
    print(f"  alternances régulières ~{target:.0f} éch (préambule) : {best} "
          f"(seuil : {args.min_preamble})")
    if best >= args.min_preamble:
        print("  ✅ Trame PRÉSENTE — lance analyze_capture.py.")
        return 0
    print("  ❌ Pas de préambule franc : la trame n'a pas été capturée.")
    print("     -> recapture en émettant PENDANT la fenêtre (voir protocole).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
