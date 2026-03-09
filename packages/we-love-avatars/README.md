# we-love-avatars

Create animated avatar images with moving loops and gradient backgrounds.

## Features

- **Multi-Dimensional Gradients**: Aurora (5 layers) and Plasma (7 layers) with temporal evolution
- **Organic Color Palettes**: Dynamic generator creates natural paths through color space
- **Parallel Rendering**: Use all CPU cores for 1.7-8x speedup (up to 746 fps on 16 cores!)
- **7 Gradient Types**: Linear, radial, angular, diagonal, wave, aurora, plasma
- **Vibrant Aurora Colors**: Borealis, northern lights, cosmic plasma, ethereal rainbows
- **Random Squiggles**: Optional random loop generation for endless variations
- **Smooth Transitions**: All color transitions < 33 units, loop-around < 30 units
- **Slow, Mesmerizing Animation**: 30-second full-circle loops for true aurora effect
- **Bold, Scalable Lines**: Line thickness automatically scales to 5-10% of image width (26-51px for 512x512)
- **Progress Bars**: Real-time feedback for rendering and encoding
- **Fast Encoding**: Optional optimize=False for 25% faster encoding
- **Multiple Loop Types**: Circles, Lissajous curves, spirals, rose curves, and epitrochoids
- **Zoom & Position**: Off-center placement and zoom for dramatic effects
- **Seed-Based Generation**: Deterministic unique avatars from any string
- **Easy Export**: Save as animated GIF or static PNG

## Installation

```bash
uv add we-love-avatars
```

## Quick Start

### The Simple Way (Recommended!)

Generate unique avatars from any string (email, username, etc.):

```python
from we_love.avatars import avatar, Avatar

# One line to generate a unique avatar from any string!
Avatar(avatar('alice@example.com')).save_gif('alice.gif')
```

That's it! Same seed = same avatar (deterministic). Different seeds = different avatars.

### Random Squiggles

Want different loops each time? Enable random generation:

```python
from we_love.avatars import avatar, Avatar, AvatarGeneratorConfig

# Gradient stays the same (from seed), loop randomizes!
gen_config = AvatarGeneratorConfig(random_loop=True)

# Generate 5 variations
for i in range(5):
    Avatar(avatar('my-seed', gen_config)).save_gif(f'variation_{i}.gif')
    # Each has a different squiggle! 🎲
```

### The Custom Way

Full control over every aspect:

```python
from we_love.avatars import Avatar, AvatarConfig, GradientConfig, LoopConfig, LoopType, GradientType

config = AvatarConfig(
    width=512,
    height=512,
    fps=30,
    duration=3.0,
    gradient_config=GradientConfig(
        colors=[
            (255, 0, 128),    # Pink
            (128, 0, 255),    # Purple
            (0, 128, 255),    # Blue
        ],
        gradient_type=GradientType.RADIAL,
        animate_shift=True,
    ),
    loop_configs=[
        LoopConfig(
            loop_type=LoopType.LISSAJOUS,
            color=(255, 255, 255),
            width=4,
            size=0.7,
            freq_x=3.0,
            freq_y=4.0,
        ),
    ],
)

avatar = Avatar(config)
avatar.save_gif('custom_avatar.gif')
```

## Loop Types

### Lissajous Curves
Beautiful parametric curves created by combining sine waves:

```python
from we_love.avatars import Loop, LoopConfig, LoopType

loop = Loop(LoopConfig(
    loop_type=LoopType.LISSAJOUS,
    freq_x=3.0,  # X frequency
    freq_y=4.0,  # Y frequency
    phase=0.5,   # Phase offset
))
```

### Rose Curves
Flower-like patterns with configurable petals:

```python
loop = Loop(LoopConfig(
    loop_type=LoopType.ROSE,
    petals=5,  # Number of petals
))
```

### Epitrochoid
Spirograph-like curves:

```python
loop = Loop(LoopConfig(
    loop_type=LoopType.EPITROCHOID,
    r_major=0.3,
    r_minor=0.1,
))
```

### Circle & Spiral
Classic shapes:

```python
# Simple circle
loop = Loop(LoopConfig(loop_type=LoopType.CIRCLE))

# Expanding spiral
loop = Loop(LoopConfig(loop_type=LoopType.SPIRAL))
```

