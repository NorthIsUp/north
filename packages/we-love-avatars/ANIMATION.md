# Animation Style Guide

## Overview

The library now uses slow, mesmerizing animations with full-circle progression for maximum aurora effect!

## Animation Settings

### Default Behavior

```python
from we_love.avatars import avatar, Avatar

config = avatar("user@example.com")
# Duration: 30 seconds (slow, hypnotic)
# FPS: 30
# Total frames: 900
# Style: Full circle (continuous flow)
```

### What Changed

| Aspect | Before | After |
|--------|--------|-------|
| **Duration** | 3 seconds | 30 seconds (10x slower) |
| **Style** | Bouncing (sine wave) | Full circle (continuous) |
| **Effect** | Quick back-and-forth | Slow, mesmerizing flow |

## Full Circle vs Bouncing

### Full Circle (Current)
- Gradients flow continuously from 0 → 1
- Smooth, endless progression
- Perfect for aurora effects
- Creates hypnotic, meditative quality

```python
# Gradient shifts from 0% → 100% over 30 seconds
# Then seamlessly loops back to start
shift = frame / total_frames  # 0.0 to 1.0
```

### Bouncing (Old)
- Gradients oscillate back and forth
- Goes 0 → 1 → 0 using sine wave
- Creates "breathing" effect
- More dynamic but less mesmerizing

```python
# Gradient oscillates 0% → 100% → 0%
shift = sin(frame / total_frames * 2π) * 0.5 + 0.5
```

## Customizing Duration

### Quick Animations
```python
from we_love.avatars import AvatarGeneratorConfig, avatar, Avatar

# Faster for testing/thumbnails
config = AvatarGeneratorConfig(duration=5.0)
Avatar(avatar("test", config)).save_gif("fast.gif", optimize=False)
# 25% faster encoding!
```

### Ultra-Slow (Maximum Hypnotic)
```python
# Even slower for desktop backgrounds
config = AvatarGeneratorConfig(duration=60.0)  # 1 minute!
Avatar(avatar("test", config)).save_gif("ultra_slow.gif")
```

### Match Music/Video
```python
# Sync to your content
config = AvatarGeneratorConfig(
    duration=15.0,  # 15 second loop
    fps=60,  # Smooth 60fps
)
Avatar(avatar("test", config)).save_gif("music_sync.gif")
```

## File Sizes

Longer animations = larger files:

| Duration | Resolution | FPS | Frames | Est. Size |
|----------|-----------|-----|--------|-----------|
| 3s | 512x512 | 30 | 90 | ~5-10MB |
| 10s | 512x512 | 30 | 300 | ~15-25MB |
| 30s | 512x512 | 30 | 900 | ~50-75MB |
| 60s | 512x512 | 30 | 1800 | ~100-150MB |

### Reducing File Size

```python
from we_love.avatars import AvatarGeneratorConfig, avatar, Avatar

# Option 1: Lower resolution
config = AvatarGeneratorConfig(
    width=256,
    height=256,
    duration=30.0,
)

# Option 2: Lower FPS (still smooth)
config = AvatarGeneratorConfig(
    fps=20,  # Instead of 30
    duration=30.0,
)

# Option 3: Shorter duration
config = AvatarGeneratorConfig(
    duration=10.0,  # Still slow and mesmerizing
)

Avatar(avatar("test", config)).save_gif("smaller.gif")
```

## Aurora Examples

All aurora examples now use 30-second full-circle animations:

```bash
mise run aurora
```

This generates:
- `aurora_borealis.gif` - Classic aurora (30s loop)
- `northern_lights.gif` - Pink-purple glow (30s loop)
- `cosmic_plasma.gif` - Full spectrum chaos (30s loop)
- `ethereal_rainbow.gif` - Multi-color aurora (30s loop)
- `mystic_ocean.gif` - Ocean aurora (30s loop)

## Progress Bars

Since 30-second animations generate 900 frames, you can enable a progress bar to see rendering progress:

```python
from we_love.avatars import avatar, Avatar

config = avatar("user@example.com")
av = Avatar(config)

# Enable progress bar
av.save_gif("avatar.gif", progress=True)

# Shows:
# Rendering frames: 100%|████████| 900/900 [00:05<00:00, 164.03frame/s]
```

### When to Use Progress Bars

- **Enable** (`progress=True`): Interactive scripts, CLI tools, manual generation
- **Disable** (default): Automation, batch processing, background jobs

## Tips

1. **30 seconds is perfect** for desktop backgrounds and screensavers
2. **10-15 seconds** works well for social media/web
3. **5 seconds** for quick previews and thumbnails
4. **Lower FPS to 20** if file size is a concern
5. **Full circle motion** creates better loops than bouncing
6. **Longer = more mesmerizing** for aurora effects
7. **Use progress bars** for long renders (helpful feedback!)

## Technical Details

The gradient animation uses a simple linear progression:

```python
# Full circle (current)
shift = frame / total_frames  # Goes from 0.0 to 1.0
pos = (base_gradient + shift) % 1.0  # Wraps seamlessly
```

This creates a continuous, endless flow that perfectly captures the aurora effect!
