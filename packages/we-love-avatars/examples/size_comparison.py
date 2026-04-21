"""Demonstrate how line thickness scales with image size."""

from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar


def example_size_scaling() -> None:
    """Generate avatars at different sizes to show line scaling."""
    print("Generating avatars at different sizes...")
    print("Line width is always 3-5% of image width\n")

    sizes = [
        (256, "256x256 (small)"),
        (512, "512x512 (default)"),
        (1024, "1024x1024 (large)"),
    ]

    for size, label in sizes:
        gen_config = AvatarGeneratorConfig(
            width=size,
            height=size,
            fps=20,
            duration=2.0,
        )

        config = avatar("example", gen_config)
        width = config.loop_configs[0].width
        pct = (width / size) * 100

        av = Avatar(config)
        av.save_gif(f"output/size_{size}.gif")

        print(f"✓ {label:20} → {width:3}px line ({pct:.1f}% of width)")

    print("\nAll sizes generated! Line thickness scales proportionally.")


if __name__ == "__main__":
    print("=" * 60)
    print("LINE THICKNESS SCALING DEMO")
    print("=" * 60)
    print()

    example_size_scaling()

    print()
    print("=" * 60)
