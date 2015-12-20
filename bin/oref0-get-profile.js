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

if (!module.parent) {
    
    var pumpsettings_input = process.argv.slice(2, 3).pop()
    var bgtargets_input = process.argv.slice(3, 4).pop()
    var isf_input = process.argv.slice(4, 5).pop()
    var basalprofile_input = process.argv.slice(5, 6).pop()
    var maxiob_input = process.argv.slice(6, 7).pop()
    var carbratio_input = process.argv.slice(7, 8).pop()
    
    if (!pumpsettings_input || !bgtargets_input || !isf_input || !basalprofile_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<pump_settings.json> <bg_targets.json> <insulin_sensitivities.json> <basal_profile.json> [<max_iob.json>] [<carb_ratios.json>]');
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

    var maxiob_data = { max_iob: 0 };
    if (typeof maxiob_input != 'undefined') {
        maxiob_data = require(cwd + '/' + maxiob_input);
    }
    var fs = require('fs');
    var carbratio_data = { };
    //console.log("carbratio_input",carbratio_input);
    if (typeof carbratio_input != 'undefined') {
        try {
            carbratio_data = JSON.parse(fs.readFileSync(carbratio_input, 'utf8'));
        } catch (e) {
            console.error("Warning: could not parse carbratio_data. Meal Assist disabled.");
        }
    }
    //console.log(carbratio_data);
    var inputs = {
      settings: pumpsettings_data
    , targets: bgtargets_data
    , basals: basalprofile_data
    , isf: isf_data
    , max_iob: maxiob_data.max_iob || 0
    , carbratio: carbratio_data
    };

    var profile = generate(inputs);

    console.log(JSON.stringify(profile));
}
