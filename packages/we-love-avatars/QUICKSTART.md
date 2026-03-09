# Quick Start Guide

Get started with `we-love-avatars` in 30 seconds!

## Installation

```bash
uv add we-love-avatars
```

## Your First Animated Avatar (One Line!)

```python
from we_love.avatars import avatar, Avatar

# Generate unique avatar from any string
Avatar(avatar('alice@example.com')).save_gif('alice.gif')
```

That's it! You now have a unique animated avatar. Same seed always produces the same avatar (perfect for user profiles!).

### With Parallel Rendering (FASTEST!)

For maximum speed, use all your CPU cores:

```python
Avatar(avatar('alice@example.com')).save_gif(
    'alice.gif',
    parallel=True,    # ⚡ Use all CPU cores
    optimize=False,   # ⚡ Fast encoding
    progress=True,    # See the speed!
)

# Shows: 
# Rendering frames (16 cores): 100%|████| 900/900 [00:02<00:00, 392fps]
# Encoding GIF (900 frames, 256 colors, fast)...
# ✓ Saved alice.gif (77.8 MB)
```

**Speed**: ~14s total (vs 23s sequential) - **1.7x faster!**

## More Examples

```python
# Different users get different avatars
Avatar(avatar('bob@example.com')).save_gif('bob.gif')
Avatar(avatar('charlie@example.com')).save_gif('charlie.gif')

# Username as seed
Avatar(avatar('cool_user_123')).save_gif('user.gif')
```

## Customize It

```python
from we_love.avatars import (
    Avatar,
    AvatarConfig,
    GradientConfig,
    GradientType,
    LoopConfig,
    LoopType,
)

# Custom configuration
config = AvatarConfig(
    width=512,
    height=512,
    fps=30,
    duration=2.0,
    
    # Gradient background
    gradient_config=GradientConfig(
        colors=[
            (255, 0, 128),   # Pink
            (128, 0, 255),   # Purple  
            (0, 128, 255),   # Blue
        ],
        gradient_type=GradientType.RADIAL,
    ),
    
    # Animated loops
    loop_configs=[
        LoopConfig(
            loop_type=LoopType.LISSAJOUS,
            color=(255, 255, 255),
            width=4,
            freq_x=3.0,
            freq_y=4.0,
        ),
    ],
)

avatar = Avatar(config)
avatar.save_gif('custom-avatar.gif')
```

## Try Different Loop Types

```python
# Circle
LoopConfig(loop_type=LoopType.CIRCLE)

# Rose curve (flower pattern)
LoopConfig(loop_type=LoopType.ROSE, petals=5)

# Spiral
LoopConfig(loop_type=LoopType.SPIRAL)

# Epitrochoid (spirograph)
LoopConfig(
    loop_type=LoopType.EPITROCHOID,
    r_major=0.3,
    r_minor=0.1,
)
```

## Multiple Loops

Stack multiple loops for complex animations:

```python
loop_configs=[
    LoopConfig(loop_type=LoopType.LISSAJOUS, size=0.7),
    LoopConfig(loop_type=LoopType.CIRCLE, size=0.4, speed=2.0),
    LoopConfig(loop_type=LoopType.ROSE, petals=5, size=0.5),
]
```

## Gradient Types

```python
# Linear gradient
GradientConfig(gradient_type=GradientType.LINEAR, angle=45)

# Radial gradient (from center)
GradientConfig(gradient_type=GradientType.RADIAL)

# Angular gradient (circular)
GradientConfig(gradient_type=GradientType.ANGULAR)

# Diagonal gradient
GradientConfig(gradient_type=GradientType.DIAGONAL)
```

## Run Examples

Using mise (recommended):

```bash
cd packages/we-love-avatars

# Quick demo
mise run demo

# All examples
mise run examples
```

Or check out the `examples/` directory:

```bash
cd examples
uv run python demo.py
uv run python basic.py
```

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Explore different loop types and parameters
- Experiment with color combinations
- Share your creations!

## Aurora Gradients (NEW!)

Get ethereal, multi-dimensional rainbow gradients:

```python
from we_love.avatars import Avatar, AvatarConfig, GradientConfig, GradientType, LoopConfig, LoopType

config = AvatarConfig(
    gradient_config=GradientConfig(
        colors=[
            (10, 80, 60),    # Deep teal
            (40, 120, 180),  # Sky blue
            (80, 60, 180),   # Purple
            (120, 200, 160), # Bright teal
        ],
        gradient_type=GradientType.AURORA,  # ✨ Aurora effect!
        smooth_loop=True,
    ),
    loop_configs=[
        LoopConfig(
            loop_type=LoopType.EPITROCHOID,
            size=1.6,
            offset_x=0.3,
        ),
    ],
)

Avatar(config).save_gif('aurora.gif')
```

Run examples: `mise run aurora`

## Tips

- Use 5+ colors for richest aurora effects
- Try `GradientType.AURORA` or `GradientType.PLASMA` for ethereal effects
- Keep loop count under 5 for best performance
- Start with `fps=30, duration=2.0` for smooth animations
- Optimize GIFs with `optimize=True` (default)
- Use `size=1.2-1.8` with offset for dramatic zoomed effects
