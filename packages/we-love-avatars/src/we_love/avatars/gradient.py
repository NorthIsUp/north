"""Gradient background generation for animated avatars."""

from enum import StrEnum
from typing import Self

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field


class GradientType(StrEnum):
    """Type of gradient to render."""

    LINEAR = "linear"
    RADIAL = "radial"
    ANGULAR = "angular"
    DIAGONAL = "diagonal"
    WAVE = "wave"
    AURORA = "aurora"
    PLASMA = "plasma"
    CLOUDS = "clouds"


class GradientConfig(BaseModel):
    """Configuration for gradient backgrounds."""

    colors: list[tuple[int, int, int]] = Field(
        default_factory=lambda: [(255, 0, 128), (128, 0, 255)],
        description="List of RGB colors to interpolate between",
    )
    gradient_type: GradientType = Field(
        default=GradientType.LINEAR,
        description="Type of gradient",
    )
    angle: float = Field(
        default=0.0,
        description="Angle in degrees for linear/diagonal gradients",
    )
    animate_shift: bool = Field(
        default=True,
        description="Whether to shift gradient colors over time",
    )
    wave_frequency: float = Field(
        default=2.0,
        description="Frequency for wave gradients",
    )
    wave_amplitude: float = Field(
        default=0.3,
        description="Amplitude for wave gradients",
    )
    smooth_loop: bool = Field(
        default=True,
        description="Ensure smooth color transitions when animation loops",
    )
    cloud_scale: float = Field(
        default=1.5,
        description="Scale for cloud noise patterns (lower = larger, gentler clouds)",
    )
    cloud_drift: float = Field(
        default=0.008,
        description="Drift speed for cloud movement",
    )


