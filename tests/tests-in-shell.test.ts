// Runner for unit tests which are written in bash. For each file in the
// oref0/tests directory whose name ends in .sh, generates a separate test
// which runs it and asserts that it exits with status 0 (success).

require('should')
import * as fs from 'fs'
import * as path from 'path'
import * as child_process from 'child_process'

describe("shell-script tests", function() {
    var bashUnitTestFiles = [];
    fs.readdirSync("tests").forEach(function(filename) {
        if(filename.endsWith(".sh"))
            bashUnitTestFiles.push(path.join("tests", filename));
    });

    bashUnitTestFiles.forEach(function(testFile) {
        it(testFile, function() {
            var utilProcess = child_process.spawnSync(testFile, [], {
                timeout: 120000, //milliseconds
                encoding: "utf-8",
            });

            //console.error("=================");
            //console.error(testFile);
            //console.error("=================");
            //console.error(testFile + "stdout: \n", utilProcess.stdout);
            //console.error(testFile + "stderr: \n", utilProcess.stderr);
            //console.error(utilProcess.error);
            should.equal(utilProcess.status, 0, "Bash unit test returned failure: run " + testFile + " manually for details.");
        }, 120000);
    });
});
