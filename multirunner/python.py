from __future__ import print_function

import argparse
import fileinput
try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO
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
        self.streams = {
            name: StringIO() for name in 
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
        spec = json.loads(spec)
        execution_info = spec['exec_info']
    except ALWAYS_RAISE:
        raise
    except:
        return False, {
            'stack': traceback.format_exc(),
            'when': 'loading spec'
        }

    try:
        code = execution_info['code']
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py') as ntf:
            path = ntf.name
            ntf.write(code)
    except ALWAYS_RAISE:
        raise
    except:
        try: os.remove(path)
        except FileNotFoundError: pass

        return False, {
            'stack': traceback.format_exc(),
            'when': 'writing file'
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

def main(in_data):
    fin = iter(in_data)
    spec = next(fin)
    valid, data = validate_spec(spec)
    if valid:
        print('OK')
        for item in fin:
            import random
            if random.random() > .9:
                raise Exception()
            val = handle_item(data, item)
            if val is None:
                break
            print(json.dumps(val))
    else:
        print('ERROR')
        print(json.dumps(data))

if __name__ == '__main__':
    try:
        main(fileinput.input())
    except ALWAYS_RAISE:
        pass