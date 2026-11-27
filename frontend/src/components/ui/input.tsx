import * as React from 'react'
import { cn } from '@/lib/utils'

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-9 w-full rounded-lg border border-line bg-canvas-edge px-3 text-sm text-fg placeholder:text-muted focus:border-accent/60 focus:outline-none',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        'min-h-20 w-full rounded-lg border border-line bg-canvas-edge px-3 py-2 text-sm text-fg placeholder:text-muted focus:border-accent/60 focus:outline-none',
        className,
      )}
      {...props}
    />
  ),
)
Textarea.displayName = 'Textarea'

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'h-9 rounded-lg border border-line bg-canvas-edge px-2 text-sm text-fg focus:border-accent/60 focus:outline-none',
        className,
      )}
      {...props}
    />
  )
}
