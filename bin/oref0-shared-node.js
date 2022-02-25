#!/usr/bin/env node

'use strict';

var os = require("os");
var ns_status = require("./ns-status");
var oref0_normalize_temps = require("./oref0-normalize-temps");
var oref0_calculate_iob = require("./oref0-calculate-iob");
var oref0_meal = require("./oref0-meal");
var oref0_get_profile = require("./oref0-get-profile");
var oref0_get_ns_entries = require("./oref0-get-ns-entries");
var fs = require('fs');
var requireUtils = require('../lib/require-utils');
var shared_node_utils = require('./oref0-shared-node-utils');
var console_error = shared_node_utils.console_error;
var console_log = shared_node_utils.console_log;
var initFinalResults = shared_node_utils.initFinalResults;

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

            var result = 'unknown command\n';

            console.log('command = ', command);
            var async_command = false;
            var final_result = initFinalResults();

            if (command[0] == 'ns-status') {
                // remove the first parameter.
                command.shift();
                try {
                    result = ns_status(command);
                    result = addNewlToResult(result);
                    final_result = createRetVal(result, 0);
                } catch (err) {
                    final_result.return_val = 1;
                    console.log('exception when parsing ns_status ', err);
                    console_err(final_result, 'exception when parsing ns_status ', err);
                }
            } else if (command[0] == 'oref0-normalize-temps') {
                command.shift();
                try {
                    result = oref0_normalize_temps(command);
                    result = addNewlToResult(result);
                    final_result = createRetVal(result, 0);
                } catch (err) {
                    final_result.return_val = 1;
                    console.log('exception when parsing oref0-normalize-temps ', err);
                }
            } else if (command[0] == 'oref0-calculate-iob') {
                command.shift();
                try {
                    result = oref0_calculate_iob(command);
                    result = addNewlToResult(result);
                    final_result = createRetVal(result, 0);
                } catch (err) {
                    final_result.return_val = 1;
                    console.log('exception when parsing oref0-calculate-iob ', err);
                }
            }  else if (command[0] == 'oref0-meal') {
                command.shift();
                try {
                    result = oref0_meal(final_result, command);
                    final_result.stdout = addNewlToResult(final_result.stdout); // put them both in a new function ????????????
                    final_result.err = addNewlToResult(final_result.err);
                } catch (err) {
                    final_result.return_val = 1;
                    console.log('exception when parsing oref0-meal ', err);
                }
            } else if (command[0] == 'oref0-get-profile') {
                command.shift();
                try {
                    oref0_get_profile(final_result, command);
                    final_result.stdout = addNewlToResult(final_result.stdout); // put them both in a new function ????????????
                    final_result.err = addNewlToResult(final_result.err);
                } catch (err) {
                    final_result.return_val = 1;
                    console.log('exception when parsing oref0-get-profile ', err);
                }
            } else if (command[0] == 'oref0-get-ns-entries') {
                async_command = true;

                var final_result = initFinalResults();
                function print_callback(final_result) {
                    try {
                        final_result.stdout = addNewlToResult(final_result.stdout); // put them both in a new function ????????????
                        final_result.err = addNewlToResult(final_result.err);
                        s.write(JSON.stringify(final_result));
                        s.end();
                    } catch (err) {
                        // I assume here that error happens when handeling the socket, so not trying to close it
                        console.log('exception in print_callback ', err);
                    }
                }
                command.shift();
                try {
                    result = oref0_get_ns_entries(command, print_callback, final_result);
                    result = addNewlToResult(result);
                } catch (err) {
                    final_result.return_val = 1;
                    console.log('exception when parsing oref0-get-profile ', err);
                }
            } else if (command[0] == 'ping') {
                result = 'pong';
                final_result = createRetVal(result, 0);
            } else if (command[0] == 'json') {
                // remove the first parameter.
                command.shift();
                try {
                    var return_val;
                    [result, return_val] = jsonWrapper(command);
                    result = addNewlToResult(result);
                    final_result = createRetVal(result, return_val);
                } catch (err) {
                    final_result.return_val = 1;
                    console.log('exception when running json_wrarpper ', err);
                }
            } else {
                console.error('Unknown command = ', command);
                console_error(final_result, 'Unknown command = ', command);
                final_result.return_val = 1;
            }
            if(!async_command) {
                s.write(JSON.stringify(final_result));
                s.end();
            }
        });
    });
}

/**
 * Return a function for the given JS code that returns.
 *
 * If no 'return' in the given javascript snippet, then assume we are a single
 * statement and wrap in 'return (...)'. This is for convenience for short
 * '-c ...' snippets.
 */
function funcWithReturnFromSnippet(js) {
    // auto-"return"
    if (js.indexOf('return') === -1) {
        if (js.substring(js.length - 1) === ';') {
            js = js.substring(0, js.length - 1);
        }
        js = 'return (' + js + ')';
    }
    return (new Function(js));
}


function addNewlToResult(result) {
    if (result === undefined) {
        // This preserves the oref0_normalize_temps behavior.
        result = ""
    } else if (result.length != 0) {
        result += "\n";
    }
    return result;
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
                return [console.error('Error found', err), 1];
            }
            return [console.error('Parsing of command arguments failed', msg), 1];
        })
        .help('help');
    var params = argv.argv;
    var inputs = params._;
    if (inputs.length > 0) {
        return [console.error('Error: too many input parameters.'), 1];
    }
    if (!params.input_file) {
        return [console.error('Error: No input file.'), 1];
    }
    if (!params.filtering_code) {
        return [console.error('Error: No filtering_code'), 1];
    }
    
    var data = requireUtils.safeLoadFile(params.input_file);
    if (!data) {
        // file is empty. For this files json returns nothing
        console.error('Error: No data loaded')
        return ["", 1];
    }
    if (!Array.isArray(data)) {
        // file is not an array of json, we do not handle this.
        console.error('Error: data is not an array.')
        return ["", 1];
    }
    
    var condFuncs = funcWithReturnFromSnippet(params.filtering_code);
    var filtered = [];
    for (var i = 0; i < data.length; i++) {
        if (condFuncs.call(data[i])) {
            filtered.push(data[i]);
        }
    }
    return [JSON.stringify(filtered, null, 2), 0];
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
