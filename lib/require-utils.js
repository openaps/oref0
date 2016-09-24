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

function requireWithTimestamp (path) {
  var resolved = safeRequire(path);

  if (resolved) {
    resolved.timestamp = fs.statSync(path).mtime;
  }

  return resolved;
}


module.exports = {
  safeRequire: safeRequire
  , requireWithTimestamp: requireWithTimestamp
};