# ha-go-e-charger

[![Tests](https://github.com/crapitouille/ha-go-e-charger/actions/workflows/tests.yml/badge.svg)](https://github.com/crapitouille/ha-go-e-charger/actions/workflows/tests.yml)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

Package Home Assistant pour piloter une borne **go-e Charger Gemini** (11 kW) **sans go-e Controller** :
la fonction « surplus PV natif » de la borne est alimentée par Home Assistant (clé locale `ids`),
et d'autres modes (maintenant, automatique, tarifs) s'ajoutent par-dessus.

> ⚠️ Ce dépôt est un **package YAML** (`packages/`), pas une intégration HACS ni un blueprint :
> Home Assistant n'offre pas de bouton d'import en un clic pour ce type de contenu.
> Voir [Installation](#installation) (une seule commande) et les raccourcis ci-dessous.

## Modes

| Mode | Comportement |
|---|---|
| **Off** | Charge coupée. |
| **Maintenant** | Charge forcée en triphasé au courant choisi (limité par le plafond réseau). **La cible SoC est ignorée.** |
| **Surplus** | Régulation par Home Assistant (seuils de démarrage/arrêt, mono/triphasé avec hystérésis). |
| **Surplus natif** | La borne régule elle-même le surplus PV ; HA lui envoie `pGrid` toutes les 5 s. |
| **Automatique** | Tarif bas depuis le réseau jusqu'à la cible SoC, puis surplus natif au-delà. |
| **Tarification dynamique** | Charge pendant les heures creuses d'un calendrier choisi, jusqu'à la cible SoC. |
| **Tarification statique** | Charge quand un capteur « off-peak » choisi est actif, jusqu'à la cible SoC. |

Fonctions transverses : plafond de soutirage réseau (protection disjoncteur), blocage de la décharge de la
batterie maison, réveil de la BYD endormie (bouton *Force poll*), rafraîchissement ciblé du SoC,
télémétrie solaire/réseau (kWh par semaine).

## Prérequis

- Home Assistant avec **MQTT** et l'intégration [syssi/homeassistant-goecharger-mqtt](https://github.com/syssi/homeassistant-goecharger-mqtt)
  (ou équivalent publiant les topics `go-eCharger/<série>/…`).
- API HTTP locale de la borne activée (clé `ids`, firmware ≥ 59.x ; testé en 60.6).
- Entités attendues (à adapter, voir plus bas) : un capteur de puissance réseau P1
  (`sensor.p1_meter_power`, + = soutirage), le SoC de la voiture
  (`sensor.byd_sealion_7_battery_level`), l'intégration BYD (`button.byd_sealion_7_force_poll`,
  `switch.byd_sealion_7_disable_polling`).

## Raccourcis vers votre Home Assistant

Ces boutons passent par [my.home-assistant.io](https://my.home-assistant.io) : ils fonctionnent une fois votre
instance enregistrée sur ce service (une fois pour toutes).

| Étape | Bouton |
|---|---|
| Ajouter l'intégration MQTT (si absente) | [![Ouvrir MQTT](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mqtt) |
| Vérifier la configuration, recharger le YAML | [![Contrôles du serveur](https://my.home-assistant.io/badges/server_controls.svg)](https://my.home-assistant.io/redirect/server_controls/) |
| Ouvrir vos tableaux de bord (pour ajouter le dashboard) | [![Tableaux de bord](https://my.home-assistant.io/badges/lovelace_dashboards.svg)](https://my.home-assistant.io/redirect/lovelace_dashboards/) |
| Contrôler les entités créées (`go_e_*`) | [![États](https://my.home-assistant.io/badges/developer_states.svg)](https://my.home-assistant.io/redirect/developer_states/) |

## Installation

1. Dans `configuration.yaml` (une seule fois) :
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
2. Télécharger le package dans `/config/packages/` — depuis le add-on **Terminal & SSH** (ou *Advanced SSH*) :
   ```bash
   mkdir -p /config/packages
   wget -O /config/packages/go_e_package.yaml \
     https://raw.githubusercontent.com/crapitouille/ha-go-e-charger/main/packages/go_e_package.yaml
   ```
   (Le dépôt doit être public pour que ce lien fonctionne.)
3. **Adapter** les valeurs propres à votre installation (voir ci-dessous).
4. *Outils de développement → YAML → Vérifier la configuration*, puis redémarrer (ou recharger le YAML).
5. Dans l'interface, choisir le mode, les sélecteurs (calendrier, capteur off-peak, batterie…) et la cible SoC.

### À adapter dans le fichier

| Valeur par défaut | À remplacer par | Occurrences |
|---|---|---|
| `258457` (série de la borne) | le numéro de série de votre borne (topics MQTT et entités `go_echarger_<série>_…`) | ~27 |
| `192.168.0.198` | l'IP fixe de votre borne (réservation DHCP recommandée) | 2 |
| `sensor.p1_meter_power` | votre capteur de puissance réseau | 7 |
| `sensor.byd_sealion_7_*`, `button.byd_sealion_7_force_poll`, `switch.byd_sealion_7_disable_polling` | vos entités voiture (ou retirer les automatisations SoC/réveil) | – |

Un rechercher/remplacer global suffit pour la série et l'IP.

### Dashboard « Go-e Mobilité » (optionnel)

`dashboards/go_e_mobilite.yaml` reprend deux vues :
- **Mobilité** : mode, statut, phases, SoC voiture, jauges borne / PV / surplus, historiques.
- **Configurations** : tous les réglages (courant manuel, seuils de surplus, plafond réseau, calendrier,
  capteur off-peak, batterie maison, cible SoC).

Installation (après le package, pour que les entités `go_e_*` existent) :
1. Bouton *Tableaux de bord* ci-dessus → **Ajouter un tableau de bord** → *Nouveau tableau de bord depuis zéro*.
2. L'ouvrir, puis menu ⋮ → **Modifier** → menu ⋮ → **Éditeur de configuration brut**.
3. Remplacer tout le contenu par celui de `dashboards/go_e_mobilite.yaml`, puis enregistrer.

Adapter les entités extérieures au package (`sensor.go_echarger_258457_*`, `sensor.solaredge_i126_dc_power`,
`sensor.p1_meter_power`, `sensor.byd_sealion_7_battery_level`). Les images de fond et restrictions
d'utilisateurs de l'instance d'origine ont été retirées.

## Tests de régression

Les tests évaluent les **vrais templates Jinja** du package (et vérifient que le dashboard ne référence que des entités définies) avec des fonctions Home Assistant simulées
et comparent l'ancien et le nouveau comportement sur plusieurs milliers de scénarios.

```bash
pip install -r requirements-dev.txt
python tests/test_go_e_regression.py
```

Ils s'exécutent aussi automatiquement sur GitHub à chaque *push* / *pull request*
(`.github/workflows/tests.yml`). Pour une évolution du comportement, mettre à jour la ligne « ancienne
version » du test pour que seules les différences voulues soient autorisées.

> Les tests valident la logique des templates, pas le pilotage réel de la borne : après toute modification,
> testez sur la borne.

## Licence

MIT — voir [LICENSE](LICENSE). Ce projet n'est pas affilié à go-e GmbH.
