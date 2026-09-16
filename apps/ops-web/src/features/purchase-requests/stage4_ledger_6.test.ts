/**
 * A four-decimal unit price must survive the trip to the API.
 *
 * The line-item form accepts up to four decimals ("Enter a price like 12.50,
 * with at most four decimals") and the column behind it is `Numeric(12, 4)`,
 * but `purchaseRequestPayload` sends `roundMoney(toNumber(line.unit_price))`,
 * which rounds to cents. A part quoted at $0.0525 each is silently ordered at
 * $0.05, so a thousand of them are budgeted at $50.00 instead of $52.50.
 */

import { describe, expect, it } from 'vitest'

import { toPurchaseRequestPayload, type PurchaseRequestInput } from '@/api/contracts/purchaseRequests'

function draft(unitPrice: string, quantity = '1000'): PurchaseRequestInput {
  return {
    title: 'Fasteners',
    project_id: null,
    vendor_id: null,
    needed_by: '',
    purpose: '',
    budget_code: '',
    shipping_amount: '',
    tax_amount: '',
    items: [
      {
        key: 'line-1',
        part_id: null,
        description: 'M3 washer',
        vendor_part_number: '',
        url: '',
        quantity,
        unit_price: unitPrice,
        receive_location_id: null,
      },
    ],
  } as PurchaseRequestInput
}

describe('toPurchaseRequestPayload', () => {
  it('keeps the four decimals the form accepts', () => {
    expect(toPurchaseRequestPayload(draft('0.0525')).items[0].unit_price).toBe(0.0525)
  })

  it('does not round a sub-cent quote away', () => {
    expect(toPurchaseRequestPayload(draft('12.3456')).items[0].unit_price).toBe(12.3456)
  })
})
