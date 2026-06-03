build: 
	python ./src/translator.py ./example/$(DIR)/sources.s ./example/$(DIR)/out.maibinbin --debug=./example/$(DIR)/translator.debug
run:
	python ./src/machine.py ./example/$(DIR)/out.maibinbin --conf=./example/$(DIR)/config.yaml 2> ./example/$(DIR)/machine.log
build-o:
	python ./src/translator.py ./example/$(DIR)/sources.s ./example/$(DIR)/out.maibinbin --debug=./example/$(DIR)/translator.debug --optimize

EXAMPLE_DIRS := $(wildcard example/*)

build-and-run-all:
	@for dir in $(EXAMPLE_DIRS); do \
		echo "=== $$dir ==="; \
		$(MAKE) build-o DIR=$$(basename $$dir); \
		$(MAKE) run DIR=$$(basename $$dir); \
	done


collect-golden:
	@for dir in $(EXAMPLE_DIRS); do \
		name=$$(basename $$dir); \
		\
		machine_yml=tests/golden/machine/$$name.yml; \
		mkdir -p tests/golden/machine; \
		{ \
			echo "config_file: |"; \
			sed 's/^/  /' $$dir/config.yaml; \
			echo "bin_file: !!binary |"; \
			base64 $$dir/out.maibinbin | sed 's/^/  /'; \
			echo "machine_log: |"; \
			sed 's/^/  /' $$dir/machine.log; \
		} > $$machine_yml; \
		echo "Written $$machine_yml"; \
		\
		translator_yml=tests/golden/translator/$$name.yml; \
		mkdir -p tests/golden/translator; \
		{ \
			echo "sources: |"; \
			sed 's/^/  /' $$dir/sources.s; \
			echo ""; \
			echo "bin_out: !!binary |"; \
			base64 $$dir/out.maibinbin | sed 's/^/  /'; \
			echo "translator_debug: |"; \
			sed 's/^/  /' $$dir/translator.debug; \
		} > $$translator_yml; \
		echo "Written $$translator_yml"; \
	done