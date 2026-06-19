#!/usr/bin/env bash
# Capture d'appuis de TON PROPRE fob avec le HackRF.
#
# Méthode : repère d'abord la fréquence exacte (315 / 433.92 / 868.35 MHz selon
# la région et le modèle) avec un waterfall (gqrx ou `hackrf_sweep`), puis
# enregistre plusieurs appuis successifs du MÊME bouton dans des fichiers séparés.
# L'analyse différentielle a besoin d'au moins ~8 captures du même bouton.
#
# Usage : ./capture.sh <freq_hz> <prefix> <nb_captures>
# Exemple : ./capture.sh 433920000 fob_lock 12
set -euo pipefail

FREQ="${1:?freq en Hz, ex 433920000}"
PREFIX="${2:?prefixe de fichier, ex fob_lock}"
COUNT="${3:-10}"
SAMPLE_RATE="${SAMPLE_RATE:-2000000}"   # 2 Msps : large pour de l'OOK étroit
LNA_GAIN="${LNA_GAIN:-32}"
VGA_GAIN="${VGA_GAIN:-30}"
SECONDS_PER="${SECONDS_PER:-1}"
OUT_DIR="${OUT_DIR:-captures}"

mkdir -p "$OUT_DIR"
NUM_SAMPLES=$(( SAMPLE_RATE * SECONDS_PER ))

echo "Fréquence : $FREQ Hz | $SAMPLE_RATE sps | $COUNT captures de ${SECONDS_PER}s"
echo "Appuie une fois sur le bouton à chaque invite."
for i in $(seq 1 "$COUNT"); do
  OUT="$OUT_DIR/${PREFIX}_$(printf '%02d' "$i").cs8"
  read -r -p "Capture $i/$COUNT — prêt ? [Entrée] "
  hackrf_transfer -r "$OUT" -f "$FREQ" -s "$SAMPLE_RATE" \
    -n "$NUM_SAMPLES" -l "$LNA_GAIN" -g "$VGA_GAIN" >/dev/null
  echo "  -> $OUT"
done
echo "Terminé. Analyse : python scripts/analyze_capture.py $OUT_DIR/${PREFIX}_*.cs8"
