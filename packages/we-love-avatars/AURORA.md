# Aurora-Inspired Gradients

Multi-dimensional, ethereal rainbow gradients reminiscent of the aurora borealis!

## ✨ New Gradient Types

### AURORA - Aurora Borealis Effect
Multi-dimensional flowing waves that create ethereal, shifting patterns like the northern lights.

```python
from we_love.avatars import Avatar, AvatarConfig, GradientConfig, GradientType, LoopConfig, LoopType

config = AvatarConfig(
    gradient_config=GradientConfig(
        colors=[
            (10, 80, 60),  # Deep teal
            (40, 120, 180),  # Sky blue
            (80, 60, 180),  # Purple
            (120, 200, 160),  # Bright teal
            (40, 100, 140),  # Ocean blue
        ],
        gradient_type=GradientType.AURORA,
        smooth_loop=True,
    ),
    loop_configs=[
        LoopConfig(
            loop_type=LoopType.EPITROCHOID,
            size=1.6,
            offset_x=0.3,
            offset_y=-0.2,
        ),
    ],
)

Avatar(config).save_gif("aurora.gif")
```

**How it works**: Combines **5 wave layers** (horizontal, vertical, diagonal, radial, modulation) with **temporal evolution** - patterns evolve over 30 seconds, not just shift! Creates truly multi-dimensional aurora effect.

### PLASMA - Cosmic Plasma Effect
Chaotic multi-frequency waves creating energetic, plasma-like gradients.

```python
gradient_config = GradientConfig(
    colors=[
        (255, 60, 120),  # Hot pink
        (200, 100, 255),  # Violet
        (100, 150, 255),  # Sky blue
        (120, 255, 200),  # Cyan
        (255, 200, 100),  # Gold
    ],
    gradient_type=GradientType.PLASMA,
    smooth_loop=True,
)
```

**How it works**: Uses **7 different wave layers** (4 directional + radial + angular + non-linear XY interaction) with **independent time speeds** - creates chaotic, energetic plasma that evolves in multiple dimensions!

## 🎨 Aurora Color Palettes

The generator now includes 6 ultra-smooth, aurora-inspired color palettes with 8 colors each for seamless transitions (all adjacent colors < 35 units apart):

### 1. Aurora Borealis (green → teal → blue → purple)
Smooth progression through classic northern lights colors:
```python
[(10, 80, 60), (20, 100, 100), (40, 120, 140), (60, 120, 180), (80, 100, 180), (90, 80, 170), (70, 100, 150)]
```

### 2. Northern Lights (pink → purple → blue)
Smooth pink-to-purple gradations with NO harsh transitions:
```python
[(140, 80, 160), (130, 70, 170), (120, 60, 180), (110, 60, 190), (100, 70, 200), (90, 80, 200), (110, 70, 185)]
```

### 3. Ethereal Rainbow (smooth spectrum)
Gentle progression through soft rainbow hues:
```python
[(200, 80, 140), (180, 100, 180), (140, 120, 220), (100, 150, 240), (120, 200, 220), (140, 220, 200), (160, 180, 180)]
```

### 4. Cosmic Teal (cyan → blue → purple)
Smooth aquatic to celestial transition:
```python
[(60, 180, 200), (70, 160, 210), (80, 140, 220), (90, 120, 220), (100, 100, 210), (110, 90, 200), (80, 130, 215)]
```

### 5. Mystic Violet (smooth purple gradations)
Seamless deep-to-light purple progression:
```python
[(80, 40, 120), (100, 50, 150), (120, 60, 180), (140, 80, 200), (150, 100, 210), (130, 70, 190), (110, 55, 165)]
```

### 6. Ocean Aurora (blue → teal → cyan)
Smooth oceanic color flow:
```python
[(40, 100, 160), (50, 130, 180), (60, 160, 200), (70, 180, 210), (80, 200, 200), (70, 190, 190), (60, 170, 180)]
```

## 🌈 All 7 Gradient Types

1. **AURORA** ✨ - Multi-dimensional flowing waves (NEW!)
2. **PLASMA** ✨ - Chaotic multi-frequency waves (NEW!)
3. **WAVE** - Asymmetric wave gradient
4. **RADIAL** - Center to edge
5. **ANGULAR** - Circular/rotating
6. **LINEAR** - Straight line
7. **DIAGONAL** - Corner to corner

## 📊 What Changed

### Before
- 4-5 gradient types
- Muted, single-dimensional colors
- Simple color palettes (2-4 colors)
- Possible harsh color transitions

### After
- 7 gradient types with multi-dimensional effects
- Vibrant, aurora-inspired palettes
- Rich color palettes (7 colors per palette)
- Smooth, gradual color transitions (no harsh jumps)
- Aurora and Plasma gradients create flowing, ethereal effects

## 🎯 Seed-Based Generation

The seed-based generator now preferentially creates aurora/plasma gradients:

```python
from we_love.avatars import avatar, Avatar

# These will likely get aurora or plasma gradients
Avatar(avatar("alice")).save_gif("alice.gif")
Avatar(avatar("bob")).save_gif("bob.gif")
```

Priority gradient types (when `enable_wave_gradients=True`):
1. AURORA (highest priority)
2. PLASMA
3. WAVE
4. RADIAL

## 🚀 Examples

Run the aurora examples:

```bash
mise run aurora

# Or directly:
uv run python examples/aurora.py
```

This generates:
- `aurora_borealis.gif` - Classic green-blue-purple aurora
- `northern_lights.gif` - Pink-purple ethereal glow
- `cosmic_plasma.gif` - Full spectrum chaotic plasma
- `ethereal_rainbow.gif` - Multi-color aurora
- `mystic_ocean.gif` - Teal-cyan ocean aurora

## 💡 Tips for Best Results

1. **Use 5+ colors** for richest aurora effects
2. **Mix complementary colors** (blue+orange, purple+yellow)
3. **Slow animations (20-30 seconds)** for mesmerizing aurora flow
4. **Full circle progression** - gradients flow continuously without bouncing
5. **Combine with zoomed loops** for dramatic effects
6. **Try different loop types** - epitrochoid and Lissajous work especially well
7. **Line thickness scales automatically** - 5-10% of image width for bold, prominent visibility at any size

## 🎨 Custom Aurora Palettes

Create your own:

```python
gradient_config = GradientConfig(
    colors=[
        (your_color_1),
        (your_color_2),
        (your_color_3),
        (your_color_4),
        (your_color_5),
    ],
    gradient_type=GradientType.AURORA,
    smooth_loop=True,
)
```

**Pro tip**: Use colors from the same temperature range (warm or cool) for harmonious results, or mix temperatures for dramatic contrast!
