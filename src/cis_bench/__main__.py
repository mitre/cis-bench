"""Allow running cis-bench as a module: python -m cis_bench

This provides a fallback when the 'cis-bench' command is not in PATH.
"""

from cis_bench.cli.app import cli

if __name__ == "__main__":
    cli()
