#!/usr/bin/env node

/*
  Determine Basal

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
/* istanbul ignore next */
if (!module.parent) {
    var determinebasal = init();

    var iob_input = process.argv.slice(2, 3).pop();
    var currenttemp_input = process.argv.slice(3, 4).pop();
    var glucose_input = process.argv.slice(4, 5).pop();
    var profile_input = process.argv.slice(5, 6).pop();
    var offline = process.argv.slice(6, 7).pop();
    var meal_input = process.argv.slice(7, 8).pop();

    if (!iob_input || !currenttemp_input || !glucose_input || !profile_input) {
        console.error('usage: ', process.argv.slice(0, 2), '<iob.json> <currenttemp.json> <glucose.json> <profile.json> [Offline] [meal.json]');
        process.exit(1);
    }
    
    var fs = require('fs');
    try {
        var cwd = process.cwd();
        var glucose_data = require(cwd + '/' + glucose_input);
        var currenttemp = require(cwd + '/' + currenttemp_input);
        var iob_data = require(cwd + '/' + iob_input);
        var profile = require(cwd + '/' + profile_input);
        var glucose_status = determinebasal.getLastGlucose(glucose_data);
    } catch (e) {
        return console.error("Could not parse input data: ", e);
    }

    //console.log(carbratio_data);
    var meal_data = { };
    //console.error("meal_input",meal_input);
    if (typeof meal_input != 'undefined') {
        try {
            meal_data = JSON.parse(fs.readFileSync(meal_input, 'utf8'));
            console.error(JSON.stringify(meal_data));
        } catch (e) {
            console.error("Warning: could not parse meal_input. Meal Assist disabled.");
        }
    }
    //if (meal_input) { meal_data = require(cwd + '/' + meal_input); }

    if (!glucose_status.isFailure) {
        console.error(glucose_status.reasonHint);
        return 1;
    }

    console.error(JSON.stringify(glucose_status));
    console.error(JSON.stringify(currenttemp));
    console.error(JSON.stringify(iob_data));
    console.error(JSON.stringify(profile));
    
    var setTempBasal = require('../lib/basal-set-temp'); 
    
    rT = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile, undefined, meal_data, setTempBasal);

    if(typeof rT.error === 'undefined') {
        console.log(JSON.stringify(rT));
    } else {
        console.error(rT.error);
    }

}

    
function init() {

    var determinebasal = {
        name: 'determine-basal'
        , label: "OpenAPS Determine Basal"
    };
    
    determinebasal.getLastGlucose = require('../lib/glucose-get-last');
    determinebasal.determine_basal = require('../lib/determine-basal/determine-basal');
    return determinebasal;

}
module.exports = init;
