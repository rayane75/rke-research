"""Chargement des fichiers IQ produits par le HackRF.

`hackrf_transfer -r capture.bin` écrit des échantillons I/Q entrelacés signés
8 bits (format cs8) : 2 octets par échantillon. On les ramène en complexes
normalisés [-1, 1] pour le reste de la chaîne.
"""

from __future__ import annotations

import numpy as np


def load_cs8(path: str) -> np.ndarray:
    """Lit un fichier cs8 (sortie native hackrf_transfer) en complex64."""
    raw = np.fromfile(path, dtype=np.int8)
    if raw.size % 2 != 0:
        raw = raw[:-1]
    i = raw[0::2].astype(np.float32) / 128.0
    q = raw[1::2].astype(np.float32) / 128.0
    return (i + 1j * q).astype(np.complex64)


def load_cf32(path: str) -> np.ndarray:
    """Lit un fichier float32 entrelacé (sortie GNU Radio / SoapySDR)."""
    raw = np.fromfile(path, dtype=np.float32)
    if raw.size % 2 != 0:
        raw = raw[:-1]
    return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)


def load(path: str) -> np.ndarray:
    """Devine le format depuis l'extension (.cf32/.fc32 -> float, sinon cs8)."""
    lower = path.lower()
    if lower.endswith((".cf32", ".fc32", ".f32")):
        return load_cf32(path)
    return load_cs8(path)
