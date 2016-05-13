

exports.xyzbuilder = {
  foo: {
    default: 'ok'
  },
  baz: {
    default: 'optional'
  }

};

var reference = require('./exported-loop.json');


function oref0_reports (argv) {
  var reference = require('./some-reports');
  var devs = [ ];
  if (argv.oref0) {
    reference.forEach(function (item) {
      if (item.type == 'report') {
        // if (item[item.name].device == 'pump') {
        if ([null, 'get-profile', 'calculate-iob', 'determine-basal'].indexOf(item[item.name].device) > 0) {
          devs.push(item);
        }
      }
    });

  }
  console.log(JSON.stringify(devs, '  '));
}

function oref0_devices (argv) {
  var devs = [ ];
  if (argv.oref0) {
    reference.forEach(function (item) {
      if (item.type == 'device') {
        if (item.extra.cmd == 'oref0') {
          devs.push(item);
        }
      }
    });

  }
  console.log(JSON.stringify(devs, '  '));
}

function per_type (yargs) {
  return yargs
     .command('oref0', 'generate oref0 devices', {oref0: {default: true}}, oref0_devices)
    ;
}

function per_shape (yargs) {
  return yargs
     .command('oref0-inputs', 'generate reports for oref0', {oref0: {default: true}}, oref0_reports)
     .command('medtronic-pump', 'organize output from medtronic pump', {name: {default: 'pump'}}, medtronic_pump_reports)
     // .command('glucose', '', { }, oref0_reports)
    ;
}

function medtronic_pump_reports (argv) {
  var reference = require('./medtronic-pump-reports');
  var out = [ ];
  reference.forEach(function (item) {
    if (item[item.name].device == 'pump') {
      if (argv.name != 'pump') {
        item[item.name].device = argv.name;
      }
    }
    out.push(item);
  });
  console.log(JSON.stringify(out));
  return out;
}

function per_alias (yargs) {
  return yargs
     .command('common', 'generate common aliases', {common: {default: true}}, print_aliases)
}

function print_aliases (argv) {
  var devs = [ ];
  if (argv.common) {
    reference.forEach(function (item) {
      if (item.type == 'alias') {
        devs.push(item);
      }
    });
  }
  console.log(JSON.stringify(devs, '  '));
}


function run ( ) {
}

exports.builder = function (yargs) {
  return yargs
     .command('device <type>', 'generate devices', per_type, run)
     .command('reports <shape>', 'generate reports', per_shape, run)
     .command('alias <type>', 'generate aliases', per_alias, run)
     .strict( )
     // .usage('$0 mint <type>')
     // .demand('type', 1)
     // .choices('type', ['devices', 'reports', 'alias', '*'])
     // .options('bazbaz', { default: 'blah' })
    ;
}

exports.handler = function (argv) {
  // console.log('args', argv);
  // return argv.command(

}
