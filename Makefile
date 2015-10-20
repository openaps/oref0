TESTS=tests/*.js

all: test

report:
	# report results to community
test:
	./node_modules/.bin/mocha ${TESTS}
