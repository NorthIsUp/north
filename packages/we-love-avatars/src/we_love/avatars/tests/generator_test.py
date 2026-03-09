"""Tests for seed-based avatar generation."""

from we_love.avatars.avatar import Avatar, AvatarConfig
from we_love.avatars.generator import AvatarGenerator, AvatarGeneratorConfig, avatar


def test_avatar_function() -> None:
    """Test the main avatar() function."""
    config = avatar('test@example.com')

    assert isinstance(config, AvatarConfig)
    assert config.width == 512
    assert config.height == 512
    assert len(config.loop_configs) > 0


def test_deterministic_generation() -> None:
    """Test that same seed produces same config."""
    seed = 'alice@example.com'

    config1 = avatar(seed)
    config2 = avatar(seed)

    # Should produce identical configs
    assert config1.gradient_config.gradient_type == config2.gradient_config.gradient_type
    assert len(config1.loop_configs) == len(config2.loop_configs)
    assert config1.loop_configs[0].loop_type == config2.loop_configs[0].loop_type
    assert config1.loop_configs[0].color == config2.loop_configs[0].color


def test_different_seeds_different_configs() -> None:
    """Test that different seeds produce different configs."""
    config1 = avatar('alice@example.com')
    config2 = avatar('bob@example.com')

    # Should produce different configs (extremely unlikely to be identical)
    # Check at least one property differs
    differs = (
        config1.gradient_config.gradient_type != config2.gradient_config.gradient_type
        or len(config1.loop_configs) != len(config2.loop_configs)
        or config1.loop_configs[0].loop_type != config2.loop_configs[0].loop_type
    )
    assert differs


def test_generator_class() -> None:
    """Test AvatarGenerator class."""
    generator = AvatarGenerator()
    config = generator.generate_config('test')

    assert isinstance(config, AvatarConfig)
    assert len(config.loop_configs) > 0


def test_generator_with_config() -> None:
    """Test generator with custom config."""
    gen_config = AvatarGeneratorConfig(
        width=256,
        height=256,
        fps=20,
        duration=2.0,
        enable_zoom=False,
        max_loops=1,
    )

    config = avatar('test', gen_config)

    assert config.width == 256
    assert config.height == 256
    assert config.fps == 20
    assert config.duration == 2.0
    assert len(config.loop_configs) == 1


def test_generator_generate_avatar() -> None:
    """Test generating full Avatar instance."""
    generator = AvatarGenerator()
    av = generator.generate('test@example.com')

    assert isinstance(av, Avatar)
    assert av.config.width == 512


def test_zoom_disabled() -> None:
    """Test generation with zoom disabled."""
    gen_config = AvatarGeneratorConfig(enable_zoom=False)
    config = avatar('test', gen_config)

    # When zoom disabled, offsets should be 0
    for loop in config.loop_configs:
        assert loop.offset_x == 0.0
        assert loop.offset_y == 0.0
        # Size should be < 1.0
        assert loop.size < 1.0


def test_wave_gradients_disabled() -> None:
    """Test generation with wave gradients disabled."""
    gen_config = AvatarGeneratorConfig(enable_wave_gradients=False)
    config = avatar('test', gen_config)

    # Should not use WAVE gradient type
    from we_love.avatars.gradient import GradientType

    assert config.gradient_config.gradient_type != GradientType.WAVE


def test_color_palette_generation() -> None:
    """Test that color palettes are generated."""
    config = avatar('test')

    assert len(config.gradient_config.colors) >= 2
    # Colors should be valid RGB tuples
    for color in config.gradient_config.colors:
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)


def test_loop_parameters() -> None:
    """Test that loop parameters are within valid ranges."""
    config = avatar('test')

    for loop in config.loop_configs:
        # Line width should be 5-10% of image width
        width_pct = (loop.width / config.width) * 100
        assert 5.0 <= width_pct <= 10.0, f'Width {loop.width}px is {width_pct:.1f}% of {config.width}px'
        assert 0.0 < loop.size <= 2.0
        assert 0.0 < loop.speed <= 2.0
        assert len(loop.color) == 3
        assert all(0 <= c <= 255 for c in loop.color)
