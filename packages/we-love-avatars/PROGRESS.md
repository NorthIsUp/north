# Progress Bars

Optional progress bars for avatar generation!

## Why Progress Bars?

With 30-second animations at 30fps, you're rendering **900 frames**. That takes 5-20 seconds depending on your system. Progress bars give you:

- ✅ Visual feedback on rendering progress
- ✅ Estimated time remaining
- ✅ Frames per second performance metric
- ✅ Assurance the process is working

## Basic Usage

### Enable Progress Bar

```python
from we_love.avatars import avatar, Avatar

config = avatar("user@example.com")
av = Avatar(config)

# Simply add progress=True
av.save_gif("avatar.gif", progress=True)
```

**Output:**
```
Rendering frames: 100%|████████| 900/900 [00:05<00:00, 156fps]
Encoding GIF (900 frames, 256 colors, optimized)...
✓ Saved output/avatar.gif (22.1 MB)
```

### Faster Encoding

For quicker generation, disable optimization:

```python
# 20-30% faster encoding, ~15% larger file
av.save_gif("avatar.gif", progress=True, optimize=False)

# Output:
# Rendering frames: 100%|████████| 900/900 [00:05<00:00, 156fps]
# Encoding GIF (900 frames, 256 colors, fast)...
# ✓ Saved output/avatar.gif (25.6 MB)
```

**Speed comparison** (900 frames):
- `optimize=True`: ~15 seconds total (6s render + 9s encode)
- `optimize=False`: ~12 seconds total (6s render + 6s encode) **25% faster!**

### Without Progress Bar (Default)

```python
# Default behavior: silent rendering
av.save_gif("avatar.gif")

# Or explicitly disable
av.save_gif("avatar.gif", progress=False)
```

## Use Cases

### Interactive Scripts ✅
```python
# User is waiting - show progress
print("Generating your avatar...")
av.save_gif("avatar.gif", progress=True)
print("✓ Complete!")
```

### Batch Processing
```python
users = ["alice", "bob", "charlie", "diana", "eve"]

for user in users:
    print(f"Generating for {user}:")
    config = avatar(user)
    av = Avatar(config)
    av.save_gif(f"{user}.gif", progress=True)
    print()
```

**Output:**
```
Generating for alice:
Rendering frames: 100%|████████| 900/900 [00:05<00:00, 163frame/s]

Generating for bob:
Rendering frames: 100%|████████| 900/900 [00:05<00:00, 165frame/s]
...
```

### Automation ❌
```python
# Background jobs, CI/CD, etc. - disable progress
for user in users:
    av = Avatar(avatar(user))
    av.save_gif(f"{user}.gif")  # Silent
```

## Advanced: Just Frames

You can also show progress when rendering frames without saving:

```python
config = avatar("test")
av = Avatar(config)

# Render all frames with progress
frames = av.render_all_frames(progress=True)

# Now do something with frames
for i, frame in enumerate(frames):
    frame.save(f"frame_{i:04d}.png")
```

## Technical Details

### Library: tqdm

We use [`tqdm`](https://github.com/tqdm/tqdm) - the most popular Python progress bar library.

- Lightweight and fast
- Automatic fallback if not available
- Beautiful, informative output

### Performance

Progress bars add minimal overhead:
- **Without progress**: ~164 fps
- **With progress**: ~163 fps (~0.6% slower)

Worth it for the feedback!

### Fallback Behavior

If `tqdm` isn't available (shouldn't happen with our deps):
```python
av.save_gif("avatar.gif", progress=True)
# Falls back to silent rendering gracefully
```

## Customization

The progress bar shows:
- **Description**: "Rendering frames"
- **Progress**: XX% complete with bar
- **Count**: Current/Total frames
- **Speed**: Frames per second
- **ETA**: Time remaining

All handled automatically by `tqdm`!

## Examples

Run the progress examples:

```bash
mise run progress

# Or directly:
uv run python examples/with_progress.py
```

This demonstrates:
- Generating with progress
- Generating without progress
- Batch generation with progress

## When NOT to Use

- **Background jobs**: No one watching, progress adds noise
- **API endpoints**: Progress not visible to end users
- **Automated testing**: Keep output clean
- **Production logging**: Use proper logging instead

## Summary

```python
# Interactive, manual generation
av.save_gif("avatar.gif", progress=True)  # ✅ Show progress

# Automation, background jobs
av.save_gif("avatar.gif")  # ✅ Silent (default)
```

Simple, optional, and helpful! 🎯
