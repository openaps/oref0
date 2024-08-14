export const tz = (a: Date | string): Date => {
    return new Date(new Date(a).toISOString())
}

export const format = (a: Date) => {
    const newDate = new Date(a)
    const absOffset = Math.abs(a.getTimezoneOffset())
    const hours = Math.ceil(absOffset / 60)
    const minutes = absOffset - hours * 60
    const sign = a.getTimezoneOffset() < 0 ? '+' : '-'
    newDate.setMinutes(a.getMinutes() - a.getTimezoneOffset())

    return `${newDate.toISOString().substring(0, 19) + sign + hours.toString().padStart(2, '0')}:${minutes
        .toString()
        .padStart(2, '0')}`
}
