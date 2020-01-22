#!/usr/bin/env node

'use strict';

var os = require("os");
var ns_status = require("./ns-status");
var oref0_normalize_temps = require("./oref0-normalize-temps");
var json = require("json");
var uniqueFilename = require('unique-filename')
var fs = require('fs');
var requireUtils = require('../lib/require-utils');

function createRetVal(stdout, return_val) {
    var returnObj = {
        err: "",
        stdout: stdout,
        return_val: return_val
    }
    return returnObj;
}

function serverListen() {

    const net = require('net');
    const fs = require('fs');
    const unixSocketServer = net.createServer({
        allowHalfOpen: true
    });

    var socketPath = '/tmp/oaps_shared_node';
    try {
        fs.unlinkSync(socketPath);
    } catch (err) {
        if (err.code == 'ENOENT') {
            // Intentionly ignored.
        } else {
            throw err;
        }
    }
    unixSocketServer.listen(socketPath, () => {
        console.log('now listening');
    });

    unixSocketServer.on('end', function() {
        console.log("server 2 disconnected from port");
    });

    unixSocketServer.on('connection', (s) => {
        console.log('got connection!');
        s.allowHalfOpen = true;
        s.on('end', function() {
            console.log("server 2 disconnected from port");
        });

        s.on('error', function(err) {
            console.log("there was an error in the client and the error is: " + err.code);
        });

        s.on("data", function(data) {
            //... do stuff with the data ...
            console.log('read data', data.toString());
            var command = data.toString().split(' ');

            // Split by space except for inside quotes 
            // (https://stackoverflow.com/questions/16261635/javascript-split-string-by-space-but-ignore-space-in-quotes-notice-not-to-spli)
            var command = data.toString().match(/\\?.|^$/g).reduce((p, c) => {
                if (c === '"') {
                    p.quote ^= 1;
                } else if (!p.quote && c === ' ') {
                    p.a.push('');
                } else {
                    p.a[p.a.length - 1] += c.replace(/\\(.)/, "$1");
                }
                return p;
            }, {
                a: ['']
            }).a;

            command = command.map(s => s.trim());

            var result = 'unknown command';
            var return_val = 0;

            console.log('command = ', command);

            if (command[0] == 'ns-status') {
                // remove the first parameter.
                command.shift();
                try {
                    result = ns_status(command);
                    //sleepFor(2000);
                } catch (err) {
                    return_val = 1;
                    console.log('exception when parsing ns_status ', err);
                }
            } else if (command[0] == 'oref0-normalize-temps') {
                command.shift();
                try {

                    result = oref0_normalize_temps(command);
                } catch (err) {
                    return_val = 1;
                    console.log('exception when parsing oref0-normalize-temps ', err);
                }
            } else if (command[0] == 'ping') {
                result = 'pong';
            } else if (command[0] == 'json') {
                // remove the first parameter.
                command.shift();
                try {
                    result = jsonWrapper(command);
                } catch (err) {
                    return_val = 1;
                    console.log('exception when running json_wrarpper ', err);
                }
            } else {
                console.error('Unknown command = ', command);
                return_val = 1;
            }
            s.write(JSON.stringify(createRetVal(result, return_val)));
            s.end();
        });
    });
}

// The goal is to run something like:
// json -f monitor/status.1.json -c "minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38"
function jsonWrapper(argv_params) {
    var argv = require('yargs')(argv_params)
        .usage('$0 json -f monitor/status.1.json -c \"minAgo=(new Date()-new Date(this.dateString))/60/1000; return minAgo < 10 && minAgo > -5 && this.glucose > 38\"')
        .option('input_file', {
            alias: 'f',
            nargs: 1,
            describe: "Input/Output file",
            default: false
        })
        .option('filtering_code', {
            alias: 'c',
            nargs: 1,
            describe: "Conditional filtering",
            default: false
        })
        .strict(true)
        .fail(function(msg, err, yargs) {
            if (err) {
                return console.error('Error found', err);
            }
            return console.error('Parsing of command arguments failed', msg)
        })
        .help('help');
    var params = argv.argv;
    var inputs = params._;
    if (inputs.length > 0) {
        return console.error('Error: too many input parameters.');
    }
    if (!params.input_file) {
        return console.error('Error: No input file.');
    }
    if (!params.filtering_code) {
        return console.error('Error: No filtering_code');
    }
    // Copy the input file to a temp one (we must work inplace).
    var jsonTmpfile = uniqueFilename(os.tmpdir(), 'json_input')
    fs.copyFileSync(params.input_file, jsonTmpfile);
    console.log("Coppied file to ", jsonTmpfile);

    var newCommand = ['node', '/home/pi/lib/json', '-I', '-f', jsonTmpfile, '-c', params.filtering_code];
    json.main(newCommand);
    // output should be in the temp file.
    var output = requireUtils.safeLoadFile(jsonTmpfile);
    // Shoud we check for errors here?
    return output;
}


if (!module.parent) {
    serverListen();
}

// Functions needed to simulate a stack node.
const util = require('util');
const vm = require('vm');

function sleepFor(sleepDuration) {
    var now = new Date().getTime();
    while (new Date().getTime() < now + sleepDuration) {
        /* do nothing */ }
}
