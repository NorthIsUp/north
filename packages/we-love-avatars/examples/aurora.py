"""Aurora-inspired gradient examples - ethereal, multi-dimensional rainbows."""

from we_love.avatars import (
    Avatar,
    AvatarConfig,
    GradientConfig,
    GradientType,
    LoopConfig,
    LoopType,
)


def example_aurora_borealis() -> None:
    """Classic aurora borealis with green-blue-purple gradients."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=30.0,  # Slow, mesmerizing aurora flow
        gradient_config=GradientConfig(
            colors=[
                (30, 95, 95),  # Teal (start)
                (40, 105, 120),  # Teal-cyan
                (50, 112, 145),  # Cyan-blue
                (60, 113, 168),  # Sky blue (peak)
                (50, 112, 145),  # Cyan-blue (mirror)
                (40, 105, 120),  # Teal-cyan (mirror)
                (30, 95, 95),  # Teal (end = start)
            ],
            gradient_type=GradientType.AURORA,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.EPITROCHOID,
                color=(255, 255, 240),
                width=6,
                r_major=0.4,
                r_minor=0.14,
                size=1.6,
                offset_x=0.3,
                offset_y=-0.2,
                speed=0.7,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/aurora_borealis.gif", progress=True)
    print("Created: output/aurora_borealis.gif")


def example_northern_lights() -> None:
    """Northern lights with pink-purple-blue ethereal glow."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=30.0,  # Slow, mesmerizing aurora flow
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
            gradient_type=GradientType.AURORA,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.LISSAJOUS,
                color=(255, 240, 250),
                width=7,
                freq_x=3.0,
                freq_y=5.0,
                size=1.5,
                offset_x=-0.2,
                offset_y=0.3,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/northern_lights.gif", progress=True)
    print("Created: output/northern_lights.gif")


def example_cosmic_plasma() -> None:
    """Chaotic plasma effect with full spectrum rainbow."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=30.0,  # Slow, mesmerizing aurora flow
        gradient_config=GradientConfig(
            colors=[
                (165, 95, 170),  # Pink-purple (start)
                (150, 110, 195),  # Lavender
                (135, 128, 210),  # Light purple
                (120, 145, 218),  # Sky blue (peak)
                (135, 128, 210),  # Light purple (mirror)
                (150, 110, 195),  # Lavender (mirror)
                (165, 95, 170),  # Pink-purple (end = start)
            ],
            gradient_type=GradientType.PLASMA,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.EPITROCHOID,
                color=(255, 255, 255),
                width=6,
                r_major=0.38,
                r_minor=0.13,
                size=1.8,
                offset_x=0.4,
                offset_y=-0.3,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/cosmic_plasma.gif", progress=True)
    print("Created: output/cosmic_plasma.gif")


def example_ethereal_rainbow() -> None:
    """Full spectrum ethereal rainbow with aurora effect."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=30.0,  # Slow, mesmerizing aurora flow
        gradient_config=GradientConfig(
            colors=[
                (180, 90, 160),  # Soft pink-purple
                (170, 100, 175),  # Pink-lavender
                (160, 110, 190),  # Lavender
                (145, 120, 205),  # Light purple
                (130, 135, 215),  # Purple-blue
                (120, 150, 220),  # Sky blue
                (125, 165, 215),  # Blue-cyan
                (135, 180, 205),  # Cyan-teal
            ],
            gradient_type=GradientType.AURORA,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.ROSE,
                color=(255, 255, 240),
                width=5,
                petals=7,
                size=1.4,
                offset_x=-0.3,
                offset_y=0.3,
                speed=0.8,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/ethereal_rainbow.gif", progress=True)
    print("Created: output/ethereal_rainbow.gif")


def example_mystic_ocean() -> None:
    """Ocean aurora with teal-cyan-blue flowing gradients."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=30.0,  # Slow, mesmerizing aurora flow
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
            gradient_type=GradientType.PLASMA,
            smooth_loop=True,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.LISSAJOUS,
                color=(240, 255, 255),
                width=8,
                freq_x=4.0,
                freq_y=3.0,
                size=1.7,
                offset_x=0.2,
                offset_y=-0.4,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/mystic_ocean.gif", progress=True)
    print("Created: output/mystic_ocean.gif")


if __name__ == "__main__":
    print("=" * 60)
    print("AURORA-INSPIRED GRADIENTS")
    print("Multi-dimensional ethereal rainbows")
    print("=" * 60)
    print()

    print("starting example_aurora_borealis")
    example_aurora_borealis()
    print("starting example_northern_lights")
    example_northern_lights()
    print("starting example_cosmic_plasma")
    example_cosmic_plasma()
    print("starting example_ethereal_rainbow")
    example_ethereal_rainbow()
    print("starting example_mystic_ocean")
    example_mystic_ocean()

    print()
    print("=" * 60)
    print("✨ All aurora examples generated!")
    print("=" * 60)
