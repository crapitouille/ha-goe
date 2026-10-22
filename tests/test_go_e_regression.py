#!/usr/bin/env python3
"""
Tests de regression du package go_e_package.yaml

Evalue les VRAIS templates Jinja du package (pas une copie de la logique) avec
des fonctions HA simulees (states, is_state, state_attr, now, states.sensor.x).

Usage :  python3 tests/test_go_e_regression.py [chemin/go_e_package.yaml]

Contenu :
  1. Structure   : YAML valide, 11 automatisations, ids uniques, options du
                   selecteur de mode inchangees, tous les templates compilent.
  2. Pilotage    : grille de scenarios, comparaison ANCIEN (ligne desired_frc
                   restauree) vs NOUVEAU. Seule difference admise :
                   mode=Maintenant & SoC atteint & plafond OK  ->  frc 1 -> 2.
  3. Maintenant  : invariants (frc=2, psm=2, 6<=amp<=16, amp<=amp_cap, Off et
                   plafond restent prioritaires).
  4. Autres modes: non-regression exhaustive (frc/amp/psm identiques).
  5. Reveil BYD  : table de verite de la nouvelle condition.
"""
import itertools
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import yaml
from jinja2 import Environment

from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "packages" / "go_e_package.yaml"
PATH = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT)

NEW_LINE = "{% elif soc_atteint and mode not in ['Surplus', 'Automatique', 'Maintenant'] %} 1"
OLD_LINE = "{% elif soc_atteint and mode not in ['Surplus', 'Automatique'] %} 1"

MODES = ["Off", "Maintenant", "Surplus", "Surplus natif", "Automatique",
         "Tarification dynamique", "Tarification statique"]

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)

# --------------------------------------------------------------------------
# Chargement YAML (tolere les tags HA type !secret / !include)
# --------------------------------------------------------------------------
class L(yaml.SafeLoader):
    pass


def _any(loader, suffix, node):
    return None


L.add_multi_constructor("!", _any)

with open(PATH, encoding="utf-8") as f:
    RAW = f.read()
DOC = yaml.load(RAW, Loader=L)

failures = []
checks = 0


def check(cond, msg):
    global checks
    checks += 1
    if not cond:
        failures.append(msg)


# --------------------------------------------------------------------------
# Environnement Jinja simule
# --------------------------------------------------------------------------
def convert(s):
    """Rend la valeur comme HA (type natif) a partir de la sortie texte."""
    if not isinstance(s, str):
        return s
    t = s.strip()
    if t in ("True", "true"):
        return True
    if t in ("False", "false"):
        return False
    if t == "None":
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


def make_env(ents, attrs=None, psm_age=600, self_last_triggered=None):
    attrs = attrs or {}
    env = Environment()

    def states(e):
        return ents.get(e, "unknown")

    def is_state(e, v):
        return states(e) == v

    def state_attr(e, a):
        return attrs.get((e, a))

    env.globals["states"] = _States(states, psm_age)
    env.globals["is_state"] = is_state
    env.globals["state_attr"] = state_attr
    env.globals["now"] = lambda: NOW
    env.globals["this"] = SimpleNamespace(
        attributes={"last_triggered": self_last_triggered})
    return env


class _States:
    """states('x') appelable + states.sensor.go_e_psm.last_changed."""

    def __init__(self, fn, psm_age):
        self._fn = fn
        self.sensor = SimpleNamespace(
            go_e_psm=SimpleNamespace(last_changed=NOW - timedelta(seconds=psm_age)))

    def __call__(self, e):
        return self._fn(e)


_CACHE = {}


def compiled(env, src):
    """Compile une seule fois chaque template (les globals sont passes au rendu)."""
    key = src
    if key not in _CACHE:
        _CACHE[key] = env.from_string(src)
    return _CACHE[key]


def eval_variables(variables, env):
    ctx = dict(env.globals)
    for k, v in variables.items():
        if isinstance(v, str) and ("{{" in v or "{%" in v):
            v = convert(compiled(env, v).render(**ctx))
        ctx[k] = v
    return ctx


def get_auto(auto_id):
    for a in DOC["automation"]:
        if a.get("id") == auto_id:
            return a
    raise KeyError(auto_id)


# --------------------------------------------------------------------------
# 1) STRUCTURE
# --------------------------------------------------------------------------
autos = DOC["automation"]
check(len(autos) == 11, f"11 automatisations attendues, {len(autos)} trouvees")
ids = [a.get("id") for a in autos]
check(len(ids) == len(set(ids)), "ids d'automatisations non uniques")
check(all(ids), "automatisation sans id")

