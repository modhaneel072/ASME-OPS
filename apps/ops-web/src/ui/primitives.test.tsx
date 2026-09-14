import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Button, Dialog, DropdownMenu, FilterChip, Tabs } from '.'

describe('Dialog', () => {
  it('traps focus, closes on Escape and restores focus to the opener', async () => {
    const user = userEvent.setup()
    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <Button onClick={() => setOpen(true)}>Open</Button>
          <Dialog
            open={open}
            onClose={() => setOpen(false)}
            title="Confirm"
            footer={
              <>
                <Button onClick={() => setOpen(false)}>Cancel</Button>
                <Button variant="primary">Confirm</Button>
              </>
            }
          >
            <p>Body</p>
          </Dialog>
        </>
      )
    }
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Open' })
    await user.click(opener)
    const dialog = screen.getByRole('dialog', { name: 'Confirm' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    const close = within(dialog).getByRole('button', { name: 'Close' })
    expect(close).toHaveFocus()
    await user.tab()
    await user.tab()
    await user.tab()
    // wraps back to the first focusable element
    expect(close).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })
})

describe('Tabs', () => {
  it('moves selection with arrow keys and announces counts', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    function Harness() {
      const [value, setValue] = useState<'todo' | 'done'>('todo')
      return (
        <Tabs
          label="Work"
          value={value}
          onChange={(v) => {
            setValue(v)
            onChange(v)
          }}
          items={[
            { value: 'todo', label: 'To Do', count: 4 },
            { value: 'done', label: 'Done', count: 12 },
          ]}
        />
      )
    }
    render(<Harness />)
    const todo = screen.getByRole('tab', { name: /To Do/ })
    expect(todo).toHaveAttribute('aria-selected', 'true')
    todo.focus()
    await user.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith('done')
    expect(screen.getByRole('tab', { name: /Done/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /Done/ })).toHaveTextContent('12')
  })
})

describe('DropdownMenu', () => {
  it('opens with keyboard, navigates items and selects with Enter', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <DropdownMenu
        label="Actions"
        items={[
          { key: 'a', label: 'First', onSelect: () => onSelect('a') },
          { key: 'b', label: 'Second', onSelect: () => onSelect('b') },
        ]}
        trigger={(props) => (
          <button type="button" {...props} ref={props.ref}>
            More
          </button>
        )}
      />,
    )
    const trigger = screen.getByRole('button', { name: 'More' })
    trigger.focus()
    await user.keyboard('{ArrowDown}')
    const menu = await screen.findByRole('menu')
    expect(menu).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'First' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Second' })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(onSelect).toHaveBeenCalledWith('b')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})

describe('FilterChip', () => {
  it('toggles options immediately and shows a summary', async () => {
    const user = userEvent.setup()
    function Harness() {
      const [value, setValue] = useState<string[]>([])
      return (
        <FilterChip
          label="Status"
          value={value}
          onChange={setValue}
          options={[
            { value: 'open', label: 'Open' },
            { value: 'done', label: 'Done' },
          ]}
        />
      )
    }
    render(<Harness />)
    const chip = () => screen.getByRole('button', { name: /^Status/ })
    await user.click(chip())
    await user.click(screen.getByRole('checkbox', { name: 'Open' }))
    expect(screen.getByRole('checkbox', { name: 'Open' })).toHaveAttribute('aria-checked', 'true')
    expect(chip()).toHaveTextContent('Open')
    await user.click(screen.getByRole('button', { name: 'Clear Status filter' }))
    expect(chip()).not.toHaveTextContent('Open')
  })
})