class Gradient:
    """Generate animated gradient backgrounds."""

    def __init__(self, config: GradientConfig | None = None) -> None:
        """Initialize gradient generator.

        Args:
            config: Gradient configuration, uses defaults if None
        """
        self.config = config or GradientConfig()

    @classmethod
    def from_colors(
        cls,
        colors: list[tuple[int, int, int]],
        gradient_type: GradientType = GradientType.LINEAR,
    ) -> Self:
        """Create a gradient from a list of colors.

        Args:
            colors: List of RGB tuples
            gradient_type: Type of gradient to create

        Returns:
            Gradient instance
        """
        return cls(GradientConfig(colors=colors, gradient_type=gradient_type))

    def _normalize_position(self, pos: np.ndarray) -> np.ndarray:
        """Normalize position array to 0-1 range.

        Args:
            pos: Position array

        Returns:
            Normalized array (0-1)
        """
        return (pos - pos.min()) / (pos.max() - pos.min())

    def _fbm(self, x: np.ndarray, y: np.ndarray, z: float, octaves: int = 4) -> np.ndarray:
        """Fractional Brownian Motion - layered noise.

        Args:
            x: X coordinates
            y: Y coordinates
            z: Time/Z coordinate
            octaves: Number of noise layers

        Returns:
            FBM noise values
        """
        value = np.zeros_like(x)
        amplitude = 0.5
        frequency = 1.0

        for _ in range(octaves):
            # Simple Perlin-style noise using numpy
            nx = np.sin(x * frequency * np.pi * 2.0 + z) * np.cos(y * frequency * np.pi * 1.7)
            ny = np.cos(x * frequency * np.pi * 1.3 + z) * np.sin(y * frequency * np.pi * 2.3)
            noise = (nx + ny) * 0.5

            value += amplitude * noise
            amplitude *= 0.5
            frequency *= 2.0

        return value

    def render(
        self,
        width: int,
        height: int,
        frame: int = 0,
        total_frames: int = 60,
    ) -> Image.Image:
        """Render a gradient background for a specific frame.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            frame: Current frame number
            total_frames: Total number of frames in animation

        Returns:
            PIL Image with gradient background
        """
        # Create coordinate grids
        x = np.linspace(0, 1, width)
        y = np.linspace(0, 1, height)
        xx, yy = np.meshgrid(x, y)

        # Calculate gradient position based on type
        if self.config.gradient_type == GradientType.LINEAR:
            angle_rad = np.radians(self.config.angle)
            pos = xx * np.cos(angle_rad) + yy * np.sin(angle_rad)
        elif self.config.gradient_type == GradientType.RADIAL:
            center_x, center_y = 0.5, 0.5
            pos = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2)
            pos = self._normalize_position(pos)
        elif self.config.gradient_type == GradientType.ANGULAR:
            center_x, center_y = 0.5, 0.5
            pos = np.arctan2(yy - center_y, xx - center_x)
            pos = (pos + np.pi) / (2 * np.pi)
        elif self.config.gradient_type == GradientType.WAVE:
            # Asymmetric wave gradient
            angle_rad = np.radians(self.config.angle)
            base = xx * np.cos(angle_rad) + yy * np.sin(angle_rad)
            wave = np.sin(base * np.pi * self.config.wave_frequency)
            pos = base + wave * self.config.wave_amplitude
            pos = self._normalize_position(pos)
        elif self.config.gradient_type == GradientType.AURORA:
            # Aurora borealis - MULTI-DIMENSIONAL with temporal evolution
            # Time-based phase for evolving patterns
            t = (frame / total_frames) * 2 * np.pi

            # Layer 1: Horizontal waves with time evolution
            wave_h = np.sin(xx * np.pi * 3.2 + yy * np.pi * 1.8 + t * 0.7)

            # Layer 2: Vertical waves with different time speed
            wave_v = np.cos(yy * np.pi * 2.7 + xx * np.pi * 1.3 + t * 1.2)

            # Layer 3: Diagonal waves
            wave_d = np.sin((xx + yy) * np.pi * 2.3 + t * 0.5)

            # Layer 4: Radial waves for depth
            r = np.sqrt((xx - 0.5) ** 2 + (yy - 0.5) ** 2)
            wave_r = np.cos(r * np.pi * 4.5 + t * 0.9)

            # Layer 5: Modulation layer (affects intensity of other layers)
            mod = np.sin(xx * np.pi * 1.5) * np.cos(yy * np.pi * 1.8)

            # Combine all layers with varying weights and modulation
            pos = wave_h * 0.28 + wave_v * 0.26 + wave_d * 0.22 + wave_r * 0.14 + mod * wave_h * 0.10
            pos = self._normalize_position(pos)

        elif self.config.gradient_type == GradientType.PLASMA:
            # Plasma - CHAOTIC MULTI-DIMENSIONAL energy
            # Time-based evolution
            t = (frame / total_frames) * 2 * np.pi

            # Multiple overlapping wave patterns with time
            p1 = np.sin(xx * np.pi * 4.3 + t * 1.5)
            p2 = np.sin(yy * np.pi * 3.7 + t * 1.1)
            p3 = np.sin((xx + yy) * np.pi * 2.5 + t * 0.8)
            p4 = np.cos((xx - yy) * np.pi * 3.1 - t * 1.3)

            # Radial component for depth
            r = np.sqrt((xx - 0.5) ** 2 + (yy - 0.5) ** 2)
            p5 = np.sin(r * np.pi * 5.2 + t * 2.0)

            # Angular component for rotation
            angle = np.arctan2(yy - 0.5, xx - 0.5)
            p6 = np.cos(angle * 3.0 + t * 0.6)

            # Non-linear interaction between waves
            p7 = np.sin(xx * yy * np.pi * 6.0 + t)

            # Combine all with different weights
            pos = p1 * 0.20 + p2 * 0.18 + p3 * 0.16 + p4 * 0.14 + p5 * 0.12 + p6 * 0.12 + p7 * 0.08
            pos = self._normalize_position(pos)

        elif self.config.gradient_type == GradientType.CLOUDS:
            # Cloud-like gradient with domain warping (inspired by IQ's techniques)
            # https://iquilezles.org/articles/warp/
            t = (frame / total_frames) * 2 * np.pi

            # Persistent drift - clouds flow in a direction
            drift_x = t * self.config.cloud_drift * 0.3
            drift_y = t * self.config.cloud_drift * 0.2

            # First layer of noise (q)
            q_x = self._fbm(xx + drift_x, yy + drift_y, t * 0.04)
            q_y = self._fbm(xx + drift_x + 5.2, yy + drift_y + 1.3, t * 0.036)

            # Second layer warped by first (r)
            r_x = self._fbm(xx + 4.0 * q_x + 1.7 + drift_x * 0.8, yy + 4.0 * q_y + 9.2 + drift_y * 0.8, t * 0.032)
            r_y = self._fbm(xx + 4.0 * q_x + 8.3 + drift_x * 0.8, yy + 4.0 * q_y + 2.8 + drift_y * 0.8, t * 0.028)

            # Final warped pattern
            warp_strength = 1.5
            warped_x = xx + warp_strength * r_x + drift_x
            warped_y = yy + warp_strength * r_y + drift_y

            # Sample final density
            pos = self._fbm(warped_x * self.config.cloud_scale, warped_y * self.config.cloud_scale, t * 0.02)

            # Map from -1,1 to 0,1 with smooth falloff
            pos = pos * 0.5 + 0.5
            pos = self._normalize_position(pos)

        else:  # DIAGONAL
            pos = (xx + yy) / 2

        # Apply animation shift
        if self.config.animate_shift:
            # Full circle progression (0 to 1, no bouncing)
            shift = frame / total_frames
            pos = (pos + shift) % 1.0

        # Interpolate between colors
        return self._interpolate_colors(pos, width, height)

    def _interpolate_colors(self, pos: np.ndarray, width: int, height: int) -> Image.Image:
        """Interpolate colors based on position array.

        Args:
            pos: Position array (0-1) for each pixel
            width: Image width
            height: Image height

        Returns:
            PIL Image with interpolated colors
        """
        num_colors = len(self.config.colors)
        if num_colors < 2:
            msg = "At least 2 colors required for gradient"
            raise ValueError(msg)

        # Scale position to color segments
        pos_scaled = pos * (num_colors - 1)
        segment = np.floor(pos_scaled).astype(int)
        segment = np.clip(segment, 0, num_colors - 2)
        local_pos = pos_scaled - segment

        # Initialize RGB arrays
        r = np.zeros_like(pos)
        g = np.zeros_like(pos)
        b = np.zeros_like(pos)

        # Interpolate for each segment
        for i in range(num_colors - 1):
            mask = segment == i
            c1 = self.config.colors[i]
            c2 = self.config.colors[i + 1]

            r[mask] = c1[0] + (c2[0] - c1[0]) * local_pos[mask]
            g[mask] = c1[1] + (c2[1] - c1[1]) * local_pos[mask]
            b[mask] = c1[2] + (c2[2] - c1[2]) * local_pos[mask]

        # Combine into image
        rgb = np.dstack([r, g, b]).astype(np.uint8)
        return Image.fromarray(rgb, mode="RGB")
