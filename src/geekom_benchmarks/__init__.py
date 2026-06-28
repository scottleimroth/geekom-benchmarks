"""geekom_benchmarks — canonical local-AI benchmark & agent-readiness suite.

Reference hardware: GEEKOM A9 Max (AMD Ryzen AI 9 HX 370 / Radeon 890M / 24 GB
unified memory) running Lemonade (llama.cpp Vulkan), but the architecture is
adapter-based so other hosts/runtimes (Ollama, LM Studio, NVIDIA, Apple Silicon)
can be added without touching the runners.

Design rule: ONE runner base, ONE result schema, ONE report generator.
"""

__version__ = "1.0.0"
