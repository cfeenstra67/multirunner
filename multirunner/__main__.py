import argparse
import atexit
import json
import logging
import os
from .runner import JobRunner
from .settings import ALWAYS_RAISE, RUNNER_HANDLERS, YAML_ENABLED
import sys
import warnings

def parse_args(argv=sys.argv[1:], default_loglvl=logging.INFO):
	parser = argparse.ArgumentParser('MultiRunner')
	parser.add_argument('-s', '--spec-file', type=str, default=None,
		help='YAML file containing job specification. Optional--jobs can '
		'be run using only command line args. Some options, like custom '
		'handlers and executables, can only be specified in a spec file.')
	
	parser.add_argument('-d', '--data', type=str, default=sys.stdin,
		help='Data file to be used as input. uses stdin by default. '
		'Input data should be one JSON object per line')
	parser.add_argument('--encoding', type=str, default='utf-8',
		help='Encoding to be used reading data file, if applicable')

	parser.add_argument('-n', '--n-processes', type=int, default=os.cpu_count(),
		help='Number of processes to spawn to process the input.')

	parser.add_argument('-o', '--output-file', type=str, default=sys.stdout,
		help='Output file to write the results of the job to. Default is stdout')
	parser.add_argument('--output-mode', type=str, default='w+',
		help='Mode to use when opening the output file; default w+, '
		'(if this is being provided, it should be one of [w, w+, a, a+])')

	parser.add_argument('-L', '--loglevel', type=str, default=default_loglvl,
		help='Log level. default INFO')
	parser.add_argument('-l', '--logfile', type=str, default=sys.stdout,
		help='File to write logger output to.')

	parser.add_argument('-e', '--exec-type', type=str, default=None,
		help='Overrides exec_type in spec if one is being provided')
	parser.add_argument('-c', '--code', type=str, default=None,
		help='Overrides exec_info->code in spec if one is being provided')
	parser.add_argument('--handler', type=str, default=None,
		help='Overrides exec_info->handler in spec if one is being provided')
	parser.add_argument('--setup-hook', type=str, default=None,
		help='Overrides exec_info->setup_hook in spec if one is being provided')

	args = parser.parse_args(argv)
	# if args.spec_file is None:
	# 	parser.error('You must provide a spec')


	if isinstance(args.data, str):
		try:
			stream = open(args.data, encoding=args.encoding)
		except BaseException as exc:
			parser.error('Error opening data stream: %s %s' % (exc.__class__.__name__, str(exc)))
		else:
			atexit.register(stream.close)
			args.data = stream

	if isinstance(args.output_file, str):
		try:
			args.output_mode = args.output_mode.replace('b', '')
			stream = open(args.output_file, args.output_mode)
		except BaseException as exc:
			parser.error('Error when opening output stream: %s %s' % (exc.__class__.__name__, str(exc)))
		else:
			atexit.register(stream.close)
			args.output_file = stream

	logger = logging.getLogger('MultiRunner')

	if isinstance(args.loglevel, str):
		try:
			args.loglevel = int(args.loglevel)
		except:
			try:
				args.loglevel = getattr(logging, args.loglevel.upper())
			except AttributeError:
				args.loglevel = default_loglvl

	if isinstance(args.logfile, str):
		handler = logging.FileHandler(args.logfile)
	else:
		handler = logging.StreamHandler(sys.stdout)

	fmtr = logging.Formatter('%(asctime)s - %(name)s - [%(levelname)s] - %(message)s')
	handler.setFormatter(fmtr)
	logger.addHandler(handler)
	logger.setLevel(args.loglevel)

	return args, parser, logger

def validate_spec(spec):
	if 'exec_type' not in spec:
		yield 'You must specify an exec_type!'
	if 'exec_info' not in spec:
		yield 'You must specify exec_info!'

def log_stats(runner, log):
	log('# Processes: %d', runner.n_procs())
	if runner.stats is not None:
		avgs = runner.stats.average_stats(per_pid=False)
		statstr = json.dumps(avgs, indent=4)
		log('Per-process average stats:\n%s', statstr)

def load_spec(args, parser):
	spec = {}
	if args.spec_file is not None:
		if YAML_ENABLED:
			import yaml
			if args.spec_file.endswith('.json'):
				loader = json.load
			else:
				loader = yaml.load
		else:
			warnings.warn('optional YAML dependency missing--spec must be JSON')
			loader = json.load

		try:
			with open(args.spec_file) as f:
				spec = loader(f)
				assert isinstance(spec, dict)
		except (yaml.reader.ReaderError, AssertionError) as exc:
			parser.error('Error loading YAML spec. Spec must be a valid YAML object')
			return
		except BaseException as exc:
			parser.error('Error opening spec file: %s %s' % (exc.__class__.__name__, str(exc)))
			return

	if args.exec_type is not None:
		spec['exec_type'] = args.exec_type

	if args.code is not None:
		exec_info = spec.setdefault('exec_info', {})
		exec_info['code'] = {'type': 'path', 'data': args.code}

	if args.handler is not None:
		exec_info = spec.setdefault('exec_info', {})
		exec_info['handler'] = args.handler

	if args.setup_hook is not None:
		exec_info = spec.setdefault('exec_info', {})
		exec_info['setup_hook'] = args.setup_hook

	errs = list(validate_spec(spec))
	if len(errs) > 0:
		parser.error('Errors encountered when validating spec:\n%s' % '\n'.join(errs))
		return

	return spec

def main(argv=sys.argv[1:]):
	args, parser, logger = parse_args(argv)

	spec = load_spec(args, parser)
	if spec is None:
		return 2

	runner = JobRunner(
		spec, args.data, 
		n_procs=args.n_processes,
		logger=logger
	)

	try:
		success, err = runner.setup()
	except ALWAYS_RAISE as exc:
		logger.info('Exiting w/ %s' % exc.__class__.__name__)
		return 1

	if not success:
		parser.error('Error encountered when %s: \n%s' % (err['when'], err['stack']))
		return 2

	try:
		for item in runner.run():
			if not item.endswith('\n'):
				item += '\n'
			args.output_file.write(item)
	except ALWAYS_RAISE as exc:
		logger.info('Exiting w/ %s' % exc.__class__.__name__)
		return 1

	log_stats(runner, logger.info)

	return 0

if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))