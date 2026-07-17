"""Guardrailed one-shot local code generation harness.

The harness wraps a single Ollama code-generation call in a programmatic loop
that applies the model's file operations, then gates the result on two real
tools: slop-be-gone hygiene rules and the idud understanding artifact. Their
outputs become targeted feedback for the next one-shot attempt.
"""

__version__ = "0.2.0"
