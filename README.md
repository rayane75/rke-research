# RKE Research Lab — reverse engineering de télécommandes (RKE) au HackRF

Toolkit et méthodologie pour apprendre la **recherche de vulnérabilités** sur les
systèmes RKE (Remote Keyless Entry) modernes — KeeLoq, rolling codes, AES — avec
un HackRF, **sur ton propre matériel**.

Chaîne complète, validée de bout en bout sur du vrai signal : **capture → vérif →
démodulation → détection de bursts → décodage → analyse différentielle des champs
→ hypothèse de schéma**. Un Flipper Zero sert d'émetteur de test maîtrisé pour
s'entraîner avant le vrai fob.

## Règle non négociable : périmètre

Ce projet sert **uniquement** sur :
- un **fob de rechange** que tu as acheté (5–10 € en générique) ;
- **ta** propre voiture / ton propre véhicule ;
- du matériel sur lequel tu as une **autorisation écrite** (scope de pentest).

Pas sur les systèmes d'autrui. Ce n'est pas une formalité : c'est ce qui sépare
un chercheur (CV, publications, bug bounty) d'un voleur (casier). Toute trouvaille
passe par une **divulgation coordonnée** (voir plus bas).

## Installation

Le toolkit ne dépend que de **numpy** (runtime) et **pytest** (tests).

```bash
cd rke-research
# Debian/Ubuntu (PEP 668) : soit un venv, soit les paquets système.
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q          # 9 tests : démod, analyse différentielle, AES-128 (FIPS-197)
```

Outils système : `hackrf` (hackrf_transfer, hackrf_sweep). Optionnel : `gqrx`
(waterfall), **cd .(URH)** (inspection visuelle).

## Démarrage rapide — boucle de test au Flipper Zero

Avant d'attaquer un vrai fob, valide toute ta chaîne sur un signal **connu** que
tu émets toi-même. C'est l'étape que tout le monde saute, et qui fait qu'on ne
sait jamais si « le signal est bizarre » ou « mon décodeur est faux ».

```bash
# 1. Génère une trame de test (charge utile connue), copie le .sub sur le Flipper
python3 scripts/make_flipper_sub.py A5C3 -r 40 -o test_frame.sub

# 2. Capture pendant que le Flipper émet (maintiens OK), puis vérifie + décode
hackrf_transfer -r diff.cs8 -f 434120000 -s 2000000 -n 60000000 -l 16 -g 20
./.venv/bin/python scripts/check_capture.py diff.cs8     # ✅/❌ + saturation
./.venv/bin/python scripts/analyze_capture.py diff.cs8   # doit décoder A5C3
```

## La recette de capture qui marche (durement acquise)

| Réglage | Pourquoi |
|--------|----------|
| `-f 434120000` (≈ +200 kHz) | décale le signal hors du **pic DC** central du HackRF (zéro-IF) |
| Gain **modéré** `-l 16 -g 20` | un émetteur proche **sature** l'ADC à fort gain. `check_capture` affiche le % de saturation — vise < 2 %. |
| Antenne adaptée | quart d'onde 433 MHz = **17,3 cm**. En champ proche ça pardonne, mais une antenne accordée aide. |
| Fenêtre longue + maintenir OK | le Flipper n'émet que **pendant** que OK est tenu. Capture 20–30 s pour garantir le chevauchement. |

`check_capture.py` est ton garde-fou : il te dit **instantanément** si la trame
est présente et si l'ADC sature, avant même d'analyser.

## Méthodologie sur un vrai fob

### 1. Trouver la fréquence
Souvent sur l'étiquette FCC (315 MHz Amérique du Nord, 433.92 / 868.35 MHz
Europe). Confirme :
```bash
hackrf_sweep -f 300:900 -w 100000 -l 16 -g 20    # repère le pic quand tu appuies
```

### 2. Capturer plusieurs appuis (le différentiel a besoin de répétitions)
Plus tu appuies, plus tu révèles la vraie taille du champ variable (un compteur
ne fait basculer ses bits hauts qu'après beaucoup d'incréments).

### 3. Analyse différentielle des champs (le cœur)
```bash
# plusieurs fichiers (un appui par fichier) :
./.venv/bin/python scripts/analyze_capture.py capture1.cs8 capture2.cs8 ...
# ou plusieurs appuis dans UNE capture :
./.venv/bin/python scripts/analyze_capture.py --diff capture.cs8
```
Lecture de la carte FIXE/VARIABLE + entropie :
- **Champs fixes** (entropie 0) = numéro de série, code bouton, en-tête.
- **Zone variable** = ta cible. **Deux nombres suffisent au diagnostic :**

