# Performance Guide

Optimize avatar generation speed and file sizes!

## The "Hanging Time" Issue

When generating 900-frame (30s) animations, you'll notice two distinct phases:

### 1. Rendering Phase (~6 seconds)
```
Rendering frames: 100%|████████| 900/900 [00:05<00:00, 156fps]
```
This is fast and efficient!

### 2. Encoding Phase (~6-9 seconds)
```
Encoding GIF (900 frames, 256 colors, optimized)...
```
**This is where the "hanging" happens!** PIL is encoding 900 frames into a GIF.

## Solution: Faster Encoding

### Quick Fix: Disable Optimization

```python
from we_love.avatars import avatar, Avatar

config = avatar("user@example.com")
av = Avatar(config)

# Fast encoding (3 seconds faster!)
av.save_gif("avatar.gif", optimize=False, progress=True)
```

**Results** (900 frames):

| Setting | Render Time | Encode Time | Total Time | File Size |
|---------|-------------|-------------|------------|-----------|
| `optimize=True` | 6s | 9s | **15s** | 22 MB |
| `optimize=False` | 6s | 6s | **12s** | 26 MB (+18%) |

**Trade-off**: 25% faster, 18% larger file. Worth it for development!

## Other Speed Optimizations

### 1. Reduce Frame Count

**Fewer frames = faster generation:**

```python
from we_love.avatars import AvatarGeneratorConfig, avatar, Avatar

# Option A: Lower FPS
config_gen = AvatarGeneratorConfig(
    fps=20,  # Instead of 30
    duration=30.0,
)
# 600 frames instead of 900 → 33% faster

# Option B: Shorter duration
config_gen = AvatarGeneratorConfig(
    fps=30,
    duration=10.0,  # Instead of 30
)
# 300 frames instead of 900 → 66% faster!
```

### 2. Reduce Resolution

**Smaller images = faster rendering:**

```python
config_gen = AvatarGeneratorConfig(
    width=256,  # Instead of 512
    height=256,
    duration=30.0,
)
# 75% fewer pixels → ~50% faster
```

### 3. Combine All Optimizations

**For fastest generation:**

```python
config_gen = AvatarGeneratorConfig(
    width=256,
    height=256,
    fps=20,
    duration=10.0,
)

config = avatar("fast", config_gen)
av = Avatar(config)

# Fast encode, no optimization
av.save_gif("fast.gif", optimize=False, progress=True)

# Result: ~2 seconds total (vs 15 seconds)
# 87% faster!
```

## Performance Comparison

### Default (30s @ 30fps, 512x512, optimized)
- Frames: 900
- Render: ~6s
- Encode: ~9s
- **Total: ~15s**
- Size: ~22 MB

### Fast Development (10s @ 20fps, 256x256, no optimize)
- Frames: 200
- Render: ~1s
- Encode: ~1s
- **Total: ~2s** ⚡
- Size: ~5 MB

### Medium Quality (10s @ 30fps, 512x512, no optimize)
- Frames: 300
- Render: ~2s
- Encode: ~3s
- **Total: ~5s** 🚀
- Size: ~12 MB

## Recommendations

### Development/Testing
```python
# Fast iteration
config_gen = AvatarGeneratorConfig(
    width=256,
    height=256,
    fps=20,
    duration=5.0,
)
av.save_gif("test.gif", optimize=False, progress=True)
```

### Production/Final Output
```python
# High quality
config_gen = AvatarGeneratorConfig(
    width=512,
    height=512,
    fps=30,
    duration=30.0,
)
av.save_gif("final.gif", optimize=True, progress=True)
```

### Web/Social Media
```python
# Good balance
config_gen = AvatarGeneratorConfig(
    width=512,
    height=512,
    fps=20,
    duration=10.0,
)
av.save_gif("web.gif", optimize=False, progress=True)
```

## Understanding the Times

### Why Does Encoding Take So Long?

GIF encoding with PIL:
1. **Converts each frame** to GIF format
2. **Builds color palette** (up to 256 colors per frame)
3. **Compresses frame data** using LZW compression
4. **Optimizes** (if enabled) - removes duplicate pixels, optimizes palette

With 900 frames, this adds up!

### The optimize=True vs False Trade-off

**optimize=True** (default):
- ✅ Smaller files (20-30% reduction)
- ✅ Better for final output
- ❌ Slower encoding (~50% more time)
- ❌ Not worth it for development

**optimize=False**:
- ✅ Faster encoding (~50% faster)
- ✅ Perfect for development
- ❌ Larger files (20-30% increase)
- ❌ Still acceptable size

## Parallelization (Future)

Currently, frames render sequentially. Future optimization could:
- Render frames in parallel (multi-core)
- Could be 4-8x faster on modern CPUs
- Would require multiprocessing support

## Summary

**Eliminate the "hanging":**
1. Use `progress=True` to see what's happening
2. Use `optimize=False` for 25% faster encoding
3. Reduce frames for development (`fps=20, duration=10`)
4. Use smaller resolution for previews (`256x256`)

**Quick comparison:**
```python
# Slow but small (default)
av.save_gif("avatar.gif")  # 15s, 22MB

# Fast but larger (recommended for dev)
av.save_gif("avatar.gif", optimize=False)  # 12s, 26MB
```

The encoding message now shows you exactly what's happening, so no more wondering! 🚀
