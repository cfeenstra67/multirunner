from . import handlers
import inspect
import multiprocessing as mp
import os
import psutil
import subprocess
import sys
from .utils import python2_cmd, python3_cmd, node_cmd

_major = sys.version_info.major

DEFAULT_MEMORY = psutil.virtual_memory().total * .9
DEFAULT_CPU = mp.cpu_count()

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