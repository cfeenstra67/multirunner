from functools import wraps
import select
import subprocess
import sys
import time

class IterationCompleted(Exception):
	pass

def read_wait(streams, timeout=None, min_ready=None):
	streams = list(streams)
	if min_ready is None:
		min_ready = len(streams)

	done_streams = []
	beg = time.time()
	while True:
		if timeout is None:
			to = None
		else:
			to = timeout - (time.time() - beg)
			if to < 0:
				raise TimeoutError('an insufficient quantity of streams buffered in time')

		done, _, _ = select.select(streams, [], [], to)
		for val in done:
			streams.remove(val)
		done_streams.extend(done)

		if len(done_streams) >= min_ready or len(streams) == 0:
			return done_streams

def signal_handler(func):
	@wraps(func)
	def handler(self, signum, frame, store=True):
		if store:
			if not hasattr(self, 'signals_recvd'):
				self.signals_recvd = {}
			self.signals_recvd.setdefault(signum, 0)
			self.signals_recvd[signum] += 1
		return func(self, signum, frame)
	return handler

def locked_attr_funcs(attr):
	def _get(self):
		with self.attrlocks[attr]:
			return getattr(self, attr)

	def _set(self, val):
		with self.attrlocks[attr]:
			setattr(self, attr, val)

	_get.__name__ = 'get_%s' % attr
	_set.__name__ = 'set_%s' % attr

	return _get, _set

def command_exists(cmd, shell=False):
	wcmd = ['which']
	if shell:
		wcmd = subprocess.list2cmdline(wcmd)
		wcmd = '{} {}'.format(wcmd, cmd)
	else:
		if isinstance(cmd, str):
			cmd = [cmd]
		wcmd.extend(cmd)
	proc = subprocess.Popen(
		wcmd, 
		stdout=subprocess.PIPE, 
		stderr=subprocess.DEVNULL, 
		shell=shell
	)
	out, _ = proc.communicate()
	return bool(out)


def python2_cmd(default='python', ops=['python2', 'python']):
	if sys.version_info.major == 2:
		return sys.executable

	for op in ops:
		if command_exists(op):
			return op

	return default

def python3_cmd(default='python3', ops=['python3', 'python']):
	if sys.version_info.major == 3:
		return sys.executable

	for op in ops:
		if command_exists(op):
			return op

	return default

def node_cmd(default='node', ops=['node.js', 'node']):
	for op in ops:
		if command_exists(op):
			return op

	return default