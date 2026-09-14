import { ChevronDown, Loader2 } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { DropdownMenu, type MenuItem } from './DropdownMenu'
import styles from './buttons.module.css'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link'
export type ButtonSize = 'md' | 'sm'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  block?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading = false, leadingIcon, trailingIcon, block, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(styles.button, styles[`variant_${variant}`], size === 'sm' && styles.size_sm, block && styles.block, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 className={styles.spinner} size={16} aria-hidden="true" /> : leadingIcon ? <span className={styles.icon}>{leadingIcon}</span> : null}
      <span className={styles.label}>{children}</span>
      {trailingIcon && <span className={styles.icon}>{trailingIcon}</span>}
    </button>
  )
})

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
  variant?: 'secondary' | 'ghost' | 'primary' | 'danger'
  size?: ButtonSize
  loading?: boolean
  active?: boolean
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = 'secondary', size = 'md', loading, active, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className={cn(styles.button, styles.iconButton, styles[`variant_${variant}`], size === 'sm' && styles.size_sm, active && styles.active, className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 className={styles.spinner} size={16} aria-hidden="true" /> : children}
    </button>
  )
})

export interface LinkButtonProps {
  to: string
  variant?: ButtonVariant
  size?: ButtonSize
  leadingIcon?: ReactNode
  children: ReactNode
  className?: string
}

export function LinkButton({ to, variant = 'secondary', size = 'md', leadingIcon, children, className }: LinkButtonProps) {
  return (
    <Link to={to} className={cn(styles.button, styles[`variant_${variant}`], size === 'sm' && styles.size_sm, className)}>
      {leadingIcon && <span className={styles.icon}>{leadingIcon}</span>}
      <span className={styles.label}>{children}</span>
    </Link>
  )
}

export interface SplitButtonProps {
  label: ReactNode
  onClick: () => void
  items: MenuItem[]
  variant?: 'primary' | 'secondary'
  size?: ButtonSize
  leadingIcon?: ReactNode
  disabled?: boolean
  loading?: boolean
  menuLabel?: string
}

/** Primary action plus a chevron that opens secondary actions. */
export function SplitButton({ label, onClick, items, variant = 'primary', size = 'md', leadingIcon, disabled, loading, menuLabel = 'More actions' }: SplitButtonProps) {
  return (
    <div className={cn(styles.split, styles[`split_${variant}`], size === 'sm' && styles.size_sm)} role="group">
      <Button variant={variant} size={size} onClick={onClick} disabled={disabled} loading={loading} leadingIcon={leadingIcon} className={styles.splitMain}>
        {label}
      </Button>
      <DropdownMenu
        items={items}
        align="end"
        label={menuLabel}
        trigger={(props, open) => (
          <button
            type="button"
            {...props}
            ref={props.ref}
            className={cn(styles.button, styles.iconButton, styles[`variant_${variant}`], size === 'sm' && styles.size_sm, styles.splitChevron, open && styles.active)}
            aria-label={menuLabel}
            disabled={disabled}
          >
            <ChevronDown size={16} aria-hidden="true" />
          </button>
        )}
      />
    </div>
  )
}
