#!/usr/bin/env python3
"""Démo concrète : pourquoi AES(compteur) est imprévisible (effet d'avalanche).

Compare, appui par appui, ce qu'un fob enverrait EN CLAIR (le compteur brut) vs
ce qu'un fob moderne envoie VRAIMENT : AES(clé_secrète, compteur). Mesure combien
de bits changent à chaque incrément.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rke import aes128  # noqa: E402

KEY = bytes.fromhex("0123456789abcdef0123456789abcdef")  # clé secrète du "fob"


def hamming(a: bytes, b: bytes) -> int:
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b))


def main() -> int:
    print(f"Clé secrète du fob : {KEY.hex()}")
    print("Chaque appui incrémente le compteur. Δ = bits qui changent vs l'appui précédent.\n")
    prev_clear = prev_aes = None
    for ctr in range(6):
        clear = ctr.to_bytes(16, "big")
        enc = aes128.encrypt_block(clear, KEY)
        dc = f"Δ {hamming(clear, prev_clear):>3} bit" if prev_clear else "     —"
        da = f"Δ {hamming(enc, prev_aes):>3} bits" if prev_aes else "     —"
        print(f"appui {ctr}")
        print(f"   EN CLAIR : {clear.hex()}   {dc}")
        print(f"   AES      : {enc.hex()}   {da}")
        prev_clear, prev_aes = clear, enc

    print("\nCe qu'il faut retenir :")
    print("  • Compteur EN CLAIR : +1 ne change qu'~1 bit -> tu PRÉDIS le suivant (current+1).")
    print("  • AES(compteur)     : +1 fait sauter ~64 bits sur 128 (avalanche) -> aucun motif.")
    print("  • Sans la clé, impossible de calculer AES(compteur+1) : c'est ça, le rolling code")
    print("    solide. L'attaque ne passe plus par la radio, mais par la CLÉ (side-channel, etc.).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
