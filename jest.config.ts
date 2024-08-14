import type { Config } from 'jest';

const config: Config = {
    verbose: true,
    //preset: "ts-jest/presets/js-with-ts",
    preset: "ts-jest/presets/default",
    collectCoverage: true,
    testEnvironment: "node",
    testMatch: [
        //"**/*.test.(ts|js)"
        "**/*.test.ts"
    ],
    transform: {
        '^.+\\.tsx?$': [
            'ts-jest',
            {
                tsconfig: "./tsconfig.test.json",
                diagnostics: false
            }
        ],
    },
}

export default config;
