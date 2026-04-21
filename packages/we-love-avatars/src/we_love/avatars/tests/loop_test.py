"""Tests for loop generation."""

import pytest
from PIL import Image
from we_love.avatars.loop import Loop, LoopConfig, LoopType


@pytest.fixture
def base_image() -> Image.Image:
    """Create a base image for testing."""
    return Image.new("RGB", (200, 200), color=(0, 0, 0))


def test_loop_default_config() -> None:
    """Test loop with default configuration."""
    loop = Loop()
    assert loop.config is not None
    assert loop.config.loop_type == LoopType.LISSAJOUS


def test_loop_render_circle(base_image: Image.Image) -> None:
    """Test rendering a circle loop."""
    config = LoopConfig(loop_type=LoopType.CIRCLE)
    loop = Loop(config)
    img = loop.render(base_image)

    assert isinstance(img, Image.Image)
    assert img.size == base_image.size


def test_loop_render_lissajous(base_image: Image.Image) -> None:
    """Test rendering a Lissajous curve."""
    config = LoopConfig(
        loop_type=LoopType.LISSAJOUS,
        freq_x=3.0,
        freq_y=4.0,
    )
    loop = Loop(config)
    img = loop.render(base_image)

    assert img.size == base_image.size


def test_loop_render_spiral(base_image: Image.Image) -> None:
    """Test rendering a spiral."""
    config = LoopConfig(loop_type=LoopType.SPIRAL)
    loop = Loop(config)
    img = loop.render(base_image)

    assert img.size == base_image.size


def test_loop_render_rose(base_image: Image.Image) -> None:
    """Test rendering a rose curve."""
    config = LoopConfig(
        loop_type=LoopType.ROSE,
        petals=5,
    )
    loop = Loop(config)
    img = loop.render(base_image)

    assert img.size == base_image.size


def test_loop_render_epitrochoid(base_image: Image.Image) -> None:
    """Test rendering an epitrochoid."""
    config = LoopConfig(
        loop_type=LoopType.EPITROCHOID,
        r_major=0.3,
        r_minor=0.1,
    )
    loop = Loop(config)
    img = loop.render(base_image)

    assert img.size == base_image.size


def test_loop_animation(base_image: Image.Image) -> None:
    """Test loop animation across frames."""
    config = LoopConfig(loop_type=LoopType.CIRCLE, speed=1.0)
    loop = Loop(config)

    frame1 = loop.render(base_image, frame=0, total_frames=10)
    frame2 = loop.render(base_image, frame=5, total_frames=10)

    # Frames should be different when animating
    assert list(frame1.getdata()) != list(frame2.getdata())


def test_loop_color(base_image: Image.Image) -> None:
    """Test loop with custom color."""
    config = LoopConfig(
        loop_type=LoopType.CIRCLE,
        color=(255, 0, 0),
    )
    loop = Loop(config)
    img = loop.render(base_image)

    # Check that red pixels exist in the image
    pixels = list(img.getdata())
    assert any(r > 200 for r, _g, _b in pixels)


def test_loop_size(base_image: Image.Image) -> None:
    """Test loop with different sizes."""
    small_config = LoopConfig(loop_type=LoopType.CIRCLE, size=0.3)
    large_config = LoopConfig(loop_type=LoopType.CIRCLE, size=0.8)

    small_loop = Loop(small_config)
    large_loop = Loop(large_config)

    small_img = small_loop.render(base_image)
    large_img = large_loop.render(base_image)

    # Both should render successfully
    assert small_img.size == base_image.size
    assert large_img.size == base_image.size


def test_loop_width(base_image: Image.Image) -> None:
    """Test loop with different line widths."""
    config = LoopConfig(
        loop_type=LoopType.CIRCLE,
        width=10,
    )
    loop = Loop(config)
    img = loop.render(base_image)

    assert img.size == base_image.size


def test_loop_offset(base_image: Image.Image) -> None:
    """Test loop with offset positioning."""
    config = LoopConfig(
        loop_type=LoopType.CIRCLE,
        offset_x=0.5,
        offset_y=-0.3,
    )
    loop = Loop(config)
    img = loop.render(base_image)

    assert img.size == base_image.size


def test_loop_zoom(base_image: Image.Image) -> None:
    """Test loop with zoom (size > 1.0)."""
    config = LoopConfig(
        loop_type=LoopType.EPITROCHOID,
        size=2.0,  # Zoomed in
        offset_x=0.4,
        offset_y=-0.4,
    )
    loop = Loop(config)
    img = loop.render(base_image)

    assert img.size == base_image.size
