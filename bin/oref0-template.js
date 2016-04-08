#!/usr/bin/env node



var argv = require('yargs')
  .usage("$0 <cmd> <type> [args]")
  /*
  .option('', {
  })
  */
  .command('mint <type>', 'generate template for import', require('oref0/lib/templates/'))
  // .choices('type', ['devices', 'reports', 'alias', '*'])
  /*
  .command('devices', 'generate common device loops', function (yargs) {
    return yargs.option('b', {
      alias: 'bar'
    });
  })
  */
  .help('help')
  .alias('h', 'help')
  .completion( )
  .strict( )
  .argv
  ;

// console.log('after', argv);
