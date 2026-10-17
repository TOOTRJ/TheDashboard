"""Pure scheduling arithmetic for one synthetic native-restoration fixture.

No clock is read here, and no provider, model or native admission rule changes.
The caller observes the genuine DB clock once before and once after one wait,
before creating a run/lease or capturing any original request.
"""

PERIOD_US = 900_000_000
FIRST_PHASE_US = 6_000_000
LAST_PHASE_US = 850_000_000
MAX_WAIT_US = 56_000_000
SETUP_TIMEOUT_SECONDS = 60
MAX_CLOCK_US = 10**16


def _clock(value):
    if type(value) is not int or not 0 <= value <= MAX_CLOCK_US:
        raise ValueError('Fixture clock must be bounded integer microseconds')
    return value


def planned_wait_us(observed_us):
    phase = _clock(observed_us) % PERIOD_US
    if phase < FIRST_PHASE_US:
        delay = FIRST_PHASE_US - phase
    elif phase <= LAST_PHASE_US:
        delay = 0
    else:
        delay = PERIOD_US + FIRST_PHASE_US - phase
    if not 0 <= delay <= MAX_WAIT_US:
        raise ValueError('Fixture setup wait exceeds its bound')
    return delay


def validate_observed_slot(before_us, after_us):
    """Refuse a changed/overshot clock; never calculate another wait."""
    before_us, after_us = _clock(before_us), _clock(after_us)
    delay = planned_wait_us(before_us)
    if not before_us + delay <= after_us <= before_us + SETUP_TIMEOUT_SECONDS * 1_000_000:
        raise ValueError('Fixture setup clock did not complete its bounded original wait')
    phase = after_us % PERIOD_US
    if not FIRST_PHASE_US <= phase <= LAST_PHASE_US:
        raise ValueError('Fixture setup clock overshot its reviewed history window')
    return phase
