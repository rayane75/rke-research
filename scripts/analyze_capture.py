#!/usr/bin/env python3
"""Analyse de bout en bout : fichiers IQ -> bursts -> bits -> carte des champs.

Usage :
    python scripts/analyze_capture.py captures/fob_lock_*.cs8
    python scripts/analyze_capture.py --fs 2e6 --mode ook captures/*.cs8

Pour une seule capture : isole les trames (bursts) et affiche le décodage de la
meilleure. Pour plusieurs captures : analyse différentielle des champs.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Permet d'exécuter le script directement depuis la racine du projet
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rke import analyze, demod, framing, iq  # noqa: E402

MAX_SHOW = 256  # limite d'affichage d'un train de bits


def cap(bits: str) -> str:
    return bits if len(bits) <= MAX_SHOW else bits[:MAX_SHOW] + f"… (+{len(bits) - MAX_SHOW})"


def resolved(bits: str) -> int:
    """Nombre de bits sûrs (non '?') — sert à classer les bursts."""
    return sum(1 for c in bits if c != "?")


def decode_file(path: str, fs: float, mode: str) -> list[dict]:
    samples = iq.load(path)
    carrier = demod.fsk_bits(samples, fs) if mode == "fsk" else demod.ook_bits(samples, fs)
    return framing.decode_capture(carrier, fs)


def best_burst(bursts: list[dict], coding: str) -> dict | None:
    return max(bursts, key=lambda r: resolved(r[coding])) if bursts else None


def show_single(path: str, bursts: list[dict], coding: str) -> int:
    print(f"Fichier : {path}")
    if not bursts:
        print("  Aucun burst détecté (capture trop bruitée, gain inadapté, ou mauvaise fréquence).")
        return 1
    print(f"  {len(bursts)} burst(s) détecté(s) :")
    for i, b in enumerate(bursts):
        flag = b[coding]
        print(f"   #{i} @ {b['burst'][0]} ({b['span_ms']} ms) | "
              f"symbole {b['symbol_samples']} éch | {coding} : {cap(flag)}")
    best = best_burst(bursts, coding)
    print()
    print(f"  >>> Meilleure trame ({coding}, {resolved(best[coding])} bits sûrs) :")
    print(f"      PWM        : {cap(best['pwm'])}")
    print(f"      Manchester : {cap(best['manchester'])}")
    return 0


def show_diff(path: str, bursts: list[dict], coding: str) -> int:
    """Analyse différentielle sur les trames d'UNE capture (plusieurs appuis)."""
    frames = [b[coding] for b in bursts]
    clean = [f for f in frames if f and f.count("?") <= max(1, len(f) // 10)]
    if len(clean) < 3:
        print("Pas assez de trames propres pour le différentiel — capture plus d'appuis.")
        return 1
    target_len, _ = Counter(len(f) for f in clean).most_common(1)[0]
    group = [f for f in clean if len(f) == target_len]
    print(f"Fichier : {path}")
    print(f"  {len(bursts)} bursts | groupe dominant : {len(group)} trames de {target_len} bits\n")
    try:
        print(analyze.report_text(group))
    except ValueError as exc:
        print(f"  Différentiel impossible : {exc}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyse RKE (matériel possédé uniquement)")
    parser.add_argument("files", nargs="+", help="Fichiers IQ (.cs8 / .cf32)")
    parser.add_argument("--fs", type=float, default=2e6, help="Fréquence d'échantillonnage (Hz)")
    parser.add_argument("--mode", choices=["ook", "fsk"], default="ook")
    parser.add_argument("--coding", choices=["pwm", "manchester"], default="pwm")
    parser.add_argument("--diff", action="store_true",
                        help="Analyse différentielle des trames d'une seule capture")
    args = parser.parse_args()

    per_file: list[tuple[str, list[dict]]] = []
    for path in args.files:
        try:
            per_file.append((path, decode_file(path, args.fs, args.mode)))
        except Exception as exc:  # message lisible plutôt que trace brute
            print(f"[!] {path} : {exc}", file=sys.stderr)

    if not per_file:
        print("Aucune capture exploitable.", file=sys.stderr)
        return 1

    if len(per_file) == 1:
        path, bursts = per_file[0]
        if args.diff:
            return show_diff(path, bursts, args.coding)
        return show_single(path, bursts, args.coding)

    # Multi-captures : une meilleure trame par fichier -> analyse différentielle
    frames: list[str] = []
    for path, bursts in per_file:
        best = best_burst(bursts, args.coding)
        if best is None:
            print(f"[!] {path} : aucun burst, ignoré.", file=sys.stderr)
            continue
        frames.append(best[args.coding])

    lengths = {len(b) for b in frames}
    print(f"{len(frames)} trames | longueurs observées : {sorted(lengths)}")
    if len(lengths) > 1:
        print("(!) Longueurs inégales : aligne d'abord le codage et la qualité de capture.\n")
    print(analyze.report_text(frames))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
