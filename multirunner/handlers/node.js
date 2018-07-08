var crypto = require('crypto');
var fs = require('fs');
var os = require('os');
var path = require('path');
var readline = require('readline');

function OutputCapture() {
	this.stderr = '';
	this.stdout = '';
	this.save = {};
}

OutputCapture.prototype.writeStd = function(string, stream) {
	let save = process[stream].write;
	process[stream].write = this.save[stream] || save;
	process[stream].write(string);
	process[stream].write = save;
};

OutputCapture.prototype.write = function(stream, string, encoding, fd) {
	if (stream == 'stdout') {
		this.stdout += string;
	} else {
		this.stderr += string;
	}
};

OutputCapture.prototype.start = function() {
	this.save.stdout = process.stdout.write;
	this.save.stderr = process.stderr.write;
	process.stdout.write = this.write.bind(this, 'stdout');
	process.stderr.write = this.write.bind(this, 'stderr');
};

OutputCapture.prototype.stop = function() {
	process.stdout.write = this.save.stdout || process.stdout.write;
	process.stderr.write = this.save.stderr || process.stderr.write;
};

function sortedJSON(obj) {
	return JSON.stringify(obj, Object.keys(obj).sort());
}

function makeTmp(args) {
	let suf = args.suffix || '',
		rbytes = args.nBytes || 4,
		fname = 'tmp' + crypto.randomBytes(rbytes).readUInt32LE(0) + suf;

	fname = path.join(os.tmpdir(), fname);
	fs.writeFileSync(fname, args.data || '');
	return fname
}

function getHandler(fpath, handler) {
	fpath = path.resolve(fpath);
	let mod = require(fpath),
		handlerFunc = mod[handler];

	if (handlerFunc == null) {
		throw Error('Invalid handler "' + handler + '"')
	}

	return {
		module: mod,
		handler: handlerFunc
	}
}

function validateSpec(spec) {
	let exec_info = null;
	try {
		exec_info = JSON.parse(spec);
	} catch (exc) {
		return {
			valid: false,
			data: {
				stack: exc.stack,
				when: 'loading spec'
			}
		};
	}

	let rm = true, fpath = null;

	try {
		let code = exec_info.code, input_type = 'string';

		if (!code) {
			throw Error('"code" is a required field in exec_info')
		}

		if (code && (typeof code != 'string')) {
			input_type = code.type;
			code = code.data;
		}

		if (!code) {
			throw Error('code must be specified!');
		}

		if (input_type == 'string') {
			fpath = makeTmp({
				suffix: '.js',
				data: code
			});
		} else if (input_type == 'path') {
			fpath = code;
			rm = false;
		} else {
			throw Error(input_type + ' is not a valid input type');
		}
	} catch (exc) {
		try { if (rm) fs.unlink(fpath); }
		catch (exc) {}

		return {
			valid: false, 
			data: {
				stack: exc.stack,
				when: 'loading code'
			}
		}
	}

	try {
		let res = null;
		try {
			res = getHandler(fpath, exec_info.handler || 'main');
		} catch (exc) {
			return {
				valid: false,
				data: {
					stack: exc.stack,
					when: 'loading module'
				}
			};
		}

		try {
			setup_hook = exec_info.setup_hook;
			if (setup_hook) {
				let oc = new OutputCapture();
				oc.start();
				try { res.module[setup_hook](); }
				finally { oc.stop(); }
			}
		} catch (exc) {
			return {
				valid: false,
				data: {
					stack: exc.stack,
					when: 'setup hook'
				}
			};
		}

		return {
			valid: true,
			data: res.handler
		}
	} finally {
		try { if (rm) fs.unlink(fpath); }
		catch (exc) {}
	}}

function handleItem(handler, item, context) {
	let oc = new OutputCapture(), 
		code = 0;

	oc.start();
	try {
		try {
			arg = JSON.parse(item);
			code = handler(arg, context);
			code = parseInt(code);
			if (!isFinite(code)) 
				code = 0;
		} catch (exc) {
			console.error(exc.stack);
			code = 1;
		}
	} finally {
		oc.stop();
	}

	return {
		data: item,
		exit: code,
		stdout: oc.stdout,
		stderr: oc.stderr
	};
}

function main(argv) {
	let rl = readline.createInterface({
		input: process.stdin
	}), 
		linesRecvd = 0,
		handler = null;

	rl.on('line', function(line) {
		linesRecvd++;
		if (linesRecvd < 2) {
			result = validateSpec(line);
			if (result.valid) {
				console.log('OK');
				handler = result.data;
			} else {
				console.log('ERROR');
				console.log(sortedJSON(result.data));
				process.exit(1);
			}
		} else {
			if (handler == null) {
				throw Error('Null Handler!');
			}
			val = handleItem(handler, line);
			console.log(sortedJSON(val));
		}
	});
}

if (require.main == module) {
	main(process.argv.slice(2));
}