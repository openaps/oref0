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

function getTime(minutes) {
    var baseTime = new Date();
    baseTime.setHours('00');
    baseTime.setMinutes('00');
    baseTime.setSeconds('00');    
    
    return baseTime.getTime() + minutes * 60 * 1000;
   
}

/* Return basal rate(U / hr) at the provided timeOfDay */

function basalLookup() {
    var now = new Date();
    var basalRate = basalprofile_data[basalprofile_data.length-1].rate
    
    for (var i = 0; i < basalprofile_data.length - 1; i++) {
        if ((now >= getTime(basalprofile_data[i].minutes)) && (now < getTime(basalprofile_data[i + 1].minutes))) {
            basalRate = basalprofile_data[i].rate;
            break;
        }
    }
    profile.current_basal= Math.round(basalRate*1000)/1000;
}

function bgTargetsLookup(){
    var now = new Date();
    
    //bgtargets_data.targets.sort(function (a, b) { return a.offset > b.offset });
    var bgTargets = bgtargets_data.targets[bgtargets_data.targets.length - 1]
    
    for (var i = 0; i < bgtargets_data.targets.length - 1; i++) {
        if ((now >= getTime(bgtargets_data.targets[i].offset)) && (now < getTime(bgtargets_data.targets[i + 1].offset))) {
            bgTargets = bgtargets_data.targets[i];
            break;
        }
    }
    profile.max_bg = bgTargets.high;
    profile.min_bg = bgTargets.low;
}

function carbRatioLookup() {
    var now = new Date();
    //carbratio_data.schedule.sort(function (a, b) { return a.offset > b.offset });
    var carbRatio = carbratio_data.schedule[carbratio_data.schedule.length - 1]
    
    for (var i = 0; i < carbratio_data.schedule.length - 1; i++) {
        if ((now >= getTime(carbratio_data.schedule[i].offset)) && (now < getTime(carbratio_data.schedule[i + 1].offset))) {
            carbRatio = carbratio_data.schedule[i];
            break;
        }
    }
    profile.carbratio = carbRatio.ratio;    
}

function isfLookup() {
    var now = new Date();
    //isf_data.sensitivities.sort(function (a, b) { return a.offset > b.offset });
    var isfSchedule = isf_data.sensitivities[isf_data.sensitivities.length - 1]
    
    for (var i = 0; i < isf_data.sensitivities.length - 1; i++) {
        if ((now >= getTime(isf_data.sensitivities[i].offset)) && (now < getTime(isf_data.sensitivities[i + 1].offset))) {
            isfSchedule = isf_data.sensitivities[i];
            break;
        }
    }
    profile.sens = isfSchedule.sensitivity;
}

function maxDailyBasal(){
    basalprofile_data.sort(function (a, b) { if (a.rate < b.rate) { return 1 } if (a.rate > b.rate) { return -1; } return 0; });
    profile.max_daily_basal = Math.round( basalprofile_data[0].rate *1000)/1000;
}

/*Return maximum daily basal rate(U / hr) from profile.basals */

function maxBasalLookup() {
    
    profile.max_basal =pumpsettings_data.maxBasal;
}

if (!module.parent) {
    
    var pumpsettings_input = process.argv.slice(2, 3).pop()
    var bgtargets_input = process.argv.slice(3, 4).pop()
    var isf_input = process.argv.slice(4, 5).pop()
    var basalprofile_input = process.argv.slice(5, 6).pop()
    var carbratio_input = process.argv.slice(6, 7).pop()
    var maxiob_input = process.argv.slice(7, 8).pop()
    
    if (!pumpsettings_input || !bgtargets_input || !isf_input || !basalprofile_input || !carbratio_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<pump_settings.json> <bg_targets.json> <isf.json> <current_basal_profile.json> <carb_ratio.json> [<max_iob.json>]');
        process.exit(1);
    }
    
    var cwd = process.cwd()
    var pumpsettings_data = require(cwd + '/' + pumpsettings_input);
    var bgtargets_data = require(cwd + '/' + bgtargets_input);
    var isf_data = require(cwd + '/' + isf_input);
    var basalprofile_data = require(cwd + '/' + basalprofile_input);
    var carbratio_data = require(cwd + '/' + carbratio_input);;

    var profile = {        
          carbs_hr: 28 // TODO: verify this is completely unused and consider removing it if so
        , max_iob: 0 // if max_iob.json is not profided, never give more insulin than the pump would have
        , dia: pumpsettings_data.insulin_action_curve        
        , type: "current"
    };

    basalLookup();
    maxDailyBasal();
    maxBasalLookup()
    bgTargetsLookup();
    carbRatioLookup();
    isfLookup();
    if (typeof maxiob_input != 'undefined') {
        var maxiob_data = require(cwd + '/' + maxiob_input);
        profile.max_iob = maxiob_data.max_iob;
    }

    console.log(JSON.stringify(profile));
}
