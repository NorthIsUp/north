"""Benchmark sequential vs parallel rendering."""

import time
from multiprocessing import cpu_count

from we_love.avatars import Avatar, AvatarGeneratorConfig, avatar


def benchmark_rendering() -> None:
    """Compare sequential vs parallel rendering speeds."""
    print("=" * 60)
    print("RENDERING BENCHMARK")
    print("=" * 60)
    print()
    print(f"System: {cpu_count()} CPU cores available")
    print()

    # Use consistent seed and shorter duration for testing
    gen_config = AvatarGeneratorConfig(
        fps=30,
        duration=10.0,  # 300 frames
    )

    config = avatar("benchmark", gen_config)
    total_frames = int(config.fps * config.duration)

    print(f"Test: {total_frames} frames @ {config.fps}fps")
    print(f"Gradient: {config.gradient_config.gradient_type.value} (multi-dimensional)")
    print()

    # Sequential
    print("1. Sequential (1 core):")
    av = Avatar(config)
    start = time.time()
    av.save_gif(
        "output/bench_seq.gif",
        parallel=False,
        optimize=False,
        progress=True,
    )
    seq_time = time.time() - start
    print(f"   Total time: {seq_time:.2f}s")
    print()

    # Parallel
    print("2. Parallel (all cores):")
    av = Avatar(config)
    start = time.time()
    av.save_gif(
        "output/bench_par.gif",
        parallel=True,
        optimize=False,
        progress=True,
    )
    par_time = time.time() - start
    print(f"   Total time: {par_time:.2f}s")
    print()

    # Results
    print("=" * 60)
    speedup = seq_time / par_time
    print(f"⚡ SPEEDUP: {speedup:.2f}x faster!")
    print(f"   Sequential: {seq_time:.2f}s")
    print(f"   Parallel:   {par_time:.2f}s")
    print(f"   Saved:      {seq_time - par_time:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    benchmark_rendering()
