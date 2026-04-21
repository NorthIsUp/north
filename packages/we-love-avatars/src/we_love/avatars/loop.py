"""Loop/shape generation for animated avatars."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from PIL import ImageDraw
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from PIL import Image


class LoopType(StrEnum):
    """Type of loop animation."""

    CIRCLE = "circle"
    LISSAJOUS = "lissajous"
    SPIRAL = "spiral"
    ROSE = "rose"
    EPITROCHOID = "epitrochoid"


class LoopConfig(BaseModel):
    """Configuration for animated loops."""

    loop_type: LoopType = Field(
        default=LoopType.LISSAJOUS,
        description="Type of loop to render",
    )
    color: tuple[int, int, int] = Field(
        default=(255, 255, 255),
        description="RGB color of the loop",
    )
    width: int = Field(
        default=3,
        description="Line width in pixels",
    )
    size: float = Field(
        default=0.6,
        description="Size as fraction of image dimensions (0-1)",
    )
    speed: float = Field(
        default=1.0,
        description="Animation speed multiplier",
    )
    # Lissajous curve parameters
    freq_x: float = Field(
        default=3.0,
        description="X frequency for Lissajous curves",
    )
    freq_y: float = Field(
        default=4.0,
        description="Y frequency for Lissajous curves",
    )
    phase: float = Field(
        default=0.0,
        description="Phase offset in radians",
    )
    # Rose curve parameters
    petals: int = Field(
        default=5,
        description="Number of petals for rose curves",
    )
    # Epitrochoid parameters
    r_major: float = Field(
        default=0.3,
        description="Major radius for epitrochoid",
    )
    r_minor: float = Field(
        default=0.1,
        description="Minor radius for epitrochoid",
    )
    # Position offset
    offset_x: float = Field(
        default=0.0,
        description="Horizontal offset as fraction of image width (-1 to 1)",
    )
    offset_y: float = Field(
        default=0.0,
        description="Vertical offset as fraction of image height (-1 to 1)",
    )


class Loop:
    """Generate animated loops and curves."""

    def __init__(self, config: LoopConfig | None = None) -> None:
        """Initialize loop generator.

        Args:
            config: Loop configuration, uses defaults if None
        """
        self.config = config or LoopConfig()

    def _calculate_points(
        self,
        width: int,
        height: int,
        frame: int,
        total_frames: int,
        num_points: int = 1000,
    ) -> list[tuple[float, float]]:
        """Calculate the points for the loop path.

        Args:
            width: Image width
            height: Image height
            frame: Current frame number
            total_frames: Total frames in animation
            num_points: Number of points to generate

        Returns:
            List of (x, y) coordinates
        """
        t = np.linspace(0, 2 * np.pi, num_points)
        anim_phase = (frame / total_frames) * 2 * np.pi * self.config.speed

        # Apply offset for positioning
        center_x = width / 2 + (self.config.offset_x * width / 2)
        center_y = height / 2 + (self.config.offset_y * height / 2)
        scale = min(width, height) * self.config.size / 2

        if self.config.loop_type == LoopType.CIRCLE:
            x = center_x + scale * np.cos(t + anim_phase)
            y = center_y + scale * np.sin(t + anim_phase)

        elif self.config.loop_type == LoopType.LISSAJOUS:
            x = center_x + scale * np.sin(self.config.freq_x * t + anim_phase)
            y = center_y + scale * np.sin(self.config.freq_y * t + self.config.phase + anim_phase)

        elif self.config.loop_type == LoopType.SPIRAL:
            r = scale * (1 + t / (2 * np.pi))
            x = center_x + r * np.cos(t + anim_phase)
            y = center_y + r * np.sin(t + anim_phase)

        elif self.config.loop_type == LoopType.ROSE:
            k = self.config.petals
            r = scale * np.cos(k * t)
            x = center_x + r * np.cos(t + anim_phase)
            y = center_y + r * np.sin(t + anim_phase)

        elif self.config.loop_type == LoopType.EPITROCHOID:
            R = self.config.r_major * scale
            r = self.config.r_minor * scale
            d = (R + r) / 2
            x = center_x + (R + r) * np.cos(t + anim_phase) - d * np.cos(((R + r) / r) * (t + anim_phase))
            y = center_y + (R + r) * np.sin(t + anim_phase) - d * np.sin(((R + r) / r) * (t + anim_phase))

        else:
            msg = f"Unsupported loop type: '{self.config.loop_type}'"
            raise ValueError(msg)

        return list(zip(x, y, strict=False))

    def render(
        self,
        image: Image.Image,
        frame: int = 0,
        total_frames: int = 60,
    ) -> Image.Image:
        """Render the loop onto an image.

        Args:
            image: Base image to draw on
            frame: Current frame number
            total_frames: Total frames in animation

        Returns:
            Image with loop drawn on it
        """
        img = image.copy()
        draw = ImageDraw.Draw(img)

        points = self._calculate_points(
            img.width,
            img.height,
            frame,
            total_frames,
        )

        # Draw the loop
        draw.line(points, fill=self.config.color, width=self.config.width)

        return img
