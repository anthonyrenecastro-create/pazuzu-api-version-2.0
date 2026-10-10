"""S06 Thermodynamic Brake — adaptive sampling controller.

Contract
--------
PD controller over a *measured token-diversity proxy*: the type-token
ratio (TTR = unique tokens / total tokens) over a sliding window of the
most recent tokens (default 200, from ``ctx.parameters["sample_text"]``
or the prompt). TTR is a lexical-diversity PROXY — it is NOT true
Shannon entropy (audit #70); no entropy is estimated and no
thermodynamic dissipation is claimed. The name is metaphorical; the
math is a control loop.

Control law (per run):
    e  = ttr_target − ttr_measured
    de = e − e_prev                      (e_prev from control_history)
    u  = Kp·e + Kd·de
    u  = clip(u, −1, 1)                  # anti-windup clip; note below

Hysteresis bands: temperature/top_p are only updated when the proposed
change exceeds ``hysteresis`` (default 0.05), preventing chatter.
Oscillation detection: if the control signal changed sign more than
``oscillation_flips`` times (default 3) within the recent history, the
output is damped (halved) and flagged.

Anti-windup note: a pure PD controller has no integrator, so there is
no integrator state to wind up. The clip on u is the safeguard that
*plays the anti-windup role* if an integral term is added later; the
limitation is that clipping alone cannot correct a saturated integral
term — documented here so a future PI/PID extension adds proper
conditional integration.

Output: recommended ``{temperature, top_p}`` plus telemetry
(ttr_measured, error, control_signal, oscillation flag, whether the
hysteresis gate fired).

Assumptions
-----------
- Parameters: ``sample_text``, ``ttr_target`` (0.55), ``kp`` (0.8),
  ``kd`` (0.4), ``hysteresis`` (0.05), ``window`` (200),
  ``control_history`` (list of past u), ``prev_error``,
  ``base_temperature`` (0.7), ``base_top_p`` (0.95),
  ``oscillation_flips`` (3).

Known limitations
-----------------
- TTR is a crude proxy: it conflates vocabulary richness with
  randomness and is length-sensitive.
- Single-step PD per station run; no continuous-time guarantees.
- Mapping from u to temperature/top_p is a linear heuristic.
"""
from __future__ import annotations

import time

from pazuzu_contracts import (
    ExecutionContext,
    Station,
    StationManifest,
    StationOutput,
    StationStatus,
)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class S06ThermodynamicBrake(Station):
    """PD adaptive sampling controller on a TTR diversity proxy."""

    manifest = StationManifest(
        id="s06",
        name="Thermodynamic Brake",
        version="2.0.0",
        critical_path=True,
        description="PD controller on type-token-ratio proxy with hysteresis "
                    "bands, oscillation detection, and anti-windup clipping.",
    )

    async def run(self, ctx: ExecutionContext) -> StationOutput:
        t0 = time.perf_counter()
        params = ctx.parameters or {}
        text = params.get("sample_text", ctx.prompt or "")
        window = max(10, int(params.get("window", 200)))
        target = float(params.get("ttr_target", 0.55))
        kp = float(params.get("kp", 0.8))
        kd = float(params.get("kd", 0.4))
        hysteresis = float(params.get("hysteresis", 0.05))
        base_temp = float(params.get("base_temperature", 0.7))
        base_top_p = float(params.get("base_top_p", 0.95))
        max_flips = int(params.get("oscillation_flips", 3))

        tokens = text.split()[-window:]
        ttr = (len(set(tokens)) / len(tokens)) if tokens else 0.0

        history: list[float] = list(params.get("control_history", []))
        e_prev = float(params.get("prev_error", history[-1] if history else 0.0))
        e = target - ttr
        de = e - e_prev
        u = kp * e + kd * de
        # Anti-windup clip. Limitation (documented): this PD loop has no
        # integrator, so there is nothing to wind up; the clip bounds the
        # control effort and stands in for anti-windup if an integral term
        # is ever added (which would then also need conditional integration).
        u = _clip(u, -1.0, 1.0)

        # Oscillation detection: count sign flips of u over recent history.
        recent = (history + [u])[-8:]
        flips = sum(1 for a, b in zip(recent, recent[1:])
                    if a != 0 and b != 0 and (a > 0) != (b > 0))
        oscillating = flips > max_flips
        if oscillating:
            u = u * 0.5  # damp on detected oscillation

        prop_temp = _clip(base_temp - 0.5 * u, 0.1, 1.5)
        prop_top_p = _clip(base_top_p - 0.2 * u, 0.5, 1.0)

        # Hysteresis gate: only move if the change exceeds the band.
        last_temp = float(params.get("last_temperature", base_temp))
        last_top_p = float(params.get("last_top_p", base_top_p))
        temp_moved = abs(prop_temp - last_temp) > hysteresis
        top_p_moved = abs(prop_top_p - last_top_p) > hysteresis
        temperature = prop_temp if temp_moved else last_temp
        top_p = prop_top_p if top_p_moved else last_top_p

        data = {
            "recommended": {
                "temperature": round(temperature, 4),
                "top_p": round(top_p, 4),
            },
            "telemetry": {
                "ttr_measured": round(ttr, 4),
                "ttr_target": target,
                "error": round(e, 4),
                "error_delta": round(de, 4),
                "control_signal": round(u, 4),
                "oscillating": oscillating,
                "sign_flips": flips,
                "hysteresis_gate": {
                    "temperature_updated": temp_moved,
                    "top_p_updated": top_p_moved,
                    "band": hysteresis,
                },
                "gains": {"kp": kp, "kd": kd},
            },
            "proxy_disclaimer": (
                "Type-token ratio is a lexical-diversity PROXY, not true "
                "Shannon entropy (audit #70). No thermodynamic quantity is "
                "measured or dissipated; 'brake' is metaphorical."
            ),
        }
        warnings = []
        if oscillating:
            warnings.append("control-signal oscillation detected; output damped")
        if not tokens:
            warnings.append("empty sample window; TTR undefined, treated as 0")
        return self.output(
            ctx, data, warnings=warnings,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
