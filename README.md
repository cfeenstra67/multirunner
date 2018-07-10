This package provides functionality for operating on an input stream using using arbitrarily many child processes. The child processes operate on each item in the stream using a handler function, which can be written in any of the supported languages. Currently python2.x, python3.x, and node are supported (I'm not familiar with node versions--the `readline` module and `let` syntax are the only two things used that may be version-dependent though, everything else is pretty standard JS). 

The `JobRunner` class is the core of the package--it takes a data stream, a job specification, and a number of processes. The `JobRunner`  reads the `exec_type` from the spec (which is passed as a python dictionary or a YAML/JSON file for the CLI) and resolves an executable and a handler from it. In most cases, `exec_type` will be a string, either `python2`, `python3`, or `node` (it can also be an object specifying `executable` and `handler`). Given that, it spawns the proper number of child processes running the resolved `handler` script with the resolved executable. Then, using the `setup()` function, the runner will pass the job specification to each of the child processes, and wait for a response. If the handler is able to load the module and prepare to consume items from the data stream successfully in all child processes, the function will return a positive response indicating that the runner is ready to consume the data stream. Once that's done, the `run()` method can be used to process the items from the data stream and yield results. Results are dictionaries with keys `exit` (exit code), `data` (input), `stdout`, and `stderr`. Exit codes are the return values of the function, or 0 if an integer cannot be resolved from the return value. The `run()` function should be used with the following syntax:
```python
data = ({'foo': i} for i in range(100))
runner = JobRunner(spec, data)
valid, err = runner.setup()
assert valid

with runner.run() as gen:
	for item in gen:
		# process item
```
the context manager yielding a generator is a bit clunky syntactically, but in this case a regular generator isn't sufficient to make sure the necessary cleanup is done regardless of whether the generator is exhausted. 

## CLI

The `JobRunner` functionality can also be accessed through the CLI. Specs are provided as files, either YAML or JSON. The data stream can either be provided as a file or through stdin, where each line is a JSON object. A spec file might look like:
```yaml
exec_type: python3
exec_info:
	code:
		type: path
		data: run.py

# exec_info:
# 	code:
# 		type: string
#		data: "def setup(): pass \ndef handle(event, context): print(event, context)"
#	setup_hook: setup
#	handler: main
```
the commented example shows the other options for specifying `code`: `handler` specifies the function to be used to process items, and should take `event` and `context` args (`context` will be an empty dictionary/object currently--this is done for future use and to have the same interface as AWS Lambda). If not provided, it defaults to `main`. `setup_hook` specifies a function in the module defined by `code` to be run once when each child process is created. `code` should be either a string containing code or a object with `type` and `data` keys, where `type` is one of `string` or `path`. 

The CLI can be used (with the `multirunner` package installed):
```bash
multirunner -s spec.yml -d data.json
```
Using `python3 -m multirunner` instead of `multirunner` can be used if the package is not installed or if there is a name overlap. Use the `--help` argument ot view additional options. 

## Installation

To install, run `pip3 install git+https://github.com/cfeenstra67/multirunner.git`

The base package has no external dependencies, however `PyYAML` and `psutil` are optional dependencies. They can be installed using `git+https://github.com/cfeenstra67/multirunner.git[yaml]` and `git+https://github.com/cfeenstra67/multirunner.git[analytics]`, respectively, and everything can be installed using `git+https://github.com/cfeenstra67/multirunner.git[yaml,analytics]` in the command above.