"""Stipulated parameters for the PAZUZU Virtual Mechanics subsystem.

HONESTY BOUNDARY — read before use:
  HBAR_THAUM, E_REF, and LAMBDA_0 are STIPULATED parameters. They are internal
  simulation constants chosen for the thaumic DSL's resource model. They are
  NOT measured physical constants and must never be presented as physics.
  "Mana", "wards", "leylines", and "scrying" are domain labels for
  computational constructs (reference tables, permission predicates, graphs,
  observation operators), not claims about the physical world.
"""

# Stipulated "Thaumic Planck constant" (J·s). NOT a physical constant.
HBAR_THAUM = 1.05e-7

# Stipulated reference energy per VM operation (J/op) used by the
# "Mana-FLOP" resource-accounting metaphor. NOT a market price.
E_REF = 1e-12

# Stipulated "Netherworld barrier tension" (J/m^4). NOT a physical constant.
LAMBDA_0 = 1e-3

# Mana cost schedule per op, in abstract mana units.
# 1 mana unit is *defined* as E_REF joules inside this simulation only.
MANA_COSTS = {
    "bind": 1.0,
    "scry": 2.0,
    "route": 3.0,
    "seal": 5.0,
    "banish": 2.0,
    # "ward" and "attune" take their cost from the spell source (static literal).
}
