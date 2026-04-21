"""Constants and configuration for avatar generation."""

from __future__ import annotations

import math

# Loop type weights for selection
PREFERRED_LOOP_TYPES = ["epitrochoid", "lissajous", "rose"]

# Loop color palette (light colors that contrast with dark gradients)
LOOP_COLORS = [
    (255, 255, 240),  # Warm white
    (255, 240, 200),  # Cream
    (240, 255, 255),  # Cool white
    (255, 220, 180),  # Peach
    (200, 220, 255),  # Light blue
    (255, 200, 220),  # Light pink
]

# Line width range (percentage of image width)
LINE_WIDTH_MIN_PCT = 0.05
LINE_WIDTH_MAX_PCT = 0.10

# Size ranges
SIZE_MIN_ZOOMED = 1.2
SIZE_MAX_ZOOMED = 2.0
SIZE_MIN_NORMAL = 0.5
SIZE_MAX_NORMAL = 0.8

# Speed range
SPEED_MIN = 0.5
SPEED_MAX = 1.5

# Offset range (when zoom enabled)
OFFSET_MIN = -0.5
OFFSET_MAX = 0.5

# Epitrochoid parameter ranges
EPITROCHOID_R_MAJOR_MIN = 0.25
EPITROCHOID_R_MAJOR_MAX = 0.45
EPITROCHOID_R_MINOR_MIN = 0.08
EPITROCHOID_R_MINOR_MAX = 0.18

# Lissajous parameter ranges
LISSAJOUS_FREQ_MIN = 2.0
LISSAJOUS_FREQ_MAX = 6.0
LISSAJOUS_PHASE_MIN = 0.0
LISSAJOUS_PHASE_MAX = math.pi

# Rose parameter ranges
ROSE_PETALS_MIN = 3
ROSE_PETALS_MAX = 9

# Color palette generation
PALETTE_VARIATION = 10  # ±10 RGB units for organic variation

# Base color pairs for each palette theme: (start_color, peak_color)
BASE_COLOR_PAIRS = [
    # Aurora Borealis (teal → sky blue)
    ((35, 100, 100), (65, 118, 175)),
    # Northern Lights (purple → lavender)
    ((115, 65, 175), (108, 78, 205)),
    # Ethereal Rainbow (pink → sky blue)
    ((170, 95, 165), (125, 148, 220)),
    # Cosmic Teal (cyan → blue-purple)
    ((75, 170, 205), (95, 125, 215)),
    # Mystic Violet (deep purple → lavender)
    ((100, 55, 150), (138, 88, 200)),
    # Ocean Aurora (deep blue → cyan)
    ((55, 120, 175), (70, 172, 200)),
]
