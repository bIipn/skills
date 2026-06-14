#!/usr/bin/env python3
"""Convenience launcher.

  python run.py            # start dashboard + engine on :8000
  python run.py --scan     # one headless scan, print opportunities, exit
"""
import argparse
import asyncio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true",
                    help="Run a single detection scan and print results.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if args.scan:
        from backend.engine import engine
        results = asyncio.run(engine.tick())
        snap = engine.snapshot()
        print(snap["banner"])
        print(f"\nScanned {snap['markets_scanned']} markets in "
              f"{snap['last_scan_ms']}ms — found "
              f"{len(snap['live_opportunities'])} live opportunities:\n")
        for o in snap["live_opportunities"]:
            print(f"  [{o['kind']:>16}] {o['description'][:70]}")
            print(f"      cost ${o['cost']:.2f}  floor ${o['guaranteed_payoff']:.2f}  "
                  f"profit +${o['profit']:.2f}  edge {o['edge_pct']}%")
        print(f"\nExecuted {len(results)} trades this tick. "
              f"Bankroll: ${snap['bankroll']:.2f}")
        return

    import uvicorn
    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
