"""Toolkit de reverse engineering RKE pour HackRF.

Chaîne : iq (chargement) -> demod (OOK/FSK) -> framing (codage de ligne)
-> analyze (analyse différentielle des champs).

Usage prévu : UNIQUEMENT sur ton propre fob / du matériel que tu possèdes,
dans une démarche de recherche et de divulgation coordonnée.
"""

# Imports paresseux : on n'importe pas les sous-modules ici pour qu'un simple
# `from rke import aes128` (stdlib pur) ne tire pas numpy via demod/framing.
# `from rke import demod` continue de fonctionner (import du sous-module à la demande).
__all__ = ["aes128", "analyze", "demod", "framing", "iq"]
