#!/usr/bin/env node

'use strict';

var os = require("os");
var ns_status = require("./ns-status");	
var oref0_normalize_temps = require("./oref0-normalize-temps");	

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
    const unixSocketServer = net.createServer({allowHalfOpen:true});

    var socketPath = '/tmp/unixSocket';
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
	    command = command.map(s => s.trim());

            var result = 'unknown command';

	    console.log('command = ' , command);

            if (command[0] == 'ns-status') {
		// remove the first parameter.
		command.shift();
		try {
		    result = ns_status(command);
		    //sleepFor(2000);
		} catch (err) {
		    console.log('exception when parsing ns_status ' , err);
		}
            } else if (command [0] == 'oref0-normalize-temps') {
		command.shift();
		try {
		    
		    result = oref0_normalize_temps(command);
		} catch (err) {
		    console.log('exception when parsing oref0-normalize-temps ' , err);
		}
	    } else {
	        console.error('Unknown command = ' , command);
	    }

	    s.write(JSON.stringify(createRetVal(result, 0)));
            s.end();
        });
    });
}




if (!module.parent) {
    serverListen();
}

// Functions needed to simulate a stack node.
const util = require('util');
const vm = require('vm');

function sleepFor( sleepDuration ){
    var now = new Date().getTime();
    while(new Date().getTime() < now + sleepDuration){ /* do nothing */ } 
}





