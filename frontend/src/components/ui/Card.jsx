import { cn } from '../../utils/cn'

export function Card({ className, children, ...props }) {
  return (
    <div
      className={cn(
        "bg-dark-surface-primary rounded-xl border border-dark-border-primary shadow-gemini-sm overflow-hidden",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
