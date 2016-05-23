
v0.2.0 / 2016-05-15 
==================

## new features
* meal-assist
  * Helps administer extra insulin when needed after meals. Must be configured. Must be willing to consistently enter carbs (via pump's bolus wizard or can be configured to pull from NS care portal) to avoid triggering wtf-assist erroneously. 
* automatic sensitivity detection (auto-sens)
  * Auto-adjusts basal rates and ISF used by oref0 based on deviations from normal over the last 24h
* `nightscout` full suite of tools for managing entries and treatments
  * Makes it easier to upload, download, and manage BG and pump data to/from Nightscout.
* lots of other new tools
  * aiding setup, see `templates`, `nightscout autoconfigure-device-crud`, `alias-helper`, `device-helper` and other friendly tools designed to work in tandem with the `openaps import` features.

## changes
* `determine-basal` is now stricter with it's arguments, now producing errors when a file for a feature such as auto-sens or meal-assist is enabled but does not have appropriate input/data.
* refactored a lot of source code: most source is now organized in a re-usable way, we've started introducing switches and other niceties to the interfaces
* always temp to zero if <60 and other real-world situation improvements
* lots more error/sanity checking

## changelog
 * Merge pull request #105 from openaps/dev
 * add autosens-adjusted ISF to reason field
 * Merge pull request #112 from mddub/neutral-temps-preference
 * set_neutral_temps -> skip_neutral_temps
 * Make neutral temp basals configurable
 * provide easy way to backup/export entire configuration
 * add aliases as well
 * add detect-sensitivity to oref0 templates
 * Merge pull request #111 from mddub/preferences-not-max-iob
 * Fix last errant reference to max_iob.json
 * Update oref0-mint-max-iob to use preferences.json
 * Rename max_iob.json to preferences.json
 * disable wtfAssist and mealAssist if no meal_data
 * Merge pull request #107 from openaps/bewest/fix-cli
 * allow persisting backups in another location
 * only show one help message.
 * rm calculate-basal from help output
 * tweak usage
 * that was short-lived and probably ill considered.
 * tweak per @scottleibrand's feedback
 * restore backwards-compat for people with working meals.json
 * include calculate-basal tool
 * introduce yargs with different positional params
 * tweak older message to match
 * don't allow overriding auto-sens ratio via switch
 * patch determine-basal to take auto-sens as named params
 * fix require lines for both linked and packaged scenarios
 * tweak error message
 * introduce some informative errors for enabling wtf-assist
 * lol, narrow gap threshold for entries to 5 minutes.
 * add more help messages, add --current now to select
 * make the culling re-usable by many types
 * tweak help message, as well as fix arguments to ns
 * adjust template to accept new-style ns tools
 * make setting up Nightscout uploads even easier
 * more debugging tweaks for @garykidd and friends
 * Merge branch 'dev' of github.com:openaps/oref0 into dev
 * make nightscout fetching debuggable
 * Merge pull request #100 from jasoncalabrese/wip/remove-recieved-hack
 * remove 'recieved' hack since it's not needed with current version of mmeowlink
 * Merge pull request #87 from openaps/wip/bewest/help-output
 * add more templating/helpers
 * Merge pull request #93 from openaps/wip/bewest/autoconfigure-ns
 * Merge pull request #94 from openaps/wip/bewest/autoconfigure-stuff
 * allow timezone to use local timezone
 * templatize most medtronic reports
 * update report template
 * stub out openaps template generator
 * make sure ns-get does something in `host` mode
 * make Nightscout tools a lot easier to use in openaps.
 * if ENTRIES is supposed to be a file, fail if empty/missing
 * Merge branch 'dev' of github.com:openaps/oref0 into wip/bewest/help-output
 * Merge pull request #92 from CrushingT1D/dev
 * Merge branch 'dev' of github.com:openaps/oref0 into wip/bewest/help-output
 * Lower max override from 100 to 90
 * Merge pull request #89 from jasoncalabrese/wip/eventtype-fix
 * don't require a bg for a meal bolus
 * switch from sh to bash, fix bashisms
 * Merge branch 'dev' of github.com:openaps/oref0 into wip/bewest/import-utils
 * ensure --help output for all tools
 * Merge pull request #75 from openaps/meal-assist
 * #76: don't adjust ratio more than 2x in either direction
 * Merge branch 'dev' into meal-assist
 * #84: always temp to zero when BG < 60
 * Merge branch 'meal-assist' of github.com:openaps/oref0 into meal-assist
 * #84: always temp to zero when BG < 60
 * Merge pull request #86 from jasoncalabrese/meal-assist
 * filter Model522ResultTotals and Model722ResultTotals treatment spam
 * round target in mealAssist status message
 * Revert "temporary workaround to prevent issues from DST switchover"
 * temporary workaround to prevent issues from DST switchover
 * p50 looks better for pSensitive
 * #77: fix incorrect BGI calculation to be per 5m, not per minute, and use p30 and p60 to avoid false positives from resulting increased sensitivity
 * formatting
 * formatting
 * formatting
 * :
 * print text at the top of oref0.html for mddub watch face
 * add some docs to the tool
 * more easily print to stdout
 * Merge branch 'dev' of github.com:openaps/oref0 into dev
 * Merge branch 'dev' into meal-assist
 * use p45 for resistance detection
 * use avgDelta for calculating deviations
 * Merge branch 'meal-assist' of github.com:openaps/oref0 into meal-assist
 * use p40 for resistance detection
 * Merge pull request #74 from jasoncalabrese/wip/treatment-cleanup
 * goodbye Sara6E
 * use minDelta everywhere
 * Merge pull request #73 from jasoncalabrese/wip/treatment-cleanup
 * don't calculate autosens with less than 6h of data
 * oref0-reset-usb can be used for TI sticks, not just Carelinks
 * prevent some treatment spam from getting to NS
 * add mmtune to usage and mark it as optional
 * viewport 500
 * meta refresh
 * typo
 * add hostname
 * Merge branch 'meal-assist' of github.com:openaps/oref0 into meal-assist
 * oref0-html.js
 * update clockset.sh to work with oref0
 * Merge pull request #72 from jasoncalabrese/wip/raw
 * replicate and fix bug using sgv field from NS
 * Merge pull request #71 from jasoncalabrese/wip/raw
 * added check for inputs and use an array of cals
 * Merge branch 'dev' into wip/raw
 * added oref0-raw to the package
 * Merge pull request #69 from jasoncalabrese/wip/raw
 * not
 * added tool to support filling in raw glucose values
 * Merge pull request #67 from jasoncalabrese/wip/ns-status-tune
 * Merge branch 'dev' of github.com:openaps/oref0 into dev
 * tweak globl
 * move recieved hack from ini to ns-stauts till we find a fix in mmeowlink
 * only use the lower sens for calculating the impact of existing IOB
 * if IOB is negative, be more conservative and use the lower sens
 * pass status object instead of getting lucky
 * added mmtune timestamp
 * don't extend identical temps when >20m left
 * comment out enacted stuff for now
 * optionaly include mmtune in status
 * commas
 * disable debug output
 * increment dev version number to 0.1.3
 * increment meal-assist version number to 0.1.4
 * be quiet about meal data in pebble
 * only set mealCOB if defined
 * calculate and print mealCOB in pebble.json (display only; carbs_hr hardcoded at 30g/hr)
 * , temp
 * use current_basal as of bgTime, not now
 * less ominous warning about Meal Assist
 * missing space
 * move Mean deviation output to stderr
 * should do nothing when requested temp already running with >15m left test
 * compare currenttemp.rate to basal when setting basal as temp
 * compute and display Mean deviation
 * round sens
 * round basal
 * only set current basal as temp if not already running
 * fix bgTime calculations, and don't run with <40 BG data points
 * report caught error when Auto Sensitivity not enabled
 * handle NS as well as CGM bgTimes
 * default autosens ratio to 1 if not provided
 * Merge branch 'dev' into meal-assist
 * Merge branch 'dev' of github.com:openaps/oref0 into dev
 * make wtfAssist slightly less aggressive
 * Merge pull request #63 from jasoncalabrese/wip/ns-status-optional
 * safe require the inputs so 1 missing file doesn't cause the status upload to fail
 * don't meal-assist until minDelta is >3, and raise high-bg wtf threshold
 * put 0 in front of decimals to make github syntax checker happier
 * only print Adjusting if we're changing something
 * stringify!
 * syntax, and a test
 * adjust sens and basal according to autosens ratio
 * pass autosens_data instead of offline
 * debug to stderr not stdout
 * #58 Automatic sensitivity/resistance detection
 * #58 Automatic sensitivity/resistance detection
 * define rT.reason first
 * rT.reason cleanup
 * move simulated meal bolus code earlier in the if tree
 * set current basal as temp instead of canceling
 * set current basal as temp when no action required
 * apply simulated extended bolus as an adjustment to basal, then do everything else normally
 * change profile.current_basal over to a local variable
 * don't preempt low-temps when BG is falling
 * cut off high temps if they'd deliver >0.1U more than required
 * set wtfDeviation=40 and wtfDelta=10 now that it's gradually ramped up
 * re-apply the 10% meal bolus margin
 * use hightempinsulin instead of netbasalinsulin to calculate remainingMealBolus
 * round when using maxSafeBasal
 * only display a single mealAssistPct
 * remove 10% fudge factor on remainingMealBolus
 * round insulinReq
 * round remainingMealBolus
 * don't high-temp when minDelta < expectedDelta, and phase it in between expectedDelta and 0
 * round eventualBG to whole numbers
 * only count positive net basal towards carbs
 * set rate
 * fix var name
 * round eventualBG
 * round mealAssist
 * high-temp for remainingMealBolus if it would be enough to get snoozeBG above min_bg
 * simulate extended bolus for uncovered carbs instead of bolus snoozing
 * comment out debugging
 * phase in mealAssist and wtfAssist smoothly
 * use netbasalinsulin instead of basaliob for mealAssist
 * calculate netbasalinsulin for use in mealAssist
 * Merge pull request #60 from jasoncalabrese/wip/status-device
 * add device field to NS status, using the format openaps://hostname
 * separate out wtf-assist (lowering target) from meal-assist (ignoring boluses), and lower target if DIA/2 hours of basal above max_bg
 * wtf-indeed fix: use locally scoped min_bg instead of resetting global profile.min_bg
 * more refactoring of meal-assist logic for ease of debugging
 * add commented-out new conditional for wtf-assist for help figuring out why it breaks tests
 * refactor meal-assist conditionals to be more readable with comments
 * try... catch input errors
 * print out systemTime too if bgTime is too old
 * Merge branch 'dev' of github.com:openaps/oref0 into dev
 * time out upload attempts after 30s
 * meal assist sooner when BGI is positive (negative insulin activity)
 * Merge branch 'dev' of github.com:openaps/oref0 into dev
 * kill oref0-fix-git-corruption if it's still stuck after 15s
 * Merge pull request #53 from ktomy/master
 * Merge branch 'dev' of github.com:openaps/oref0 into dev
 * handle the case of a missing .git directory
 * Corrected positional arguments for NS profile creation
 * Merge pull request #52 from jasoncalabrese/wip/testfix-wft-assist
 * clean up
 * leave debug placeholder
 * removed debug, added test to make sure we don't high temp when rising too slowly
 * Merge pull request #51 from jasoncalabrese/wip/testfix-wft-assist
 * set deltas in tests to 4 to enable wtf assist
 * don't meal-assist when minDelta <= 3
 * don't high-temp when minDelta <=5
 * first, try oref0-fix-git-corruption.sh
 * Merge remote-tracking branch 'origin/master' into dev
 * Merge branch 'dev' of github.com:openaps/oref0 into dev
 * add @bewest fix-git-corruption script
 * make low-temps 2x as fast
 * round after 2x not before
 * low-temp faster by projecting negative deviations for 30m
 * Merge pull request #42 from openaps/meal-assist
 * bump minimum delta for wtf-assist up from 5 to 7
 * only trigger meal-assist w/o carb info while deviation > 25 && avgdelta > 5
 * activate meal assist if deviation is > 20
 * Merge branch 'meal-assist' of github.com:openaps/oref0 into meal-assist
 * if snoozeBG < profile.max_bg due to mealAssist, cancel temp (don't set a low temp here)
 * support optional carbhistory (from nightscout) in oref0-meal
 * display BGI
 * add rT.mealAssist before checking for low glucose suspend mode
 * On/Off for mealAssist
 * rename bolusiob to bolussnooze
 * round meal data
 * print Deviation in rT.mealAssist
 * prevent meal-assist mode when there are no carbs and -IOB
 * fix test
 * 10% fudge factor to allow meal assist to run when carbs are just barely covered
 * ISF and settings error checking
 * Merge branch 'meal-assist' of github.com:openaps/oref0 into meal-assist
 * adjust for deviation when calculating eventualBG in meal assist mode
 * compare max_iob to real basaliob if available
 * round avgdelta
 * round IOB output
 * calculate basaliob directly without accelerated decay
 * set new temps if old ones have 5m or less to run
 * return empty if no carbRatio
 * undefined check for carbratio_data.schedule
 * undefined check for inputs.carbratio
 * add Snooze BG to reason when using it to reset newinsulinReq
 * use insulinScheduled logic for low-temps
 * use snoozeBG here: eventualBG is not responsive to IOB
 * just use snoozeBG here: eventualBG is not responsive to IOB
 * reset target for meal assist
 * Merge branch 'meal-assist' of github.com:openaps/oref0 into meal-assist
 * re-set low-temp when running temp is lower than needed (such as when falling more slowly than predicted)
 * Merge branch 'meal-assist' of github.com:openaps/oref0 into meal-assist
 * error to stderr not stdout
 * fix failing test
 * for meal assist (when rising with uncovered carbs), set min_bg to 80, eating-soon style
 * write out meal_data
 * comment out debug statement
 * typo
 * reason
 * more merge fixes
 * spacing
 * fix merge
 * fix meal_data on new tests
 * merged falling-slower-than-BGI; tests still failing
 * Merge branch 'falling-slower-than-BGI' into meal-assist
 * get meal-assist data pipeline working
 * Merge branch 'dev' into meal-assist
 * get meal-assist branch working backwards-compatably if no meal/carb info provided
 * don't die if carbratio_input not provided, just warn
 * Merge branch 'meal-assist' of github.com:openaps/oref0 into meal-assist
 * get carb_ratio from pump/profile
 * basic meal assist algorithm working and tests passing
 * get meal_input into meal_data and get tests to match
 * collect carb and bolus data from pumphistory for last DIA hours
 * Merge branch 'master' into meal-assist
 * get carb_ratio from pump/profile
 * basic meal assist algorithm working and tests passing
 * get meal_input into meal_data and get tests to match
 * collect carb and bolus data from pumphistory for last DIA hours
 * Merge branch 'wip/refactor' into meal-assist
 * Merge branch 'wip/refactor' into meal-assist
