var http = require('https');

if (!module.parent) {
    var iob_input = process.argv.slice(2, 3).pop()
    var enacted_temps_input = process.argv.slice(3, 4).pop()
    var glucose_input = process.argv.slice(4, 5).pop()
    if (!iob_input || !enacted_temps_input || !glucose_input) {
        console.log('usage: ', process.argv.slice(0, 2), '<iob.json> <enactedBasal.json> <bgreading.json>');
        process.exit(1);
    }
}

var glucose_data = require('./' + glucose_input);
var enacted_temps = require('./' + enacted_temps_input);
var iob_data = require('./' + iob_input);



var data = JSON.stringify({
    "Id": 3,
    "temp": enacted_temps.temp,
    "rate": enacted_temps.rate,
    "duration": enacted_temps.duration,
    "bg": glucose_data[0].glucose,
    "iob": iob_data.iob,
    "timestamp": enacted_temps.timestamp,
    "received": enacted_temps.recieved
}
);

var options = {
    host: '[your_webapi].azurewebsites.net',
    port: '443',
    path: '/api/openapstempbasals',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': data.length
    }
};

var req = http.request(options, function (res) {
    var msg = '';
    
    res.setEncoding('utf8');
    res.on('data', function (chunk) {
        msg += chunk;
    });
    res.on('end', function () {
        console.log(JSON.parse(msg));
    });
});

req.write(data);
req.end();
