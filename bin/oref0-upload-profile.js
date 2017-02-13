#!/usr/bin/env node

/*
  oref0 Nightscout profile update tool

  Checks the ISF / Basal profile in Nightscout and updates the profile if
  necessary to match the profile collected by OpenAPS

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

var crypto = require('crypto');
var request = require('request');
var _ = require('lodash');

if (!module.parent) {

    var argv = require('yargs')
        .usage("$0 profile.json NSURL api-secret [--preview]")
        .option('preview', {
            alias: 'p'
            , describe: "Give a preview of the outcome without uploading"
            , default: false
        })
        .strict(true)
        .help('help');

    function usage() {
        argv.showHelp();
    }

    var params = argv.argv;
    var errors = [];
    var warnings = [];

    var profile_input = params._.slice(0, 1).pop();

    if ([null, '--help', '-h', 'help'].indexOf(profile_input) > 0) {
        usage();
        process.exit(0);
    }

    var nsurl = params._.slice(1, 2).pop();
    var apisecret = params._.slice(2, 3).pop();

    if (!profile_input || !nsurl || !apisecret) {
        usage();
        process.exit(1);
    }

    if (apisecret.length != 40) {
        var shasum = crypto.createHash('sha1');
        shasum.update(apisecret);
        apisecret = shasum.digest('hex');
    };

    try {
        var cwd = process.cwd();
        var profiledata = require(cwd + '/' + profile_input);
        
        // Rudimentary check that the profile is valid
        
        if (!profiledata.dia
          || profiledata.basalprofile.length < 1
          || profiledata.bg_targets.length < 1
          || profiledata.isfProfile.length < 1 )
          { throw "Profile JSON missing data"; }
          
    } catch (e) {
        return console.error('Could not parse input data: ', e);
    }


    var options = {
        uri: nsurl + '/api/v1/profile/current'
        , json: true
        , headers: {
            'api-secret': apisecret
        }
    };

    request(options, function(error, res, data) {
        if (error || res.statusCode != 200) {
            console.log('Loading current profile from Nightscout failed');
            process.exit(1);
        }

        var original_profile = data;
        var new_profile = _.cloneDeep(data);

        if (!data.defaultProfile) {
            console.error('Nightscout profile missing data');
            process.exit(1);
        }

        var profile_id = data.defaultProfile;
        var profile_store = new_profile.store[profile_id];

        profile_store.dia = profiledata.dia;

        // Basals

        var new_basal = [];

        _.forEach(profiledata.basalprofile, function(basalentry) {

            var newEntry = {
                time: '' + basalentry.start.substring(0, 5)
                , value: '' + +(Math.round(basalentry.rate + 'e+3') + 'e-3')
                , timeAsSeconds: '' + basalentry.minutes * 60
            };

            new_basal.push(newEntry);

        });

        profile_store.basal = new_basal;

        // BG Targets

        var new_target_low = [];
        var new_target_high = [];

        _.forEach(profiledata.bg_targets.targets, function(target_entry) {

            var time = target_entry.start.substring(0, 5);
            var seconds = parseInt(time.substring(0, 2)) * 60 * 60 + parseInt(time.substring(3, 5)) * 60;
            var low_value = Math.round(target_entry.low);
            var high_value = Math.round(target_entry.high);

            if (new_profile.units == 'mmol' && profiledata.bg_targets.units == 'mg/dL') {
                low_value = +(Math.round(target_entry.low / 18 + 'e+1') + 'e-1');
                high_value = +(Math.round(target_entry.high / 18 + 'e+1') + 'e-1');
            }

            var new_low_entry = {
                time: '' + time
                , value: '' + low_value
                , timeAsSeconds: '' + seconds
            };

            var new_high_entry = {
                time: '' + time
                , value: '' + high_value
                , timeAsSeconds: '' + seconds

            };

            new_target_low.push(new_low_entry);
            new_target_high.push(new_high_entry);
        });

        profile_store.target_low = new_target_low;
        profile_store.target_high = new_target_high;

        // ISF

        var new_sens = [];

        _.forEach(profiledata.isfProfile.sensitivities, function(isf_entry) {

            var value = Math.round(isf_entry.sensitivity);

            if (new_profile.units == 'mmol' && profiledata.isfProfile.units == 'mg/dL') {
                value = +(Math.round(isf_entry.sensitivity / 18 + 'e+1') + 'e-1');
            }

            var new_isf_entry = {
                time: isf_entry.start.substring(0, 5)
                , value: '' + value
                , timeAsSeconds: '' + isf_entry.offset * 60
            };

            new_sens.push(new_isf_entry);
        });

        profile_store.sens = new_sens;

        // Carb ratios

        var new_carb_ratios = [];

        _.forEach(profiledata.carb_ratios.schedule, function(carb_entry) {

            var new_entry = {
                time: carb_entry.start.substring(0, 5)
                , value: '' + carb_entry.ratio
                , timeAsSeconds: '' + carb_entry.offset * 60
            };

            new_carb_ratios.push(new_entry);
        });

        profile_store.carbratio = new_carb_ratios;

        // change dates & remove Mongo ID from new profile to create a new object
        // Inserts the new profile with name "OpenAPS Autosync" to not overwrite
        // human-entered data

        var upload_profile;

        if (profile_id != 'OpenAPS Autosync') {
            upload_profile = _.cloneDeep(data);
        } else {
            upload_profile = new_profile;
        }

        var do_upload = !_.isEqual(original_profile, new_profile);

        if (do_upload) {

            var d = new Date();
            profile_store.startDate = d.toISOString();

            if (profile_id != 'OpenAPS Autosync') {
                upload_profile.defaultProfile = 'OpenAPS Autosync';
                upload_profile.store['OpenAPS Autosync'] = profile_store;
            }

            delete upload_profile._id;

            upload_profile.startDate = profile_store.startDate;
            upload_profile.created_at = profile_store.startDate;
            upload_profile.mills = d.getTime();
        }

        // render preview

        if (params.preview) {

            if (_.isEqual(original_profile, new_profile)) {
                console.log('Profile in Nightscout and OpenAPS are identical');
            } else {
                console.log('Profile in Nightscout and OpenAPS differ');
                console.log('-------------- Nightscout Profile ----------------');
                console.log(JSON.stringify(original_profile, null, 2));
                console.log('-------------- New profile from OpenAPS data ----------------');
                console.log(JSON.stringify(upload_profile, null, 2));
            }

            process.exit(0);
        }

        if (do_upload) {

            console.log('Profile changed, uploading to Nightscout');

            options = {
                uri: nsurl + '/api/v1/profile/'
                , json: true
                , method: 'POST'
                , headers: {
                    'api-secret': apisecret
                }
                , body: upload_profile
            };

            request(options, function(error, res, data) {
                if (error || res.statusCode != 200) {
                    console.log(error);
                    console.log(res.body);
                } else {
                    console.log('Profile uploaded to Nightscout');
                }
            });
        } else {
            console.log('Profiles match, no upload needed');
        }
    });
}