var mealAssistFn = function mealAssistFn(meal_data, profile, iob_data, basal, sens, bg, deviation, minDelta, bgi,eventualBG, rT) {
    var target_bg = profile.target_bg;
    var min_bg = profile.min_bg;
    
    // net amount of basal insulin delivered over the last DIA hours
    var hightempinsulin = iob_data.hightempinsulin;

    var wtfAssist=0;
    var mealAssist=0;
    var mealAssistPct = 0;
    //var wtfAssistPct = 0;
    // if BG is high (more than DIA hours of basal above max_bg, i.e. above about 220mg/dL) and rising, wtf-assist
    var high = profile.max_bg + ( basal * (profile.dia) * sens );
    if ( bg > high && minDelta > Math.max(0,bgi) ) {
        wtfAssist=1;
    }
    // minDelta is > 12 and devation is > 50 wtf-assist and meal-assist
    var wtfDeviation=50;
    var wtfDelta=12;
    if ( deviation > wtfDeviation && minDelta > wtfDelta ) {
        wtfAssist=1;
        mealAssist=1;
    } else {
        // phase in mealAssist, as a fraction
        mealAssist = Math.max(0, Math.round( Math.min(deviation/wtfDeviation,minDelta/wtfDelta)*100)/100 );
    }
    var remainingMealBolus = Math.round( (1.1 * meal_data.carbs/profile.carb_ratio - ( meal_data.boluses + Math.max(0,hightempinsulin) ) )*10)/10;
        // if minDelta is >3 and >BGI, and there are uncovered carbs, meal-assist
    if ( minDelta > Math.max(3, bgi) && meal_data.carbs > 0 && remainingMealBolus > 0 ) {
        mealAssist=1;
    }
    // when rising with carbs or rising fast for no good reason, meal-assist (ignore bolus IOB)
    if (mealAssist > 0) {
        // ignore all covered IOB, and just set eventualBG to the current bg
        mAeventualBG = Math.max(bg,eventualBG) + deviation;
        eventualBG = Math.round(mealAssist*mAeventualBG + (1-mealAssist)*eventualBG);
        rT.eventualBG = eventualBG;
        //console.error("eventualBG: "+eventualBG+", mAeventualBG: "+mAeventualBG+", rT.eventualBG: "+rT.eventualBG);
    }
    // lower target for meal-assist or wtf-assist (high and rising)
    wtfAssist = Math.round( Math.max(wtfAssist, mealAssist) *100)/100;
    if (wtfAssist > 0) {
        min_bg = wtfAssist*80 + (1-wtfAssist)*min_bg;
        target_bg = (min_bg + profile.max_bg) / 2;
        var expectedDelta = Math.round(( bgi + ( target_bg - eventualBG ) / ( profile.dia * 60 / 5 ) )*10)/10;
        mealAssistPct = Math.round(mealAssist*100);
        wtfAssistPct = Math.round(wtfAssist*100);
        rT.mealAssist = "On: "+mealAssistPct+"%, "+wtfAssistPct+"%, Carbs: " + meal_data.carbs + " Boluses: " + meal_data.boluses + " Target: " + Math.round(target_bg) + " Deviation: " + deviation + " BGI: " + bgi;
    } else {
        rT.mealAssist = "Off: Carbs: " + meal_data.carbs + " Boluses: " + meal_data.boluses + " Target: " + Math.round(target_bg) + " Deviation: " + deviation + " BGI: " + bgi;
    }
    return {remainingMealBolus: remainingMealBolus, mealAssist: mealAssist, expectedDelta: expectedDelta, min_bg: min_bg};
}

module.exports = mealAssistFn;