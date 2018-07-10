from contextlib import contextmanager
from itertools import chain
import json
import logging
import os
import select
from .settings import (
	RUNNER_COMMANDS, DEFAULT_MEMORY, DEFAULT_CPU,
	ALWAYS_RAISE, RUNNER_HANDLERS, ANALYTICS_ENABLED
)
import signal
import subprocess
import sys
import threading
import time
import traceback
from .utils import signal_handler, IterationCompleted, locked_attr_funcs


def create_process(executable, spec, swap_sigint=True, universal_newlines=True, 
				   stderr=None):

	handler = None
	if swap_sigint:
		handler = signal.signal(signal.SIGINT, signal.default_int_handler)

	popen = subprocess.Popen(
		executable,
		stdin=subprocess.PIPE,
		stdout=subprocess.PIPE,
		# stderr=subprocess.DEVNULL if stderr is None else stderr,
		stderr=subprocess.PIPE,
		bufsize=1 if universal_newlines else -1,
		universal_newlines=universal_newlines
	)

	if swap_sigint:
		signal.signal(signal.SIGINT, handler)

	term = '\n' if universal_newlines else b'\n'
	if not spec.endswith(term):
		spec += term
	popen.stdin.write(spec)
	popen.stdin.flush()

	ok = popen.stdout.readline()
	ok = ok.strip().upper()
	if isinstance(ok, str):
		ok = ok.encode('ascii', 'ignore')
	ok = ok == b'OK'

	if ok:
		return True, popen

	popen.stdout.flush()
	popen.stderr.flush()
	err = popen.stdout.read() + popen.stderr.read()
	popen.terminate()
	return False, err


if ANALYTICS_ENABLED:
	import psutil
	
	class StatsCollector(object):

		def __init__(self):
			self.data = {}
			self.counts = {}
			self.procs = {}

		def update(self, pids):
			for pid in pids:
				self.counts.setdefault(pid, 0)
				current = self.data.setdefault(pid, {})
				try:
					info = self.get_stats(pid)
					if info is None:
						continue

				except (
					ProcessLookupError, 
					psutil._exceptions.AccessDenied,
					psutil._exceptions.NoSuchProcess
				):
					continue

				for k, v in info.items():
					current.setdefault(k, 0)
					current[k] += v
				self.counts[pid] += 1

		def reset(self):
			self.data = {}
			self.counts = {}
			self.procs = {}

		def get_stats(self, pid):
			proc = self.procs.get(pid)

			if proc is None:
				proc = self.procs[pid] = psutil.Process(pid)
				return

			with proc.oneshot():
				return {
					'cpus': proc.cpu_percent() / 100.,
					'memory': proc.memory_info().rss
				}

		def average_stats(self, per_pid=True):
			out = {}
			for k, v in self.data.items():
				scaled = {}
				count = self.counts[k]
				for k2, v2 in v.items():
					scaled[k2] = v2 / float(count)
				out[k] = scaled

			if per_pid:
				return out

			final = {}
			cts = {}
			for v in out.values():
				for k2, v2 in v.items():
					final.setdefault(k2, 0)
					final[k2] += v2
					cts.setdefault(k2, 0)
					cts[k2] += 1

			for k, v in final.items():
				final[k] = v / cts[k]

			return final

