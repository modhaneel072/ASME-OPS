/**
 * The live totals on the purchase-request form must agree with the server.
 *
 * `roundMoney` documents itself as "half-up to cents, the rule
 * `serializers/purchase_requests.line_total` uses", but it is implemented as
 * `Math.round((value + Number.EPSILON) * 100) / 100` on a binary float. For
 * products that land exactly on half a cent the float is already below the
 * midpoint, so `lineTotal` rounds down where the server's
 * `Decimal(...).quantize(ROUND_HALF_UP)` rounds up, and the draft the user is
 * looking at shows a different total from the one that gets stored.
 */

import { describe, expect, it } from 'vitest'

import { lineTotal, totalsFor } from '@/api/contracts/purchaseRequests'

describe('lineTotal matches the server half-up rule', () => {
  it('rounds 3 x 1.005 up to 3.02', () => {
    expect(lineTotal('3', '1.005')).toBe(3.02)
  })

  it('rounds 1 x 8.165 up to 8.17', () => {
    expect(lineTotal('1', '8.165')).toBe(8.17)
  })

  it('carries the same rule into the form subtotal', () => {
    const totals = totalsFor([{ quantity: '3', unit_price: '1.005' }], '', '')
    expect(totals.subtotal).toBe(3.02)
    expect(totals.total).toBe(3.02)
  })
})
