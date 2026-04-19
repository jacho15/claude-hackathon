const FLAG_LABEL = { critical: 'Critical', watch: 'Watch', stable: 'Stable' }

export default function FlagBadge({ flag, className = '' }) {
  return (
    <span className={`flag-badge flag-badge--${flag} ${className}`}>
      {FLAG_LABEL[flag] ?? flag}
    </span>
  )
}
