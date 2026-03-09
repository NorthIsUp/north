"""Example of using progress bars during avatar generation."""

from we_love.avatars import avatar, Avatar


def example_with_progress() -> None:
    """Generate an avatar with a progress bar."""
    print('Generating avatar with progress bar...')
    print()
    
    config = avatar('progress-demo')
    print(f'Config: {config.duration}s @ {config.fps}fps = {int(config.duration * config.fps)} frames')
    print()
    
    av = Avatar(config)
    
    # Enable progress bar + fast encoding for development
    av.save_gif('output/with_progress.gif', progress=True, optimize=False)
    
    print()
    print('✓ Complete! Avatar saved to output/with_progress.gif')


def example_without_progress() -> None:
    """Generate without progress bar (silent)."""
    print('\nGenerating avatar WITHOUT progress bar (silent)...')
    
    config = avatar('no-progress')
    av = Avatar(config)
    
    # Default behavior: no progress bar
    av.save_gif('output/without_progress.gif')
    
    print('✓ Complete! Avatar saved to output/without_progress.gif')


def example_batch_generation() -> None:
    """Generate multiple avatars with progress bars."""
    print('\nBatch generation with progress bars...')
    print()
    
    users = ['alice', 'bob', 'charlie']
    
    for user in users:
        print(f'Generating for {user}:')
        config = avatar(user)
        av = Avatar(config)
        av.save_gif(f'output/batch_{user}.gif', progress=True)
        print()


if __name__ == '__main__':
    print('=' * 60)
    print('PROGRESS BAR EXAMPLES')
    print('=' * 60)
    print()
    
    example_with_progress()
    example_without_progress()
    example_batch_generation()
    
    print()
    print('=' * 60)
    print('✨ All examples complete!')
    print('=' * 60)
