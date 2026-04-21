"""Enhanced epitrochoid examples with new features."""

from we_love.avatars import (
    Avatar,
    AvatarConfig,
    GradientConfig,
    GradientType,
    LoopConfig,
    LoopType,
)


def example_zoomed_epitrochoid() -> None:
    """Create a zoomed-in, off-center epitrochoid with wave gradient."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=4.0,
        gradient_config=GradientConfig(
            colors=[
                (20, 20, 40),  # Deep blue-black
                (80, 40, 120),  # Purple
                (120, 80, 160),  # Lighter purple
                (60, 100, 180),  # Blue
                (40, 60, 100),  # Deep blue
            ],
            gradient_type=GradientType.WAVE,
            wave_frequency=2.5,
            wave_amplitude=0.4,
            angle=45,
            animate_shift=True,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.EPITROCHOID,
                color=(255, 240, 200),
                width=4,
                r_major=0.4,
                r_minor=0.15,
                size=1.8,  # Zoomed in - we'll only see part of it
                offset_x=0.4,  # Offset diagonally
                offset_y=-0.3,
                speed=0.8,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/enhanced_epitrochoid.gif")
    print("Created: output/enhanced_epitrochoid.gif")


def example_smooth_radial() -> None:
    """Create epitrochoid with smooth radial gradient."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=3.0,
        gradient_config=GradientConfig(
            colors=[
                (10, 10, 30),
                (30, 50, 80),
                (50, 90, 140),
                (30, 50, 80),
                (10, 10, 30),
            ],
            gradient_type=GradientType.RADIAL,
            animate_shift=True,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.EPITROCHOID,
                color=(255, 200, 150),
                width=3,
                r_major=0.35,
                r_minor=0.12,
                size=2.0,
                offset_x=-0.3,
                offset_y=0.4,
                speed=1.0,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/smooth_radial.gif")
    print("Created: output/smooth_radial.gif")


def example_double_epitrochoid() -> None:
    """Create two zoomed epitrochoids with wave gradient."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=4.0,
        gradient_config=GradientConfig(
            colors=[
                (15, 5, 25),
                (60, 20, 80),
                (100, 60, 120),
                (60, 20, 80),
            ],
            gradient_type=GradientType.WAVE,
            wave_frequency=3.0,
            wave_amplitude=0.3,
            angle=135,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.EPITROCHOID,
                color=(255, 220, 180),
                width=3,
                r_major=0.4,
                r_minor=0.13,
                size=1.5,
                offset_x=0.5,
                offset_y=-0.4,
                speed=0.7,
            ),
            LoopConfig(
                loop_type=LoopType.EPITROCHOID,
                color=(180, 220, 255),
                width=2,
                r_major=0.35,
                r_minor=0.11,
                size=1.3,
                offset_x=-0.4,
                offset_y=0.5,
                speed=1.2,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/double_epitrochoid.gif")
    print("Created: output/double_epitrochoid.gif")


def example_lissajous_wave() -> None:
    """Create Lissajous with asymmetric wave gradient."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=3.0,
        gradient_config=GradientConfig(
            colors=[
                (40, 10, 50),
                (100, 40, 120),
                (160, 100, 180),
                (120, 80, 160),
                (80, 40, 100),
            ],
            gradient_type=GradientType.WAVE,
            wave_frequency=2.0,
            wave_amplitude=0.5,
            angle=90,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.LISSAJOUS,
                color=(255, 255, 240),
                width=4,
                freq_x=5.0,
                freq_y=4.0,
                size=1.6,
                offset_x=0.2,
                offset_y=-0.2,
                speed=1.0,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/lissajous_wave.gif")
    print("Created: output/lissajous_wave.gif")


if __name__ == "__main__":
    print("Generating enhanced examples...\n")
    example_zoomed_epitrochoid()
    example_smooth_radial()
    example_double_epitrochoid()
    example_lissajous_wave()
    print("\n✨ All enhanced examples generated successfully!")
