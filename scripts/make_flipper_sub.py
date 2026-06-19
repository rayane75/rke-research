#!/usr/bin/env python3
"""Génère un fichier Flipper Sub-GHz RAW (.sub) encodant une charge utile connue.

But : test en boucle fermée du toolkit. Le Flipper émet une trame PWM connue,
le HackRF la capture, et `analyze_capture.py` doit retrouver EXACTEMENT les mêmes
bits. Aucune cible tierce : ton Flipper parle à ton HackRF, sur ton banc, à basse
puissance en bande ISM 433.92 MHz.

Convention PWM (identique à rke.framing.decode_pwm) :
  '1' = porteuse haute 3T puis basse 1T
  '0' = porteuse haute 1T puis basse 3T
Préambule : N alternances à la largeur symbole T.

Le format .sub RAW liste des durées en microsecondes : positif = porteuse ON,
négatif = OFF.
"""

from __future__ import annotations

import argparse

PRESET = "FuriHalSubGhzPresetOok650Async"  # OOK/ASK asynchrone
CHUNK = 512  # Flipper limite ~512 valeurs par ligne RAW_Data


def hex_to_bits(hex_str: str) -> str:
    cleaned = hex_str.lower().replace("0x", "").replace("_", "").strip()
    if not cleaned or any(c not in "0123456789abcdef" for c in cleaned):
        raise ValueError(f"Charge utile hex invalide : {hex_str!r}")
    width = len(cleaned) * 4
    return format(int(cleaned, 16), f"0{width}b")


def frame_timings(bits: str, t_us: int, preamble_cycles: int) -> list[int]:
    seq: list[int] = []
    for _ in range(preamble_cycles):
        seq.append(+t_us)
        seq.append(-t_us)
    for b in bits:
        if b == "1":
            seq.extend([+3 * t_us, -1 * t_us])
        else:
            seq.extend([+1 * t_us, -3 * t_us])
    return seq


def build_sub(bits: str, freq: int, t_us: int, preamble: int, repeats: int) -> str:
    timings: list[int] = []
    for i in range(repeats):
        timings.extend(frame_timings(bits, t_us, preamble))
        if i < repeats - 1:
            timings.append(-t_us * 12)  # silence inter-trames
    header = [
        "Filetype: Flipper SubGhz RAW File",
        "Version: 1",
        f"Frequency: {freq}",
        f"Preset: {PRESET}",
        "Protocol: RAW",
    ]
    for i in range(0, len(timings), CHUNK):
        chunk = timings[i : i + CHUNK]
        header.append("RAW_Data: " + " ".join(str(v) for v in chunk))
    return "\n".join(header) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Génère une trame de test Flipper .sub")
    ap.add_argument("payload_hex", nargs="?", help="Charge utile en hex, ex: A5C3F0")
    ap.add_argument("-o", "--out", default="test_frame.sub")
    ap.add_argument("-f", "--freq", type=int, default=433920000)
    ap.add_argument("-t", "--symbol-us", type=int, default=250, help="Durée symbole T (µs)")
    ap.add_argument("-p", "--preamble", type=int, default=16, help="Cycles de préambule")
    ap.add_argument("-r", "--repeats", type=int, default=1)
    ap.add_argument("--beacon", type=int, metavar="CYCLES",
                    help="Mode beacon : N alternations carrées pures (test 'le Flipper émet-il ?')")
    args = ap.parse_args()

    if args.beacon:
        # Pur signal carré : que du préambule, aucune donnée. Sert à prouver que
        # la chaîne d'émission du Flipper fonctionne, indépendamment des données.
        bits = ""
        sub = build_sub(bits, args.freq, args.symbol_us, args.beacon, 1)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(sub)
        print(f"Écrit : {args.out} (BEACON, {args.beacon} cycles ~ "
              f"{args.beacon * 2 * args.symbol_us / 1000:.0f} ms de carré pur @ {args.freq} Hz)")
        print(f"  Émets-le, capture, puis : ./.venv/bin/python scripts/check_capture.py <fichier>")
        print(f"  Des milliers d'alternances = la chaîne TX du Flipper marche.")
        return 0

    if not args.payload_hex:
        ap.error("payload_hex requis (ou utilise --beacon CYCLES)")
    bits = hex_to_bits(args.payload_hex)
    sub = build_sub(bits, args.freq, args.symbol_us, args.preamble, args.repeats)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(sub)

    fronts = sub.count(" ") + sub.count("RAW_Data")  # approximatif, info seulement
    print(f"Écrit : {args.out}")
    print(f"  payload {args.payload_hex} -> {len(bits)} bits : {bits}")
    print(f"  symbole T = {args.symbol_us} µs | préambule {args.preamble} cycles | "
          f"{args.repeats} trame(s)")
    print()
    print("Boucle de test :")
    print(f"  1) Copie {args.out} sur le Flipper : SD /subghz/")
    print(f"  2) Flipper > Sub-GHz > liste > {args.out} > Émettre (garde le doigt = répète)")
    print(f"  3) En parallèle, capture au HackRF (~3 s) :")
    print(f"     hackrf_transfer -r flipper_test.cs8 -f {args.freq} -s 2000000 "
          f"-n 6000000 -l 32 -g 30")
    print(f"  4) Décode : ./.venv/bin/python scripts/analyze_capture.py flipper_test.cs8")
    print(f"     -> le champ 'pwm' doit contenir : {bits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
