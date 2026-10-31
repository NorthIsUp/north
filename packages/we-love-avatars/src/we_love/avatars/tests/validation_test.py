"""Validate rendering inputs before allocating frames or dividing time."""

import pytest
from pydantic import ValidationError
from we_love.avatars import Avatar, AvatarConfig, AvatarGeneratorConfig, GradientConfig


@pytest.mark.parametrize("field", ["width", "height", "fps", "duration"])
def test_invalid_render_settings_fail_early(field: str) -> None:
    """Zero and negative dimensions/timing must not reach Pillow or frame encoding."""
    for value in (0, -1):
        with pytest.raises(ValidationError):
            AvatarConfig.model_validate({field: value})
        with pytest.raises(ValidationError):
            AvatarGeneratorConfig.model_validate({field: value})


def test_subframe_animation_has_a_renderable_frame() -> None:
    """A valid short animation must produce one frame rather than an empty GIF input."""
    avatar = Avatar(AvatarConfig(width=8, height=8, fps=1, duration=0.01, loop_configs=[]))
    assert avatar.total_frames == 1
    assert len(avatar.render_all_frames()) == 1


@pytest.mark.parametrize("colors", [[], [(1, 2, 3)], [(0, 0, 0), (256, 0, 0)]])
def test_invalid_gradient_palettes_fail_early(colors: list[tuple[int, int, int]]) -> None:
    """Unusable palettes must raise validation errors instead of indexing or overflow failures."""
    with pytest.raises(ValidationError):
        GradientConfig(colors=colors)
