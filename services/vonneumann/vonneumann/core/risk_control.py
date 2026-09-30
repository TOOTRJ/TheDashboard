"""Safe, expected refusals of an explicitly requested risk recovery."""

RISK_RECOVERY_MESSAGES = {
    "risk_not_halted": "This colony is not halted by its risk control.",
    "risk_trip_changed": "The risk halt has changed. Refresh its status before requesting recovery.",
    "risk_loss_unrecovered": "Account loss still reaches the original limit. Recovery is not permitted.",
    "risk_quotes_unavailable": "Fresh, complete market quotes are required before recovery.",
    "risk_history_unavailable": "Current completed candle history is required before recovery.",
    "risk_no_candidates": "No active candidates remain. This colony cannot recover.",
}


class RiskRecoveryError(RuntimeError):
    """A refused recovery preserves the existing halt and ongoing risk checks."""

    def __init__(self, code: str):
        if code not in RISK_RECOVERY_MESSAGES:
            raise ValueError("Unsupported risk recovery reason")
        self.code = code
        super().__init__(RISK_RECOVERY_MESSAGES[code])
