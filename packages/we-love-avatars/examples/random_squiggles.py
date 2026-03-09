"""Generate random squiggles - different loop every time!"""

from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar


def example_random_loops() -> None:
    """Generate 5 different random squiggles with same seed."""
    print('Generating 5 random squiggles from same seed...')
    print('(gradient stays the same, loop changes each time)')
    print()
    
    # Use random loop generation
    gen_config = AvatarGeneratorConfig(
        random_loop=True,  # ✨ Random squiggles!
        fps=30,
        duration=10.0,  # Shorter for demo
    )
    
    seed = 'random-demo'
    
    for i in range(1, 6):
        config = avatar(seed, gen_config)
        loop = config.loop_configs[0]
        
        print(f'{i}. {loop.loop_type.value:12} - ', end='')
        
        if loop.loop_type.value == 'epitrochoid':
            print(f'r_major={loop.r_major:.2f}, r_minor={loop.r_minor:.2f}')
        elif loop.loop_type.value == 'lissajous':
            print(f'freq_x={loop.freq_x:.1f}, freq_y={loop.freq_y:.1f}')
        elif loop.loop_type.value == 'rose':
            print(f'petals={loop.petals}')
        
        av = Avatar(config)
        av.save_gif(f'output/random_{i}.gif', progress=True, optimize=False)
        print()


def example_deterministic_vs_random() -> None:
    """Compare deterministic (same seed = same loop) vs random."""
    print('=' * 60)
    print('COMPARISON: Deterministic vs Random')
    print('=' * 60)
    print()
    
    seed = 'compare'
    
    # Deterministic (default)
    print('1. Deterministic (same seed = same loop):')
    config1 = avatar(seed)
    config2 = avatar(seed)
    print(f'   First:  {config1.loop_configs[0].loop_type.value}')
    print(f'   Second: {config2.loop_configs[0].loop_type.value}')
    print(f'   Same? {config1.loop_configs[0].loop_type == config2.loop_configs[0].loop_type} ✅')
    print()
    
    # Random
    print('2. Random (same seed = different loops):')
    gen_config = AvatarGeneratorConfig(random_loop=True)
    config1 = avatar(seed, gen_config)
    config2 = avatar(seed, gen_config)
    print(f'   First:  {config1.loop_configs[0].loop_type.value}')
    print(f'   Second: {config2.loop_configs[0].loop_type.value}')
    print(f'   Same? {config1.loop_configs[0].loop_type == config2.loop_configs[0].loop_type}')
    print('   (Probably different! Random each time) ✨')
    print()


if __name__ == '__main__':
    print('=' * 60)
    print('RANDOM SQUIGGLE GENERATION')
    print('=' * 60)
    print()
    
    example_deterministic_vs_random()
    example_random_loops()
    
    print()
    print('=' * 60)
    print('✨ Random squiggles generated!')
    print('Each one is different even with the same seed!')
    print('=' * 60)
