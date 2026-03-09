"""Seed-based avatar generation - create unique avatars from strings."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from we_love.avatars.avatar import AvatarConfig
from we_love.avatars.constants import (
    BASE_COLOR_PAIRS,
    EPITROCHOID_R_MAJOR_MAX,
    EPITROCHOID_R_MAJOR_MIN,
    EPITROCHOID_R_MINOR_MAX,
    EPITROCHOID_R_MINOR_MIN,
    LINE_WIDTH_MAX_PCT,
    LINE_WIDTH_MIN_PCT,
    LISSAJOUS_FREQ_MAX,
    LISSAJOUS_FREQ_MIN,
    LISSAJOUS_PHASE_MAX,
    LISSAJOUS_PHASE_MIN,
    LOOP_COLORS,
    OFFSET_MAX,
    OFFSET_MIN,
    PALETTE_VARIATION,
    PREFERRED_LOOP_TYPES,
    ROSE_PETALS_MAX,
    ROSE_PETALS_MIN,
    SIZE_MAX_NORMAL,
    SIZE_MAX_ZOOMED,
    SIZE_MIN_NORMAL,
    SIZE_MIN_ZOOMED,
    SPEED_MAX,
    SPEED_MIN,
)
from we_love.avatars.gradient import GradientConfig, GradientType
from we_love.avatars.loop import LoopConfig, LoopType

if TYPE_CHECKING:
    from we_love.avatars.avatar import Avatar


class AvatarGeneratorConfig(BaseModel):
    """Configuration for avatar generation from seeds."""

    width: int = Field(default=512, description='Avatar width')
    height: int = Field(default=512, description='Avatar height')
    fps: int = Field(default=30, description='Frames per second')
    duration: float = Field(default=30.0, description='Animation duration in seconds')
    enable_zoom: bool = Field(default=True, description='Enable zoom and offset')
    enable_wave_gradients: bool = Field(
        default=True, description='Enable wave gradients'
    )
    max_loops: int = Field(default=1, description='Maximum number of loops')
    random_loop: bool = Field(
        default=False,
        description='Use random loop parameters instead of deterministic (changes each generation)',
    )


class AvatarGenerator:
    """Generate unique avatars from string seeds."""

    def __init__(self, config: AvatarGeneratorConfig | None = None) -> None:
        """Initialize generator.

        Args:
            config: Generator configuration
        """
        self.config = config or AvatarGeneratorConfig()

    def _hash_seed(self, seed: str) -> bytes:
        """Generate hash from seed string."""
        return hashlib.sha256(seed.encode()).digest()

    def _get_deterministic_value(
        self, hash_bytes: bytes, offset: int, max_value: int
    ) -> int:
        """Get a deterministic value from hash bytes.

        Args:
            hash_bytes: Hash bytes
            offset: Byte offset in hash
            max_value: Maximum value (exclusive)

        Returns:
            Deterministic integer in range [0, max_value)
        """
        byte_val = hash_bytes[offset % len(hash_bytes)]
        return byte_val % max_value

    def _get_deterministic_float(
        self, hash_bytes: bytes, offset: int, min_val: float, max_val: float
    ) -> float:
        """Get a deterministic float from hash bytes.

        Args:
            hash_bytes: Hash bytes
            offset: Byte offset in hash
            min_val: Minimum value
            max_val: Maximum value

        Returns:
            Deterministic float in range [min_val, max_val]
        """
        byte_val = hash_bytes[offset % len(hash_bytes)]
        normalized = byte_val / 255.0
        return min_val + normalized * (max_val - min_val)

    def _generate_smooth_path(
        self,
        start_color: tuple[int, int, int],
        peak_color: tuple[int, int, int],
        num_steps: int,
        hash_bytes: bytes,
        base_offset: int,
    ) -> list[tuple[int, int, int]]:
        """Generate a smooth path from start to peak with organic variation.

        Args:
            start_color: Starting RGB color
            peak_color: Peak RGB color (midpoint)
            num_steps: Number of steps to generate
            hash_bytes: Hash for deterministic variation
            base_offset: Offset for hash reads

        Returns:
            List of RGB colors forming smooth path
        """
        path = [start_color]
        
        for i in range(1, num_steps):
            # Linear interpolation as base
            t = i / num_steps
            base_r = int(start_color[0] + (peak_color[0] - start_color[0]) * t)
            base_g = int(start_color[1] + (peak_color[1] - start_color[1]) * t)
            base_b = int(start_color[2] + (peak_color[2] - start_color[2]) * t)
            
            # Add organic variation (±PALETTE_VARIATION units)
            var_range = PALETTE_VARIATION * 2 + 1
            var_r = self._get_deterministic_value(hash_bytes, base_offset + i * 3, var_range) - PALETTE_VARIATION
            var_g = self._get_deterministic_value(hash_bytes, base_offset + i * 3 + 1, var_range) - PALETTE_VARIATION
            var_b = self._get_deterministic_value(hash_bytes, base_offset + i * 3 + 2, var_range) - PALETTE_VARIATION
            
            # Apply variation with clamping
            r = max(0, min(255, base_r + var_r))
            g = max(0, min(255, base_g + var_g))
            b = max(0, min(255, base_b + var_b))
            
            path.append((r, g, b))
        
        return path

    def _generate_color_palette(self, hash_bytes: bytes, offset: int) -> list[tuple[int, int, int]]:
        """Generate a harmonious color palette from hash.
        
        Creates an organic circular path: start → peak → back to start
        Uses different paths for outbound and return for natural look.

        Args:
            hash_bytes: Hash bytes
            offset: Starting offset

        Returns:
            List of RGB color tuples (7 colors, first = last)
        """
        # Select base hue
        hue_sector = self._get_deterministic_value(hash_bytes, offset, len(BASE_COLOR_PAIRS))
        start_color, peak_color = BASE_COLOR_PAIRS[hue_sector]
        
        # Generate organic circular path: start → peak → back to start
        # Use different hash offsets for outbound vs return for variation
        
        # Outbound: start → peak (4 colors including endpoints)
        outbound = self._generate_smooth_path(
            start_color, peak_color, 4, hash_bytes, offset + 100
        )
        
        # Return: peak → start (4 colors including endpoints)
        # Different hash offset creates different path back!
        return_path = self._generate_smooth_path(
            peak_color, start_color, 4, hash_bytes, offset + 200
        )
        
        # Combine: outbound[0,1,2,3=peak] + return[1,2,3=start]
        # Total: 7 colors with start appearing twice (start and end)
        palette = outbound + return_path[1:]
        
        return palette

    def _generate_loop_color(self, hash_bytes: bytes, offset: int) -> tuple[int, int, int]:
        """Generate loop color that contrasts with background.

        Args:
            hash_bytes: Hash bytes
            offset: Starting offset

        Returns:
            RGB color tuple
        """
        idx = self._get_deterministic_value(hash_bytes, offset, len(LOOP_COLORS))
        return LOOP_COLORS[idx]

    def generate_config(self, seed: str) -> AvatarConfig:
        """Generate avatar configuration from seed string.

        Args:
            seed: Any string (username, email, etc.)

        Returns:
            Deterministic AvatarConfig based on seed
        """
        hash_bytes = self._hash_seed(seed)

        # Generate gradient
        colors = self._generate_color_palette(hash_bytes, 0)

        # Choose gradient type
        if self.config.enable_wave_gradients:
            gradient_types = [
                GradientType.AURORA,
                GradientType.PLASMA,
                GradientType.CLOUDS,
                GradientType.WAVE,
                GradientType.RADIAL,
            ]
        else:
            gradient_types = [
                GradientType.LINEAR,
                GradientType.RADIAL,
                GradientType.ANGULAR,
                GradientType.DIAGONAL,
            ]

        gradient_type = gradient_types[
            self._get_deterministic_value(hash_bytes, 4, len(gradient_types))
        ]

        gradient_config = GradientConfig(
            colors=colors,
            gradient_type=gradient_type,
            angle=self._get_deterministic_float(hash_bytes, 5, 0, 360),
            wave_frequency=self._get_deterministic_float(hash_bytes, 6, 1.5, 3.5),
            wave_amplitude=self._get_deterministic_float(hash_bytes, 7, 0.2, 0.5),
            smooth_loop=True,
            animate_shift=True,
        )

        # Generate loops
        if self.config.random_loop:
            # Use true randomness for loop parameters
            import random
            
            num_loops = self.config.max_loops
        else:
            # Deterministic from seed
            num_loops = self._get_deterministic_value(
                hash_bytes, 8, self.config.max_loops
            ) + 1

        loop_configs = []
        for i in range(num_loops):
            base_offset = 10 + i * 10

            if self.config.random_loop:
                import random
                
                # Random loop type
                loop_types = [LoopType[t.upper()] for t in PREFERRED_LOOP_TYPES]
                loop_type = random.choice(loop_types)
                
                # Random parameters
                width_pct = random.uniform(LINE_WIDTH_MIN_PCT, LINE_WIDTH_MAX_PCT)
                line_width = int(self.config.width * width_pct)
                
                size_min = SIZE_MIN_ZOOMED if self.config.enable_zoom else SIZE_MIN_NORMAL
                size_max = SIZE_MAX_ZOOMED if self.config.enable_zoom else SIZE_MAX_NORMAL
                
                loop_config = LoopConfig(
                    loop_type=loop_type,
                    color=random.choice(LOOP_COLORS),
                    width=line_width,
                    size=random.uniform(size_min, size_max),
                    speed=random.uniform(SPEED_MIN, SPEED_MAX),
                )
                
                # Random type-specific parameters
                if loop_type == LoopType.LISSAJOUS:
                    loop_config.freq_x = random.uniform(LISSAJOUS_FREQ_MIN, LISSAJOUS_FREQ_MAX)
                    loop_config.freq_y = random.uniform(LISSAJOUS_FREQ_MIN, LISSAJOUS_FREQ_MAX)
                    loop_config.phase = random.uniform(LISSAJOUS_PHASE_MIN, LISSAJOUS_PHASE_MAX)
                elif loop_type == LoopType.ROSE:
                    loop_config.petals = random.randint(ROSE_PETALS_MIN, ROSE_PETALS_MAX)
                elif loop_type == LoopType.EPITROCHOID:
                    loop_config.r_major = random.uniform(EPITROCHOID_R_MAJOR_MIN, EPITROCHOID_R_MAJOR_MAX)
                    loop_config.r_minor = random.uniform(EPITROCHOID_R_MINOR_MIN, EPITROCHOID_R_MINOR_MAX)
                
                # Random offset if zoom enabled
                if self.config.enable_zoom:
                    loop_config.offset_x = random.uniform(OFFSET_MIN, OFFSET_MAX)
                    loop_config.offset_y = random.uniform(OFFSET_MIN, OFFSET_MAX)
            else:
                # Deterministic from seed (original behavior)
                loop_types = [LoopType[t.upper()] for t in PREFERRED_LOOP_TYPES]
                loop_type = loop_types[
                    self._get_deterministic_value(hash_bytes, base_offset, len(loop_types))
                ]

                # Generate loop parameters using constants
                width_pct = self._get_deterministic_float(
                    hash_bytes, base_offset + 2, LINE_WIDTH_MIN_PCT, LINE_WIDTH_MAX_PCT
                )
                line_width = int(self.config.width * width_pct)
                
                size_min = SIZE_MIN_ZOOMED if self.config.enable_zoom else SIZE_MIN_NORMAL
                size_max = SIZE_MAX_ZOOMED if self.config.enable_zoom else SIZE_MAX_NORMAL
                
                loop_config = LoopConfig(
                    loop_type=loop_type,
                    color=self._generate_loop_color(hash_bytes, base_offset + 1),
                    width=line_width,
                    size=self._get_deterministic_float(hash_bytes, base_offset + 3, size_min, size_max),
                    speed=self._get_deterministic_float(hash_bytes, base_offset + 4, SPEED_MIN, SPEED_MAX),
                )

                # Add type-specific parameters using constants
                if loop_type == LoopType.LISSAJOUS:
                    loop_config.freq_x = self._get_deterministic_float(
                        hash_bytes, base_offset + 5, LISSAJOUS_FREQ_MIN, LISSAJOUS_FREQ_MAX
                    )
                    loop_config.freq_y = self._get_deterministic_float(
                        hash_bytes, base_offset + 6, LISSAJOUS_FREQ_MIN, LISSAJOUS_FREQ_MAX
                    )
                    loop_config.phase = self._get_deterministic_float(
                        hash_bytes, base_offset + 7, LISSAJOUS_PHASE_MIN, LISSAJOUS_PHASE_MAX
                    )
                elif loop_type == LoopType.ROSE:
                    petal_range = ROSE_PETALS_MAX - ROSE_PETALS_MIN + 1
                    loop_config.petals = (
                        self._get_deterministic_value(hash_bytes, base_offset + 5, petal_range) + ROSE_PETALS_MIN
                    )
                elif loop_type == LoopType.EPITROCHOID:
                    loop_config.r_major = self._get_deterministic_float(
                        hash_bytes, base_offset + 5, EPITROCHOID_R_MAJOR_MIN, EPITROCHOID_R_MAJOR_MAX
                    )
                    loop_config.r_minor = self._get_deterministic_float(
                        hash_bytes, base_offset + 6, EPITROCHOID_R_MINOR_MIN, EPITROCHOID_R_MINOR_MAX
                    )

                # Add offset if zoom enabled
                if self.config.enable_zoom:
                    loop_config.offset_x = self._get_deterministic_float(
                        hash_bytes, base_offset + 8, OFFSET_MIN, OFFSET_MAX
                    )
                    loop_config.offset_y = self._get_deterministic_float(
                        hash_bytes, base_offset + 9, OFFSET_MIN, OFFSET_MAX
                    )

            loop_configs.append(loop_config)

        return AvatarConfig(
            width=self.config.width,
            height=self.config.height,
            fps=self.config.fps,
            duration=self.config.duration,
            gradient_config=gradient_config,
            loop_configs=loop_configs,
        )

    def generate(self, seed: str) -> Avatar:
        """Generate avatar from seed string.

        Args:
            seed: Any string (username, email, etc.)

        Returns:
            Avatar instance ready to render
        """
        from we_love.avatars.avatar import Avatar

        config = self.generate_config(seed)
        return Avatar(config)


def avatar(seed: str, config: AvatarGeneratorConfig | None = None) -> AvatarConfig:
    """Generate avatar configuration from seed string.

    This is the main API - simple and clean!

    Args:
        seed: Any string (username, email, etc.)
        config: Optional generator configuration

    Returns:
        Deterministic AvatarConfig based on seed

    Example:
        >>> from we_love.avatars import avatar, Avatar
        >>> config = avatar("alice@example.com")
        >>> Avatar(config).save_gif("alice.gif")
    """
    generator = AvatarGenerator(config)
    return generator.generate_config(seed)
