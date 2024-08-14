import { Schema } from '@effect/schema'
import * as O from 'effect/Order'
import { PumpHistoryEvent } from './PumpHistoryEvent'

// https://github.com/nightscout/cgm-remote-monitor/blob/21e0591d49235845acba58cf8b3cc7339921185b/lib/api3/swagger.json

const EventType = Schema.NonEmptyString.annotations({
    description: 'The type of treatment event',
    examples: [
        'BG Check',
        'Snack Bolus',
        'Meal Bolus',
        'Correction Bolus',
        'Carb Correction',
        'Combo Bolus',
        'Announcement',
        'Note',
        'Question',
        'Exercise',
        'Site Change',
        'Sensor Start',
        'Sensor Change',
        'Pump Battery Change',
        'Insulin Change',
        'Temp Basal',
        'Profile Switch',
        'D.A.D. Alert',
        'Temporary Target',
        'OpenAPS Offline',
        'Bolus Wizard',
    ],
})

export const NightscoutTreatment = Schema.Struct({
    eventType: EventType,
    created_at: Schema.NonEmptyString,
    id: Schema.optionalWith(Schema.String, { nullable: true }),

    // from Nightscout DocumentBase
    identifier: Schema.optionalWith(Schema.String, { nullable: true }).annotations({
        description:
            'Main addressing, required field that identifies document in the collection.\n\nThe client should not create the identifier, the server automatically assigns it when the document is inserted.\n\nThe server calculates the identifier in such a way that duplicate records are automatically merged (deduplicating is made by `date`, `device` and `eventType` fields).\n\nThe best practise for all applications is not to loose identifiers from received documents, but save them carefully for other consumer applications/systems.\n\nAPI v3 has a fallback mechanism in place, for documents without `identifier` field the `identifier` is set to internal `_id`, when reading or addressing these documents.\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)',
        examples: ['53409478-105f-11e9-ab14-d663bd873d93'],
    }),
    date: Schema.optional(Schema.Int).annotations({
        description:
            "Required timestamp when the record or event occured, you can choose from three input formats\n- Unix epoch in milliseconds (1525383610088)\n- Unix epoch in seconds (1525383610)\n- ISO 8601 with optional timezone ('2018-05-03T21:40:10.088Z' or '2018-05-03T23:40:10.088+02:00')\n\nThe date is always stored in a normalized form - UTC with zero offset. If UTC offset was present, it is going to be set in the `utcOffset` field.\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)",
        examples: [1525383610088],
    }),
    utcOffset: Schema.optional(Schema.Int).annotations({
        description:
            'Local UTC offset (timezone) of the event in minutes. This field can be set either directly by the client (in the incoming document) or it is automatically parsed from the `date` field.\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)',
        examples: [120],
    }),
    app: Schema.optional(Schema.String).annotations({
        description:
            'Application or system in which the record was entered by human or device for the first time.\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)',
        examples: ['xdrip'],
    }),
    device: Schema.optional(Schema.String).annotations({
        description:
            'The device from which the data originated (including serial number of the device, if it is relevant and safe).\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)',
        examples: ['dexcom G5'],
    }),
    _id: Schema.optional(Schema.String).annotations({
        description:
            'Internally assigned database id. This field is for internal server purposes only, clients communicate with API by using identifier field.',
        examples: ['58e9dfbc166d88cc18683aac'],
    }),
    srvCreated: Schema.optional(Schema.Int).annotations({
        description:
            "The server's timestamp of document insertion into the database (Unix epoch in ms). This field appears only for documents which were inserted by API v3.\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)",
        examples: [1525383610088],
    }),
    subject: Schema.optional(Schema.String).annotations({
        description:
            'Name of the security subject (within Nightscout scope) which has created the document. This field is automatically set by the server from the passed JWT.\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)',
        examples: ['uploader'],
    }),
    srvModified: Schema.optional(Schema.Int).annotations({
        description:
            "The server's timestamp of the last document modification in the database (Unix epoch in ms). This field appears  only for documents which were somehow modified by API v3 (inserted, updated or deleted).\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)",
        examples: [1525383610088],
    }),
    modifiedBy: Schema.optional(Schema.String).annotations({
        description:
            'Name of the security subject (within Nightscout scope) which has patched or deleted the document for the last time. This field is automatically set by the server.\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)',
        examples: ['admin'],
    }),
    isValid: Schema.optional(Schema.Boolean).annotations({
        description:
            'A flag set by the server only for deleted documents. This field appears only within history operation and for documents which were deleted by API v3 (and they always have a false value)\n\nNote&#58; this field is immutable by the client (it cannot be updated or patched)',
        examples: [false],
    }),
    isReadOnly: Schema.optional(Schema.Boolean).annotations({
        description:
            'A flag set by client that locks the document from any changes. Every document marked with `isReadOnly=true` is forever immutable and cannot even be deleted.\n\nAny attempt to modify the read-only document will end with status 422 UNPROCESSABLE ENTITY.',
        examples: [true],
    }),

    // from Nightscout Treatment
    glucose: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Current glucose',
    }),
    glucoseType: Schema.optionalWith(Schema.String, { nullable: true }).annotations({
        description: 'Method used to obtain glucose, Finger or Sensor',
        examples: ['Sensor', 'Finger', 'Manual'],
    }),
    units: Schema.optionalWith(Schema.String, { nullable: true }).annotations({
        description:
            'The units for the glucose value, mg/dl or mmol/l. It is strongly recommended to fill in this field when `glucose` is entered',
        examples: ['mg/dl', 'mmol/l'],
    }),
    carbs: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Amount of carbs given',
    }),
    protein: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Amount of protein given',
    }),
    fat: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Amount of fat given',
    }),
    insulin: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Amount of insulin, if any',
    }),
    duration: Schema.optionalWith(Schema.Int, { nullable: true }).annotations({
        description: 'Duration in minutes',
    }),
    preBolus: Schema.optionalWith(Schema.Int, { nullable: true }).annotations({
        description: 'How many minutes the bolus was given before the meal started',
    }),
    splitNow: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Immediate part of combo bolus (in percent)',
    }),
    splitExt: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Extended part of combo bolus (in percent)',
    }),
    percent: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Eventual basal change in percent',
    }),
    absolute: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Eventual basal change in absolute value (insulin units per hour)',
    }),
    targetTop: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Top limit of temporary target',
    }),
    targetBottom: Schema.optionalWith(Schema.Number, { nullable: true }).annotations({
        description: 'Bottom limit of temporary target',
    }),
    profile: Schema.optionalWith(Schema.String, { nullable: true }).annotations({
        description: 'Name of the profile to which the pump has been switched',
    }),
    reason: Schema.optionalWith(Schema.String, { nullable: true }).annotations({
        description:
            'For example the reason why the profile has been switched or why the temporary target has been set',
    }),
    notes: Schema.optionalWith(Schema.String, { nullable: true }).annotations({
        description: 'Description/notes of treatment',
    }),
    enteredBy: Schema.optionalWith(Schema.String, { nullable: true }).annotations({
        description: 'Who entered the treatment',
    }),

    // not found in Nightscout swagger doc
    timestamp: Schema.optionalWith(Schema.String, { nullable: true }),
    ratio: Schema.optionalWith(Schema.Number, { nullable: true }),
    rawDuration: Schema.optionalWith(PumpHistoryEvent, { nullable: true }),
    rawRate: Schema.optionalWith(PumpHistoryEvent, { nullable: true }),
    bolus: Schema.optionalWith(PumpHistoryEvent, { nullable: true }),
    wizard: Schema.optionalWith(PumpHistoryEvent, { nullable: true }),
    square: Schema.optionalWith(PumpHistoryEvent, { nullable: true }),
    rate: Schema.optionalWith(Schema.Number, { nullable: true }),
    foodType: Schema.optionalWith(Schema.String, { nullable: true }),
    fpuID: Schema.optionalWith(Schema.String, { nullable: true }),
    amount: Schema.optionalWith(Schema.Number, { nullable: true }),
    bg: Schema.optionalWith(Schema.Number, { nullable: true }),
}).annotations({
    identifier: 'NightscoutTreatment',
    title: 'Nightscout Treatment',
    description: 'T1D compensation action',
})

export type NightscoutTreatment = typeof NightscoutTreatment.Type

export const Order: O.Order<NightscoutTreatment> = O.mapInput(O.Date, a => new Date(a.created_at))
