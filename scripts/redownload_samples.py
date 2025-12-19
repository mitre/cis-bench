#!/usr/bin/env python3
"""Re-download samples with COMPLETE scraper (all fields)."""

from cis_bench.fetcher.auth import AuthManager
from cis_bench.fetcher.workbench import WorkbenchScraper

# Diverse benchmarks
SAMPLES = [
    ("1444", "Juniper OS (4+ years old)"),
    ("11511", "AlmaLinux OS 9"),
    ("19197", "Apple iPadOS 18"),
    ("23598", "AlmaLinux OS 8 v4.0.0"),
]


def main():
    print("Re-downloading samples with COMPLETE scraper...")
    print("(Now capturing: CIS Controls, MITRE, NIST, Profiles, Artifacts, Parent)\n")

    # Authenticate
    session = AuthManager.get_authenticated_session(browser="chrome")
    print("✓ Authenticated\n")

    scraper = WorkbenchScraper(session)

    for benchmark_id, name in SAMPLES:
        url = f"https://workbench.cisecurity.org/benchmarks/{benchmark_id}"
        print(f"Downloading: {name} ({benchmark_id})")

        def progress(msg):
            if "Found" in msg or "Successfully" in msg:
                print(f"  {msg}")

        try:
            benchmark = scraper.download_benchmark(url, progress_callback=progress)

            # Save using Pydantic's method
            import re

            safe_name = re.sub(r"[^\w\s-]", "", benchmark.title).strip()
            safe_name = re.sub(r"[-\s]+", "_", safe_name).lower()
            output_path = f"./samples/{safe_name}.json"

            benchmark.to_json_file(output_path)

            # Show what we got
            rec = benchmark.recommendations[0] if benchmark.recommendations else None
            if rec:
                print("  ✓ Sample data from first recommendation:")
                print(f"    - Profiles: {rec.profiles}")
                print(f"    - CIS Controls: {len(rec.cis_controls)}")
                print(f"    - MITRE: {'✓' if rec.mitre_mapping else '✗'}")
                print(f"    - NIST: {len(rec.nist_controls)}")
                print(f"    - Artifacts: {len(rec.artifacts)}")
                print(f"    - Parent: {'✓' if rec.parent else '✗'}")

            print()

        except Exception as e:
            print(f"  ✗ Error: {e}\n")
            import traceback

            traceback.print_exc()

    print("✓ Re-download complete!")


if __name__ == "__main__":
    main()
