.PHONY: install test scan daily dashboard watch clean help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements.txt

test:  ## Run all tests
	python -m pytest tests/ -v

scan:  ## Run a scan on default chains
	python nansenscope.py scan --chains ethereum,base

scan-all:  ## Scan all 18 chains
	python nansenscope.py scan --all-chains

daily:  ## Full daily pipeline (scan + signals + alerts + charts + report + dashboard)
	python nansenscope.py daily --chains ethereum,base,solana,arbitrum,bnb

dashboard:  ## Open interactive dashboard from latest data
	python -c "from dashboard import generate_dashboard; generate_dashboard()"

watch:  ## Start continuous monitoring
	python nansenscope.py watch --chains ethereum,base --interval 5

profile:  ## Profile a wallet (usage: make profile ADDR=0x...)
	python nansenscope.py profile --address $(ADDR) --chain ethereum

clean:  ## Remove generated reports and charts
	rm -rf reports/*.md reports/charts/*.png reports/dashboard.html
