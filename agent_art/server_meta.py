"""UI/mapping ranges per trait (kept out of server.py so core code can import them)."""

# trait -> (min, max, step) for the UI sliders
TRAIT_RANGES = {
    "thickness": (0.05, 2, 0.05), "like_x": (-1, 1, 0.05), "like_y": (-1, 1, 0.05),
    "like_total_angle": (-1, 1, 0.05), "init_angle": (0, 360, 5), "turn_propensity": (0, 1, 0.01),
    "jitter": (0, 1, 0.01), "step": (0.2, 8, 0.1), "momentum_decay": (0.95, 1, 0.001),
    "min_step": (0.05, 2, 0.05), "vision": (2, 100, 1), "comfort_distance": (0, 40, 0.5),
    "affinity_same": (-1, 1, 0.05), "affinity_other": (-1, 1, 0.05), "social_strength": (0, 1, 0.01),
    "goal_size": (3, 60, 1), "goal_strength": (0, 1, 0.01),
}
