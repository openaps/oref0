#!/usr/bin/env node

function findRecord(arr, tell, date) {
	for (var i = 0; i < arr.length; ++i)
	{
		if (arr[i]._tell == tell && arr[i].date == date)
		{
			return i;
		}
	}
	return -1;
}

function usage ( ) {
    console.log('usage: ', process.argv.slice(0, 2), '<glucose.json>');

}

if (!module.parent) {
  var glucose_input = process.argv[2];
  if ([null, '--help', '-h', 'help'].indexOf(glucose_input) > 0) {
    usage( );
    process.exit(0)
  }

  if (!glucose_input) {
    usage( );
    process.exit(1);
  }

  var cwd = process.cwd();
  var glucose_data = require(cwd + '/' + glucose_input);
  glucose_data.sort(function (a, b) { return Date.parse(a.date) - Date.parse(b.date) });

  filtered = glucose_data.filter(function(x) { return x.name == "GlucoseSensorData" });

  var last_entries = [];
  var last_entry_used = 0;
  var window_mins = 15;
  var max_entries = window_mins / 5;
  var max_time = window_mins * 1000 * 60;

  var last_date = new Date(0);
  var last_glucose = 0;

  for (var i = 0; i < filtered.length; ++i) {
	var record = filtered[i];
	var output_record = glucose_data[findRecord(glucose_data, record._tell, record.date)];
	var current_date = Date.parse(record.date);

	var delta = 0; //record.sgv - last_glucose;
	var delta_time = 0;

	if (record.name != "GlucoseSensorData")
	{
		continue;
	}

    if (record.sgv == 0)
    {
        continue;
    }
	var used_records = 0;
	for (var j = 0; j < max_entries; j++)
	{
		var past_record = last_entries[j];
		if (typeof past_record == "undefined" || past_record.sgv == 0)
		{
			continue;
		}
		var entry_delta_time = current_date - past_record.time;

		if (entry_delta_time <= max_time)
		{
			delta_time = entry_delta_time;
			delta += ((record.sgv - past_record.sgv) * 1000 * 60) / delta_time;
			used_records++;
		}
	}	
	delta /= used_records;
	last_entries[last_entry_used] = {time: current_date, sgv: record.sgv};
	last_entry_used = (last_entry_used + 1 ) % max_entries;
	if (current_date - last_date <= max_time)
	{

		if (delta > 3)
		{
			output_record.trend_arrow = "DOUBLE_UP";
			output_record.direction = "DoubleUp";
		}
		else if (delta > 2)
		{
			output_record.trend_arrow = "SINGLE_UP";
			output_record.direction = "SingleUp";
		}
		else if (delta > 1)
		{
			output_record.trend_arrow = "45_UP";
			output_record.direction = "FortyFiveUp";
		}
		else if (delta < -3)
		{
			output_record.trend_arrow = "DOUBLE_DOWN";
			output_record.direction = "DoubleDown";
		}
		else if (delta < -2)
		{
			output_record.trend_arrow = "SINGLE_DOWN";
			output_record.direction = "SingleDown";
		}
		else if (delta < -1)
		{
			output_record.trend_arrow = "45_DOWN";
			output_record.direction = "FortyFiveDown";
		}
		else
		{
			output_record.trend_arrow = "FLAT";
			output_record.direction = "Flat";
		}
	}

	last_glucose = record.sgv;	
	last_date = current_date;
  }

  console.log(JSON.stringify(glucose_data));
}

