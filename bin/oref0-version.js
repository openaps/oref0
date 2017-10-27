#!/usr/bin/env node

// Simple script to check current version / branch of oref0 installed and check for updates
const execSync = require('child_process').execSync;
const argv = require('yargs').argv;

var branch = execSync(`cd $HOME/src/oref0/ && git rev-parse --abbrev-ref HEAD`).toString().trim().toLowerCase();
var version = execSync(`jq .version "$HOME/src/oref0/package.json"`).toString().trim().substr(1).slice(0, -1);


if (argv.checkForUpdates) {
	execSync(`cd $HOME/src/oref0/ && git fetch`); // pull latest remote info
	var behind = execSync(`cd $HOME/src/oref0/ && git rev-list --count ${branch}...origin/${branch}`).toString().trim();
	if (parseInt(behind) > 0) {
		// we are out of date
		console.log(`Your instance of oref0 [${version}, ${branch}] is out-of-date by ${behind} commits, you may want to consider updating.`);
		if (branch !== "master") {
			console.log(`\nYou are currently running a development branch of oref0.  Such branches change frequently.`);
			console.log(`Please read the latest PR notes and update with the latest commits to dev before reporting any issues.\n`);
		} else {
			console.log(`Please make sure to read any new documentation that may accompany update, as some things may have changed.`);
		}
	} else {
		console.log(`Your instance of oref0 [${version}, ${branch}] is up-to-date.`);
	}
} else {
	// simple version check and report.
	console.log(`${version} [${branch}]`);
}
