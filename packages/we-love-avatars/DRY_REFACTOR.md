# DRY Refactoring Summary

Consolidated repeated code and magic numbers across the project.

## What Was DRYed Up

### 1. Created `constants.py`

Centralized all magic numbers and configuration constants:

**Before**: Repeated throughout `generator.py`
```python
# Scattered across the file:
width_pct = random.uniform(0.05, 0.10)
loop_config.freq_x = random.uniform(2.0, 6.0)
loop_config.r_major = random.uniform(0.25, 0.45)
# ... repeated 10+ times
```

**After**: Single source of truth
```python
# constants.py
LINE_WIDTH_MIN_PCT = 0.05
LINE_WIDTH_MAX_PCT = 0.10
LISSAJOUS_FREQ_MIN = 2.0
LISSAJOUS_FREQ_MAX = 6.0
EPITROCHOID_R_MAJOR_MIN = 0.25
EPITROCHOID_R_MAJOR_MAX = 0.45

# generator.py
width_pct = random.uniform(LINE_WIDTH_MIN_PCT, LINE_WIDTH_MAX_PCT)
```

**Benefit**: Change once, applies everywhere

### 2. Consolidated Loop Colors

**Before**: List repeated in 2 places
```python
# In _generate_loop_color:
colors = [
    (255, 255, 240),
    (255, 240, 200),
    ...
]

# In random loop generation:
color=random.choice([
    (255, 255, 240),
    (255, 240, 200),
    ...
])
```

**After**: Single definition
```python
# constants.py
LOOP_COLORS = [
    (255, 255, 240),
    (255, 240, 200),
    ...
]

# Used everywhere
random.choice(LOOP_COLORS)
```

### 3. Centralized Color Palette Pairs

**Before**: 6 color pairs defined inline
```python
color_pairs = [
    ((35, 100, 100), (65, 118, 175)),
    ...
]
```

**After**: Constants module
```python
# constants.py
BASE_COLOR_PAIRS = [...]

# generator.py
start_color, peak_color = BASE_COLOR_PAIRS[hue_sector]
```

### 4. Extracted Color Interpolation

**Before**: 28 lines of interpolation code at end of render()

**After**: Separate method
```python
def _interpolate_colors(self, pos, width, height) -> Image.Image:
    # 28 lines of interpolation logic
    
# render() method
return self._interpolate_colors(pos, width, height)
```

**Benefit**: render() method is now cleaner and focused

### 5. Extracted Position Normalization

**Before**: Repeated 5 times
```python
pos = (pos - pos.min()) / (pos.max() - pos.min())
```

**After**: Helper method
```python
def _normalize_position(self, pos):
    return (pos - pos.min()) / (pos.max() - pos.min())

# Used everywhere
pos = self._normalize_position(pos)
```

### 6. Unified Loop Type Selection

**Before**: Repeated lists
```python
# Deterministic:
loop_types = [LoopType.EPITROCHOID, LoopType.LISSAJOUS, LoopType.ROSE]

# Random:
loop_types = [LoopType.EPITROCHOID, LoopType.LISSAJOUS, LoopType.ROSE]
```

**After**: Single constant
```python
# constants.py
PREFERRED_LOOP_TYPES = ['epitrochoid', 'lissajous', 'rose']

# Both use:
loop_types = [LoopType[t.upper()] for t in PREFERRED_LOOP_TYPES]
```

## Constants Module Contents

All configuration values in one place:

```python
# Loop selection
PREFERRED_LOOP_TYPES
LOOP_COLORS

# Line thickness
LINE_WIDTH_MIN_PCT = 0.05
LINE_WIDTH_MAX_PCT = 0.10

# Size ranges
SIZE_MIN_ZOOMED = 1.2
SIZE_MAX_ZOOMED = 2.0
SIZE_MIN_NORMAL = 0.5
SIZE_MAX_NORMAL = 0.8

# Animation speed
SPEED_MIN = 0.5
SPEED_MAX = 1.5

# Position offset
OFFSET_MIN = -0.5
OFFSET_MAX = 0.5

# Epitrochoid parameters
EPITROCHOID_R_MAJOR_MIN = 0.25
EPITROCHOID_R_MAJOR_MAX = 0.45
EPITROCHOID_R_MINOR_MIN = 0.08
EPITROCHOID_R_MINOR_MAX = 0.18

# Lissajous parameters
LISSAJOUS_FREQ_MIN = 2.0
LISSAJOUS_FREQ_MAX = 6.0
LISSAJOUS_PHASE_MIN = 0.0
LISSAJOUS_PHASE_MAX = 3.14

# Rose parameters
ROSE_PETALS_MIN = 3
ROSE_PETALS_MAX = 9

# Color generation
PALETTE_VARIATION = 10
BASE_COLOR_PAIRS = [...]  # 6 palette themes
```

## Benefits

### 1. Single Source of Truth
Want thicker lines? Change `LINE_WIDTH_MAX_PCT` in one place.

### 2. Easier Maintenance
All configuration values documented and visible in one file.

### 3. Consistency
Both deterministic and random generation use same ranges.

### 4. Cleaner Code
- `generator.py`: Reduced magic numbers
- `gradient.py`: Extracted repeated logic
- Both files more readable

### 5. Easier Testing
Constants can be imported and verified in tests.

## Code Reduction

### generator.py
- **Before**: ~450 lines with repeated constants
- **After**: ~403 lines, cleaner logic

### gradient.py
- **Before**: ~250 lines with repeated normalization
- **After**: ~247 lines with helper methods

### New File
- **constants.py**: 69 lines of centralized configuration

**Net**: Slightly more lines overall, but much better organized!

## Usage

Users can now import constants for customization:

```python
from we_love.avatars.constants import (
    LINE_WIDTH_MIN_PCT,
    LINE_WIDTH_MAX_PCT,
    LOOP_COLORS,
)

# See what ranges are used
print(f"Line width: {LINE_WIDTH_MIN_PCT}-{LINE_WIDTH_MAX_PCT}")
print(f"Available colors: {len(LOOP_COLORS)}")
```

## What We Didn't DRY

### Kept Separate (Intentionally)
- Individual gradient type calculations (each is unique)
- Loop type-specific parameters (different per type)
- Test fixtures (better for test isolation)
- Example files (educational, show different patterns)

These have similarity but different purposes - keeping them separate is clearer.

## Summary

✅ **Eliminated**: 50+ instances of magic numbers  
✅ **Centralized**: All configuration constants  
✅ **Extracted**: 2 helper methods  
✅ **Maintained**: Code clarity and readability  
✅ **Tests**: All 43 passing  

The codebase is now more maintainable and the configuration is transparent!
