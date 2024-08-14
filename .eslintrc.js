module.exports = {
    parser: '@typescript-eslint/parser',
    parserOptions: {
        project: './tsconfig.test.json',
    },
    env: {
        node: true,
    },
    parserOptions: {
        ecmaVersion: 2019,
        project: './tsconfig.json',
        sourceType: 'module',
    },
    plugins: ['import', 'fp-ts'],
    extends: [
        'eslint:recommended',
        'plugin:@typescript-eslint/recommended',
        'prettier',
        'plugin:node/recommended',
        'plugin:prettier/recommended',
        'plugin:fp-ts/all',
        'plugin:import/typescript',
    ],
    settings: {
        'import/resolver': {
            typescript: true,
            node: {
                extensions: ['.ts', '.tsx', '.js', '.jsx', '.json'],
            },
        },
    },
    rules: {
        complexity: 'off',
        curly: 'error',
        'default-case': 'off',
        'dot-notation': 'off',
        eqeqeq: 'error',
        'guard-for-in': 'error',
        'id-match': 'error',
        'no-bitwise': 'error',
        'no-console': 'off',
        'no-eq-null': 'error',
        'no-extend-native': 'error',
        'no-extra-bind': 'error',
        'no-implicit-coercion': 'error',
        'no-implicit-globals': 'error',
        'no-invalid-this': 'off',
        'no-lone-blocks': 'error',
        'no-native-reassign': 'error',
        'no-nested-ternary': 'error',
        'no-new-func': 'error',
        'no-new-wrappers': 'error',
        'no-param-reassign': 'error',
        'no-redeclare': 'off',
        'no-shadow': 'off',
        'no-undef-init': 'error',
        'no-unused-vars': 'off',
        'no-useless-call': 'error',
        'no-useless-concat': 'error',
        'no-var': 'error',
        'no-void': 'error',
        'new-cap': [
            'error',
            {
                newIsCap: true,
                capIsNew: false,
            },
        ],
        'prefer-arrow-callback': 'error',
        'prefer-const': 'error',
        'prefer-rest-params': 'error',
        'prefer-template': 'error',
        'wrap-iife': ['error', 'inside'],

        'node/no-unsupported-features/es-syntax': ['error', { ignores: ['modules'] }],
        'node/no-missing-import': 'off',
        'import/no-unresolved': 'error',

        '@typescript-eslint/no-empty-object-type': 'off',
        '@typescript-eslint/dot-notation': 'error',
        '@typescript-eslint/no-namespace': 'warn',
        '@typescript-eslint/consistent-type-definitions': 'error',
        '@typescript-eslint/no-empty-interface': 'off',
        '@typescript-eslint/explicit-function-return-type': 'off',
        '@typescript-eslint/explicit-module-boundary-types': 'off',
        '@typescript-eslint/no-explicit-any': 'off', // https://github.com/typescript-eslint/typescript-eslint/issues/1071,
        '@typescript-eslint/unified-signatures': 'error',
        '@typescript-eslint/consistent-type-imports': 'error',
        '@typescript-eslint/no-unused-vars': [
            'warn',
            {
                "args": "all",
                "argsIgnorePattern": "^_",
                "caughtErrors": "all",
                "caughtErrorsIgnorePattern": "^_",
                "destructuredArrayIgnorePattern": "^_",
                "varsIgnorePattern": "^_",
                "ignoreRestSiblings": true
            },
        ],
        '@typescript-eslint/no-shadow': ['error', { hoist: 'all', ignoreTypeValueShadow: true }],

        'prettier/prettier': 'error',

        'import/no-duplicates': ['error', { 'prefer-inline': false }],
        'import/no-deprecated': 'off', // https://github.com/import-js/eslint-plugin-import/issues/1532
        'import/no-unresolved': 'off',
        'import/export': 'off',
        'import/order': [
            'error',
            {
                groups: ['external', 'builtin', 'parent', 'sibling', 'index'],
                pathGroups: [
                    {
                        pattern: '*.scss',
                        group: 'parent',
                        position: 'after',
                    },
                ],
                alphabetize: {
                    order: 'asc',
                },
            },
        ],

        'fp-ts/no-module-imports': 'off',
    },
}
