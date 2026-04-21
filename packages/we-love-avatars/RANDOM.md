# Random Squiggle Generation

Generate **different loops/curves every time** - even with the same seed!

## The Feature

By default, `avatar(seed)` is **deterministic** - same seed always produces the same result. But sometimes you want variety! 

With `random_loop=True`, the **gradient stays consistent** (from seed) but the **loop randomizes** each generation!

## Basic Usage

```python
from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar

# Enable random loops
gen_config = AvatarGeneratorConfig(random_loop=True)

# Same seed, different loops each time!
for i in range(5):
    config = avatar("my-seed", gen_config)
    Avatar(config).save_gif(f"avatar_{i}.gif")
    # Each one has a different squiggle! ✨
```

## Deterministic vs Random

### Deterministic (Default)

```python
config1 = avatar("alice")
config2 = avatar("alice")

# Everything is identical:
# ✅ Same gradient
# ✅ Same loop type
# ✅ Same loop parameters
# ✅ Same position/size
```

**Use case**: User profiles, consistent branding

### Random

```python
gen_config = AvatarGeneratorConfig(random_loop=True)

config1 = avatar("alice", gen_config)
config2 = avatar("alice", gen_config)

# Gradient is same (from seed):
# ✅ Same colors
# ✅ Same gradient type

# Loop is random:
# 🎲 Different loop type (epitrochoid vs lissajous vs rose)
# 🎲 Different parameters (frequencies, petals, radii)
# 🎲 Different position (offset_x, offset_y)
# 🎲 Different size
```

**Use case**: Variations, exploration, art generation

## What Gets Randomized?

### Loop Type
- Epitrochoid
- Lissajous
- Rose

Randomly chosen each generation!

### Loop Parameters

**Epitrochoid**:
- `r_major`: 0.25-0.45 (random)
- `r_minor`: 0.08-0.18 (random)

**Lissajous**:
- `freq_x`: 2.0-6.0 (random)
- `freq_y`: 2.0-6.0 (random)
- `phase`: 0.0-π (random)

**Rose**:
- `petals`: 3-9 (random)

### Position & Style
- `size`: 1.2-2.0 (random zoom)
- `offset_x`: -0.5 to 0.5 (random)
- `offset_y`: -0.5 to 0.5 (random)
- `color`: One of 6 light colors (random)
- `width`: 3-5% of image width (random)
- `speed`: 0.5-1.5x (random)

## What Stays Deterministic?

- ✅ Gradient colors (from seed)
- ✅ Gradient type (from seed)
- ✅ Image dimensions
- ✅ FPS and duration

## Use Cases

### Exploration: Find the Perfect Squiggle

```python
from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar

# Pick your favorite gradient
seed = "my-favorite-colors"

# Generate 10 variations
gen_config = AvatarGeneratorConfig(
    random_loop=True,
    fps=20,
    duration=5.0,  # Quick previews
)

for i in range(10):
    config = avatar(seed, gen_config)
    Avatar(config).save_gif(f"variation_{i}.gif", optimize=False)

# Pick the best one!
```

### Art Series: Consistent Aesthetic, Varied Loops

```python
# Create a series with consistent colors but varied squiggles
theme_seed = "midnight-aurora"

gen_config = AvatarGeneratorConfig(random_loop=True)

for i in range(20):
    config = avatar(theme_seed, gen_config)
    Avatar(config).save_gif(f"series_{i:02d}.gif")

# All have same color theme, different squiggles!
```

### NFT/Generative Art

```python
# Generate collection with user addresses + randomness
users = ["user1", "user2", "user3"]

gen_config = AvatarGeneratorConfig(random_loop=True)

for user in users:
    # Generate 5 variations per user
    for variant in range(5):
        config = avatar(f"{user}-{variant}", gen_config)
        Avatar(config).save_gif(f"{user}_v{variant}.gif")
```

## Example: Generate 5 Random Variations

```python
from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar

gen_config = AvatarGeneratorConfig(
    random_loop=True,
    fps=30,
    duration=10.0,
)

seed = "explore"

for i in range(5):
    config = avatar(seed, gen_config)
    loop = config.loop_configs[0]

    print(f"{i + 1}. {loop.loop_type.value} at ({loop.offset_x:.2f}, {loop.offset_y:.2f})")

    Avatar(config).save_gif(f"random_{i}.gif", progress=True, optimize=False)
```

**Output**:
```
1. epitrochoid at (0.23, -0.41)
2. rose at (-0.12, 0.35)
3. lissajous at (0.45, -0.18)
4. epitrochoid at (-0.33, 0.22)
5. rose at (0.17, -0.29)

Each one is unique! 🎲
```

## Run Examples

```bash
mise run random

# Or directly:
uv run python examples/random_squiggles.py
```

This generates:
- Comparison of deterministic vs random
- 5 random variations from the same seed

## Technical Details

### How It Works

```python
if config.random_loop:
    # Use Python's random module
    loop_type = random.choice([EPITROCHOID, LISSAJOUS, ROSE])
    freq_x = random.uniform(2.0, 6.0)
    offset_x = random.uniform(-0.5, 0.5)
    # ... etc
else:
    # Use deterministic hash-based values
    loop_type = hash_choice(seed, [EPITROCHOID, LISSAJOUS, ROSE])
    freq_x = hash_float(seed, 2.0, 6.0)
    offset_x = hash_float(seed, -0.5, 0.5)
```

### Randomness Source

Uses Python's `random` module:
- Truly random (uses system entropy)
- Different each execution
- Not repeatable (that's the point!)

### Seeding the Randomness

If you want repeatable "random" variations:

```python
import random

random.seed(42)  # Set seed for repeatability

for i in range(5):
    random.seed(42 + i)  # Different seed per variation
    config = avatar("base", gen_config)
    # Now repeatable!
```

## Best Practices

### Exploration Phase (Random)
```python
# Generate 20 variations, pick the best
gen_config = AvatarGeneratorConfig(
    random_loop=True,
    fps=20,
    duration=5.0,  # Quick previews
)

for i in range(20):
    Avatar(avatar("explore", gen_config)).save_gif(f"v{i}.gif", optimize=False)
```

### Production (Deterministic)
```python
# Once you found a good one, use its config directly
# Or just use deterministic generation from start
config = avatar("alice@example.com")
Avatar(config).save_gif("alice.gif")
```

## Summary

**Deterministic** (`random_loop=False`, default):
- Same seed → same avatar (always)
- Perfect for user profiles
- Repeatable and consistent

**Random** (`random_loop=True`):
- Same seed → different squiggles (each time)
- Perfect for exploration and art
- Gradient consistent, loop varies

Choose based on your needs! 🎯
