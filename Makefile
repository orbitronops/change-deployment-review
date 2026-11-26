.PHONY: demo test lint clean

demo:
	python -m orbitronops_change_review review examples/risky-change.yaml --baseline examples/baseline.yaml

test:
	python -m pytest -q || python -m unittest discover -s tests -v

lint:
	python -m compileall -q src tests

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
