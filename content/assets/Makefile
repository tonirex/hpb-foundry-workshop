# LiveWell workshop tasks. Run here (make validate) or from the repo root (make -C content/assets validate).
ROOT     := $(abspath ../..)
PYTHON   ?= python
ENV      ?=
RUNS     ?= 3
INITIALS ?=
LABS     ?= 0,1,2,3,4

.PHONY: help validate validate-live fill notebooks validate-rail clean-agents

help:
	@echo "make validate        content checks + narrative gate static/data layers (no Azure needed)"
	@echo "make validate-live   all layers: + graph check and RUNS=$(RUNS) data-agent calls per question (ENV=<azd env>)"
	@echo "make fill            recompute reference answers and refill the {{ref:...}} values in story and lab pages"
	@echo "make notebooks       lab*.py -> lab*.ipynb next to them (jupytext; the .ipynb files are not committed)"
	@echo "make validate-rail   run Labs LABS=$(LABS) top to bottom as INITIALS=test and check the key signals (~20 min)"
	@echo "make clean-agents    delete every livewell-<INITIALS>-* agent and memory store (INITIALS from content/assets/.env)"

validate:
	cd "$(ROOT)" && $(PYTHON) scripts/check-content.py
	cd "$(ROOT)" && $(PYTHON) scripts/validate-narrative.py --layers static,data --check --no-report
	cd "$(ROOT)" && $(PYTHON) -m unittest discover -s scripts/tests -p "test_*.py"

validate-live:
	cd "$(ROOT)" && $(PYTHON) scripts/validate-narrative.py --layers all --runs $(RUNS) $(if $(ENV),--env $(ENV))

fill:
	cd "$(ROOT)" && $(PYTHON) scripts/validate-narrative.py --layers static,data --fill --no-report

notebooks:
	$(PYTHON) -m jupytext --to ipynb lab0_setup.py lab1_knowledge.py lab2_govern.py lab2_evaluate.py lab3_tools.py lab3_fabric.py lab4_multiagent.py

validate-rail:
	cd "$(ROOT)" && $(PYTHON) scripts/validate-builder-rail.py --labs $(LABS) $(if $(INITIALS),--initials $(INITIALS))

clean-agents:
	$(PYTHON) -c "from common import livewell_common as lw; print('deleted:', ', '.join(lw.cleanup(everything=True)) or 'nothing')"