| Taille zone variable | Entropie | Schéma probable | Sécurité |
|---|---|---|---|
| ~1 octet, incrémental | basse | **compteur en clair** | nulle (prédictible) |
| ~32 bits, aléatoire | haute | **KeeLoq** | moyenne |
| ~128 bits, aléatoire | haute | **AES-128** | forte |

### 4. Chasse aux fautes d'implémentation (là où vivent les bugs)
Le chiffrement est rarement cassé ; ce sont les **implémentations** qui pèchent :
- Le bloc chiffré **change-t-il vraiment à chaque appui** ? Statique → rejeu trivial.
- Le compteur s'incrémente-t-il proprement, ou y a-t-il un **saut prévisible** ?
- Un **nonce/IV réutilisé** (fuite en CTR/CBC) ?
- **Fenêtre de resync** énorme → rejeux différés ?
- **Clé dérivée du seul numéro de série** → prévisible si la dérivation fuit ?

### 5. Documenter et divulguer
1. Notes reproductibles (captures, paramètres, modèle, n° FCC).
2. Identifie le fournisseur (encodeur Microchip/NXP, équipementier, constructeur).
3. CERT national / contact sécurité, fenêtre de divulgation (~90 j).
4. Demande un **CVE** — c'est ça qui construit ta réputation.

## S'entraîner : générateur de trames RKE structurées

`make_rke_frames.py` fabrique des trames réalistes `[série fixe][bloc variable]
[bouton fixe]` pour t'entraîner à l'analyse différentielle sur du Flipper
maîtrisé, dans trois modes :

```bash
python3 scripts/make_rke_frames.py --mode counter -o rke_counter.sub  # 3 bits → faille
python3 scripts/make_rke_frames.py --mode rolling -o rke_frames.sub   # 32 bits → KeeLoq
python3 scripts/make_rke_frames.py --mode aes     -o aes_frames.sub   # 128 bits → AES-128
```

Émets-en un, capture, puis `analyze_capture.py --diff` : la carte des champs
reproduit le schéma injecté. Voir aussi `scripts/aes_demo.py` (effet d'avalanche :
pourquoi `AES(compteur)` est imprévisible).

## Architecture du toolkit

| Module / script | Rôle |
|---|---|
| `rke/iq.py` | Chargement IQ HackRF (cs8) et GNU Radio (cf32) |
| `rke/demod.py` | OOK/ASK (seuil sur plancher de bruit), 2-FSK, détection de bursts, estimation de symbole robuste au bruit |
| `rke/framing.py` | Débruitage des paliers, décodage PWM / Manchester, détection de préambule, décodage par burst |
| `rke/analyze.py` | Analyse différentielle, entropie par champ, hypothèse de schéma |
| `rke/aes128.py` | AES-128 en Python pur, vérifié FIPS-197 (le rolling code moderne) |
| `scripts/check_capture.py` | Vérif instantanée : trame présente ? ADC saturé ? |
| `scripts/analyze_capture.py` | Pipeline IQ → carte des champs (`--diff` pour une seule capture) |
| `scripts/make_flipper_sub.py` | Génère un `.sub` Flipper (trame de test, `--beacon`) |
| `scripts/make_rke_frames.py` | Génère des trames structurées (counter / rolling / aes) |
| `scripts/aes_demo.py` | Démo de l'effet d'avalanche AES |

## La littérature à disséquer (ta vraie formation)

- Bogdanov, *A Practical Attack on KeeLoq* — pourquoi le DPA, pas le rejeu, casse les clés.
- Garcia et al., *Dismantling Megamos Crypto* — modèle de recherche + volet juridique/disclosure.
- Verdult, Garcia, *Gone in 360 Seconds (Hitag2)* — méthodo de reverse complète.
- NCC Group (2022), *BLE relay attack on Tesla* — la faille au niveau lien, sous la crypto.
- Rolling-PWN (2022) — désync de compteur sur véhicules réels (faute d'implémentation).

## Prochains blocs

1. **Vrai fob** : appliquer toute la chaîne sur un fob acheté / le tien.
2. **Side-channel** : ChipWhisperer + DPA pour récupérer une clé sur banc — là où
   l'attaque se déplace quand l'AES tue la voie radio.
3. **Firmware** : extraire le code de l'encodeur acheté (debug, glitching).

---

> Travail de recherche sur matériel possédé, à des fins d'apprentissage et de
> divulgation coordonnée.
