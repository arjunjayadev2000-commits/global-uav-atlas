.PHONY: all analysis figures report powerbi test lint clean

all:            ## full pipeline: analysis, figures, Power BI export, report
	python run.py --all

analysis:       ## tables only
	python run.py --stage analysis

figures:        ## tables and figures
	python run.py --stage figures

powerbi:        ## star-schema export
	python run.py --stage powerbi

report:         ## rebuild the PDF
	python run.py --stage report

test:
	pytest -q

lint:
	ruff check src tests run.py

clean:          ## remove generated artefacts (raw data is never touched)
	rm -rf outputs/figures/* outputs/tables/* outputs/powerbi/* outputs/report/* \
	       data/interim/* data/processed/* outputs/run_manifest.json
