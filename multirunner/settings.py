from . import handlers
import inspect
import multiprocessing as mp
import os
import subprocess
import sys
from .utils import python2_cmd, python3_cmd, node_cmd

try:
	import psutil
	ANALYTICS_ENABLED = True
except ImportError:
	ANALYTICS_ENABLED = False

try:
	import yaml
	YAML_ENABLED = True
except ImportError:
	YAML_ENABLED = False

_major = sys.version_info.major

DEFAULT_CPU = mp.cpu_count()

if ANALYTICS_ENABLED:
	DEFAULT_MEMORY = psutil.virtual_memory().total * .9
else:
	try:
		DEFAULT_MEMORY = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
	except ValueError:
		# Not even used in the current implementation (n_procs always passed), so 
		# just estimate this if we can't find it w/ the two ways above, no need to
		# raise an error (estimating 2gb mem/core)
		DEFAULT_MEMORY = DEFAULT_CPU * 2 * 1024 ** 3

HANDLERS_DIR = os.path.dirname(inspect.getfile(handlers))

ALWAYS_RAISE = (KeyboardInterrupt, SystemExit)

PYTHON2_CMD = python2_cmd()
PYTHON3_CMD = python3_cmd()
PYTHON_CMD = PYTHON3_CMD if _major == 3 else PYTHON2_CMD

NODE_CMD = node_cmd()

RUNNER_HANDLERS = {
	'python2': os.path.join(HANDLERS_DIR, 'python.py'),
	'python3': os.path.join(HANDLERS_DIR, 'python.py'),
	'python': os.path.join(HANDLERS_DIR, 'python.py'),
	'node': os.path.join(HANDLERS_DIR, 'node.js')
}

RUNNER_COMMANDS = {
	'python2': [PYTHON2_CMD, '-u'],
	'python3': [PYTHON3_CMD, '-u'],
	'python': [PYTHON_CMD, '-u'],
	'node': [NODE_CMD, '--no-deprecation']
}