VENV_PATH = ./venv
VENV = . $(VENV_PATH)/bin/activate;
COMPONENT_NAME = mr_star_garland
VERSION = 2.0.0

.PHONY: configure
configure:
	rm -rf "$(VENV_PATH)"
	python3.14 -m venv "$(VENV_PATH)"
	$(VENV) pip install -r requirements.txt

.PHONY: clean
clean:
	@rm -rf venv

.PHONY: lint
lint:
	$(VENV) pylint custom_components/
	$(VENV) ruff check ./custom_components

.PHONY: test
test:
	$(VENV) pytest

.PHONY: publish
publish:
	@$(MAKE) lint
	@$(MAKE) test
	git add Makefile
	git commit -m "chore: release $(VERSION)"
	git tag -a v$(VERSION) -m "release $(VERSION)"
	git push && git push --tags
