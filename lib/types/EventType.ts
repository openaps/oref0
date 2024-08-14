import { Schema } from '@effect/schema'

const NightscoutEventType = Schema.Literal(
    'Temp Basal',
    'Carb Correction',
    'Temporary Target',
    'Insulin Change',
    'Site Change',
    'Pump Battery Change',
    'Announcement',
    'Sensor Start',
    'BG Check',
    'Exercise',
    'Bolus Wizard'
)

const PumpHistoryEvent = Schema.Literal(
    'Temp Basal',
    'Carb Correction',
    'Temporary Target',
    'Insulin Change',
    'Site Change',
    'Pump Battery Change',
    'Announcement',
    'Sensor Start',
    'BG Check',
    'Exercise',
    'Bolus Wizard'
)
export const EventType = Schema.Union(NightscoutEventType, PumpHistoryEvent, Schema.String)
export type EventType = typeof EventType.Type
