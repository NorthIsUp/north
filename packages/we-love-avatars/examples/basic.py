"""Basic examples of using we-love-avatars."""

from we_love.avatars import (
    Avatar,
    AvatarConfig,
    GradientConfig,
    GradientType,
    LoopConfig,
    LoopType,
)


def example_default() -> None:
    """Create an avatar with default settings."""
    avatar = Avatar()
    avatar.save_gif("output/default.gif")
    print("Created: output/default.gif")


def example_lissajous() -> None:
    """Create a Lissajous curve avatar."""
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=3.0,
        gradient_config=GradientConfig(
            colors=[
                (255, 0, 128),  # Pink
                (128, 0, 255),  # Purple
                (0, 128, 255),  # Blue
            ],
            gradient_type=GradientType.RADIAL,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.LISSAJOUS,
                color=(255, 255, 255),
                width=4,
                freq_x=3.0,
                freq_y=4.0,
                size=0.7,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/lissajous.gif")
    print("Created: output/lissajous.gif")


def example_rose() -> None:
    """Create a rose curve avatar."""
    config = AvatarConfig(
        gradient_config=GradientConfig(
            colors=[
                (255, 100, 100),
                (255, 200, 100),
            ],
            gradient_type=GradientType.LINEAR,
            angle=90,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.ROSE,
                color=(255, 255, 255),
                width=3,
                petals=7,
                size=0.6,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/rose.gif")
    print("Created: output/rose.gif")


def example_multiple_loops() -> None:
    """Create an avatar with multiple loops."""
    config = AvatarConfig(
        gradient_config=GradientConfig(
            colors=[
                (10, 10, 50),
                (50, 10, 100),
            ],
            gradient_type=GradientType.RADIAL,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.LISSAJOUS,
                color=(255, 200, 200),
                width=3,
                freq_x=3.0,
                freq_y=4.0,
                size=0.7,
                speed=1.0,
            ),
            LoopConfig(
                loop_type=LoopType.CIRCLE,
                color=(200, 200, 255),
                width=3,
                size=0.4,
                speed=2.0,
            ),
            LoopConfig(
                loop_type=LoopType.ROSE,
                color=(200, 255, 200),
                width=2,
                petals=5,
                size=0.5,
                speed=0.5,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/multiple.gif")
    print("Created: output/multiple.gif")


def example_epitrochoid() -> None:
    """Create a spirograph-like epitrochoid avatar."""
    config = AvatarConfig(
        gradient_config=GradientConfig(
            colors=[
                (30, 30, 30),
                (60, 30, 60),
            ],
            gradient_type=GradientType.ANGULAR,
        ),
        loop_configs=[
            LoopConfig(
                loop_type=LoopType.EPITROCHOID,
                color=(255, 255, 100),
                width=3,
                r_major=0.35,
                r_minor=0.15,
                size=0.8,
            ),
        ],
    )
    avatar = Avatar(config)
    avatar.save_gif("output/epitrochoid.gif")
    print("Created: output/epitrochoid.gif")


if __name__ == "__main__":
    example_default()
    example_lissajous()
    example_rose()
    example_multiple_loops()
    example_epitrochoid()
    print("\nAll examples generated successfully!")
