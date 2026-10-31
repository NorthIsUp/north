"""Deterministic avatar configuration and image rendering.

>>> config = AvatarConfig(width=8, height=8, fps=1, duration=0.1, loop_configs=[])
>>> image = Avatar(config).render_frame(0)
>>> image.size
(8, 8)
"""

from we_love.avatars.avatar import Avatar, AvatarConfig
from we_love.avatars.generator import AvatarGenerator, AvatarGeneratorConfig, avatar
from we_love.avatars.gradient import Gradient, GradientConfig, GradientType
from we_love.avatars.loop import Loop, LoopConfig, LoopType

__all__ = [
    "Avatar",
    "AvatarConfig",
    "AvatarGenerator",
    "AvatarGeneratorConfig",
    "Gradient",
    "GradientConfig",
    "GradientType",
    "Loop",
    "LoopConfig",
    "LoopType",
    "avatar",
]
