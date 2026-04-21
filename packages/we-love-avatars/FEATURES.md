# New Features

## 🎨 Enhanced Gradient System

### Wave Gradients
Create asymmetric, flowing gradients with configurable frequency and amplitude:

```python
from we_love.avatars import GradientConfig, GradientType

gradient = GradientConfig(
    colors=[
        (20, 20, 40),
        (80, 40, 120),
        (120, 80, 160),
    ],
    gradient_type=GradientType.WAVE,
    wave_frequency=2.5,  # How many waves
    wave_amplitude=0.4,  # Wave intensity
    angle=45,  # Wave direction
)
```

### Smooth Looping
No more harsh transitions when animations loop! Set `smooth_loop=True` for butter-smooth gradients:

```python
gradient = GradientConfig(
    colors=[(10, 10, 30), (50, 90, 140), (10, 10, 30)],
    animate_shift=True,
    smooth_loop=True,  # ✨ Smooth, seamless looping
)
```

**Before:** Gradient jumps when looping back to start  
**After:** Smooth sine-wave transition, perfectly seamless

## 🎯 Loop Positioning & Zoom

### Offset Positioning
Position loops anywhere in the frame - perfect for creating off-center, zoomed-in effects:

```python
from we_love.avatars import LoopConfig, LoopType

loop = LoopConfig(
    loop_type=LoopType.EPITROCHOID,
    size=1.8,  # Zoom in (>1.0 shows only part of the curve)
    offset_x=0.4,  # Move right (range: -1 to 1)
    offset_y=-0.3,  # Move up (range: -1 to 1)
)
```

### Zoomed Curves
Set `size > 1.0` to zoom in and reveal intricate details:

```python
loop = LoopConfig(
    loop_type=LoopType.EPITROCHOID,
    size=2.0,  # 2x zoom - only see partial curve
    offset_x=0.5,
    offset_y=-0.4,
)
```

## 🎬 Complete Example

Create a stunning zoomed epitrochoid with wave gradient:

```python
from we_love.avatars import Avatar, AvatarConfig, GradientConfig, GradientType, LoopConfig, LoopType

config = AvatarConfig(
    width=512,
    height=512,
    fps=30,
    duration=4.0,
    # Smooth wave gradient
    gradient_config=GradientConfig(
        colors=[
            (20, 20, 40),
            (80, 40, 120),
            (120, 80, 160),
            (60, 100, 180),
        ],
        gradient_type=GradientType.WAVE,
        wave_frequency=2.5,
        wave_amplitude=0.4,
        angle=45,
        smooth_loop=True,  # ✨ Seamless looping
    ),
    # Zoomed, off-center epitrochoid
    loop_configs=[
        LoopConfig(
            loop_type=LoopType.EPITROCHOID,
            color=(255, 240, 200),
            width=4,
            r_major=0.4,
            r_minor=0.15,
            size=1.8,  # ✨ Zoomed in
            offset_x=0.4,  # ✨ Off-center
            offset_y=-0.3,
            speed=0.8,
        ),
    ],
)

avatar = Avatar(config)
avatar.save_gif("beautiful_avatar.gif")
```

## 📊 All Gradient Types

1. **LINEAR** - Straight line gradient
2. **RADIAL** - Center to edge
3. **ANGULAR** - Circular/rotating
4. **DIAGONAL** - Corner to corner
5. **WAVE** - ✨ NEW! Asymmetric flowing waves

## 🚀 Try the Enhanced Examples

```bash
# Run the new enhanced examples
mise run enhanced

# Or directly
uv run python examples/enhanced.py
```

This generates:
- `enhanced_epitrochoid.gif` - Zoomed wave gradient epitrochoid
- `smooth_radial.gif` - Smooth radial with offset
- `double_epitrochoid.gif` - Two zoomed curves
- `lissajous_wave.gif` - Lissajous with wave gradient

## 🎨 Color Tips

For smooth, professional gradients:

1. **Use 3-5 colors** for best results
2. **Repeat first/last color** for seamless loops:
   ```python
   colors = [(30, 30, 60), (100, 80, 140), (30, 30, 60)]
   ```
3. **Stay in same hue family** for cohesive look
4. **Always enable smooth_loop** for animations
