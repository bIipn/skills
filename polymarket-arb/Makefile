# Simple commands for setting up and running the bot.
# Use the project venv if it exists, else system python3.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: help install test backtest paper run live logs stop dashboard

help:
	@echo "Polymarket arb bot — common commands:"
	@echo "  make install    Set up venv + deps + 24/7 launchd service (macOS)"
	@echo "  make test       Run the test suite"
	@echo "  make backtest   Run a 500-tick offline backtest"
	@echo "  make paper      Run with REAL prices + SIMULATED fills (no key needed)"
	@echo "  make run        Run with current .env settings (foreground)"
	@echo "  make dashboard  Open the dashboard in a browser"
	@echo "  make logs       Tail the service logs"
	@echo "  make stop       Stop the 24/7 service"

install:
	./deploy/install-macos.sh

test:
	$(PY) -m pytest -q

backtest:
	$(PY) run.py --backtest --ticks 500

# Safe dry run: live market data, simulated execution. Needs NO credentials.
paper:
	PM_DATA_MODE=live PM_EXECUTION_MODE=paper $(PY) run.py

# Kalshi-only demo (the venue you can legally trade): real Kalshi prices,
# simulated fills, no credentials.
kalshi:
	PM_VENUE=kalshi PM_DATA_MODE=live PM_EXECUTION_MODE=paper $(PY) run.py

# Market-making demo on Kalshi: quote both sides, earn rewards + spread.
market-make:
	PM_VENUE=kalshi PM_MARKET_MAKING=1 PM_DATA_MODE=live PM_EXECUTION_MODE=paper $(PY) run.py

run:
	$(PY) run.py

# Live trading — only after funding a burner wallet and filling .env. Owner step.
live:
	PM_DATA_MODE=live PM_EXECUTION_MODE=live $(PY) run.py

dashboard:
	open http://localhost:8000 || echo "open http://localhost:8000 in your browser"

logs:
	tail -f logs/arb.out.log logs/arb.err.log

stop:
	launchctl unload $$HOME/Library/LaunchAgents/com.polymarket-arb.plist 2>/dev/null || true
	@echo "Service stopped."
