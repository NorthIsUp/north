"""Quick demo of we-love-avatars."""

from we_love.avatars import (
    Avatar,
    AvatarConfig,
    GradientConfig,
    GradientType,
    LoopConfig,
    LoopType,
)


def main() -> None:
    """Create a beautiful animated avatar."""
    # Configure a vibrant gradient background
    gradient = GradientConfig(
        colors=[
            (255, 0, 128),  # Hot pink
            (128, 0, 255),  # Purple
            (0, 128, 255),  # Blue
            (0, 255, 200),  # Cyan
        ],
        gradient_type=GradientType.RADIAL,
        animate_shift=True,
    )

    # Configure multiple animated loops
    loops = [
        # Main Lissajous curve
        LoopConfig(
            loop_type=LoopType.LISSAJOUS,
            color=(255, 255, 255),
            width=4,
            freq_x=3.0,
            freq_y=4.0,
            size=0.7,
            speed=1.0,
        ),
        # Inner rotating circle
        LoopConfig(
            loop_type=LoopType.CIRCLE,
            color=(255, 255, 200),
            width=3,
            size=0.3,
            speed=2.5,
        ),
        # Outer rose pattern
        LoopConfig(
            loop_type=LoopType.ROSE,
            color=(200, 255, 255),
            width=2,
            petals=7,
            size=0.85,
            speed=0.5,
        ),
    ]

    # Create the avatar
    config = AvatarConfig(
        width=512,
        height=512,
        fps=30,
        duration=3.0,
        gradient_config=gradient,
        loop_configs=loops,
    )

    avatar = Avatar(config)

    # Save as GIF
    print('Generating animated avatar...')
    avatar.save_gif('output/demo.gif')
    print('✓ Created: output/demo.gif')

    # Save a single frame as PNG
    avatar.save_png('output/demo.png', frame=15)
    print('✓ Created: output/demo.png')

    print('\nDone! Check the output/ directory.')


if __name__ == '__main__':
    main()
