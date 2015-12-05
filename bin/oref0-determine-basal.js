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

    if (!iob_input || !currenttemp_input || !glucose_input || !profile_input) {
        console.error('usage: ', process.argv.slice(0, 2), '<iob.json> <currenttemp.json> <glucose.json> <profile.json> [Offline]');
        process.exit(1);
    }
    
    var cwd = process.cwd();
    var glucose_data = require(cwd + '/' + glucose_input);
    var currenttemp = require(cwd + '/' + currenttemp_input);
    var iob_data = require(cwd + '/' + iob_input);
    var profile = require(cwd + '/' + profile_input);
    var glucose_status = determinebasal.getLastGlucose(glucose_data);

    //if old reading from Dexcom do nothing

    var systemTime = new Date();
    var bgTime;
    if (glucose_data[0].display_time) {
        bgTime = new Date(glucose_data[0].display_time.replace('T', ' '));
    } else if (glucose_data[0].dateString) {
        bgTime = new Date(glucose_data[0].dateString);
    } else { console.error("Could not determine last BG time"); }
    var minAgo = (systemTime - bgTime) / 60 / 1000;

    if (minAgo > 10 || minAgo < -5) { // Dexcom data is too old, or way in the future
        var reason = "BG data is too old, or clock set incorrectly "+bgTime;
        console.error(reason);
        return 1;
    }
    console.error(JSON.stringify(glucose_status));
    console.error(JSON.stringify(currenttemp));
    console.error(JSON.stringify(iob_data));
    console.error(JSON.stringify(profile));
    
    var setTempBasal = require('../lib/basal-set-temp'); 
    
    rT = determinebasal.determine_basal(glucose_status, currenttemp, iob_data, profile, undefined, setTempBasal);

    if(typeof rT.error === 'undefined') {
        console.log(JSON.stringify(rT));
    } else {
        console.error(rT.error);
    }
    rT=rT;

}
    
function init() {

    var determinebasal = {
        name: 'determine-basal'
        , label: "OpenAPS Determine Basal"
        , pluginType: 'pill-major'
    };
    
    determinebasal.getLastGlucose = require('../lib/glucose-get-last');
    determinebasal.determine_basal = require('../lib/determine-basal/determine-basal');
    return determinebasal;

}
module.exports = init;
