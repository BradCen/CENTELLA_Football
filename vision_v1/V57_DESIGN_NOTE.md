# V57 design note

The V57 assignment primitive is deliberately small and causal. It uses only predicted world-space motion and detection confidence at inference time. It does not know official Alfheim player IDs and it does not read the truth file.

This file is a validated primitive, not a claimed benchmark win. The existing V56 OOS benchmark remains the authoritative end-to-end anonymous result until this primitive is integrated and measured end-to-end.
