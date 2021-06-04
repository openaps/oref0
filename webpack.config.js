const path = require('path');
const TerserPlugin = require("terser-webpack-plugin");

module.exports = {
  mode: 'production',
  entry: {
    iob: './lib/iob/index.js',
    meal: './lib/meal/index.js',
    "determineBasal": './lib/determine-basal/determine-basal.js',
    "glucoseGetLast": './lib/glucose-get-last.js',
    "basalSetTemp": './lib/basal-set-temp.js',
    autosens: './lib/determine-basal/autosens.js',
    profile: './lib/profile/index.js',
    "autotunePrep": './lib/autotune-prep/index.js',
    "autotuneCore": './lib/autotune/index.js'
  },
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: '[name].js',
    libraryTarget: 'var',
    library: 'freeaps_[name]'
  },
  optimization: {
    minimize: true,
    minimizer: [new TerserPlugin()],
  },
};
