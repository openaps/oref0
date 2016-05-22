#!/usr/bin/env node

/*
  Get Basal Information

  Released under MIT license. See the accompanying LICENSE.txt file for
  full terms and conditions

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.

*/

var generate = require('oref0/lib/profile/');
function usage ( ) {
        console.log('usage: ', process.argv.slice(0, 2), '<pump_settings.json> <bg_targets.json> <insulin_sensitivities.json> <basal_profile.json> [<max_iob.json>] [<carb_ratios.json>] [<temptargets.json>]');
}

if (!module.parent) {
    
    var pumpsettings_input = process.argv.slice(2, 3).pop()
    if ([null, '--help', '-h', 'help'].indexOf(pumpsettings_input) > 0) {
      usage( );
      process.exit(0)
    }
    var bgtargets_input = process.argv.slice(3, 4).pop()
    var isf_input = process.argv.slice(4, 5).pop()
    var basalprofile_input = process.argv.slice(5, 6).pop()
    var preferences_input = process.argv.slice(6, 7).pop()
    var carbratio_input = process.argv.slice(7, 8).pop()
    var temptargets_input = process.argv.slice(8, 9).pop()
    
    if (!pumpsettings_input || !bgtargets_input || !isf_input || !basalprofile_input) {
        usage( );
        process.exit(1);
    }
    
    var cwd = process.cwd()
    var pumpsettings_data = require(cwd + '/' + pumpsettings_input);
    var bgtargets_data = require(cwd + '/' + bgtargets_input);
    if (bgtargets_data.units !== 'mg/dL') {
      console.log('BG Target data is expected to be expressed in mg/dL.'
                 , 'Found', bgtargets_data.units, 'in', bgtargets_input, '.');
      process.exit(2);
    }
    var isf_data = require(cwd + '/' + isf_input);
    if (isf_data.units !== 'mg/dL') {
      console.log('ISF is expected to be expressed in mg/dL.'
                 , 'Found', isf_data.units, 'in', isf_input, '.');
      process.exit(2);
    }
    var basalprofile_data = require(cwd + '/' + basalprofile_input);

    var preferences = {};
    if (typeof preferences_input != 'undefined') {
        preferences = require(cwd + '/' + preferences_input);
    }
    var fs = require('fs');
    var carbratio_data = { };
    //console.log("carbratio_input",carbratio_input);
    if (typeof carbratio_input != 'undefined') {
        try {
            carbratio_data = JSON.parse(fs.readFileSync(carbratio_input, 'utf8'));

        } catch (e) {
            var msg = { error: e, msg: "Could not parse carbratio_data. Feature Meal Assist enabled but cannot find required carb_ratios.", file: carbratio_input };
            console.error(msg.msg);
            console.log(JSON.stringify(msg));
            process.exit(1);
        }
        var errors = [ ];

        if (!(carbratio_data.schedule && carbratio_data.schedule[0].start && carbratio_data.schedule[0].ratio)) {
          errors.push({msg: "Carb ratio data should have an array called schedule with a start and ratio fields.", file: carbratio_input, data: carbratio_data});
        } else {
        }
        if (carbratio_data.units != 'grams') {
          errors.push({msg: "Carb ratio should have units field set to 'grams'.", file: carbratio_input, data: carbratio_data});
        }
        if (errors.length) {

          errors.forEach(function (msg) {
            console.error(msg.msg);
          });
          console.log(JSON.stringify(errors));
          process.exit(1);
        }
    }
    var temptargets_data = { };
    if (typeof temptargets_input != 'undefined') {
        try {
            temptargets_data = JSON.parse(fs.readFileSync(temptargets_input, 'utf8'));
        } catch (e) {
            //console.error("Could not parse temptargets_data.");
        }
    }

    //console.log(carbratio_data);
    var inputs = {
      settings: pumpsettings_data
    , targets: bgtargets_data
    , basals: basalprofile_data
    , isf: isf_data
    , max_iob: preferences.max_iob || 0
    , skip_neutral_temps: preferences.skip_neutral_temps || false
    , carbratio: carbratio_data
    , temptargets: temptargets_data
    };

    var profile = generate(inputs);

    console.log(JSON.stringify(profile));
}
