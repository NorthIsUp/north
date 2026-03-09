# Cloud Gradients - Domain Warping

Organic, billowing cloud-like gradients using **domain warping** techniques inspired by [Inigo Quilez](https://iquilezles.org/articles/warp/).

## What is Domain Warping?

Instead of just sampling noise, we **warp the sampling coordinates** using other noise layers. This creates organic, flowing patterns like real clouds!

## The Technique

```
1. Generate first noise layer (q)
   q = (fbm(x, y), fbm(x+offset, y+offset))

2. Use q to warp coordinates for second layer (r)
   r = (fbm(x + 4*q.x, y + 4*q.y), fbm(x + 4*q.x + offset, y + 4*q.y + offset))

3. Use r to warp final sampling  
   density = fbm(x + warp_strength*r.x, y + warp_strength*r.y)

4. Add temporal drift for motion
   All coordinates drift slowly over time
```

**Result**: Billowing, organic cloud patterns that flow naturally!

## Basic Usage

```python
from we_love.avatars import Avatar, AvatarConfig, GradientConfig, GradientType, LoopConfig, LoopType

config = AvatarConfig(
    gradient_config=GradientConfig(
        colors=[
            (30, 95, 95),    # Teal
            (40, 105, 120),  # Cyan
            (50, 112, 145),  # Blue
            (60, 113, 168),  # Sky blue
            (50, 112, 145),  # Blue
            (40, 105, 120),  # Cyan
            (30, 95, 95),    # Teal (circular!)
        ],
        gradient_type=GradientType.CLOUDS,
        cloud_scale=1.5,    # Large, gentle clouds (lower = larger!)
        cloud_drift=0.008,  # Gentle drift
    ),
    loop_configs=[
        LoopConfig(
            loop_type=LoopType.EPITROCHOID,
            size=1.7,
            offset_x=0.3,
            offset_y=-0.2,
        ),
    ],
)

Avatar(config).save_gif('clouds.gif', parallel=True, optimize=False, progress=True)
```

## Parameters

### cloud_scale (default: 1.5)
Controls the size of cloud features (LOWER = LARGER):
- **0.5-1.0**: Massive, gentle billows
- **1.5-2.0**: Large, soft clouds (default)
- **3.0-5.0**: Medium clouds
- **6.0-8.0**: Fine, detailed wisps

**Tip**: Lower values zoom into the noise pattern, creating huge, gentle features!

### cloud_drift (default: 0.008)
Controls how fast clouds drift:
- **0.005-0.008**: Very gentle drift (meditative, default)
- **0.01-0.015**: Moderate drift
- **0.02+**: Fast flowing clouds

## How It Works

### Layer 1: Base Noise (q)
```python
q_x = fbm(x + drift, y + drift, time)
q_y = fbm(x + offset + drift, y + offset + drift, time)
```
Creates the base turbulence pattern.

### Layer 2: Warped Noise (r)
```python
r_x = fbm(x + 4*q_x + drift*0.8, y + 4*q_y + drift*0.8, time)
r_y = fbm(x + 4*q_x + offset + drift*0.8, y + 4*q_y + offset + drift*0.8, time)
```
Samples noise at warped coordinates for organic flow.

### Layer 3: Final Pattern
```python
density = fbm((x + warp_strength*r_x)*cloud_scale, (y + warp_strength*r_y)*cloud_scale, time)
```
The final cloud density, sampled at double-warped coordinates!

### FBM (Fractional Brownian Motion)
Each FBM call layers 4 octaves of noise:
```python
value = amplitude_1 * noise_1 +
        amplitude_2 * noise_2 (2x frequency) +
        amplitude_3 * noise_3 (4x frequency) +
        amplitude_4 * noise_4 (8x frequency)
```

**Result**: Detail at multiple scales, like real clouds!

## Comparison with Other Gradients

### AURORA (5 sine wave layers)
- Mathematical, precise
- Flowing waves
- ~100 fps rendering

### PLASMA (7 sine wave layers)
- Chaotic, energetic
- Sharp patterns
- ~80 fps rendering

### CLOUDS (domain warping + FBM)
- Organic, billowing
- Soft, natural patterns
- ~95 fps rendering
- **Most realistic/natural looking!**

## Examples

Run the cloud examples:

```bash
mise run clouds
```

Generates:
- `cosmic_clouds.gif` - Teal/blue cosmic clouds
- `ethereal_mist.gif` - Purple misty clouds
- `ocean_fog.gif` - Blue ocean fog

## Advanced: Combine with Random Loops

```python
from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar, GradientConfig, GradientType

# Get organic gradient from seed
config = avatar('my-seed')

# Force cloud gradient
config.gradient_config.gradient_type = GradientType.CLOUDS
config.gradient_config.cloud_scale = 4.5
config.gradient_config.cloud_drift = 0.015

# Enable random loop for extra variety
gen_config = AvatarGeneratorConfig(random_loop=True)

for i in range(10):
    config_variant = avatar('my-seed', gen_config)
    config_variant.gradient_config = config.gradient_config  # Keep cloud gradient
    
    Avatar(config_variant).save_gif(f'cloud_variant_{i}.gif', parallel=True, optimize=False)
```

## Technical Details

### Domain Warping Benefits
1. **Organic shapes**: Looks natural, not computer-generated
2. **Infinite detail**: Zoom in and patterns stay interesting
3. **Smooth motion**: Drift creates flowing animation
4. **No repetition**: Pattern doesn't obviously repeat

### Performance
- FBM with 4 octaves per layer
- 3 FBM layers (q_x, q_y, r_x, r_y, density)
- Total: ~12 noise samples per pixel
- Still fast with parallel: ~95 fps

### File Sizes
Cloud gradients create more complex patterns:
- Simple gradients: ~25MB for 900 frames
- Cloud gradients: ~110-210MB for 900 frames

**Why?**: More variation frame-to-frame = less compression

**Solution**: Use `optimize=True` or shorter duration for smaller files

## Inspiration

Technique inspired by:
- **Inigo Quilez**: Domain warping article - https://iquilezles.org/articles/warp/
- **ASCII Clouds**: WebGL implementation
- **Perlin/Simplex noise**: For organic randomness

Combined with our circular color palettes and multi-dimensional evolution for the ultimate organic gradient! 🌥️✨
