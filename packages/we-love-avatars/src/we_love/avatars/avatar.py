"""Main avatar generation module."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from we_love.avatars.gradient import Gradient, GradientConfig
from we_love.avatars.loop import Loop, LoopConfig

if TYPE_CHECKING:
    from PIL import Image


class AvatarConfig(BaseModel):
    """Configuration for avatar generation."""

    width: int = Field(
        default=512,
        description="Avatar width in pixels",
    )
    height: int = Field(
        default=512,
        description="Avatar height in pixels",
    )
    fps: int = Field(
        default=30,
        description="Frames per second for animation",
    )
    duration: float = Field(
        default=2.0,
        description="Animation duration in seconds",
    )
    gradient_config: GradientConfig = Field(
        default_factory=GradientConfig,
        description="Gradient background configuration",
    )
    loop_configs: list[LoopConfig] = Field(
        default_factory=lambda: [LoopConfig()],
        description="List of loop configurations to render",
    )


class Avatar:
    """Generate animated avatars with loops and gradient backgrounds."""

    def __init__(self, config: AvatarConfig | None = None) -> None:
        """Initialize avatar generator.

        Args:
            config: Avatar configuration, uses defaults if None
        """
        self.config = config or AvatarConfig()
        self.gradient = Gradient(self.config.gradient_config)
        self.loops = [Loop(loop_config) for loop_config in self.config.loop_configs]

    @property
    def total_frames(self) -> int:
        """Calculate total number of frames in animation."""
        return int(self.config.fps * self.config.duration)

    def render_frame(self, frame: int) -> Image.Image:
        """Render a single frame of the animation.

        Args:
            frame: Frame number to render

        Returns:
            Rendered frame as PIL Image
        """
        # Render gradient background
        img = self.gradient.render(
            self.config.width,
            self.config.height,
            frame,
            self.total_frames,
        )

        # Render each loop
        for loop in self.loops:
            img = loop.render(img, frame, self.total_frames)

        return img

    def render_all_frames(self, progress: bool = False, parallel: bool = False, workers: int | None = None) -> list[Image.Image]:
        """Render all frames of the animation.

        Args:
            progress: Show progress bar during rendering
            parallel: Use multiprocessing for parallel rendering (much faster!)
            workers: Number of worker processes (default: CPU count)

        Returns:
            List of all frames as PIL Images
        """
        if parallel:
            # Parallel rendering using multiprocessing
            from multiprocessing import Pool, cpu_count

            num_workers = workers or cpu_count()

            if progress:
                try:
                    from tqdm import tqdm

                    with Pool(num_workers) as pool:
                        frames = list(
                            tqdm(
                                pool.imap(self.render_frame, range(self.total_frames)),
                                total=self.total_frames,
                                desc=f"Rendering frames ({num_workers} cores)",
                                unit="frame",
                            )
                        )
                except ImportError:
                    with Pool(num_workers) as pool:
                        frames = pool.map(self.render_frame, range(self.total_frames))
            else:
                with Pool(num_workers) as pool:
                    frames = pool.map(self.render_frame, range(self.total_frames))

            return frames
        elif progress:
            try:
                from tqdm import tqdm

                return [
                    self.render_frame(i)
                    for i in tqdm(
                        range(self.total_frames),
                        desc="Rendering frames",
                        unit="frame",
                    )
                ]
            except ImportError:
                # Fallback if tqdm not available
                return [self.render_frame(i) for i in range(self.total_frames)]
        else:
            return [self.render_frame(i) for i in range(self.total_frames)]

    def save_gif(
        self,
        path: str | Path,
        optimize: bool = True,
        loop: int = 0,
        progress: bool = False,
        colors: int = 256,
        parallel: bool = False,
        workers: int | None = None,
    ) -> None:
        """Save animation as an animated GIF.

        Args:
            path: Output file path
            optimize: Whether to optimize the GIF (slower but smaller)
            loop: Number of loops (0 = infinite)
            progress: Show progress bar during rendering
            colors: Number of colors in GIF palette (default: 256, use 128 for faster encoding)
            parallel: Use multiprocessing for parallel rendering (much faster on multi-core CPUs!)
            workers: Number of worker processes (default: CPU count)
        """
        frames = self.render_all_frames(progress=progress, parallel=parallel, workers=workers)

        # Convert to path
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Calculate frame duration in milliseconds
        duration = int(1000 / self.config.fps)

        # Show encoding status if progress enabled
        if progress:
            opt_msg = "optimized" if optimize else "fast"
            print(f"Encoding GIF ({len(frames)} frames, {colors} colors, {opt_msg})...")

        # Quantize frames to reduce color palette if needed
        if colors < 256:
            from PIL import Image as PILImage

            quantized = []
            for frame in frames:
                # Convert to palette mode with specified colors
                quantized.append(frame.convert("P", palette=PILImage.ADAPTIVE, colors=colors).convert("RGB"))
            frames = quantized

        # Save as GIF
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=loop,
            optimize=optimize,
        )

        if progress:
            import os

            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"✓ Saved {output_path} ({size_mb:.1f} MB)")

    def save_png(self, path: str | Path, frame: int = 0) -> None:
        """Save a single frame as PNG.

        Args:
            path: Output file path
            frame: Frame number to save (default: 0)
        """
        img = self.render_frame(frame)

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        img.save(output_path, format="PNG")
