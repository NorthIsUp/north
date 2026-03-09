"""Cloud-like gradients with domain warping (inspired by IQ's techniques)."""

from we_love.avatars import (
    Avatar,
    AvatarConfig,
    GradientConfig,
    GradientType,
    LoopConfig,
    LoopType,
)


def example_cosmic_clouds() -> None:
    """Cosmic clouds with domain warping."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=30.0,
        gradient_config=GradientConfig(
            colors=[
                (30, 95, 95),    # Teal (start)
                (40, 105, 120),  # Teal-cyan
                (50, 112, 145),  # Cyan-blue
                (60, 113, 168),  # Sky blue (peak)
                (50, 112, 145),  # Cyan-blue (mirror)
                (40, 105, 120),  # Teal-cyan (mirror)
                (30, 95, 95),    # Teal (end = start)
            ],
            gradient_type=GradientType.CLOUDS,
            cloud_scale=1.5,   # Large, gentle clouds
            cloud_drift=0.008,  # Slow, gentle drift
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.EPITROCHOID,
                color=(255, 255, 240),
                width=40,
                r_major=0.4,
                r_minor=0.14,
                size=1.7,
                offset_x=0.3,
                offset_y=-0.2,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/cosmic_clouds.gif", parallel=True, optimize=False, progress=True)
    print("Created: output/cosmic_clouds.gif")


def example_ethereal_mist() -> None:
    """Ethereal misty clouds."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=30.0,
        gradient_config=GradientConfig(
            colors=[
                (118, 68, 178),  # Purple (start)
                (115, 67, 185),  # Deep purple
                (110, 70, 195),  # Purple-blue
                (105, 75, 200),  # Blue-purple (peak)
                (110, 70, 195),  # Purple-blue (mirror)
                (115, 67, 185),  # Deep purple (mirror)
                (118, 68, 178),  # Purple (end = start)
            ],
            gradient_type=GradientType.CLOUDS,
            cloud_scale=1.2,   # Very large, soft clouds
            cloud_drift=0.006,  # Very gentle drift
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.LISSAJOUS,
                color=(240, 255, 255),
                width=35,
                freq_x=4.0,
                freq_y=3.0,
                size=1.5,
                offset_x=-0.2,
                offset_y=0.3,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/ethereal_mist.gif", parallel=True, optimize=False, progress=True)
    print("Created: output/ethereal_mist.gif")


def example_ocean_fog() -> None:
    """Ocean fog with slow drift."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=30.0,
        gradient_config=GradientConfig(
            colors=[
                (58, 125, 180),  # Deep blue (start)
                (62, 140, 188),  # Ocean blue
                (66, 155, 194),  # Blue-cyan
                (68, 168, 198),  # Cyan (peak)
                (66, 155, 194),  # Blue-cyan (mirror)
                (62, 140, 188),  # Ocean blue (mirror)
                (58, 125, 180),  # Deep blue (end = start)
            ],
            gradient_type=GradientType.CLOUDS,
            cloud_scale=1.8,   # Large, billowing features
            cloud_drift=0.01,   # Slow, meditative drift
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.ROSE,
                color=(255, 255, 240),
                width=38,
                petals=7,
                size=1.4,
                offset_x=0.4,
                offset_y=-0.3,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/ocean_fog.gif", parallel=True, optimize=False, progress=True)
    print("Created: output/ocean_fog.gif")


if __name__ == "__main__":
    print("=" * 60)
    print("CLOUD GRADIENTS - Domain Warping")
    print("Inspired by Inigo Quilez's techniques")
    print("=" * 60)
    print()
    
    example_cosmic_clouds()
    print()
    example_ethereal_mist()
    print()
    example_ocean_fog()
    
    print()
    print("=" * 60)
    print("✨ Cloud gradients generated!")
    print("=" * 60)
