import { MaterialIcon } from './MaterialIcon'

type StarRatingProps = {
  rating: number
  max?: number
  size?: number
}

export function StarRating({ rating, max = 5, size = 16 }: StarRatingProps) {
  return (
    <div className="flex text-status-warning">
      {Array.from({ length: max }, (_, i) => (
        <MaterialIcon
          key={i}
          name="star"
          filled={i < rating}
          size={size}
          className={i >= rating ? 'text-outline-variant' : ''}
        />
      ))}
    </div>
  )
}
