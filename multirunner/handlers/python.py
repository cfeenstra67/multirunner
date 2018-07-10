from __future__ import print_function

import argparse
import fileinput
try:
    from io import StringIO, BytesIO
except ImportError:
    from StringIO import StringIO
    from BytesIO import BytesIO
import json
import logging
import os
import signal
import sys
import tempfile
import traceback

ALWAYS_RAISE = (KeyboardInterrupt, SystemExit)

class OutputCapture(object):

    def __init__(self, stdout=True, stderr=True):
        self.capture = {
            'stdout': stdout,
            'stderr': stderr
        }

        io_con = BytesIO if sys.version_info.major == 2 else StringIO
        self.streams = {
            name: io_con() for name in 
            ['stdout', 'stderr']
        }
        self.saves = {
            name: getattr(sys, name) for name in
            ['stdout', 'stderr']
        }

    def __enter__(self):
        for stream in ['stdout', 'stderr']:
            if self.capture[stream]:
                setattr(sys, stream, self.streams[stream])
        return self

    def __exit__(self, *args, **kwargs):
        for stream in ['stdout', 'stderr']:
            setattr(sys, stream, self.saves[stream])

def get_handler(path, mod_name, handler):
    major, minor = sys.version_info[:2]
    if major == 2:
        import imp
        mod = imp.load_source(mod_name, path)
    else:
        if minor < 5:
            from importlib.machinery import SourceFileLoader
            mod = SourceFileLoader(mod_name, path).load_module()
        else:
            import importlib.util
            spec = importlib.util.spec_from_file_location(mod_name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

    try:
        handler = getattr(mod, handler)
    except AttributeError:
        raise ValueError('Invalid handler "%s"' % str(handler))
    return handler, mod

def validate_spec(spec):
    try:
        execution_info = json.loads(spec)
    except ALWAYS_RAISE:
        raise
    except:
        return False, {
            'stack': traceback.format_exc(),
            'when': 'loading spec'
        }

    rm, path = True, None
    try:
        code, input_type = execution_info['code'], 'string'

        if isinstance(code, dict):
            input_type = code['type']
            code = code['data']

        if input_type == 'string':
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py') as ntf:
                path = ntf.name
                ntf.write(code)
        elif input_type == 'path':
            assert os.path.isfile(code), '%s is not a valid local path' % str(code)
            path = code
            rm = False
        else:
            raise ValueError('%s is not a valid input type' % str(input_type))

    except ALWAYS_RAISE:
        raise
    except:
        if path is not None:
            try: os.remove(path)
            except FileNotFoundError: pass

        return False, {
            'stack': traceback.format_exc(),
            'when': 'loading code'
        }

    try:
        try:
            mod_name = execution_info.get('mod_name', 'run')
            handler = execution_info.get('handler', 'main')
            handler_func, mod = get_handler(path, mod_name, handler)
        except ALWAYS_RAISE:
            raise
        except:
            return False, {
                'stack': traceback.format_exc(),
                'when': 'loading module'
            }

        try:
            init_hook = execution_info.get('setup_hook')
            if init_hook is not None:
                with OutputCapture():
                    getattr(mod, init_hook)()
        except ALWAYS_RAISE:
            raise
        except:
            return False, {
                'stack': traceback.format_exc(),
                'when': 'setup hook'
            }

        return True, handler_func
    finally:
        if rm:
            try: os.remove(path)
            except FileNotFoundError: pass

def handle_item(handler, item, context_arg=True):
    oc = OutputCapture()
    with oc:
        try:
            args = json.loads(item),
            if context_arg:
                args += {},
            code = handler(*args)
            try:
                code = int(code)
            except:
                code = 0
        except ALWAYS_RAISE:
            raise
        except:
            code = 1
            traceback.print_exc()

    return {
        'data': item,
        'exit': code,
        'stdout': oc.streams['stdout'].getvalue(),
        'stderr': oc.streams['stderr'].getvalue()
    }

def iterate_stdin():
    '''
    Something weird about iterating through sys.stdin (which
    I think is what fileinput does internally) in python2--it 
    doesn't start iterating until it's closed or something.
    '''
    while True:
        line = sys.stdin.readline()
        yield line

def main(in_data):
    fin = iter(in_data)
    spec = next(fin)

    valid, data = validate_spec(spec)
    if valid:
        sys.stdout.write('OK\n')
        sys.stdout.flush()
        # print('OK')
        for item in fin:
            val = handle_item(data, item)
            if val is None:
                break
            print(json.dumps(val, sort_keys=True))
    else:
        print('ERROR')
        print(json.dumps(data, sort_keys=True))

if __name__ == '__main__':
    lines = iterate_stdin if sys.version_info.major == 2 else fileinput.input
    try:
        main(lines())
    except ALWAYS_RAISE:
        pass