## Gradient Types

```python
from we_love.avatars import Gradient, GradientConfig, GradientType

# Aurora borealis (multi-dimensional flowing waves)
gradient = Gradient(GradientConfig(
    gradient_type=GradientType.AURORA,
    colors=[(10, 80, 60), (40, 120, 180), (80, 60, 180)],
))

# Plasma (chaotic multi-frequency waves)
gradient = Gradient(GradientConfig(
    gradient_type=GradientType.PLASMA,
    colors=[(255, 60, 120), (200, 100, 255), (100, 150, 255)],
))

# Wave (asymmetric flowing gradient)
gradient = Gradient(GradientConfig(
    gradient_type=GradientType.WAVE,
    wave_frequency=2.5,
    wave_amplitude=0.4,
))

# Classic gradients
gradient = Gradient(GradientConfig(gradient_type=GradientType.LINEAR))
gradient = Gradient(GradientConfig(gradient_type=GradientType.RADIAL))
gradient = Gradient(GradientConfig(gradient_type=GradientType.ANGULAR))
```

## Multiple Loops

Combine multiple loops for more complex animations:

```python
config = AvatarConfig(
    loop_configs=[
        LoopConfig(
            loop_type=LoopType.LISSAJOUS,
            color=(255, 200, 200),
            freq_x=3.0,
            freq_y=4.0,
        ),
        LoopConfig(
            loop_type=LoopType.CIRCLE,
            color=(200, 200, 255),
            size=0.4,
            speed=2.0,
        ),
    ],
)
```

## Advanced Usage

### Render Individual Frames

```python
avatar = Avatar()

# Render a specific frame
frame = avatar.render_frame(15)

# Get all frames (with optional progress bar)
frames = avatar.render_all_frames(progress=True)

# Save a single frame
avatar.save_png('frame.png', frame=0)
```

### Parallel Rendering & Fast Encoding

Use all your CPU cores for maximum speed:

```python
from we_love.avatars import avatar, Avatar

config = avatar('user@example.com')
av = Avatar(config)

# Parallel rendering + fast encoding = FASTEST!
av.save_gif('avatar.gif', parallel=True, optimize=False, progress=True)

# Output:
# Rendering frames (16 cores): 100%|████| 900/900 [00:02<00:00, 392fps]
# Encoding GIF (900 frames, 256 colors, fast)...
# ✓ Saved output/avatar.gif (77.8 MB)
```

**Speed comparison** (16 cores, 900 frames):
- Sequential, optimize: ~26s, 22 MB
- Sequential, fast: ~23s, 26 MB
- **Parallel, fast**: ~14s, 78 MB ⚡ **1.9x faster!**

For development, use `parallel=True, optimize=False` to max out your CPU!

### Custom Colors

```python
from we_love.avatars import Gradient

# Create gradient from custom colors
gradient = Gradient.from_colors(
    colors=[
        (255, 0, 0),    # Red
        (255, 165, 0),  # Orange
        (255, 255, 0),  # Yellow
        (0, 255, 0),    # Green
        (0, 0, 255),    # Blue
        (238, 130, 238),# Violet
    ],
    gradient_type=GradientType.LINEAR,
)
```

## Running Examples

Using mise (recommended):

```bash
cd packages/we-love-avatars

# Variety showcase (100 random UUIDs - see the full range!)
mise run variety-quick      # 10 samples (quick preview)
mise run variety-sample     # 20 samples (good variety)
mise run variety            # 100 avatars (full showcase)

# Aurora gradients (ethereal multi-dimensional rainbows)
mise run aurora

# Seed-based generation (generate from strings)
mise run seed-based

# Random squiggles (different loop each time)
mise run random

# Performance benchmark
mise run benchmark

# Basic examples
mise run demo
mise run examples
mise run enhanced

# Open output directory
mise run open-output
```

Or directly with uv:

```bash
cd packages/we-love-avatars

# Run demo
uv run python examples/demo.py

# Run all examples
uv run python examples/basic.py
```

See the `examples/` directory for more usage examples.

## Development

```bash
# Run tests
mise run test

# Clean generated files
mise run clean

# Clean everything including .venv
mise run clean-all
```

## License

MIT
