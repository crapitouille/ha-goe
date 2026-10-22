# Changelog

## [Non publié]
- Dashboard « Go-e Mobilité » (vues Mobilité et Configurations) dans `dashboards/`.
- Mode **Maintenant** : la coupure sur la cible SoC est ignorée (la charge
  continue jusqu'à l'arrêt de la voiture). « Off » et le plafond de puissance
  réseau restent prioritaires.
- Réveil BYD : pas de « Force poll » en mode Maintenant lorsque le SoC a
  atteint la cible (un `car=4` est alors l'arrêt normal de la voiture).
- Tests de régression automatisés (16 128 scénarios ancien/nouveau).

## [1.0.0]
- Modes Off / Maintenant / Surplus / Surplus natif / Automatique /
  Tarification dynamique / Tarification statique.
- Simulation du go-e Controller via la clé locale `ids` (surplus PV natif).
- Réveil de la BYD endormie via « Force poll », télémétrie solaire/réseau.
