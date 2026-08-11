"""Design targets for CENTELLA Football's gameplay identity.

These values are a product specification, not a claim that every target is
already implemented in the inherited engine. Keeping the targets executable
makes future tuning measurable instead of subjective.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameplayTargets:
    # Input & responsiveness
    target_input_poll_hz: int = 60
    max_visible_input_latency_ms: int = 85
    quick_pass_intent_ms: int = 110
    quick_shot_intent_ms: int = 140
    direction_change_commit_ms: int = 70
    action_buffer_ms: int = 260

    # Philosophy
    ball_independence: float = 1.0
    defensive_auto_tackle: float = 0.0
    defensive_jockey_assist: float = 0.22
    pass_auto_direction: float = 0.28
    pass_auto_power: float = 0.20

    # Elite players should fail mainly because of pressure/body shape/difficulty,
    # not because the game injects arbitrary incompetence.
    elite_unforced_error_ceiling: float = 0.025
    contextual_error_weight: float = 0.82

    # Match tempo: faster to respond than PES 2021, without FIFA-style pinball.
    tempo_reference: float = 1.08


TARGETS = GameplayTargets()
