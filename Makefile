build-and-run: 
	ls -a
	python ./src/translator.py ./example/$(DIR)/sources.s ./example/$(DIR)/out.maibinbin --debug=./example/$(DIR)/translator.debug
	python ./src/machine.py ./example/$(DIR)/out.maibinbin --conf=./example/$(DIR)/config.yaml 2> ./example/$(DIR)/machine.log