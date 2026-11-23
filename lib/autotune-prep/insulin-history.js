'use strict';

function finiteNumber(value) {
    return (typeof value === 'number' || (typeof value === 'string' && value.trim() !== '')) &&
        Number.isFinite(Number(value));
}

function hasInsulinHistory(rows, start, end) {
    if (typeof start === 'undefined') start = -Infinity;
    if (typeof end === 'undefined') end = Infinity;
    const pairedBasalDurations = new Map(rows.filter(row => row && row._type === 'TempBasalDuration' &&
        typeof row.timestamp === 'string' && finiteNumber(row['duration (min)']) && Number(row['duration (min)']) > 0)
        .map(row => [row.timestamp, Number(row['duration (min)'])]));

    function basalOverlapsPeriod(time, duration) {
        return finiteNumber(duration) && Number(duration) > 0 && time + Number(duration) * 60000 > start;
    }

    return rows.some(row => {
        if (!row) return false;
        const time = Date.parse(row.created_at || row.timestamp);
        if (!Number.isFinite(time) || time >= end) return false;

        const bolus = row.bolus && row.bolus._type === 'Bolus' ? row.bolus : row;
        if (bolus._type === 'Bolus') {
            return time >= start && finiteNumber(bolus.amount) && Number(bolus.amount) > 0;
        }
        if (time >= start && (['Meal Bolus', 'Correction Bolus', 'Snack Bolus', 'Bolus Wizard'].indexOf(row.eventType) !== -1 ||
            row.enteredBy === 'xdrip' || row.enteredBy === 'HAPP_App')) {
            if (finiteNumber(row.insulin) && Number(row.insulin) > 0) return true;
        }
        if (row.eventType === 'Temp Basal') {
            const rate = row.enteredBy === 'HAPP_App' || row.enteredBy === 'openaps://AndroidAPS' ? row.absolute :
                (typeof row.amount !== 'undefined' ? row.amount : row.rate);
            return finiteNumber(rate) && Number(rate) >= 0 && basalOverlapsPeriod(time, row.duration);
        }
        return row._type === 'TempBasal' && row.temp !== 'percent' &&
            finiteNumber(row.rate) && Number(row.rate) >= 0 &&
            basalOverlapsPeriod(time, pairedBasalDurations.get(row.timestamp));
    });
}

module.exports = hasInsulinHistory;
