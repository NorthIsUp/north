# Multi-Dimensional Gradients

Aurora and Plasma gradients now evolve across **multiple dimensions** over time!

## What is Multi-Dimensional?

Instead of just shifting a static gradient pattern, the gradient **itself evolves** with layered wave interactions across:

- **Spatial dimensions**: X, Y, Radial, Angular
- **Temporal dimension**: Patterns change over 30 seconds
- **Interaction dimension**: Waves modulate each other

## Aurora Gradient (5 Layers)

The aurora gradient combines **5 independent wave layers**:

### Layer 1: Horizontal Waves
```python
wave_h = sin(x·π·3.2 + y·π·1.8 + time·0.7)
```
Flows left-to-right with gentle temporal evolution

### Layer 2: Vertical Waves
```python
wave_v = cos(y·π·2.7 + x·π·1.3 + time·1.2)
```
Flows top-to-bottom with faster time evolution

### Layer 3: Diagonal Waves
```python
wave_d = sin((x+y)·π·2.3 + time·0.5)
```
Diagonal flow across the image

### Layer 4: Radial Waves (Depth)
```python
r = √[(x-0.5)² + (y-0.5)²]
wave_r = cos(r·π·4.5 + time·0.9)
```
Creates depth perception - waves emanate from center

### Layer 5: Modulation
```python
mod = sin(x·π·1.5) · cos(y·π·1.8)
```
Modulates other layers for complex interactions

### Combined
```python
gradient = (
    wave_h × 0.28 +
    wave_v × 0.26 +
    wave_d × 0.22 +
    wave_r × 0.14 +
    mod × wave_h × 0.10
)
```

**Result**: Flowing, organic patterns that evolve like real aurora borealis!

## Plasma Gradient (7 Layers)

The plasma gradient is even more chaotic with **7 interacting layers**:

### Layers 1-4: Directional Waves
```python
p1 = sin(x·π·4.3 + time·1.5)  # Horizontal, fast time
p2 = sin(y·π·3.7 + time·1.1)  # Vertical, medium time
p3 = sin((x+y)·π·2.5 + time·0.8)  # Diagonal up
p4 = cos((x-y)·π·3.1 - time·1.3)  # Diagonal down, reverse time
```

### Layer 5: Radial (Depth)
```python
r = √[(x-0.5)² + (y-0.5)²]
p5 = sin(r·π·5.2 + time·2.0)  # Very fast time evolution
```

### Layer 6: Angular (Rotation)
```python
angle = arctan2(y-0.5, x-0.5)
p6 = cos(angle·3.0 + time·0.6)  # Rotating pattern
```

### Layer 7: Non-Linear Interaction
```python
p7 = sin(x·y·π·6.0 + time)  # Complex XY interaction
```

### Combined
```python
gradient = (
    p1 × 0.20 + p2 × 0.18 + p3 × 0.16 + p4 × 0.14 +
    p5 × 0.12 + p6 × 0.12 + p7 × 0.08
)
```

**Result**: Chaotic, energetic plasma with depth and rotation!

## Key Differences from Simple Gradients

### Simple Gradient (e.g., LINEAR)
- **Dimensions**: 1 (just shifts)
- **Layers**: 1 (single gradient)
- **Evolution**: None (static pattern)
- **Effect**: Basic color progression

### Multi-Dimensional (AURORA/PLASMA)
- **Dimensions**: 5-7 (spatial + temporal)
- **Layers**: 5-7 (overlapping waves)
- **Evolution**: Complex (patterns morph over time)
- **Effect**: Living, breathing, organic

## Visual Impact

### Before (Simple RADIAL)
```
Frame 0:   [Static radial gradient]
Frame 450: [Same radial gradient, just shifted]
Frame 900: [Same radial gradient, shifted more]
```
Pattern stays the same, just shifts position

### After (AURORA)
```
Frame 0:   [Wave pattern A]
Frame 450: [Wave pattern B] ← DIFFERENT PATTERN!
Frame 900: [Wave pattern A] ← Back to start (seamless)
```
Pattern itself evolves, creating truly dynamic animation

## Temporal Evolution

Each wave layer has its own time speed:

| Layer | Speed | Effect |
|-------|-------|--------|
| Aurora H-wave | 0.7x | Slow horizontal drift |
| Aurora V-wave | 1.2x | Fast vertical flow |
| Aurora Radial | 0.9x | Medium depth pulsing |
| Plasma Radial | 2.0x | Fast energy bursts |
| Plasma Angular | 0.6x | Slow rotation |

**Result**: Layers move at different speeds, creating complex interference patterns!

## Wave Interference

When multiple waves overlap, they create:

- **Constructive interference**: Bright areas where waves align
- **Destructive interference**: Dark areas where waves cancel
- **Moving patterns**: As waves evolve at different speeds

This creates the **ethereal, flowing aurora effect**!

## Comparison

```python
from we_love.avatars import Avatar, AvatarConfig, GradientConfig, GradientType, LoopConfig, LoopType

# Simple radial (1D)
simple = AvatarConfig(
    gradient_config=GradientConfig(
        gradient_type=GradientType.RADIAL,
    )
)

# Multi-dimensional aurora (5D)
aurora = AvatarConfig(
    gradient_config=GradientConfig(
        gradient_type=GradientType.AURORA,
    )
)

# Ultra multi-dimensional plasma (7D)
plasma = AvatarConfig(
    gradient_config=GradientConfig(
        gradient_type=GradientType.PLASMA,
    )
)
```

## Technical Details

### Time Parameter
```python
t = (frame / total_frames) * 2π
```
Goes from 0 to 2π over 30 seconds, giving each wave layer smooth temporal evolution

### Why Different Frequencies?
```python
# If all waves had same frequency:
wave1 = sin(x·π·3 + t)
wave2 = sin(y·π·3 + t)
# Result: Regular, predictable pattern

# With different frequencies:
wave1 = sin(x·π·3.2 + t·0.7)
wave2 = cos(y·π·2.7 + t·1.2)
# Result: Complex, organic, never-repeating (within 30s)
```

### Mathematical Beauty

The gradients use:
- **Sine/cosine waves**: Smooth, continuous functions
- **Different frequencies**: 1.3x to 5.2x base frequency
- **Phase offsets**: Time evolution at 0.5x to 2.0x speed
- **Non-linear terms**: XY interactions, radial distance

**Combined**: Create patterns that look natural, not algorithmic!

## Examples

### See Multi-Dimensional in Action

```bash
mise run aurora

# Generates 5 aurora examples with multi-dimensional gradients:
# - aurora_borealis.gif (5-layer aurora)
# - northern_lights.gif (5-layer aurora)
# - cosmic_plasma.gif (7-layer plasma)
# - ethereal_rainbow.gif (5-layer aurora)
# - mystic_ocean.gif (7-layer plasma)
```

### Seed-Based
```python
from we_love.avatars import avatar, Avatar

# Automatically gets multi-dimensional gradients
Avatar(avatar("your-seed")).save_gif("avatar.gif", progress=True, optimize=False)
```

## Why This Matters

✅ **More realistic**: Real auroras are multi-dimensional light phenomena  
✅ **Never boring**: Pattern constantly evolves over 30 seconds  
✅ **Organic feel**: Looks natural, not computer-generated  
✅ **Depth perception**: Radial waves create 3D-like effect  
✅ **Complex beauty**: Simple rules create complex emergent patterns

The gradients are no longer just colored bands - they're **living, breathing, multi-dimensional light shows**! 🌌✨
