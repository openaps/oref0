import * as stats from './glucose-stats'

interface Options {
    glucose_hist: any[]
}

export function updateGlucoseStats(options: Options) {
    const hist = (options.glucose_hist || [])
        .map(value => ({
            ...value,
            // @todo: in tests, dateString is undefined
            readDateMills: value.dateString ? new Date(value.dateString).getTime() : Date.now(),
        }))
        .sort((a, b) => a.readDateMills - b.readDateMills)

    if (hist && hist.length > 0) {
        const noise_val = stats.calcSensorNoise(null, hist, null, null)

        let ns_noise_val = stats.calcNSNoise(noise_val, hist)

        if ('noise' in options.glucose_hist[0]) {
            console.error('Glucose noise CGM reported level: ', options.glucose_hist[0].noise)
            ns_noise_val = Math.max(ns_noise_val, options.glucose_hist[0].noise)
        }

        console.error('Glucose noise calculated: ', noise_val, ' setting noise level to ', ns_noise_val)

        options.glucose_hist[0].noise = ns_noise_val
    }

    return options.glucose_hist
}

export default updateGlucoseStats
