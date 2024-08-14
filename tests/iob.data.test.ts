import data from './iob.data.json'
import generate from '../lib/iob'
import * as fs from 'fs'

describe('iob', () => {
    it('should', () => {
        const result = generate({
            history: data.pumpHistory,
            history24: null,
            profile: data.profile,
            clock: data.clock,
            autosens: data.autosens ? data.autosens : undefined,
        })

        expect(JSON.parse(JSON.stringify(result))).toStrictEqual(JSON.parse(JSON.stringify(data.iob)))
    })
})
