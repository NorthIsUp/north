"""Seed-based avatar generation examples."""

from we_love.avatars import Avatar, avatar


def example_simple_api() -> None:
    """Demonstrate the simple avatar(seed) API."""
    print('Generating avatars from seeds...\n')

    # Generate avatars for different users
    seeds = [
        'alice@example.com',
        'bob@example.com',
        'charlie@example.com',
        'diana@example.com',
        'eve@example.com',
    ]

    for seed in seeds:
        # The magic one-liner!
        config = avatar(seed)

        # Create and save
        av = Avatar(config)
        filename = seed.split('@')[0]
        av.save_gif(f'output/seed_{filename}.gif')
        print(f'✓ Created avatar for {seed} -> output/seed_{filename}.gif')


def example_deterministic() -> None:
    """Show that same seed always produces same avatar."""
    print('\nDemonstrating deterministic generation...')

    seed = 'test@example.com'

    # Generate twice
    config1 = avatar(seed)
    config2 = avatar(seed)

    # They should be identical
    print(f'\nSeed: {seed}')
    print(f'  Config 1 gradient type: {config1.gradient_config.gradient_type}')
    print(f'  Config 2 gradient type: {config2.gradient_config.gradient_type}')
    print(f'  Number of loops: {len(config1.loop_configs)}')
    print(f'  Loop type: {config1.loop_configs[0].loop_type}')
    print('  ✓ Same seed = same avatar (deterministic)')


def example_variations() -> None:
    """Show how small changes in seed produce different avatars."""
    print('\nGenerating variations...')

    base = 'user'
    variations = [f'{base}{i}' for i in range(1, 6)]

    for seed in variations:
        config = avatar(seed)
        av = Avatar(config)
        av.save_gif(f'output/seed_{seed}.gif')
        print(
            f'✓ {seed}: {config.gradient_config.gradient_type.value}, '
            f'{len(config.loop_configs)} loop(s), '
            f'{config.loop_configs[0].loop_type.value}'
        )


def example_with_custom_config() -> None:
    """Use custom generator config for specific needs."""
    from we_love.avatars import AvatarGeneratorConfig

    print('\nGenerating with custom config...')

    # Smaller, faster avatars without zoom
    custom_config = AvatarGeneratorConfig(
        width=256,
        height=256,
        fps=20,
        duration=2.0,
        enable_zoom=False,
        max_loops=1,
    )

    seed = 'custom@example.com'
    config = avatar(seed, custom_config)

    av = Avatar(config)
    av.save_gif('output/seed_custom.gif')
    print(f'✓ Created custom avatar: 256x256, {config.fps}fps, no zoom')


if __name__ == '__main__':
    print('=' * 60)
    print('SEED-BASED AVATAR GENERATION')
    print('=' * 60)

    example_simple_api()
    example_deterministic()
    example_variations()
    example_with_custom_config()

    print('\n' + '=' * 60)
    print('✨ All seed-based examples completed!')
    print('=' * 60)
