TESTS=tests/*.js

all: test

test:
	mocha ${TESTS}
