# Variety Showcase

Generate hundreds of unique avatars to see the full range of possibilities!

## Quick Start

```bash
# Generate 10 samples (quick preview)
mise run variety-quick

# Generate 20 samples (good variety)
mise run variety-sample

# Generate 100 avatars (full showcase)
mise run variety
```

## What It Does

Generates avatars from **random UUIDs** to showcase the variety:

- Different gradient types (aurora, plasma, wave, radial)
- Different gradient colors (6 palette themes)
- Different loop types (epitrochoid, lissajous, rose)
- Different loop parameters (frequencies, petals, radii)
- Different positions and sizes

## Example Output

```
Generating 10 sample avatars for quick preview...

 1. 795e91b7... → radial   + lissajous   
 2. 10fd59ed... → radial   + epitrochoid 
 3. 2c4dfb34... → aurora   + rose        
 4. afce3dd6... → aurora   + rose        
 5. 293eabae... → aurora   + epitrochoid 
 6. eeacb265... → aurora   + rose        
 7. 39912296... → aurora   + rose        
 8. 405dfdb8... → radial   + epitrochoid 
 9. bbc5240d... → wave     + rose        
10. 9419f0b9... → aurora   + rose        

✨ 10 samples in output/variety/
```

## Statistical Analysis

When generating 100 avatars, you'll see distribution like:

### Gradient Types
```
aurora     ██████████████ 35 (35%)
radial     ██████████     25 (25%)
plasma     ████████       20 (20%)
wave       ██████         15 (15%)
angular    ██             5  (5%)
```

### Loop Types
```
epitrochoid  ████████████  33 (33%)
lissajous    ████████████  33 (33%)
rose         ████████████  34 (34%)
```

Pretty even distribution across loop types!

## Performance

With parallel rendering (16 cores):

| Count | Resolution | Time | Speed |
|-------|-----------|------|-------|
| 10 samples | 256×256 | ~23s | 2.3s per avatar |
| 20 samples | 256×256 | ~45s | 2.25s per avatar |
| 100 full | 256×256 | ~3.5 min | 2.1s per avatar |

Using `parallel=True, optimize=False` for maximum speed!

## Use Cases

### 1. Explore Possibilities
```bash
mise run variety-sample

# Browse output/variety/ to see what's possible
# Pick your favorites!
```

### 2. Find Inspiration
Generate 100, find 5-10 you love, then:
```python
from we_love.avatars import avatar, Avatar

# Recreate your favorite
favorite_seed = 'the-seed-from-filename'
Avatar(avatar(favorite_seed)).save_gif('favorite.gif')
```

### 3. Statistical Testing
```python
from we_love.avatars import avatar
from collections import Counter
import uuid

gradient_types = Counter()

for _ in range(1000):
    config = avatar(str(uuid.uuid4()))
    gradient_types[config.gradient_config.gradient_type.value] += 1

# Verify distribution is balanced
print(gradient_types)
```

### 4. Gallery/Portfolio
Generate a gallery of your generative art:

```bash
mise run variety

# Creates 100 unique avatars
# Each with organic gradients and unique squiggles
# Perfect for showcasing the system's capabilities
```

## Custom Variety Showcase

Run with your own parameters:

```python
from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar
import uuid

# Custom generation settings
gen_config = AvatarGeneratorConfig(
    width=512,
    height=512,
    fps=30,
    duration=30.0,  # Full quality
    random_loop=True,  # Extra variety!
)

for i in range(50):
    seed = str(uuid.uuid4())
    config = avatar(seed, gen_config)
    
    Avatar(config).save_gif(
        f'gallery/piece_{i:03d}.gif',
        parallel=True,
        optimize=False,
        progress=True,
    )
```

## What You'll See

### Gradient Variety
- **Aurora Borealis**: Teal → Blue flowing waves
- **Northern Lights**: Purple → Lavender glow
- **Ethereal Rainbow**: Pink → Blue spectrum
- **Cosmic Teal**: Cyan → Purple cosmic
- **Mystic Violet**: Deep → Light purple
- **Ocean Aurora**: Blue → Cyan oceanic

### Loop Variety
- **Epitrochoid**: Spirograph-like curves with different radii
- **Lissajous**: Figure-8 patterns with different frequencies
- **Rose**: Flower patterns with 3-9 petals

### Position Variety
- Different zoom levels (1.2-2.0x)
- Different offsets (anywhere in frame)
- Different sizes and speeds

### Color Variety
- 6 different light colors for loops
- 26-51px bold line widths
- Organic color paths through 7-color palettes

## File Organization

The script organizes output:

```
output/variety/
  ├── avatar_000.gif  (UUID: xxx, aurora + epitrochoid)
  ├── avatar_001.gif  (UUID: yyy, plasma + lissajous)
  ├── avatar_002.gif  (UUID: zzz, radial + rose)
  ...
  └── avatar_099.gif
```

## Tips

1. **Start small**: Use `variety-quick` (10) to see if you like the settings
2. **Use parallel**: Significantly faster with multi-core CPUs
3. **Lower resolution**: 256×256 is 4x faster than 512×512
4. **Short duration**: 3s loops generate much faster than 30s
5. **Disable optimize**: Faster encoding, larger files (ok for exploration)

## Summary

```bash
# Quick preview (10 avatars, ~25 seconds)
mise run variety-quick

# Good variety (20 avatars, ~45 seconds)  
mise run variety-sample

# Full showcase (100 avatars, ~3.5 minutes)
mise run variety
```

Each avatar is **completely unique** - different gradients, colors, loops, and positions. See the full creative range of the generator! 🎨✨
