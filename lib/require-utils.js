'use strict';

var fs = require('fs');

function safeRequire (path) {
  var resolved;

  try {
    resolved = require(path);
  } catch (e) {
    console.error("Could not require: " + path, e);
  }

  return resolved;
}

function safeLoadFile(path) {
  
  var resolved;

  try {
    resolved = JSON.parse(fs.readFileSync(path, 'utf8'));
    //console.log('content = ' , resolved);
  } catch (e) {
    console.error("Could not require: " + path, e);
  }
  return resolved;
}

function requireWithTimestamp (path) {
  var resolved = safeLoadFile(path);

  if (resolved) {
    resolved.timestamp = fs.statSync(path).mtime;
  }
  return resolved;
}

// Functions that are needed in order to test the module. Can be removed in the future.

function compareMethods(path) {
  var new_data = safeLoadFile(path);
  var old_data = safeRequire(path);
  if (JSON.stringify(new_data) === JSON.stringify(old_data) ) {
    console.log("test passed", new_data, old_data); 
  } else {
    console.log("test failed"); 
  }
}

// Module tests.
if (!module.parent) {
 // Write the first file: and test it.
 var obj = {x: "x", y: 1}
 fs.writeFileSync('/tmp/file1.json', JSON.stringify(obj));
 compareMethods('/tmp/file1.json');

  // Check a non existing object.
  compareMethods('/tmp/not_exist.json');
  
  // check a file that is not formated well.
  fs.writeFileSync('/tmp/bad.json', '{"x":"x","y":1');
  compareMethods('/tmp/bad.json');

  // Rewrite the file and reread it.
  var new_obj = {x: "x", y: 2}
  fs.writeFileSync('/tmp/file1.json', JSON.stringify(new_obj));
  var obj_read = safeLoadFile('/tmp/file1.json');
  if (JSON.stringify(new_obj) === JSON.stringify(obj_read) ) {
    console.log("test passed"); 
  } else {
    console.log("test failed"); 
  }

}

module.exports = {
  safeRequire: safeRequire
  , requireWithTimestamp: requireWithTimestamp
  , safeLoadFile: safeLoadFile
};
