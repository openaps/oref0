var path = require('path');
var webpack = require('webpack');
module.exports = {
    mode: 'production',
    entry: './lib/webpack-exports.js',
    target: 'node',
    output: {
        path: path.resolve(__dirname, 'build'),
        filename: 'bundle.js',
        libraryTarget: 'var',
        library: 'OpenAPS'
    }
};