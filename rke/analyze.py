"""Analyse différentielle des trames — le cœur du reverse RKE.

Tu captures N appuis de TON fob, tu alignes les trames, puis tu regardes
bit par bit ce qui est FIXE (numéro de série, code bouton, en-tête) et ce qui
VARIE (compteur, partie chiffrée). La taille et la position de la zone variable
révèlent le schéma :

  - ~32 bits qui varient    -> probable KeeLoq (bloc 32 bits)
  - ~64 / 128 bits          -> probable AES (bloc 128 bits, parfois tronqué)
  - 1 octet qui s'incrémente -> compteur en clair (drapeau d'implémentation faible)

C'est de l'analyse de protocole sur ton propre matériel : on comprend, on ne
force rien.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2


@dataclass(frozen=True)
class FieldReport:
    position: int
    length: int
    kind: str          # "fixed" | "varying"
    sample_values: list[str]


def align_frames(frames: list[str]) -> list[str]:
    """Tronque toutes les trames à la longueur commune minimale (alignement à gauche)."""
    clean = [f for f in frames if f and "?" not in f]
    if not clean:
        raise ValueError("Aucune trame propre (sans '?') à analyser")
    n = min(len(f) for f in clean)
    return [f[:n] for f in clean]


def bit_variability(frames: list[str]) -> list[float]:
    """Pour chaque position : proportion de '1' à travers les captures.

    0.0 ou 1.0 => bit fixe. Proche de 0.5 => bit qui varie franchement.
    """
    aligned = align_frames(frames)
    n = len(aligned[0])
    count = len(aligned)
    out = []
    for pos in range(n):
        ones = sum(1 for f in aligned if f[pos] == "1")
        out.append(ones / count)
    return out


def segment_fields(frames: list[str], tol: float = 1e-9) -> list[FieldReport]:
    """Regroupe les bits contigus de même nature (fixe vs variable) en champs."""
    aligned = align_frames(frames)
    var = bit_variability(aligned)
    reports: list[FieldReport] = []
    pos = 0
    n = len(var)
    while pos < n:
        is_fixed = var[pos] <= tol or var[pos] >= 1 - tol
        start = pos
        while pos < n and ((var[pos] <= tol or var[pos] >= 1 - tol) == is_fixed):
            pos += 1
        length = pos - start
        samples = [f[start : start + length] for f in aligned[:3]]
        reports.append(
            FieldReport(
                position=start,
                length=length,
                kind="fixed" if is_fixed else "varying",
                sample_values=samples,
            )
        )
    return reports


def shannon_entropy(frames: list[str], start: int, length: int) -> float:
    """Entropie (bits) d'un champ à travers les captures — détecte le vrai aléa."""
    values = [f[start : start + length] for f in align_frames(frames)]
    total = len(values)
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return -sum((c / total) * log2(c / total) for c in counts.values())


def guess_scheme(reports: list[FieldReport]) -> str:
    """Heuristique : déduit le schéma probable de la plus grande zone variable."""
    varying = [r for r in reports if r.kind == "varying"]
    if not varying:
        return "Aucune zone variable : code FIXE (rejeu trivial) ou captures identiques."
    biggest = max(varying, key=lambda r: r.length)
    n = biggest.length
    if n <= 8:
        return f"Zone variable {n} bits : probable COMPTEUR EN CLAIR (faille d'implémentation)."
    if 24 <= n <= 40:
        return f"Zone variable {n} bits : compatible bloc KeeLoq (32 bits)."
    if 56 <= n <= 72:
        return f"Zone variable {n} bits : bloc chiffré ~64 bits (AES tronqué / autre)."
    if 112 <= n <= 136:
        return f"Zone variable {n} bits : compatible bloc AES-128."
    return f"Zone variable {n} bits : schéma à caractériser (comparer aux specs encodeur)."


def report_text(frames: list[str]) -> str:
    """Rapport lisible : carte des champs + entropie + hypothèse de schéma."""
    reports = segment_fields(frames)
    lines = [f"Trames analysées : {len(align_frames(frames))}", ""]
    lines.append(f"{'pos':>4}  {'len':>4}  {'type':<8}  {'entropie':>8}  exemple")
    for r in reports:
        ent = shannon_entropy(frames, r.position, r.length)
        sample = r.sample_values[0] if r.sample_values else ""
        preview = sample if len(sample) <= 24 else sample[:21] + "..."
        lines.append(
            f"{r.position:>4}  {r.length:>4}  {r.kind:<8}  {ent:>8.2f}  {preview}"
        )
    lines.append("")
    lines.append("Hypothèse : " + guess_scheme(reports))
    return "\n".join(lines)
