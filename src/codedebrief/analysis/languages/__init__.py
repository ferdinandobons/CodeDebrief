"""Per-language profiles for the profile-driven tree-sitter analyzer.

Each module here defines a `LanguageProfile` and a `build_analyzer(root, config)`
factory. The factory is referenced lazily from `analysis/registry.py`, so a language's
grammar is imported only when a file of that language is actually analyzed.
"""
