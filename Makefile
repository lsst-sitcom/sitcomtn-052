BUILDDIR = _build
.PHONY:
init:
	pip install tox pre-commit
	pre-commit install


.PHONY:
lint:
	tox run -e lint,linkcheck

.PHONY:
add-author:
	tox run -e add-author

.PHONY:
sync-authors:
	tox run -e sync-authors

.PHONY:
clean:
	rm -rf _build
	rm -rf .technote
	rm -rf .tox
	git checkout index.rst
	rm -f _static/burndown.png
	rm -f _static/block*




index.rst: bin/generate_dmtn.py 
	PYTHONPATH=milestones python3 bin/generate_dmtn.py

_static/report.csv:
	PYTHONPATH=milestones python3 milestones/milestones.py report --output=_static/report.csv 

_static/blockschedule.pdf:
	PYTHONPATH=milestones python3 milestones/milestones.py blockschedule --start-date -20 --output=_static/blockschedule.pdf 
	PYTHONPATH=milestones python3 milestones/milestones.py blockschedule --start-date -20 --output=_static/blockschedule.png

_static/burndown.png:
	PYTHONPATH=milestones python3 milestones/milestones.py burndown --prefix="SIT COM SUM"  --output=_static/burndown.png --months=3
	PYTHONPATH=milestones python3 milestones/milestones.py burndown --prefix="SUM"  --output=_static/burndownSUM.png --months=3
	PYTHONPATH=milestones python3 milestones/milestones.py burndown --prefix="SIT"  --output=_static/burndownSIT.png --months=3
	PYTHONPATH=milestones python3 milestones/milestones.py burndown --prefix="COM"  --output=_static/burndownCOM.png --months=3

_static/graph_%.png:
	PYTHONPATH=milestones python3 milestones/milestones.py graph --wbs=$* --output=$@.dot
	dot -Tpng $@.dot > $@


html: index.rst _static/burndown.png _static/graph_06C.00.png _static/graph_06C.01.png _static/graph_06C.02.png  _static/blockschedule.pdf  _static/report.csv
	tox run -e html
	cp  _static/blockschedule.pdf $(BUILDDIR)/html
	cp  _static/report.csv $(BUILDDIR)/html

