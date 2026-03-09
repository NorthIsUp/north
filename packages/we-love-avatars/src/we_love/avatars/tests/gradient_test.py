"""Tests for gradient generation."""

import pytest
from PIL import Image

from we_love.avatars.gradient import Gradient, GradientConfig, GradientType


def test_gradient_default_config() -> None:
    """Test gradient with default configuration."""
    gradient = Gradient()
    assert gradient.config is not None
    assert len(gradient.config.colors) >= 2


def test_gradient_render_linear() -> None:
    """Test rendering a linear gradient."""
    config = GradientConfig(
        colors=[(255, 0, 0), (0, 0, 255)],
        gradient_type=GradientType.LINEAR,
    )
    gradient = Gradient(config)
    img = gradient.render(100, 100)

    assert isinstance(img, Image.Image)
    assert img.size == (100, 100)
    assert img.mode == 'RGB'


def test_gradient_render_radial() -> None:
    """Test rendering a radial gradient."""
    config = GradientConfig(
        colors=[(255, 255, 255), (0, 0, 0)],
        gradient_type=GradientType.RADIAL,
    )
    gradient = Gradient(config)
    img = gradient.render(200, 200)

    assert img.size == (200, 200)


def test_gradient_render_angular() -> None:
    """Test rendering an angular gradient."""
    config = GradientConfig(
        colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
        gradient_type=GradientType.ANGULAR,
    )
    gradient = Gradient(config)
    img = gradient.render(150, 150)

    assert img.size == (150, 150)


def test_gradient_animation() -> None:
    """Test gradient animation across frames."""
    config = GradientConfig(
        colors=[(255, 0, 0), (0, 0, 255)],
        animate_shift=True,
        smooth_loop=False,  # Use linear shift for predictable test
    )
    gradient = Gradient(config)

    frame1 = gradient.render(100, 100, frame=0, total_frames=10)
    frame2 = gradient.render(100, 100, frame=5, total_frames=10)

    # Frames should be different when animating
    assert list(frame1.getdata()) != list(frame2.getdata())


def test_gradient_from_colors() -> None:
    """Test creating gradient from colors."""
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    gradient = Gradient.from_colors(colors, GradientType.LINEAR)

    assert gradient.config.colors == colors
    assert gradient.config.gradient_type == GradientType.LINEAR


def test_gradient_insufficient_colors() -> None:
    """Test gradient with insufficient colors raises error."""
    config = GradientConfig(colors=[(255, 0, 0)])
    gradient = Gradient(config)

    with pytest.raises(ValueError, match='At least 2 colors required'):
        gradient.render(100, 100)


def test_gradient_angle() -> None:
    """Test gradient with different angles."""
    config = GradientConfig(
        colors=[(255, 0, 0), (0, 0, 255)],
        gradient_type=GradientType.LINEAR,
        angle=45.0,
    )
    gradient = Gradient(config)
    img = gradient.render(100, 100)

    assert img.size == (100, 100)


def test_gradient_smooth_loop() -> None:
    """Test gradient with smooth looping animation."""
    config = GradientConfig(
        colors=[(255, 0, 0), (0, 0, 255)],
        animate_shift=True,
        smooth_loop=True,
    )
    gradient = Gradient(config)

    frame1 = gradient.render(100, 100, frame=0, total_frames=60)
    frame2 = gradient.render(100, 100, frame=15, total_frames=60)

    # Frames should be different when animating
    assert list(frame1.getdata()) != list(frame2.getdata())


def test_gradient_wave() -> None:
    """Test wave gradient type."""
    config = GradientConfig(
        colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
        gradient_type=GradientType.WAVE,
        wave_frequency=2.0,
        wave_amplitude=0.3,
    )
    gradient = Gradient(config)
    img = gradient.render(150, 150)

    assert img.size == (150, 150)