opts = DOC["input_select"]["go_e_mode"]["options"]
check(opts == MODES, f"options du selecteur de mode modifiees : {opts}")

# Tous les templates compilent
env0 = make_env({})


def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(o, str) and ("{{" in o or "{%" in o):
        yield path, o


n_tpl = 0
for p, t in walk(DOC):
    n_tpl += 1
    try:
        env0.parse(t)
    except Exception as e:  # noqa: BLE001
        check(False, f"template invalide {p}: {e}")
check(n_tpl > 50, f"trop peu de templates trouves ({n_tpl})")

check(NEW_LINE in RAW, "ligne desired_frc NOUVELLE introuvable dans le package")
check(OLD_LINE not in RAW, "ancienne ligne desired_frc encore presente")

# --------------------------------------------------------------------------
# 2-4) PILOTAGE : ANCIEN vs NOUVEAU
# --------------------------------------------------------------------------
pil = get_auto("go_e_pilotage_charge")
VARS_NEW = pil["variables"]
VARS_OLD = dict(VARS_NEW)
VARS_OLD["desired_frc"] = VARS_NEW["desired_frc"].replace(NEW_LINE, OLD_LINE)
check(VARS_OLD["desired_frc"] != VARS_NEW["desired_frc"],
      "impossible de reconstruire l'ancienne version (remplacement sans effet)")


def scenario_ents(mode, soc, cible, p_grid, p_car, offpeak, psm, amp, frc, manual):
    return {
        "input_select.go_e_mode": mode,
        "input_select.go_e_puissance_max_reseau": "17250",
        "input_select.go_e_calendrier_hc": "binary_sensor.cal_hc",
        "binary_sensor.cal_hc": "on" if offpeak else "off",
        "input_select.go_e_offpeak": "binary_sensor.offpeak",
        "binary_sensor.offpeak": "on" if offpeak else "off",
        "input_select.go_e_batterie_puissance": "Aucun",
        "input_select.go_e_batterie_signe": "Charge positive",
        "input_select.go_e_surplus_priorite": "Voiture",
        "input_number.go_e_courant_manuel": str(manual),
        "input_number.go_e_soc_cible": str(cible),
        "input_number.go_e_surplus_demarrage": "1450",
        "input_number.go_e_surplus_arret": "1150",
        "input_number.go_e_surplus_triphase": "4200",
        "sensor.byd_sealion_7_battery_level": str(soc),
        "sensor.p1_meter_power": str(p_grid),
        "sensor.go_echarger_258457_power_total": str(p_car),
        "sensor.go_e_psm": str(psm),
        "sensor.go_e_amp": str(amp),
        "sensor.go_e_frc": str(frc),
    }


GRID = dict(
    mode=MODES,
    soc=[40, 60, 100],
    cible=[60, 100],
    p_grid=[-6000, -1000, 500, 17000],      # injection forte/faible, soutirage, plafond
    p_car=[0, 10000],
    offpeak=[False, True],
    psm=[1, 2],
    amp=[6, 16],
    frc=[1, 2],
    manual=[6, 10, 16],
)

n_scen = 0
n_diff = 0
for combo in itertools.product(*GRID.values()):
    sc = dict(zip(GRID.keys(), combo))
    ents = scenario_ents(**sc)
    env = make_env(ents, psm_age=600)
    new = eval_variables(VARS_NEW, env)
    old = eval_variables(VARS_OLD, env)
    n_scen += 1

    f_new, f_old = int(new["desired_frc"]), int(old["desired_frc"])
    a_new, a_old = int(new["desired_amp"]), int(old["desired_amp"])
    p_new, p_old = int(new["desired_psm"]), int(old["desired_psm"])
    tag = f"{sc}"

    # amp et psm ne doivent JAMAIS changer
    check(a_new == a_old, f"amp change {a_old}->{a_new} : {tag}")
    check(p_new == p_old, f"psm change {p_old}->{p_new} : {tag}")

    expected_diff = (sc["mode"] == "Maintenant" and bool(new["soc_atteint"])
                     and bool(new["cap_ok"]))
    if f_new != f_old:
        n_diff += 1
        check(expected_diff, f"difference frc inattendue {f_old}->{f_new} : {tag}")
        check((f_old, f_new) == (1, 2), f"transition frc inattendue {f_old}->{f_new} : {tag}")
    else:
        check(not expected_diff,
              f"difference frc attendue mais absente (frc={f_new}) : {tag}")

    # Invariants Maintenant
    if sc["mode"] == "Maintenant":
        if not bool(new["cap_ok"]):
            check(f_new == 1, f"Maintenant + plafond depasse doit couper : {tag}")
        else:
            check(f_new == 2, f"Maintenant + plafond OK doit forcer frc=2 : {tag}")
            check(p_new == 2, f"Maintenant doit etre en triphase : {tag}")
            check(6 <= a_new <= 16, f"amp hors bornes {a_new} : {tag}")
            check(a_new <= max(int(new["amp_cap"]), 6),
                  f"amp {a_new} > amp_cap {new['amp_cap']} : {tag}")
    # Off reste prioritaire
    if sc["mode"] == "Off":
        check(f_new == 1, f"Off doit couper : {tag}")

