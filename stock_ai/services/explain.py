"""Phase 8: plain-language explanation built only from existing backend
signals -- never invents an observation the data doesn't support."""
from __future__ import annotations


def build_explanation(structure: dict | None, signal: dict | None) -> dict:
    positives: list[str] = []
    risks: list[str] = []

    if structure:
        positives.extend(structure.get("important_observations", []))
        if structure.get("market_structure") == "BULLISH":
            positives.append("Overall price structure is trending bullish (higher highs and higher lows).")
        elif structure.get("market_structure") == "BEARISH":
            risks.append("Overall price structure is trending bearish (lower highs and lower lows).")

        distance_to_resistance = structure.get("distance_to_resistance")
        if distance_to_resistance is not None and distance_to_resistance < 0.03:
            risks.append("Resistance is nearby.")

        if structure.get("breakout_status") == "BREAKDOWN":
            risks.append("Price recently broke below a support level.")
        elif structure.get("breakout_status") == "FAILED_BREAKOUT":
            risks.append("A recent breakout attempt failed.")

    if signal:
        classification = signal.get("classification", {})
        calibrated_probability = classification.get("calibrated_probability")
        if calibrated_probability is not None and calibrated_probability < 0.60:
            risks.append("Current model confidence is limited.")
        if classification.get("signal_status") == "NO_STRONG_SIGNAL":
            risks.append("The current setup does not meet the model's validated confidence requirements.")

    return {"positives": positives[:6], "risks": risks[:6]}
