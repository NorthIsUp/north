"""Generate 100 random avatars to showcase variety."""

import uuid
from collections import Counter

from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar


def generate_variety_showcase(count: int = 100) -> None:
    """Generate many avatars to showcase variety.

    Args:
        count: Number of avatars to generate
    """
    print('=' * 60)
    print(f'VARIETY SHOWCASE - Generating {count} Random Avatars')
    print('=' * 60)
    print()
    
    # Use faster settings for quick generation
    gen_config = AvatarGeneratorConfig(
        fps=15,
        duration=3.0,  # Quick 3-second loops
        width=256,      # Smaller for faster generation
        height=256,
    )
    
    # Track variety
    gradient_types = Counter()
    loop_types = Counter()
    
    print(f'Generating {count} avatars from random UUIDs...')
    print()
    
    for i in range(count):
        # Generate random UUID as seed
        seed = str(uuid.uuid4())
        
        # Generate avatar config
        config = avatar(seed, gen_config)
        
        # Track what we got
        grad_type = config.gradient_config.gradient_type.value
        loop_type = config.loop_configs[0].loop_type.value
        
        gradient_types[grad_type] += 1
        loop_types[loop_type] += 1
        
        # Generate avatar
        av = Avatar(config)
        av.save_gif(
            f'output/variety/avatar_{i:03d}.gif',
            parallel=True,
            optimize=False,
        )
        
        # Progress update every 10
        if (i + 1) % 10 == 0:
            print(f'  ✓ Generated {i + 1}/{count} avatars...')
    
    print()
    print('=' * 60)
    print('VARIETY ANALYSIS')
    print('=' * 60)
    print()
    
    print('Gradient Type Distribution:')
    for grad_type, count_val in gradient_types.most_common():
        pct = (count_val / count) * 100
        bar = '█' * int(pct / 2)
        print(f'  {grad_type:10} {bar:25} {count_val:3} ({pct:5.1f}%)')
    
    print()
    print('Loop Type Distribution:')
    for loop_type, count_val in loop_types.most_common():
        pct = (count_val / count) * 100
        bar = '█' * int(pct / 2)
        print(f'  {loop_type:12} {bar:25} {count_val:3} ({pct:5.1f}%)')
    
    print()
    print('=' * 60)
    print(f'✨ {count} unique avatars generated!')
    print('=' * 60)
    print()
    print(f'View them in: output/variety/')
    print(f'Each one is unique with different:')
    print(f'  - Gradient colors (organic paths)')
    print(f'  - Gradient type (aurora/plasma/wave/radial)')
    print(f'  - Loop type (epitrochoid/lissajous/rose)')
    print(f'  - Loop parameters (frequencies/petals/radii)')
    print(f'  - Position & size')


def generate_sample_grid(count: int = 20) -> None:
    """Generate a smaller sample for quick preview.

    Args:
        count: Number of samples (default: 20)
    """
    print(f'Generating {count} sample avatars for quick preview...')
    print()
    
    gen_config = AvatarGeneratorConfig(
        fps=10,
        duration=2.0,
        width=256,
        height=256,
    )
    
    for i in range(count):
        seed = str(uuid.uuid4())
        config = avatar(seed, gen_config)
        
        grad = config.gradient_config.gradient_type.value
        loop = config.loop_configs[0].loop_type.value
        
        print(f'{i+1:2}. {seed[:8]}... → {grad:8} + {loop:12}')
        
        Avatar(config).save_gif(
            f'output/variety/sample_{i:02d}.gif',
            parallel=True,
            optimize=False,
        )
    
    print()
    print(f'✨ {count} samples in output/variety/')


if __name__ == '__main__':
    import sys
    
    # Check if user wants quick sample or full showcase
    if len(sys.argv) > 1 and sys.argv[1] == 'sample':
        generate_sample_grid(20)
    elif len(sys.argv) > 1 and sys.argv[1] == 'quick':
        generate_sample_grid(10)
    else:
        # Full showcase
        generate_variety_showcase(100)