class JobRunner(object):

	def __init__(self, spec, data_stream, memory_lim=DEFAULT_MEMORY, logger=logging.getLogger(),
				 executables=RUNNER_COMMANDS, cpu_lim=DEFAULT_CPU, n_procs=None, maintain=True,
				 handlers=RUNNER_HANDLERS):

		self.spec = spec
		self.executables = executables
		self.handlers = handlers
		self.memory_lim = memory_lim
		self.cpu_lim = cpu_lim
		self.data_stream = data_stream
		self.logger = logger
		self.data_stream = iter(data_stream)
		self._n_procs = n_procs

		self._procs = {}
		self.streams = {}
		self.exec_type = None
		self.exec_info = None
		self.executable = None
		self.handler = None
		self.signals_recvd = {}
		if ANALYTICS_ENABLED:
			self._stats = StatsCollector()
		else:
			self._stats = None
		self._running = False
		self.attrlocks = {
			name: threading.Lock() for name
			in ['_stats', '_procs', '_running']
		}
		self.monitor_thread = None
		self.time_elapsed = 0.
		self.items_processed = 0
		self.create = maintain

	get_stats, set_stats = locked_attr_funcs('_stats')
	stats = property(get_stats, set_stats)

	get_procs, set_procs = locked_attr_funcs('_procs')
	procs = property(get_procs, set_procs)

	get_running, set_running = locked_attr_funcs('_running')
	running = property(get_running, set_running)

	def n_procs(self):
		if self._n_procs is not None:
			return self._n_procs

		memory_estimate = float(self.spec.get('memory_estimate', 64 * 1024 ** 2))
		cpu_estimate = float(self.spec.get('cpu_estimate', 1.))

		m_n_procs = int(round(self.memory_lim / memory_estimate))
		c_n_procs = int(round(self.cpu_lim / cpu_estimate))

		return max(min(m_n_procs, c_n_procs), 1)

	def create_process(self, executable, handler, exec_info):
		spec_str = json.dumps(exec_info)
		executable = executable.copy()
		executable.append(handler)
		return create_process(executable, spec_str)

	def kill_process(self, proc, soft=True, wait=False):
		if soft:
			proc.send_signal(signal.SIGINT)
		else:
			proc.terminate()
		if wait:
			if isinstance(wait, int):
				proc.wait(wait)
			else:
				proc.wait()

	def loop(self):
		waiters = list(self.procs)
		ready = select.select()

	def setup(self, n_procs=None):
		if n_procs is None:
			n_procs = self.n_procs()

		try:
			self.exec_type = self.spec['exec_type']
		except ALWAYS_RAISE:
			raise
		except:
			return False, {
				'stack': traceback.format_exc(),
				'when': 'getting exec_type'
			}

		try:
			if isinstance(self.exec_type, dict):
				self.executable = self.exec_type['executable']
				self.handler = self.exec_type['handler']
				if self.executable.startswith('!'):
					self.executable = self.executables[self.executable[1:]]
				if self.handler.startswith('!'):
					self.handler = self.handlers[self.handler[1:]]
			else:
				self.executable = self.executables[self.exec_type]
				self.handler = self.handlers[self.exec_type]
		except ALWAYS_RAISE:
			raise
		except:
			return False, {
				'stack': traceback.format_exc(),
				'when': 'resolving executable/handler paths'
			}

		try:
			self.exec_info = self.spec['exec_info']
		except ALWAYS_RAISE:
			raise
		except:
			return False, {
				'stack': traceback.format_exc(),
				'when': 'getting exec_info'
			}

		all_success = True
		err = None
		self.logger.debug('creating %d processes', n_procs)
		self.logger.debug('executable: %s', self.executable)
		self.logger.debug('handler: %s', self.handler)
		for _ in range(n_procs):
			success, proc = self.create_process(
				self.executable, 
				self.handler, 
				self.exec_info
			)
			if not success:
				all_success = False
				try:
					proc = json.loads(proc)
				except:
					err = {
						'stack': proc,
						'when': 'decoding error (raw provided)'
					}
				break

			self.logger.debug('created %d', proc.pid)
			fn = proc.stdout.fileno()
			self.procs[fn] = proc
			self.streams[fn] = proc.stdout

		if not all_success:
			self.terminate(soft=False)
			self.procs, self.streams = {}, {}
			return False, err

		return True, None

	def terminate(self, soft=True, wait=False):
		for proc in self.procs.values():
			self.kill_process(proc, soft=soft, wait=wait)

	@signal_handler
	def handle_sigint(self, signum, frame):
		self.logger.debug('received SIGINT')
		n_ints = self.signals_recvd[signum]
		if n_ints > 1:
			self.logger.debug('SIGINT #%d. Terminating', n_ints)
			self.terminate(soft=False)

		if self.monitor_thread is not None and self.monitor_thread.is_alive():
			self.kill_monitoring_thread()

		raise KeyboardInterrupt

	def handle_stream(self, stream):
		out = stream.readline()
		fn = stream.fileno()
		proc = self.procs[fn]
		if not self.seed(proc.stdin):
			proc.stdin.close()
			self.kill_process(proc, soft=False, wait=True)
			del self.procs[fn], self.streams[fn]
		return out

	def handle_broken_stream(self, stream):
		fn = stream.fileno()
		proc = self.procs[fn]
		self.kill_process(proc, soft=False, wait=True)
		del self.procs[fn], self.streams[fn]
		if self.signals_recvd.get(signal.SIGINT, 0) > 0 or not self.create:
			return
		self.logger.debug('process died. creating new')
		success, proc = self.create_process(self.executable, self.handler, self.exec_info)
		self.logger.debug('created')
		if success:
			if self.seed(proc.stdin):
				fn = proc.stdout.fileno()
				self.procs[fn] = proc
				self.streams[fn] = proc.stdout
			else:
				self.kill_process(proc, soft=False, wait=True)
		else:
			self.create = False

	def write_line(self, stream, item):
		term = '\n' if isinstance(item, str) else b'\n'
		if not item.endswith(term):
			item += term
		stream.write(item)
		stream.flush()

	def loop(self, timeout=None):
		waiters = list(self.streams.values())
		if len(waiters) == 0:
			raise IterationCompleted()

		ready, _, _ = select.select(waiters, [], [], timeout)
		for stream in ready:
			try:
				item = self.handle_stream(stream)
				if item:
					yield item
			except BrokenPipeError:
				self.handle_broken_stream(stream)


	def seed(self, stream):
		try:
			val = next(self.data_stream)
		except StopIteration:
			return False
		else:
			try:
				self.write_line(stream, val)
			except:
				self.data_stream = chain([val], self.data_stream)
				raise
			return True

	def seed_procs(self):
		vals = list(self.procs.values())
		max_ind = -1
		for ind, proc in enumerate(self.procs.values()):
			self.logger.debug('seeding %d' % proc.pid)
			if not self.seed(proc.stdin):
				break
			max_ind = ind

		# delete unneeded processes
		remaining = len(vals) - max_ind - 1
		if remaining > 0:
			self.logger.debug('deleting %d processe(s)', remaining)
			for proc in vals[-remaining:]:
				fn = proc.stdout.fileno()
				self.kill_process(proc, soft=False, wait=True)
				del self.procs[fn], self.streams[fn]

	def update_stats(self):
		procs = [v.pid for v in self.procs.values() if not v.returncode]
		self.stats.update(procs)

	def monitor(self, interval=0.1):
		if self.stats is None:
			return
		try:
			while self.running:
				try:
					self.update_stats()
				except ALWAYS_RAISE:
					raise
				except:
					self.logger.error('error getting process stats: %s', traceback.format_exc())
				time.sleep(interval)
		except ALWAYS_RAISE:
			pass

	def create_monitoring_thread(self):
		orig = signal.signal(signal.SIGINT, signal.default_int_handler)
		thread = threading.Thread(target=self.monitor)
		signal.signal(signal.SIGINT, orig)
		return thread

	def kill_monitoring_thread(self, wait=False):
		running = self.running
		try:
			self.running = False
			if wait:
				self.monitor_thread.join()
		finally:
			self.running = running

	def gen(self, beg, timeout=None):
		while True:
			try:
				for item in self.loop(timeout):
					self.items_processed += 1
					self.time_elapsed = time.time() - beg
					yield item
			except IterationCompleted:
				break

	@contextmanager
	def run(self, timeout=None, swap_sigint=True, monitor=True):

		self.monitor_thread = None
		self.time_elapsed, self.items_processed = 0., 0
		self.create = True

		if swap_sigint:
			orig = signal.signal(signal.SIGINT, self.handle_sigint)

		if monitor:
			self.monitor_thread = self.create_monitoring_thread()
			self.running = True
			self.monitor_thread.start()

		try:
			beg = time.time()
			self.seed_procs()
			yield self.gen(beg, timeout)
		finally:
			self.terminate(soft=False, wait=True)
			self.procs, self.streams = {}, {}

			self.time_elapsed = time.time() - beg
			if swap_sigint:
				signal.signal(signal.SIGINT, orig)
			if monitor:
				self.kill_monitoring_thread(wait=True)
				self.monitor_thread = None
