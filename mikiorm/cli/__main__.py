#!/usr/bin/env python3
"""
Redirects to the CLI tool when the package is run as a module.

Usage:
    python -m myorm makemigrations
"""
from .cli import main

if __name__ == "__main__":
    main()