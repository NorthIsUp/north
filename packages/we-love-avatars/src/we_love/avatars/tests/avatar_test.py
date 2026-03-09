"""Tests for avatar generation."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from we_love.avatars.avatar import Avatar, AvatarConfig
from we_love.avatars.gradient import GradientConfig, GradientType
from we_love.avatars.loop import LoopConfig, LoopType


def test_avatar_default_config() -> None:
    """Test avatar with default configuration."""
    avatar = Avatar()
    assert avatar.config is not None
    assert avatar.config.width == 512
    assert avatar.config.height == 512


def test_avatar_custom_config() -> None:
    """Test avatar with custom configuration."""
    config = AvatarConfig(
        width=256,
        height=256,
        fps=20,
        duration=1.0,
    )
    avatar = Avatar(config)

    assert avatar.config.width == 256
    assert avatar.config.height == 256
    assert avatar.config.fps == 20


def test_avatar_total_frames() -> None:
    """Test total frames calculation."""
    config = AvatarConfig(fps=30, duration=2.0)
    avatar = Avatar(config)

    assert avatar.total_frames == 60


def test_avatar_render_frame() -> None:
    """Test rendering a single frame."""
    avatar = Avatar()
    frame = avatar.render_frame(0)

    assert isinstance(frame, Image.Image)
    assert frame.size == (512, 512)


def test_avatar_render_all_frames() -> None:
    """Test rendering all frames."""
    config = AvatarConfig(fps=10, duration=0.5)
    avatar = Avatar(config)
    frames = avatar.render_all_frames()

    assert len(frames) == 5
    assert all(isinstance(f, Image.Image) for f in frames)


def test_avatar_save_gif() -> None:
    """Test saving avatar as GIF."""
    config = AvatarConfig(
        width=100,
        height=100,
        fps=10,
        duration=0.3,
    )
    avatar = Avatar(config)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / 'test.gif'
        avatar.save_gif(output_path)

        assert output_path.exists()
        # Verify it's a valid GIF
        img = Image.open(output_path)
        assert img.format == 'GIF'


def test_avatar_save_png() -> None:
    """Test saving avatar as PNG."""
    config = AvatarConfig(width=100, height=100)
    avatar = Avatar(config)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / 'test.png'
        avatar.save_png(output_path)

        assert output_path.exists()
        # Verify it's a valid PNG
        img = Image.open(output_path)
        assert img.format == 'PNG'


def test_avatar_with_gradient() -> None:
    """Test avatar with custom gradient."""
    config = AvatarConfig(
        gradient_config=GradientConfig(
            colors=[(255, 0, 0), (0, 0, 255)],
            gradient_type=GradientType.RADIAL,
        ),
    )
    avatar = Avatar(config)
    frame = avatar.render_frame(0)

    assert frame.size == (512, 512)


def test_avatar_with_loops() -> None:
    """Test avatar with multiple loops."""
    config = AvatarConfig(
        loop_configs=[
            LoopConfig(loop_type=LoopType.CIRCLE),
            LoopConfig(loop_type=LoopType.LISSAJOUS),
        ],
    )
    avatar = Avatar(config)

    assert len(avatar.loops) == 2
    frame = avatar.render_frame(0)
    assert frame.size == (512, 512)


def test_avatar_path_creation() -> None:
    """Test that avatar creates parent directories."""
    config = AvatarConfig(width=50, height=50, fps=5, duration=0.2)
    avatar = Avatar(config)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / 'nested' / 'dir' / 'test.gif'
        avatar.save_gif(output_path)

        assert output_path.exists()


def test_avatar_different_dimensions() -> None:
    """Test avatar with non-square dimensions."""
    config = AvatarConfig(width=300, height=200)
    avatar = Avatar(config)
    frame = avatar.render_frame(0)

    assert frame.size == (300, 200)
