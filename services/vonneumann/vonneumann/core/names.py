"""
Memorable probe name generator.

Names follow the pattern: {Adjective}-{Noun}-{Gen}{Index}
e.g. "Swift-Falcon-G2", "Silent-Viper-G0", "Neon-Phantom-G1"
"""

import random

_ADJECTIVES = [
    "Swift", "Silent", "Neon", "Crimson", "Shadow", "Iron", "Crystal",
    "Phantom", "Cyber", "Frost", "Dark", "Solar", "Binary", "Quantum",
    "Rogue", "Omega", "Void", "Chrome", "Nexus", "Pulse", "Ghost",
    "Nova", "Stellar", "Hyper", "Turbo", "Arc", "Flux", "Bolt",
    "Apex", "Zen", "Drift", "Echo", "Blaze", "Onyx", "Cobalt",
    "Prism", "Vector", "Signal", "Matrix", "Surge", "Titan", "Vortex",
]

_NOUNS = [
    "Falcon", "Viper", "Wolf", "Hawk", "Panther", "Cobra", "Lynx",
    "Raven", "Shark", "Eagle", "Phoenix", "Dragon", "Mantis", "Hydra",
    "Sphinx", "Griffin", "Chimera", "Kraken", "Raptor", "Specter",
    "Cipher", "Axiom", "Vertex", "Photon", "Quasar", "Nebula",
    "Proton", "Helix", "Prism", "Strider", "Sentinel", "Oracle",
    "Tempest", "Catalyst", "Reactor", "Cortex", "Daemon", "Wraith",
]

_used: set[str] = set()


def generate_probe_name(generation: int) -> str:
    """Generate a unique memorable name like 'Swift-Falcon-G2'."""
    for _ in range(100):  # prevent infinite loop
        adj = random.choice(_ADJECTIVES)
        noun = random.choice(_NOUNS)
        name = f"{adj}-{noun}-G{generation}"
        if name not in _used:
            _used.add(name)
            return name
    # Fallback with random suffix
    suffix = random.randint(100, 999)
    name = f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}-G{generation}-{suffix}"
    _used.add(name)
    return name
