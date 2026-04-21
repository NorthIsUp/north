"""We Love namespace package for creating animated avatars with moving loops and gradient backgrounds."""

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