check(n_diff > 0, "aucune difference observee : la modification n'a pas d'effet")

# --------------------------------------------------------------------------
# 5) REVEIL BYD : condition ajoutee
# --------------------------------------------------------------------------
rev = get_auto("go_e_reveil_vehicule")
conds = [c for c in rev["condition"] if c.get("condition") == "template"]
guard = [c for c in conds
         if "Maintenant" in c["value_template"] and "battery_level" in c["value_template"]]
check(len(guard) == 1, f"condition de garde Maintenant : {len(guard)} trouvee(s), 1 attendue")
if not guard:
    print("ECHEC : condition de garde du reveil introuvable")
    sys.exit(1)
tpl_guard = guard[0]["value_template"]
tpl_modes = [c for c in conds if "Tarification statique" in c["value_template"]][0]["value_template"]
tpl_throttle = [c for c in conds if "last_triggered" in c["value_template"]][0]["value_template"]

n_rev = 0
for mode, soc, cible in itertools.product(MODES, [0, 40, 59, 60, 61, 100], [60, 100]):
    ents = {
        "input_select.go_e_mode": mode,
        "sensor.byd_sealion_7_battery_level": str(soc),
        "input_number.go_e_soc_cible": str(cible),
    }
    env = make_env(ents)
    res = convert(env.from_string(tpl_guard).render())
    expected = not (mode == "Maintenant" and soc >= cible)
    check(res == expected, f"reveil garde {mode} soc={soc} cible={cible}: {res} != {expected}")
    n_rev += 1

# SoC indisponible : float(0) -> 0 >= cible faux -> reveil autorise (comportement inchange)
env = make_env({"input_select.go_e_mode": "Maintenant",
                "sensor.byd_sealion_7_battery_level": "unavailable",
                "input_number.go_e_soc_cible": "100"})
check(convert(env.from_string(tpl_guard).render()) is True,
      "SoC indisponible : le reveil doit rester autorise")

# Liste de modes et throttle inchanges
env = make_env({"input_select.go_e_mode": "Maintenant"})
check(convert(env.from_string(tpl_modes).render()) is True, "liste de modes du reveil")
env = make_env({"input_select.go_e_mode": "Off"})
check(convert(env.from_string(tpl_modes).render()) is False, "mode Off ne doit pas reveiller")
for last, exp in [(None, True), (NOW - timedelta(seconds=1000), True),
                  (NOW - timedelta(seconds=300), False)]:
    env = make_env({}, self_last_triggered=last)
    check(convert(env.from_string(tpl_throttle).render()) is exp, f"throttle last={last}")

# Les 4 conditions d'origine + la nouvelle sont presentes
check(len(rev["condition"]) == 5, f"5 conditions attendues dans le reveil, {len(rev['condition'])}")

# --------------------------------------------------------------------------
print(f"Structure      : {n_tpl} templates compiles, {len(autos)} automatisations")
print(f"Pilotage       : {n_scen} scenarios ANCIEN vs NOUVEAU, "
      f"{n_diff} differences (toutes attendues : Maintenant & SoC atteint & plafond OK)")
print(f"Reveil BYD     : {n_rev} cas de la table de verite")
print(f"Assertions     : {checks}")
if failures:
    print(f"\nECHECS ({len(failures)}):")
    for m in failures[:30]:
        print("  -", m)
    sys.exit(1)
print("\nTOUS LES TESTS PASSENT")
