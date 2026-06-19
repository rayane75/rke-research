#!/usr/bin/env python3
"""Génère UN .sub Flipper contenant N trames RKE réalistes pour s'entraîner à
l'analyse différentielle sur du Flipper maîtrisé, avant le vrai fob.

Structure d'une trame : [série fixe][bloc VARIABLE][bouton fixe], encodée en PWM
avec préambule (comme la trame de test précédente).

Deux modes pour le bloc variable :
  - rolling : pseudo-aléatoire par trame (simule un hopping code CHIFFRÉ : haute
              entropie -> un bloc variable franc, comme KeeLoq/AES).
  - counter : compteur qui s'incrémente (simule un compteur EN CLAIR : basse
              entropie, seuls les bits de poids faible bougent — la faille type).
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rke import aes128  # noqa: E402

PRESET = "FuriHalSubGhzPresetOok650Async"
CHUNK = 512


def bits_of(value: int, width: int) -> str:
    return format(value & ((1 << width) - 1), f"0{width}b")


def pwm_timings(bits: str, t: int) -> list[int]:
    """Préambule (16 alternances à T) puis chaque bit en PWM (1=3T/T, 0=T/3T)."""
    seq: list[int] = []
    for _ in range(16):
        seq += [+t, -t]
    for b in bits:
        seq += [+3 * t, -t] if b == "1" else [+t, -3 * t]
    return seq


def build_sub(frames: list[str], freq: int, t: int, gap_mult: int = 12) -> str:
    timings: list[int] = []
    for bits in frames:
        timings += pwm_timings(bits, t)
        timings.append(-t * gap_mult)  # silence inter-trames
    header = [
        "Filetype: Flipper SubGhz RAW File",
        "Version: 1",
        f"Frequency: {freq}",
        f"Preset: {PRESET}",
        "Protocol: RAW",
    ]
    for i in range(0, len(timings), CHUNK):
        header.append("RAW_Data: " + " ".join(str(v) for v in timings[i : i + CHUNK]))
    return "\n".join(header) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Génère N trames RKE structurées (.sub Flipper)")
    ap.add_argument("-o", "--out", default="rke_frames.sub")
    ap.add_argument("--serial", default="4B7", help="série fixe (hex)")
    ap.add_argument("--serial-bits", type=int, default=12)
    ap.add_argument("--button", default="2", help="bouton fixe (hex)")
    ap.add_argument("--button-bits", type=int, default=4)
    ap.add_argument("--var-bits", type=int, default=32, help="taille du bloc variable")
    ap.add_argument("--count", type=int, default=8, help="nombre de trames (appuis)")
    ap.add_argument("--mode", choices=["rolling", "counter", "aes"], default="rolling")
    ap.add_argument("--start", type=lambda x: int(x, 0), default=0, help="départ (counter/aes)")
    ap.add_argument("--key", default="0123456789abcdef0123456789abcdef",
                    help="clé AES 16 octets en hex (mode aes)")
    ap.add_argument("-f", "--freq", type=int, default=433920000)
    ap.add_argument("-t", "--symbol-us", type=int, default=250)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    serial = int(args.serial, 16)
    button = int(args.button, 16)
    var_bits = 128 if args.mode == "aes" else args.var_bits
    key = bytes.fromhex(args.key)
    rng = random.Random(args.seed)
    frames: list[str] = []
    truth: list[int] = []
    for i in range(args.count):
        if args.mode == "counter":
            var = (args.start + i) & ((1 << var_bits) - 1)
        elif args.mode == "aes":
            # vrai rolling code moderne : bloc = AES(clé, compteur)
            counter = (args.start + i).to_bytes(16, "big")
            var = int.from_bytes(aes128.encrypt_block(counter, key), "big")
        else:  # rolling : bloc pseudo-aléatoire (chiffré simulé)
            var = rng.getrandbits(var_bits)
        frames.append(
            bits_of(serial, args.serial_bits)
            + bits_of(var, var_bits)
            + bits_of(button, args.button_bits)
        )
        truth.append(var)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(build_sub(frames, args.freq, args.symbol_us))

    flen = args.serial_bits + var_bits + args.button_bits
    print(f"Écrit : {args.out}")
    print(f"  {args.count} trames de {flen} bits | mode {args.mode}")
    print(f"  structure : série {args.serial_bits}b (FIXE) | bloc {var_bits}b "
          f"(VARIABLE) | bouton {args.button_bits}b (FIXE)")
    print(f"  série=0x{args.serial} bouton=0x{args.button} | "
          f"bloc: {[hex(v) for v in truth[:5]]}{'…' if args.count > 5 else ''}")
    print()
    print("Workflow :")
    print("  1) Copie le .sub sur le Flipper, émets-le (maintiens OK), capture :")
    print("     hackrf_transfer -r diff.cs8 -f 434120000 -s 2000000 -n 60000000 -l 16 -g 20")
    print("  2) Analyse différentielle sur cette seule capture :")
    print("     ./.venv/bin/python scripts/analyze_capture.py --diff diff.cs8")
    print(f"  -> attendu : série FIXE, bloc {var_bits}b VARIABLE, bouton FIXE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
