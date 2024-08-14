export function translate<A>(treatments: ReadonlyArray<A>): A[] {
    const results: any[] = []

    function step(current: any) {
        let invalid = false
        const item = { ...current }
        switch (item._type) {
            case 'CalBGForPH':
                item.eventType = 'BG Check'
                item.glucose = item.amount
                item.glucoseType = 'Finger'
                break
            case 'BasalProfileStart':
            case 'ResultDailyTotal':
            case 'BGReceived':
            case 'Sara6E':
            case 'Model522ResultTotals':
            case 'Model722ResultTotals':
                invalid = true
                break
            default:
                break
        }

        if (!invalid) {
            results.push(item)
        }
    }
    treatments.forEach(step)
    return results
}

export default translate
