type MaterialIconProps = {
  name: string
  filled?: boolean
  className?: string
  size?: number
}

export function MaterialIcon({ name, filled = false, className = '', size }: MaterialIconProps) {
  const style = size ? { fontSize: size } : undefined
  return (
    <span
      aria-hidden="true"
      className={`material-symbols-outlined ${filled ? 'icon-fill' : ''} ${className}`}
      style={style}
    >
      {name}
    </span>
  )
}
