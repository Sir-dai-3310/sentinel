#!/usr/bin/env node
/**
 * Translation completeness check.
 * Compares the flattened key set of each locale against the reference (en)
 * and reports missing / extra keys per language.
 *
 * Usage: node scripts/check-i18n.mjs
 * Exit code: 0 when all locales are complete, 1 otherwise.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const LOCALES_DIR = join(dirname(fileURLToPath(import.meta.url)), '../src/locales')
const REFERENCE = 'en'
const LOCALES = ['zh', 'ja', 'ko', 'es']

function flatten(obj, prefix = '') {
  return Object.entries(obj).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return value !== null && typeof value === 'object'
      ? flatten(value, path)
      : [path]
  })
}

function load(locale) {
  const json = JSON.parse(
    readFileSync(join(LOCALES_DIR, locale, 'translation.json'), 'utf8')
  )
  return new Set(flatten(json))
}

const refKeys = load(REFERENCE)
let failures = 0

console.log(`[${REFERENCE}] (reference) ${refKeys.size} keys`)
for (const locale of LOCALES) {
  const keys = load(locale)
  const missing = [...refKeys].filter((k) => !keys.has(k))
  const extra = [...keys].filter((k) => !refKeys.has(k))
  console.log(`[${locale}] ${keys.size} keys`)
  if (missing.length === 0 && extra.length === 0) {
    console.log(`  OK: key set matches ${REFERENCE}`)
  } else {
    failures += missing.length
    for (const k of missing) console.log(`  MISSING: ${k}`)
    for (const k of extra) console.log(`  EXTRA:   ${k}`)
  }
}

process.exit(failures > 0 ? 1 : 0)
