# Seed-Based Avatar Generation

The simplest way to create unique, deterministic avatars!

## The One-Liner

```python
from we_love.avatars import avatar, Avatar

Avatar(avatar("alice@example.com")).save_gif("alice.gif")
```

## How It Works

The `avatar(seed)` function:
1. Takes any string as input (email, username, UUID, etc.)
2. Uses SHA-256 hash to deterministically generate all parameters
3. Returns an `AvatarConfig` ready to render

**Same seed = same avatar** (always!)  
**Different seed = different avatar** (guaranteed unique)

## Use Cases

### User Profile Avatars

```python
from we_love.avatars import avatar, Avatar


def generate_user_avatar(email: str) -> None:
    """Generate avatar for user email."""
    Avatar(avatar(email)).save_gif(f"avatars/{email}.gif")


# Each user gets a unique, consistent avatar
generate_user_avatar("alice@example.com")
generate_user_avatar("bob@example.com")
```

### API Endpoints

```python
from we_love.avatars import avatar, Avatar
from fastapi import FastAPI

app = FastAPI()


@app.get("/avatar/{username}")
async def get_avatar(username: str):
    config = avatar(username)
    av = Avatar(config)
    av.save_gif(f"/tmp/{username}.gif")
    return FileResponse(f"/tmp/{username}.gif")
```

### Batch Generation

```python
from we_love.avatars import avatar, Avatar

users = ["alice", "bob", "charlie", "diana", "eve"]

for user in users:
    Avatar(avatar(user)).save_gif(f"output/{user}.gif")
    print(f"✓ Generated avatar for {user}")
```

## Customization

### Default Behavior

```python
config = avatar("user@example.com")
# - 512x512 resolution
# - 30 fps, 30 second duration (slow, mesmerizing)
# - Aurora/plasma/wave/radial gradient (varies by seed)
# - 1 loop (epitrochoid/lissajous/rose)
# - Zoom and offset enabled
# - Full circle animation (no bouncing)
```

### Custom Generator Config

Control the generation parameters:

```python
from we_love.avatars import avatar, Avatar, AvatarGeneratorConfig

# Smaller, faster avatars
custom_config = AvatarGeneratorConfig(
    width=256,
    height=256,
    fps=20,
    duration=2.0,
    enable_zoom=False,  # No offset/zoom
    enable_wave_gradients=False,  # Only linear/radial/angular
    max_loops=1,  # Exactly one loop (this is the default)
)

config = avatar("user@example.com", custom_config)
Avatar(config).save_gif("small_avatar.gif")
```

## What Gets Generated?

For each seed, the system deterministically selects:

### Gradient
- **Type**: LINEAR, RADIAL, ANGULAR, DIAGONAL, or WAVE
- **Colors**: 4 harmonious colors from one of 6 palettes
- **Angle**: 0-360 degrees
- **Wave parameters**: Frequency (1.5-3.5), amplitude (0.2-0.5)

### Loop (1 by default)
- **Type**: EPITROCHOID, LISSAJOUS, or ROSE
- **Color**: Light/warm contrasting color
- **Width**: 5-10% of image width (BOLD, super visible lines)
  - 256x256: 13-26px
  - 512x512: 26-51px
  - 1024x1024: 51-102px
- **Size**: 1.2-2.0 (zoomed in to show details)
- **Speed**: 0.5-1.5x
- **Offset**: -0.5 to 0.5 on both axes (when zoom enabled)
- **Type-specific params**: Frequencies, petals, radii, etc.

## Advanced Usage

### Generator Class

For more control:

```python
from we_love.avatars import AvatarGenerator

generator = AvatarGenerator()

# Generate config
config = generator.generate_config("user@example.com")

# Or generate full Avatar
avatar = generator.generate("user@example.com")
avatar.save_gif("output.gif")
```

### Inspect Config Before Rendering

```python
config = avatar("test@example.com")

print(f"Gradient type: {config.gradient_config.gradient_type}")
print(f"Number of loops: {len(config.loop_configs)}")  # Always 1 by default
print(f"Loop type: {config.loop_configs[0].loop_type}")

# Modify if needed
config.duration = 5.0
config.loop_configs[0].color = (255, 0, 0)

# Then render
Avatar(config).save_gif("modified.gif")
```

## Examples

See `examples/seed_based.py` for complete examples:

```bash
cd packages/we-love-avatars
uv run python examples/seed_based.py
```

This generates:
- Individual user avatars
- Deterministic testing
- Variations
- Custom configurations

## Why Use Seeds?

✅ **Deterministic** - Same input always produces same output  
✅ **Unique** - Different inputs produce visually distinct avatars  
✅ **No Storage** - Regenerate on-demand, no need to store configs  
✅ **Perfect for Users** - Email/username → consistent avatar  
✅ **Simple API** - One function call!

## Performance

Generating an avatar from seed is fast:
- Config generation: ~1ms
- Rendering (512x512, 3s @ 30fps): ~2-3 seconds

For production use, consider:
- Cache generated GIFs
- Use smaller sizes for thumbnails (256x256)
- Reduce FPS/duration for faster generation
